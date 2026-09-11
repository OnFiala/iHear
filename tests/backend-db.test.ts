import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import pg from "pg";

const DATABASE_URL =
  process.env.DATABASE_URL ??
  "postgresql://postgres:postgres@127.0.0.1:54322/postgres";

test("database enforces tenant, idempotency, queue, lease, search, and global budget contracts", async () => {
  const client = new pg.Client({ connectionString: DATABASE_URL });
  await client.connect();
  await client.query("begin");
  try {
    await client.query(
      "update ihear.budget_accounts set total_limit_usd = 100, daily_limit_usd = 3, frozen_at = null, freeze_reason = null where account_key = 'astra-global'",
    );
    const hash = (byte: number) => Buffer.alloc(32, byte);
    const workspace = async (byte: number) =>
      (
        await client.query<{ id: string }>(
          "select ihear.create_workspace_with_capability($1, $2) as id",
          [hash(byte), hash(byte + 40)],
        )
      ).rows[0].id;
    const workspaceA = await workspace(1);
    const workspaceB = await workspace(2);
    const profile = {
      displayName: "Searchable Alex",
      audiogram: { frequencies: [500], left: [20], right: [25] },
      aids: {
        side: "bilateral",
        left: { model: "Example", tier: "110" },
        right: { model: "Example", tier: "110" },
      },
      followUpDate: "2026-09-20",
      note: "prefers quiet café",
      timezone: "Europe/Prague",
    };
    const insertPatient = async (workspaceId: string, name: string) =>
      (
        await client.query<{ id: string }>(
          `
      insert into ihear.patients (workspace_id, display_name, audiogram, aids, follow_up_date, note, timezone)
      values ($1, $2, $3, $4, $5, $6, $7) returning id
    `,
          [
            workspaceId,
            name,
            profile.audiogram,
            profile.aids,
            profile.followUpDate,
            profile.note,
            profile.timezone,
          ],
        )
      ).rows[0].id;
    const patientA = await insertPatient(workspaceA, profile.displayName);
    const patientB = await insertPatient(workspaceB, "Other Tenant");

    await client.query("savepoint tenant_fk");
    await assert.rejects(
      client.query(
        "insert into ihear.capabilities (workspace_id, patient_id, kind, token_hash, expires_at) values ($1, $2, 'patient', $3, now() + interval '1 day')",
        [workspaceB, patientA, hash(80)],
      ),
      /foreign key constraint/,
    );
    await client.query("rollback to savepoint tenant_fk");

    const reserveEvent = async (
      eventId: string,
      suffix: number,
      workspaceId = workspaceA,
      patientId = patientA,
    ) => {
      const fingerprint = hash(100 + suffix);
      const result = await client.query<{
        value: { disposition: string; status: string };
      }>(
        `
        select ihear.reserve_event_upload(
          $1, $2, $3, $4, 'difficult', 'Several people talking', 'Music or TV',
          '2026-09-11T12:00:00Z', $5, $6, $7, $8, 32044, 1, 1
        ) as value
      `,
        [
          eventId,
          workspaceId,
          patientId,
          hash(10),
          { sampleRate: 16000, sourceLabel: "Phone microphone" },
          `${workspaceId}/${patientId}/${eventId}.wav`,
          hash(90 + suffix),
          fingerprint,
        ],
      );
      return { ...result.rows[0].value, fingerprint };
    };

    const eventIds = Array.from({ length: 6 }, () => randomUUID());
    const first = await reserveEvent(eventIds[0], 0);
    assert.equal(first.disposition, "reserved");
    await client.query("select ihear.finalize_event_upload($1, $2, $3, $4)", [
      eventIds[0],
      workspaceA,
      patientA,
      first.fingerprint,
    ]);
    const duplicate = await reserveEvent(eventIds[0], 0);
    assert.equal(duplicate.disposition, "existing");
    assert.equal(duplicate.status, "queued");

    await client.query("savepoint event_conflict");
    await assert.rejects(reserveEvent(eventIds[0], 1), /event_conflict/);
    await client.query("rollback to savepoint event_conflict");

    for (let index = 1; index < eventIds.length; index += 1)
      await reserveEvent(eventIds[index], index);
    const queueCount = await client.query<{ count: string }>(
      `
      select count(*) from pgmq.q_ihear_jobs q
      join ihear.jobs j on j.id::text = q.message ->> 'jobId'
      where j.event_id = $1
    `,
      [eventIds[0]],
    );
    assert.equal(
      Number(queueCount.rows[0].count),
      1,
      "duplicate finalization must enqueue once",
    );

    const searchName = await client.query(
      "select id from ihear.search_patients($1, $2, null, null, null)",
      [workspaceA, "Alex"],
    );
    const searchEvent = await client.query(
      "select id from ihear.search_patients($1, $2, null, null, null)",
      [workspaceA, "Music"],
    );
    const isolatedSearch = await client.query(
      "select id from ihear.search_patients($1, $2, null, null, null)",
      [workspaceB, "Alex"],
    );
    assert.deepEqual(
      searchName.rows.map((row) => row.id),
      [patientA],
    );
    assert.deepEqual(
      searchEvent.rows.map((row) => row.id),
      [patientA],
    );
    assert.equal(isolatedSearch.rowCount, 0);

    const ownJob = await client.query<{ id: string }>(
      "select id from ihear.jobs where event_id = $1 and kind = 'event_analysis'",
      [eventIds[0]],
    );
    const jobId = ownJob.rows[0].id;
    const attemptA = randomUUID();
    const attemptB = randomUUID();
    await client.query("savepoint invalid_worker_id");
    await assert.rejects(
      client.query("select * from ihear.claim_job($1, $2, 180)", [
        jobId,
        "stable-worker-name",
      ]),
      /invalid_job_lease/,
    );
    await client.query("rollback to savepoint invalid_worker_id");
    const claim = await client.query(
      "select * from ihear.claim_job($1, $2, 180)",
      [jobId, attemptA],
    );
    const secondClaim = await client.query(
      "select * from ihear.claim_job($1, $2, 180)",
      [jobId, attemptB],
    );
    assert.equal(claim.rowCount, 1);
    assert.equal(secondClaim.rowCount, 0);
    const renewed = await client.query<{ renewed: boolean }>(
      "select ihear.renew_job_lease($1, $2, 180) as renewed",
      [jobId, attemptA],
    );
    const wrongRenewal = await client.query<{ renewed: boolean }>(
      "select ihear.renew_job_lease($1, $2, 180) as renewed",
      [jobId, attemptB],
    );
    assert.equal(renewed.rows[0].renewed, true);
    assert.equal(wrongRenewal.rows[0].renewed, false);
    await client.query(
      "update ihear.jobs set lease_expires_at = now() - interval '1 second' where id = $1",
      [jobId],
    );
    await client.query("savepoint expired_finish");
    await assert.rejects(
      client.query("select ihear.finish_job($1, $2)", [jobId, attemptA]),
      /job_lease_not_owned/,
    );
    await client.query("rollback to savepoint expired_finish");
    const reclaimed = await client.query(
      "select * from ihear.claim_job($1, $2, 180)",
      [jobId, attemptB],
    );
    assert.equal(reclaimed.rowCount, 1);
    const staleRenewal = await client.query<{ renewed: boolean }>(
      "select ihear.renew_job_lease($1, $2, 180) as renewed",
      [jobId, attemptA],
    );
    assert.equal(staleRenewal.rows[0].renewed, false);
    await client.query("savepoint stale_attempt_persist");
    await assert.rejects(
      client.query(
        "select ihear.persist_analysis($1, $2, 'ready', $3, $4)",
        [jobId, attemptA, { duration_seconds: 1 }, { pipeline: "stale" }],
      ),
      /job_lease_not_owned/,
    );
    await client.query("rollback to savepoint stale_attempt_persist");
    await client.query("savepoint stale_attempt_finish");
    await assert.rejects(
      client.query("select ihear.finish_job($1, $2)", [jobId, attemptA]),
      /job_lease_not_owned/,
    );
    await client.query("rollback to savepoint stale_attempt_finish");
    const analysis = await client.query<{ id: string }>(
      "select ihear.persist_analysis($1, $2, 'ready', $3, $4) as id",
      [jobId, attemptB, { duration_seconds: 1 }, { pipeline: "test" }],
    );
    await client.query(
      "select ihear.persist_interpretation($1, $2, $3, 'unavailable', 'v1', 'held_ambiguity', null, $4)",
      [jobId, attemptB, analysis.rows[0].id, { reason: "test" }],
    );
    await client.query("select ihear.mark_audio_deleted($1, $2)", [
      eventIds[0],
      `${workspaceA}/${patientA}/${eventIds[0]}.wav`,
    ]);
    await client.query("select ihear.finish_job($1, $2, $3)", [
      jobId,
      attemptB,
      { ok: true },
    ]);
    const completed = await client.query<{
      status: string;
      audio_deleted_at: Date;
      report_revision: string;
    }>(
      `
      select e.status, e.audio_deleted_at, p.report_revision
      from ihear.events e join ihear.patients p on p.id = e.patient_id where e.id = $1
    `,
      [eventIds[0]],
    );
    assert.equal(completed.rows[0].status, "ready");
    assert.ok(completed.rows[0].audio_deleted_at);
    assert.ok(Number(completed.rows[0].report_revision) > 3);

    const usageIds: string[] = [];
    for (let index = 0; index < 5; index += 1) {
      const reservation = await client.query<{
        value: { status: string; usageId: string };
      }>(
        `
        select ihear.reserve_api_budget($1, $2, $3, null, 'event_interpretation', 'test-model', .5, $4, false, '2026-09-11T12:00:00Z') as value
      `,
        [workspaceA, patientA, eventIds[index], `event-${index}`],
      );
      assert.equal(reservation.rows[0].value.status, "reserved");
      usageIds.push(reservation.rows[0].value.usageId);
      if (index === 0) {
        const ambiguous = await client.query<{ value: { status: string } }>(
          `
          select ihear.reserve_api_budget($1, $2, $3, null, 'event_interpretation', 'test-model', .5, $4, true, '2026-09-11T12:00:00Z') as value
        `,
          [workspaceA, patientA, eventIds[index], `event-${index}`],
        );
        assert.equal(ambiguous.rows[0].value.status, "held_ambiguity");
        await client.query("select ihear.settle_api_budget($1, .4, $2)", [
          reservation.rows[0].value.usageId,
          "provider-test",
        ]);
      }
    }
    const sixth = await client.query<{ value: { status: string } }>(
      `
      select ihear.reserve_api_budget($1, $2, $3, null, 'event_interpretation', 'test-model', .1, 'event-5', false, '2026-09-11T12:00:00Z') as value
    `,
      [workspaceA, patientA, eventIds[5]],
    );
    assert.equal(sixth.rows[0].value.status, "held_event_limit");
    const crossWorkspaceBudget = await client.query<{
      value: { status: string };
    }>(
      `
      select ihear.reserve_api_budget($1, $2, null, null, 'report_interpretation', 'test-model', .7, 'report-other', false, '2026-09-11T12:00:00Z') as value
    `,
      [workspaceB, patientB],
    );
    assert.equal(
      crossWorkspaceBudget.rows[0].value.status,
      "held_budget",
      "daily budget must be global across workspaces",
    );

    await client.query(
      "select ihear.settle_api_budget_overage($1, .6, $2, $3)",
      [
        usageIds[1],
        "provider-overage-test",
        "Provider cost exceeded reservation",
      ],
    );
    const frozen = await client.query<{
      frozen_at: Date;
      freeze_reason: string;
    }>(
      "select frozen_at, freeze_reason from ihear.budget_accounts where account_key = 'astra-global'",
    );
    assert.ok(frozen.rows[0].frozen_at);
    assert.equal(
      frozen.rows[0].freeze_reason,
      "Provider cost exceeded reservation",
    );
    const afterFreeze = await client.query<{ value: { status: string } }>(
      `
      select ihear.reserve_api_budget($1, $2, null, null, 'report_interpretation', 'test-model', .01, 'after-freeze', false, '2026-09-11T12:00:00Z') as value
    `,
      [workspaceB, patientB],
    );
    assert.equal(afterFreeze.rows[0].value.status, "held_budget_frozen");

    const tableDefaultReport = await client.query<{ report_version: number }>(
      `insert into ihear.reports (workspace_id, patient_id, input_revision)
       select workspace_id, id, report_revision from ihear.patients where id = $1
       returning report_version`,
      [patientB],
    );
    assert.equal(tableDefaultReport.rows[0].report_version, 2);

    const report = await client.query<{
      value: { reportId: string; status: string };
    }>("select ihear.ensure_report_job($1, $2, 1) as value", [
      workspaceA,
      patientA,
    ]);
    assert.equal(report.rows[0].value.status, "queued");
    const reportV1Again = await client.query<{
      value: { reportId: string; status: string };
    }>("select ihear.ensure_report_job($1, $2, 1) as value", [
      workspaceA,
      patientA,
    ]);
    assert.equal(
      reportV1Again.rows[0].value.reportId,
      report.rows[0].value.reportId,
    );
    const reportV2 = await client.query<{
      value: { reportId: string; status: string };
    }>("select ihear.ensure_report_job($1, $2) as value", [
      workspaceA,
      patientA,
    ]);
    assert.equal(reportV2.rows[0].value.status, "queued");
    assert.notEqual(
      reportV2.rows[0].value.reportId,
      report.rows[0].value.reportId,
    );
    const reportVersions = await client.query<{
      id: string;
      report_version: number;
      job_version: number;
    }>(
      `select r.id, r.report_version, j.version as job_version
       from ihear.reports r
       join ihear.jobs j on j.report_id = r.id and j.kind = 'report'
       where r.id = any($1::uuid[])
       order by r.report_version`,
      [[report.rows[0].value.reportId, reportV2.rows[0].value.reportId]],
    );
    assert.deepEqual(
      reportVersions.rows.map(({ report_version, job_version }) => ({
        report_version,
        job_version,
      })),
      [
        { report_version: 1, job_version: 1 },
        { report_version: 2, job_version: 2 },
      ],
    );
    const reportJob = await client.query<{ id: string }>(
      "select id from ihear.jobs where report_id = $1 and kind = 'report'",
      [report.rows[0].value.reportId],
    );
    const reportAttemptA = randomUUID();
    const reportAttemptB = randomUUID();
    await client.query("select * from ihear.claim_job($1, $2, 180)", [
      reportJob.rows[0].id,
      reportAttemptA,
    ]);
    await client.query(
      "update ihear.jobs set lease_expires_at = now() - interval '1 second' where id = $1",
      [reportJob.rows[0].id],
    );
    await client.query("select * from ihear.claim_job($1, $2, 180)", [
      reportJob.rows[0].id,
      reportAttemptB,
    ]);
    await client.query("savepoint stale_report_attempt");
    await assert.rejects(
      client.query("select ihear.persist_report_result($1, $2, 'ready', $3)", [
        reportJob.rows[0].id,
        reportAttemptA,
        `${workspaceA}/${patientA}/${report.rows[0].value.reportId}/${reportAttemptA}.pdf`,
      ]),
      /job_lease_not_owned/,
    );
    await client.query("rollback to savepoint stale_report_attempt");
    await client.query("savepoint shared_report_path");
    await assert.rejects(
      client.query("select ihear.persist_report_result($1, $2, 'ready', $3)", [
        reportJob.rows[0].id,
        reportAttemptB,
        `${workspaceA}/${patientA}/${report.rows[0].value.reportId}.pdf`,
      ]),
      /invalid_report_object_path/,
    );
    await client.query("rollback to savepoint shared_report_path");
    const queuedAfterReport = randomUUID();
    const queuedReservation = await reserveEvent(queuedAfterReport, 7);
    await client.query(
      "select ihear.finalize_event_upload($1, $2, $3, $4)",
      [queuedAfterReport, workspaceA, patientA, queuedReservation.fingerprint],
    );
    const reportRevisions = await client.query<{
      input_revision: string;
      report_revision: string;
    }>(
      `select r.input_revision, p.report_revision
       from ihear.reports r join ihear.patients p on p.id = r.patient_id
       where r.id = $1`,
      [report.rows[0].value.reportId],
    );
    assert.ok(
      Number(reportRevisions.rows[0].report_revision) >
        Number(reportRevisions.rows[0].input_revision),
    );
    await client.query("savepoint stale_report");
    await assert.rejects(
      client.query("select ihear.persist_report_result($1, $2, 'ready', $3)", [
        reportJob.rows[0].id,
        reportAttemptB,
        `${workspaceA}/${patientA}/${report.rows[0].value.reportId}/${reportAttemptB}.pdf`,
      ]),
      /report_input_stale/,
    );
    await client.query("rollback to savepoint stale_report");
    await client.query(
      "select ihear.fail_job($1, $2, 'Report input changed while the report was generated.')",
      [reportJob.rows[0].id, reportAttemptB],
    );

    await client.query("savepoint browser_grant");
    await client.query("set local role anon");
    await assert.rejects(
      client.query("select * from ihear.patients"),
      /permission denied/,
    );
    await client.query("rollback to savepoint browser_grant");
    await client.query("savepoint authenticated_grant");
    await client.query("set local role authenticated");
    await assert.rejects(
      client.query("select * from ihear.patients"),
      /permission denied/,
    );
    await client.query("rollback to savepoint authenticated_grant");
  } finally {
    await client.query("rollback");
    await client.end();
  }
});
