# Data model and worker contract

This document is the exact backend contract for the local milestone. The migration is the executable source of truth if this document and SQL ever diverge. All application data lives in the private `ihear` schema. Browser roles receive no grants. Next.js and the worker connect from trusted server processes only.

## Storage and queue constants

- `AUDIO_BUCKET=ihear-audio`, private, WAV only, 2.1 MB object limit.
- `REPORT_BUCKET=ihear-reports`, private, PDF only, 10 MB object limit.
- `QUEUE_NAME=ihear_jobs`, a durable logged pgmq queue.
- `PIPELINE_VERSION=1`, `REPORT_VERSION=1`.
- Audio object key: `<workspace_id>/<patient_id>/<event_id>.wav`.
- Report object key: `<workspace_id>/<patient_id>/<report_id>.pdf`.
- Queue payload: `{"jobId":"<uuid>","kind":"event_analysis|report","version":1}`. The database row, not the queue message, is authoritative.

The server reads these five values from environment variables and defaults to the listed local values. It rejects a runtime override that does not match the applied migration, preventing the application and worker from silently addressing different infrastructure. A future rename/version bump therefore requires a migration and runtime configuration change together.

The Next.js direct Postgres pool reads `DATABASE_POOL_MAX`, defaults to 3 connections per process, rejects values outside 1–10, and uses a 10-second connection timeout. Worker database connections are configured separately.

## Tables

All UUID primary keys use `gen_random_uuid()`. All timestamps are `timestamptz` in UTC. Every tenant-owned row carries `workspace_id`, and composite foreign keys prevent cross-workspace references.

### `ihear.workspaces`

`id uuid primary key`, `created_at timestamptz`.

### `ihear.capabilities`

`id uuid primary key`, `workspace_id uuid not null`, `patient_id uuid null`, `kind text` (`owner` or `patient`), `token_hash bytea unique not null`, `expires_at timestamptz null`, `revoked_at timestamptz null`, `created_at timestamptz`, `last_used_at timestamptz null`.

Owner capabilities have no `patient_id` and do not expire. Patient capabilities have a `patient_id`, always expire, and never confer owner scope. Only SHA-256 hashes of random 32-byte tokens are stored. Raw tokens exist only in separate `ihear_owner` and `ihear_patient` HttpOnly, SameSite=Lax cookies; Secure follows the actual HTTPS request and is mandatory in production. API authorization reads only the cookie for its required scope. A clinician may therefore test a pairing link without destroying owner authority, while a fresh phone receives no owner capability for the paired workspace. Rotating or revoking pairing revokes every patient capability for that patient.

### `ihear.patients`

`id uuid primary key`, `workspace_id uuid not null`, `display_name text`, `audiogram jsonb`, `aids jsonb`, `follow_up_date date`, `note text`, `timezone text default 'Europe/Prague'`, `profile_version integer default 1`, `report_revision bigint default 1`, `search_vector tsvector`, `created_at timestamptz`, `updated_at timestamptz`.

The profile update trigger increments `profile_version` and `report_revision`. Historical events retain their original `profile_snapshot`. `search_vector` covers display name and note.

### `ihear.pairing_tokens`

`id uuid primary key`, `workspace_id uuid not null`, `patient_id uuid not null`, `token_hash bytea unique not null`, `expires_at timestamptz not null`, `revoked_at timestamptz null`, `created_at timestamptz`, `last_redeemed_at timestamptz null`, `redemption_count integer default 0`.

The displayed grouped code is the raw base32 token formatted for readability; it is never stored. A valid unexpired token may be redeemed again to restore a patient session. Rotation and DELETE revoke the token and all previously issued patient capabilities.

### `ihear.events`

`id uuid primary key` (client supplied), `workspace_id uuid not null`, `patient_id uuid not null`, `kind text` (`understood` or `difficult`), `difficulty text null`, `environment text null`, `captured_at timestamptz`, `capture jsonb`, `profile_snapshot jsonb`, `profile_version integer`, `audio_object_path text unique`, `audio_deleted_at timestamptz null`, `audio_sha256 bytea`, `request_fingerprint bytea`, `audio_bytes integer`, `duration_seconds numeric`, `pipeline_version integer default 1`, `status text` (`uploading`, `queued`, `analysing`, `ready`, `failed`), `error text null`, `search_vector tsvector`, `created_at timestamptz`, `updated_at timestamptz`.

The route rejects a declared oversized body early, then reads the request stream through a hard 2.3 MB cap before multipart parsing. This also bounds chunked requests and false `Content-Length` headers. The server then computes the fingerprint from canonical metadata plus the audio SHA-256. `reserve_event_upload` takes the scoped IP hash, serializes on the event ID, applies admission limits only for a new event, and snapshots the current profile. Reserving the same `(workspace_id, patient_id, id)` and fingerprint returns the same row; any mismatch is a conflict. Only an `uploading` reservation may write or rewrite the deterministic Storage object; a terminal failed duplicate returns its existing state without reintroducing deleted audio. Finalization and durable enqueue are one SQL transaction. `difficulty` and `environment` are required for `difficult` events and must be null for `understood` events. The event search vector covers kind, difficulty, environment, and the capture source label.

### `ihear.analyses`

`id uuid primary key`, `workspace_id uuid not null`, `patient_id uuid not null`, `event_id uuid not null`, `pipeline_version integer`, `status text` (`ready` or `failed`), `result jsonb null`, `provenance jsonb`, `error text null`, `created_at timestamptz`, `updated_at timestamptz`, unique `(event_id, pipeline_version)`.

The worker persists deterministic DSP here before any interpretation attempt. A trigger increments the patient's `report_revision` when a materially new analysis is inserted or changed.

### `ihear.interpretations`

`id uuid primary key`, `workspace_id uuid not null`, `patient_id uuid not null`, `event_id uuid not null`, `analysis_id uuid not null`, `pipeline_version integer`, `model text`, `prompt_version text`, `status text` (`held_ambiguity`, `held_budget`, `ready`, `failed`, `unavailable`, `skipped`), `result jsonb null`, `provenance jsonb`, `error text null`, `api_usage_id uuid null`, `created_at timestamptz`, `updated_at timestamptz`, unique `(analysis_id, model, prompt_version)`.

No interpretation is attempted when deterministic evidence is ambiguous. That state is persisted as `held_ambiguity`, without a budget reservation.

### `ihear.reports`

`id uuid primary key`, `workspace_id uuid not null`, `patient_id uuid not null`, `input_revision bigint`, `report_version integer default 1`, `status text` (`queued`, `generating`, `ready`, `failed`), `object_path text null unique`, `error text null`, `created_at timestamptz`, `updated_at timestamptz`, unique `(patient_id, input_revision, report_version)`.

POST creates at most one report and one job for the current `(patient_id, report_revision, REPORT_VERSION)`. GET only reads status. The download API streams the private object after owner authorization.

### `ihear.jobs`

`id uuid primary key`, `workspace_id uuid not null`, `patient_id uuid not null`, `event_id uuid null`, `report_id uuid null`, `kind text` (`event_analysis` or `report`), `version integer`, `status text` (`queued`, `running`, `retry`, `succeeded`, `failed`), `payload jsonb`, `result jsonb null`, `queue_message_id bigint null`, `attempt_count integer default 0`, `max_attempts integer default 3`, `available_at timestamptz`, `lease_expires_at timestamptz null`, `worker_id text null`, `last_error text null`, `created_at timestamptz`, `updated_at timestamptz`.

There is one event job per `(event_id, kind, version)` and one report job per `(report_id, kind, version)`. A job points to exactly one event or report.

### `ihear.budget_accounts`, `ihear.api_usage`, and `ihear.rate_limit_counters`

`budget_accounts`: singleton `account_key text primary key` fixed to `astra-global`, `total_limit_usd numeric(10,6) default 20`, `daily_limit_usd numeric(10,6) default 3`, `budget_timezone text default 'Europe/Prague'`, `frozen_at timestamptz null`, `freeze_reason text null`, `created_at timestamptz`, `updated_at timestamptz`.

`api_usage`: `id uuid primary key`, `workspace_id uuid not null`, `patient_id uuid not null`, `event_id uuid null`, `job_id uuid null`, `kind text` (`event_interpretation` or `report_interpretation`), `usage_day date`, `patient_day date`, `state text` (`reserved`, `settled`, `released`), `reserved_usd numeric(10,6)`, `actual_usd numeric(10,6) null`, `model text`, `idempotency_key text`, `provider_request_id text null`, `created_at timestamptz`, `settled_at timestamptz null`, unique `(workspace_id, idempotency_key)`.

`rate_limit_counters`: `scope text`, `subject_hash bytea`, `window_start timestamptz`, `request_count integer`, primary key `(scope, subject_hash, window_start)`. The server stores only scoped hashes, never raw IP addresses.

Budget reservation locks the singleton global account, counts usage across every workspace, and atomically enforces the USD 20 total and USD 3 per day in the fixed budget timezone. The five `event_interpretation` limit remains per patient/day in that patient's clinic timezone. Retry uses the same reservation only for the same provider attempt result; ambiguous evidence always returns `held_ambiguity` before idempotency lookup, and a deliberate new paid attempt requires a new atomic reservation and idempotency key. Normal settlement requires actual cost at or below the reserved upper bound. If provider-reported cost nevertheless exceeds it, `settle_api_budget_overage(usage_id, actual_cost, provider_request_id, reason)` records the full actual amount and freezes the singleton account in the same transaction. Every subsequent reservation returns `held_budget_frozen`, including idempotent keys, so no retry can make another paid call until explicit owner repair. Limits never auto-increase.

`ihear.create_workspace_with_capability(...)` atomically enforces 10 creations per scoped IP hash/hour and 200 globally/hour. `ihear.assert_event_admission(...)` enforces 60 event admissions per scoped IP hash/hour, 30 per patient/hour, 500 globally/hour, and at most 200 active event jobs. Rejection raises `rate_limit_exceeded` and rolls the counter changes back. These limits are operational safeguards, not product entitlements.

## SQL/RPC worker interface

The worker uses direct Postgres, schema-qualified calls, and transactions. It never updates lease or budget fields ad hoc.

1. Read one durable message with `pgmq.read('ihear_jobs', visibility_timeout_seconds, 1)`.
2. Call `ihear.claim_job(job_id, worker_id, lease_seconds)`. An empty result means another worker owns it, it is delayed, or it is terminal.
   While processing, heartbeat with `ihear.renew_job_lease(job_id, worker_id, lease_seconds)`. It returns `true` only while the same worker owns an unexpired running lease and atomically extends both the job lease and pgmq visibility. `false` means ownership was lost; the worker must stop without persisting or completing. Lease seconds are bounded to 10–1800.
3. For `event_analysis`, download the path from `events.audio_object_path`, validate again, persist DSP with `ihear.persist_analysis(...)`, then delete the audio object only after that transaction commits and call idempotent `ihear.mark_audio_deleted(event_id, expected_path)`. The path remains as an audit reference while `audio_deleted_at` proves retention cleanup.
4. Before a paid call, reject ambiguous evidence locally and persist `held_ambiguity`; otherwise call `ihear.reserve_api_budget(workspace_id, patient_id, event_id, job_id, kind, model, maximum_cost_usd, idempotency_key, false)`. It returns JSON with `status` equal to `reserved`, `existing`, `held_budget`, `held_budget_frozen`, `held_event_limit`, or `held_ambiguity`, plus `usageId` when reserved/existing.
5. On provider success call `ihear.settle_api_budget(usage_id, actual_cost_usd, provider_request_id)`. On a pre-call abort call `ihear.release_api_budget(usage_id)`. If actual provider cost exceeds the reservation, call `ihear.settle_api_budget_overage(...)`, persist a terminal interpretation failure, and do not classify it as ambiguity.
6. Persist interpretation with `ihear.persist_interpretation(...)`.
7. Call `ihear.finish_job(job_id, worker_id, result)` only after durable outputs exist. It archives the current pgmq message.
8. For retryable failure call `ihear.retry_job(job_id, worker_id, error, delay_seconds)`; this archives the old message and sends a new delayed message, bounded by `max_attempts`. For permanent failure call `ihear.fail_job(job_id, worker_id, error)`.

All worker functions are `SECURITY INVOKER`, live only in private schema `ihear`, have a fixed `search_path`, and are revoked from `PUBLIC`, `anon`, and `authenticated`. The trusted database roles retain execute access. pgmq is not exposed through `pgmq_public`.

`persist_analysis`, `persist_interpretation`, `persist_report_result`, `finish_job`, `retry_job`, and `fail_job` all require the caller's lease to remain unexpired. Report persistence also locks and compares the report's `input_revision` with the current patient `report_revision`; `report_input_stale` means the worker must discard any obsolete PDF object and terminally fail the old job. A later POST creates the new-revision report/job.

## Search contract

`ihear.search_patients(workspace_id, query, status, difficulty, follow_up)` returns patients only from the supplied server-authorized workspace. Query matching uses PostgreSQL full-text search against patient display name/note and an `EXISTS` match against event kind/difficulty/environment/source label. Filters are combined in SQL. No browser-supplied workspace identifier is accepted.

## RLS and tenant isolation

RLS is enabled and forced on every `ihear` table as defense in depth, with no browser policies. `anon` and `authenticated` have no schema, table, sequence, or function privileges. The application resolves a hashed capability first, then includes the resulting `workspace_id` and optional `patient_id` in every query. Composite foreign keys enforce that referenced rows share a workspace and patient. The private Storage buckets have no browser policies; only trusted server/worker service credentials operate on objects.

## Local verification evidence

On 2026-09-11, the CLI-named migrations applied to the local Supabase stack without schema errors. Rollback-only Postgres integration tests exercised tenant foreign-key denial, event idempotency and single enqueue, exclusive claim/lease renewal, expired-lease rejection, DSP/interpretation persistence, audio deletion marking, full-text search, global cross-workspace budget enforcement, per-patient event limits, overage settlement/freeze, stale-report rejection, report enqueue, and direct `anon` schema denial. Supabase database lint and security/performance advisors returned no issues.

A separate live HTTP check loaded the local public key only in process memory and used an existing private report object. Anonymous database select and insert were denied; anonymous Storage list did not reveal the object; upload and direct download were denied. No probe write succeeded and no private payload or key was printed.
