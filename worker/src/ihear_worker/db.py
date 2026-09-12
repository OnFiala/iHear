from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class QueueMessage:
    message_id: int
    payload: dict[str, Any]


class ReportInputStale(RuntimeError):
    pass


class WorkerDatabase:
    def __init__(self, database_url: str, queue_name: str, worker_id: str):
        self._database_url = database_url
        self._queue_name = queue_name
        self.worker_id = worker_id

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

    def read_message(self, visibility_seconds: int) -> QueueMessage | None:
        with self.connection() as connection:
            row = connection.execute(
                "select msg_id, message from pgmq.read(%s, %s, 1)",
                (self._queue_name, visibility_seconds),
            ).fetchone()
        return QueueMessage(int(row["msg_id"]), row["message"]) if row else None

    def archive_unusable_message(self, message_id: int) -> None:
        with self.connection() as connection:
            connection.execute("select pgmq.archive(%s, %s)", (self._queue_name, message_id))

    def claim_job(self, job_id: str, lease_seconds: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            return connection.execute(
                "select * from ihear.claim_job(%s, %s, %s)",
                (job_id, self.worker_id, lease_seconds),
            ).fetchone()

    def renew_job_lease(self, job_id: str, lease_seconds: int) -> bool:
        with self.connection() as connection:
            row = connection.execute(
                "select ihear.renew_job_lease(%s,%s,%s) as renewed",
                (job_id, self.worker_id, lease_seconds),
            ).fetchone()
        return bool(row and row["renewed"])

    def event_context(self, job: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self.connection() as connection:
            event = connection.execute(
                """
                select id::text, workspace_id::text, patient_id::text, kind, difficulty,
                       environment, captured_at::text, capture, profile_snapshot,
                       audio_object_path, audio_deleted_at::text, pipeline_version
                from ihear.events where id = %s and workspace_id = %s
                """,
                (job["event_id"], job["workspace_id"]),
            ).fetchone()
            history_rows = connection.execute(
                """
                select e.kind, e.difficulty, e.environment, e.captured_at::text,
                       a.result as analysis
                from ihear.events e
                left join ihear.analyses a
                  on a.event_id = e.id and a.pipeline_version = e.pipeline_version and a.status = 'ready'
                where e.patient_id = %s and e.workspace_id = %s and e.id <> %s
                order by e.captured_at desc limit 20
                """,
                (job["patient_id"], job["workspace_id"], job["event_id"]),
            ).fetchall()
        if not event:
            raise LookupError("Event referenced by job does not exist")
        return event, list(reversed(history_rows))

    def persist_analysis(self, job_id: str, status: str, result: dict[str, Any] | None, provenance: dict[str, Any], error: str | None = None) -> str:
        with self.connection() as connection:
            row = connection.execute(
                "select ihear.persist_analysis(%s,%s,%s,%s,%s,%s) as id",
                (job_id, self.worker_id, status, Jsonb(result) if result is not None else None, Jsonb(provenance), error),
            ).fetchone()
        return str(row["id"])

    def existing_analysis(self, job: dict[str, Any]) -> dict[str, Any] | None:
        with self.connection() as connection:
            return connection.execute(
                "select id::text, result, provenance from ihear.analyses where event_id = %s and pipeline_version = %s and status = 'ready'",
                (job["event_id"], job["version"]),
            ).fetchone()

    def existing_interpretation(self, analysis_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            return connection.execute(
                """
                select id::text, status, result, api_usage_id::text
                from ihear.interpretations
                where analysis_id = %s and model = 'gpt-6-astra' and prompt_version = 'ihear-event-v1'
                """,
                (analysis_id,),
            ).fetchone()

    def reserve_budget(self, job: dict[str, Any], maximum_cost: Decimal, idempotency_key: str, ambiguous: bool = False) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute(
                "select ihear.reserve_api_budget(%s,%s,%s,%s,%s,%s,%s,%s,%s) as result",
                (
                    job["workspace_id"], job["patient_id"], job["event_id"], job["id"],
                    "event_interpretation", "gpt-6-astra", maximum_cost, idempotency_key, ambiguous,
                ),
            ).fetchone()
        return row["result"]

    def persist_interpretation(
        self, job_id: str, analysis_id: str, status: str, result: dict[str, Any] | None,
        provenance: dict[str, Any], error: str | None = None, usage_id: str | None = None,
    ) -> str:
        with self.connection() as connection:
            row = connection.execute(
                "select ihear.persist_interpretation(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) as id",
                (
                    job_id, self.worker_id, analysis_id, "gpt-6-astra", "ihear-event-v1", status,
                    Jsonb(result) if result is not None else None, Jsonb(provenance), error, usage_id,
                ),
            ).fetchone()
        return str(row["id"])

    def settle_and_persist_interpretation(
        self, job_id: str, analysis_id: str, usage_id: str, actual_cost: Decimal,
        provider_request_id: str, result: dict[str, Any], provenance: dict[str, Any],
    ) -> str:
        with self.connection() as connection:
            connection.execute(
                "select ihear.settle_api_budget(%s,%s,%s)",
                (usage_id, actual_cost, provider_request_id),
            )
            row = connection.execute(
                "select ihear.persist_interpretation(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) as id",
                (
                    job_id, self.worker_id, analysis_id, "gpt-6-astra", "ihear-event-v1", "ready",
                    Jsonb(result), Jsonb(provenance), None, usage_id,
                ),
            ).fetchone()
        return str(row["id"])

    def release_budget(self, usage_id: str) -> None:
        with self.connection() as connection:
            connection.execute("select ihear.release_api_budget(%s)", (usage_id,))

    def settle_budget_overage(
        self, usage_id: str, actual_cost: Decimal, provider_request_id: str, reason: str,
    ) -> None:
        # Commit settlement/freeze independently. If the following interpretation
        # write fails, the frozen account remains durable and prevents a paid retry.
        with self.connection() as connection:
            connection.execute(
                "select ihear.settle_api_budget_overage(%s,%s,%s,%s)",
                (usage_id, actual_cost, provider_request_id, reason[:500]),
            )

    def report_context(self, job: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        with self.connection() as connection:
            report = connection.execute(
                "select id::text, input_revision, report_version, status, object_path from ihear.reports where id = %s",
                (job["report_id"],),
            ).fetchone()
            patient = connection.execute(
                "select id::text, display_name, audiogram, aids, follow_up_date::text, note, timezone from ihear.patients where id = %s and workspace_id = %s",
                (job["patient_id"], job["workspace_id"]),
            ).fetchone()
            event_rows = connection.execute(
                """
                select e.id::text, e.kind, e.difficulty, e.environment, e.captured_at::text,
                       e.capture, a.result as analysis, i.status as interpretation_status,
                       i.result as interpretation
                from ihear.events e
                left join ihear.analyses a
                  on a.event_id = e.id and a.pipeline_version = e.pipeline_version and a.status = 'ready'
                left join ihear.interpretations i
                  on i.analysis_id = a.id and i.model = 'gpt-6-astra' and i.prompt_version = 'ihear-event-v1'
                where e.patient_id = %s and e.workspace_id = %s
                order by e.captured_at asc
                """,
                (job["patient_id"], job["workspace_id"]),
            ).fetchall()
        if not report or not patient:
            raise LookupError("Report job references missing patient or report")
        return report, patient, event_rows

    def persist_report(self, job_id: str, object_path: str) -> None:
        try:
            with self.connection() as connection:
                connection.execute(
                    "select ihear.persist_report_result(%s,%s,'ready',%s,null)",
                    (job_id, self.worker_id, object_path),
                )
        except psycopg.Error as exc:
            if "report_input_stale" in str(exc):
                raise ReportInputStale("Report input revision changed during generation") from exc
            raise

    def finish_job(self, job_id: str, result: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute("select ihear.finish_job(%s,%s,%s)", (job_id, self.worker_id, Jsonb(result)))

    def retry_job(self, job_id: str, error: str, delay_seconds: int) -> str:
        with self.connection() as connection:
            row = connection.execute(
                "select ihear.retry_job(%s,%s,%s,%s) as status",
                (job_id, self.worker_id, error[:500], delay_seconds),
            ).fetchone()
        return row["status"]

    def fail_job(self, job_id: str, error: str) -> None:
        with self.connection() as connection:
            connection.execute("select ihear.fail_job(%s,%s,%s)", (job_id, self.worker_id, error[:500]))

    def schedule_due_reports(self, report_version: int, limit: int = 50) -> int:
        with self.connection() as connection:
            # Match the database growth paths: admission lock first, patient
            # row locks second. The lock also keeps two schedulers from
            # selecting the same due set before either has created its jobs.
            connection.execute("select ihear.lock_sandbox_capacity()")
            due = connection.execute(
                """
                select p.workspace_id, p.id
                from ihear.patients p
                where p.follow_up_date <= ((now() at time zone p.timezone)::date + 1)
                  and extract(hour from (now() at time zone p.timezone)) >= 8
                  and not exists (
                    select 1 from ihear.reports r
                    where r.patient_id = p.id and r.input_revision = p.report_revision
                      and r.report_version = %s
                  )
                order by p.follow_up_date, p.id limit %s
                for update skip locked
                """,
                (report_version, limit),
            ).fetchall()
            scheduled = 0
            for patient in due:
                try:
                    # A rejected candidate rolls back only its own admission
                    # work. Earlier jobs in the bounded batch still commit.
                    with connection.transaction():
                        row = connection.execute(
                            "select ihear.ensure_scheduled_report_job(%s,%s,%s) as result",
                            (patient["workspace_id"], patient["id"], report_version),
                        ).fetchone()
                except psycopg.Error as exc:
                    if exc.sqlstate == "P0001":
                        continue
                    raise
                if row and bool(row["result"].get("enqueued")):
                    scheduled += 1
        return scheduled

    def terminal_audio_cleanup_candidates(self, retention_days: int = 7, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return connection.execute(
                """
                select id::text, audio_object_path
                from ihear.events
                where audio_object_path is not null and audio_deleted_at is null
                  and (
                    exists (
                      select 1 from ihear.analyses a
                      where a.event_id = ihear.events.id and a.status = 'ready'
                    )
                    or (
                      status = 'failed'
                      and updated_at < now() - make_interval(days => %s)
                    )
                  )
                order by updated_at limit %s
                """,
                (retention_days, limit),
            ).fetchall()

    def mark_audio_deleted(self, event_id: str, object_path: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "select ihear.mark_audio_deleted(%s,%s)",
                (event_id, object_path),
            )
