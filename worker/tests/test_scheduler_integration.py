"""Explicit opt-in regression probe against an empty disposable PostgreSQL DB."""
from datetime import datetime, timezone
import os
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from ihear_worker.db import WorkerDatabase


def test_real_scheduler_commits_free_slots_and_drains_after_saturation():
    dsn = os.environ.get("IHEAR_SCHEDULER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Requires the dedicated empty ihear_security_verify database")
    database = WorkerDatabase(dsn, "ihear_jobs", str(uuid4()))
    workspace = None
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as setup:
        observed = setup.execute("""
            select current_database() as name,
              (select count(*) from ihear.workspaces) as workspaces,
              (select count(*) from pgmq.q_ihear_jobs) as messages,
              (select count(*) from ihear.rate_limit_counters
                where scope = 'report_growth_global_hour') as report_counters
        """).fetchone()
        assert observed == {
            "name": "ihear_security_verify", "workspaces": 0,
            "messages": 0, "report_counters": 0,
        }, "Refusing to mutate a nonempty or unrecognized database"
        caps = setup.execute("select * from ihear.sandbox_limits").fetchone()
        assert caps["max_pending_reports_global"] == 50
        assert caps["max_pending_reports_workspace"] == 50
        try:
            workspace = setup.execute(
                "insert into ihear.workspaces default values returning id"
            ).fetchone()["id"]
            # Always make the scheduler's clinic clock noon, independently of CI time.
            offset = 12 - datetime.now(timezone.utc).hour
            clinic_timezone = f"Etc/GMT{-offset:+d}"
            patients = setup.execute("""
                insert into ihear.patients
                  (workspace_id, display_name, audiogram, aids, follow_up_date, note, timezone)
                select %s, 'Scheduler fixture', '{}'::jsonb, '{}'::jsonb,
                  current_date - 2, '', %s from generate_series(1, 51)
                returning id
            """, (workspace, clinic_timezone)).fetchall()
            setup.execute(
                "select ihear.ensure_scheduled_report_job(%s,%s,2)",
                (workspace, patients[0]["id"]),
            )
            assert database.schedule_due_reports(2, 50) == 49
            assert setup.execute(
                "select count(*) as n from ihear.jobs where status = 'queued'"
            ).fetchone()["n"] == 50
            assert database.schedule_due_reports(2, 50) == 0

            message = database.read_message(30)
            assert message is not None, "A full report queue must remain drainable"
            job_id = message.payload["jobId"]
            assert database.claim_job(job_id, 30) is not None
            database.fail_job(job_id, "Disposable scheduler regression fixture")

            # Exhaust web report-growth admission. Periodic scheduling still fills
            # the newly available slot, without raising or undoing the first batch.
            setup.execute("""
                select ihear.consume_rate_limit(
                  'report_growth_global_hour',
                  extensions.digest('ihear-report-growth-global','sha256'), 200, 3600
                ) from generate_series(1, 200)
            """)
            assert database.schedule_due_reports(2, 50) == 1
            assert database.read_message(30) is not None
        finally:
            if workspace is not None:
                job_ids = [str(row["id"]) for row in setup.execute(
                    "select id from ihear.jobs where workspace_id = %s", (workspace,)
                ).fetchall()]
                for table in ("q_ihear_jobs", "a_ihear_jobs"):
                    setup.execute(
                        f"delete from pgmq.{table} where message->>'jobId' = any(%s)",
                        (job_ids,),
                    )
                setup.execute("delete from ihear.workspaces where id = %s", (workspace,))
                setup.execute("""
                    delete from ihear.rate_limit_counters
                    where scope = 'report_growth_global_hour'
                """)
