create extension if not exists pgcrypto with schema extensions;
create extension if not exists pgmq;

create schema if not exists ihear;
revoke all on schema ihear from public, anon, authenticated;
grant usage on schema ihear to service_role;

create table ihear.workspaces (
  id uuid primary key default extensions.gen_random_uuid(),
  created_at timestamptz not null default now()
);

create table ihear.patients (
  id uuid primary key default extensions.gen_random_uuid(),
  workspace_id uuid not null references ihear.workspaces(id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 120),
  audiogram jsonb not null,
  aids jsonb not null,
  follow_up_date date not null,
  note text not null default '' check (char_length(note) <= 4000),
  timezone text not null default 'Europe/Prague' check (char_length(timezone) between 1 and 80),
  profile_version integer not null default 1 check (profile_version > 0),
  report_revision bigint not null default 1 check (report_revision > 0),
  search_vector tsvector not null default ''::tsvector,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, workspace_id)
);

create table ihear.capabilities (
  id uuid primary key default extensions.gen_random_uuid(),
  workspace_id uuid not null references ihear.workspaces(id) on delete cascade,
  patient_id uuid,
  kind text not null check (kind in ('owner', 'patient')),
  token_hash bytea not null unique check (octet_length(token_hash) = 32),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  foreign key (patient_id, workspace_id) references ihear.patients(id, workspace_id) on delete cascade,
  check (
    (kind = 'owner' and patient_id is null and expires_at is null)
    or (kind = 'patient' and patient_id is not null and expires_at is not null)
  )
);

create table ihear.pairing_tokens (
  id uuid primary key default extensions.gen_random_uuid(),
  workspace_id uuid not null,
  patient_id uuid not null,
  token_hash bytea not null unique check (octet_length(token_hash) = 32),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  last_redeemed_at timestamptz,
  redemption_count integer not null default 0 check (redemption_count >= 0),
  foreign key (patient_id, workspace_id) references ihear.patients(id, workspace_id) on delete cascade
);

create table ihear.events (
  id uuid primary key,
  workspace_id uuid not null,
  patient_id uuid not null,
  kind text not null check (kind in ('understood', 'difficult')),
  difficulty text,
  environment text,
  captured_at timestamptz not null,
  capture jsonb not null,
  profile_snapshot jsonb not null,
  profile_version integer not null check (profile_version > 0),
  audio_object_path text not null unique,
  audio_deleted_at timestamptz,
  audio_sha256 bytea not null check (octet_length(audio_sha256) = 32),
  request_fingerprint bytea not null check (octet_length(request_fingerprint) = 32),
  audio_bytes integer not null check (audio_bytes > 0 and audio_bytes <= 2202000),
  duration_seconds numeric(8,4) not null check (duration_seconds > 0 and duration_seconds <= 10.1),
  pipeline_version integer not null default 1 check (pipeline_version > 0),
  status text not null default 'uploading' check (status in ('uploading', 'queued', 'analysing', 'ready', 'failed')),
  error text,
  search_vector tsvector not null default ''::tsvector,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (patient_id, workspace_id) references ihear.patients(id, workspace_id) on delete cascade,
  unique (id, workspace_id, patient_id),
  check (
    (kind = 'understood' and difficulty is null and environment is null)
    or (kind = 'difficult' and nullif(btrim(difficulty), '') is not null and nullif(btrim(environment), '') is not null)
  )
);

create table ihear.analyses (
  id uuid primary key default extensions.gen_random_uuid(),
  workspace_id uuid not null,
  patient_id uuid not null,
  event_id uuid not null,
  pipeline_version integer not null check (pipeline_version > 0),
  status text not null check (status in ('ready', 'failed')),
  result jsonb,
  provenance jsonb not null default '{}'::jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (event_id, workspace_id, patient_id) references ihear.events(id, workspace_id, patient_id) on delete cascade,
  unique (event_id, pipeline_version),
  check ((status = 'ready' and result is not null and error is null) or status = 'failed')
);

create table ihear.budget_accounts (
  account_key text primary key default 'astra-global' check (account_key = 'astra-global'),
  total_limit_usd numeric(10,6) not null default 20 check (total_limit_usd >= 0),
  daily_limit_usd numeric(10,6) not null default 3 check (daily_limit_usd >= 0),
  budget_timezone text not null default 'Europe/Prague' check (budget_timezone = 'Europe/Prague'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into ihear.budget_accounts (account_key) values ('astra-global');

create table ihear.rate_limit_counters (
  scope text not null,
  subject_hash bytea not null check (octet_length(subject_hash) = 32),
  window_start timestamptz not null,
  request_count integer not null check (request_count > 0),
  primary key (scope, subject_hash, window_start)
);

create table ihear.jobs (
  id uuid primary key default extensions.gen_random_uuid(),
  workspace_id uuid not null,
  patient_id uuid not null,
  event_id uuid,
  report_id uuid,
  kind text not null check (kind in ('event_analysis', 'report')),
  version integer not null check (version > 0),
  status text not null default 'queued' check (status in ('queued', 'running', 'retry', 'succeeded', 'failed')),
  payload jsonb not null default '{}'::jsonb,
  result jsonb,
  queue_message_id bigint,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 3 check (max_attempts between 1 and 10),
  available_at timestamptz not null default now(),
  lease_expires_at timestamptz,
  worker_id text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (patient_id, workspace_id) references ihear.patients(id, workspace_id) on delete cascade,
  foreign key (event_id, workspace_id, patient_id) references ihear.events(id, workspace_id, patient_id) on delete cascade,
  check ((kind = 'event_analysis' and event_id is not null and report_id is null) or (kind = 'report' and event_id is null and report_id is not null))
);

create table ihear.api_usage (
  id uuid primary key default extensions.gen_random_uuid(),
  workspace_id uuid not null references ihear.workspaces(id) on delete cascade,
  patient_id uuid not null,
  event_id uuid,
  job_id uuid,
  kind text not null check (kind in ('event_interpretation', 'report_interpretation')),
  usage_day date not null,
  patient_day date not null,
  state text not null check (state in ('reserved', 'settled', 'released')),
  reserved_usd numeric(10,6) not null check (reserved_usd >= 0),
  actual_usd numeric(10,6),
  model text not null,
  idempotency_key text not null check (char_length(idempotency_key) between 1 and 240),
  provider_request_id text,
  created_at timestamptz not null default now(),
  settled_at timestamptz,
  foreign key (patient_id, workspace_id) references ihear.patients(id, workspace_id) on delete cascade,
  foreign key (event_id, workspace_id, patient_id) references ihear.events(id, workspace_id, patient_id) on delete cascade,
  foreign key (job_id) references ihear.jobs(id) on delete set null,
  unique (workspace_id, idempotency_key),
  check ((kind = 'event_interpretation' and event_id is not null) or (kind = 'report_interpretation' and event_id is null)),
  check (
    (state = 'reserved' and actual_usd is null and settled_at is null)
    or (state = 'settled' and actual_usd is not null and actual_usd >= 0 and settled_at is not null)
    or (state = 'released' and actual_usd is null and settled_at is not null)
  )
);

create table ihear.interpretations (
  id uuid primary key default extensions.gen_random_uuid(),
  workspace_id uuid not null,
  patient_id uuid not null,
  event_id uuid not null,
  analysis_id uuid not null references ihear.analyses(id) on delete cascade,
  pipeline_version integer not null check (pipeline_version > 0),
  model text not null,
  prompt_version text not null,
  status text not null check (status in ('held_ambiguity', 'held_budget', 'ready', 'failed', 'unavailable', 'skipped')),
  result jsonb,
  provenance jsonb not null default '{}'::jsonb,
  error text,
  api_usage_id uuid references ihear.api_usage(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (event_id, workspace_id, patient_id) references ihear.events(id, workspace_id, patient_id) on delete cascade,
  unique (analysis_id, model, prompt_version),
  check ((status = 'ready' and result is not null and error is null) or status <> 'ready')
);

create table ihear.reports (
  id uuid primary key default extensions.gen_random_uuid(),
  workspace_id uuid not null,
  patient_id uuid not null,
  input_revision bigint not null check (input_revision > 0),
  report_version integer not null default 1 check (report_version > 0),
  status text not null default 'queued' check (status in ('queued', 'generating', 'ready', 'failed')),
  object_path text unique,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (patient_id, workspace_id) references ihear.patients(id, workspace_id) on delete cascade,
  unique (id, workspace_id, patient_id),
  unique (patient_id, input_revision, report_version),
  check ((status = 'ready' and object_path is not null and error is null) or status <> 'ready')
);

alter table ihear.jobs
  add constraint jobs_report_tenant_fk
  foreign key (report_id, workspace_id, patient_id)
  references ihear.reports(id, workspace_id, patient_id) on delete cascade;

create unique index jobs_event_once_idx on ihear.jobs (event_id, kind, version) where event_id is not null;
create unique index jobs_report_once_idx on ihear.jobs (report_id, kind, version) where report_id is not null;
create index capabilities_token_hash_idx on ihear.capabilities (token_hash) where revoked_at is null;
create index pairing_tokens_token_hash_idx on ihear.pairing_tokens (token_hash) where revoked_at is null;
create index patients_workspace_idx on ihear.patients (workspace_id, updated_at desc);
create index patients_search_idx on ihear.patients using gin (search_vector);
create index events_patient_idx on ihear.events (workspace_id, patient_id, captured_at desc);
create index events_search_idx on ihear.events using gin (search_vector);
create index analyses_event_idx on ihear.analyses (event_id, pipeline_version);
create index interpretations_event_idx on ihear.interpretations (event_id, created_at desc);
create index reports_patient_idx on ihear.reports (workspace_id, patient_id, created_at desc);
create index jobs_claim_idx on ihear.jobs (status, available_at, lease_expires_at);
create index api_usage_budget_idx on ihear.api_usage (workspace_id, usage_day, state);
create index api_usage_patient_day_idx on ihear.api_usage (patient_id, patient_day, kind, state);
create index rate_limit_expiry_idx on ihear.rate_limit_counters (window_start);

create function ihear.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create function ihear.prepare_patient()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.display_name := btrim(new.display_name);
  new.note := btrim(new.note);
  new.search_vector := to_tsvector('simple', coalesce(new.display_name, '') || ' ' || coalesce(new.note, ''));
  new.updated_at := now();
  if tg_op = 'UPDATE' and (
    old.display_name is distinct from new.display_name
    or old.audiogram is distinct from new.audiogram
    or old.aids is distinct from new.aids
    or old.follow_up_date is distinct from new.follow_up_date
    or old.note is distinct from new.note
    or old.timezone is distinct from new.timezone
  ) then
    new.profile_version := old.profile_version + 1;
    new.report_revision := old.report_revision + 1;
  end if;
  return new;
end;
$$;

create trigger prepare_patient_trigger before insert or update on ihear.patients
for each row execute function ihear.prepare_patient();

create function ihear.prepare_event()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.search_vector := to_tsvector(
    'simple',
    coalesce(new.kind, '') || ' ' || coalesce(new.difficulty, '') || ' ' ||
    coalesce(new.environment, '') || ' ' || coalesce(new.capture ->> 'sourceLabel', '')
  );
  new.updated_at := now();
  return new;
end;
$$;

create trigger prepare_event_trigger before insert or update on ihear.events
for each row execute function ihear.prepare_event();

create trigger touch_analysis_trigger before update on ihear.analyses
for each row execute function ihear.touch_updated_at();
create trigger touch_interpretation_trigger before update on ihear.interpretations
for each row execute function ihear.touch_updated_at();
create trigger touch_report_trigger before update on ihear.reports
for each row execute function ihear.touch_updated_at();
create trigger touch_job_trigger before update on ihear.jobs
for each row execute function ihear.touch_updated_at();
create trigger touch_budget_account_trigger before update on ihear.budget_accounts
for each row execute function ihear.touch_updated_at();

create function ihear.bump_report_revision()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  update ihear.patients
  set report_revision = report_revision + 1,
      updated_at = now()
  where id = coalesce(new.patient_id, old.patient_id)
    and workspace_id = coalesce(new.workspace_id, old.workspace_id);
  return coalesce(new, old);
end;
$$;

create trigger analysis_report_revision_insert_trigger after insert on ihear.analyses
for each row execute function ihear.bump_report_revision();
create trigger analysis_report_revision_update_trigger
after update of status, result, provenance, error on ihear.analyses
for each row when (
  old.status is distinct from new.status or old.result is distinct from new.result
  or old.provenance is distinct from new.provenance or old.error is distinct from new.error
) execute function ihear.bump_report_revision();
create trigger interpretation_report_revision_insert_trigger after insert on ihear.interpretations
for each row execute function ihear.bump_report_revision();
create trigger interpretation_report_revision_update_trigger
after update of status, result, provenance, error, api_usage_id on ihear.interpretations
for each row when (
  old.status is distinct from new.status or old.result is distinct from new.result
  or old.provenance is distinct from new.provenance or old.error is distinct from new.error
  or old.api_usage_id is distinct from new.api_usage_id
) execute function ihear.bump_report_revision();

create function ihear.consume_rate_limit(
  p_scope text,
  p_subject_hash bytea,
  p_limit integer,
  p_window_seconds integer,
  p_now timestamptz default now()
)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_window_start timestamptz;
  v_count integer;
begin
  if p_limit < 1 or p_window_seconds < 1 or octet_length(p_subject_hash) <> 32 then
    raise exception 'invalid_rate_limit' using errcode = '22023';
  end if;
  v_window_start := to_timestamp(floor(extract(epoch from p_now) / p_window_seconds) * p_window_seconds);
  delete from ihear.rate_limit_counters where window_start < p_now - interval '7 days';
  insert into ihear.rate_limit_counters (scope, subject_hash, window_start, request_count)
  values (p_scope, p_subject_hash, v_window_start, 1)
  on conflict (scope, subject_hash, window_start) do update
    set request_count = ihear.rate_limit_counters.request_count + 1
  returning request_count into v_count;
  if v_count > p_limit then raise exception 'rate_limit_exceeded' using errcode = 'P0001'; end if;
end;
$$;

create function ihear.create_workspace_with_capability(
  p_ip_hash bytea,
  p_owner_token_hash bytea
)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
  v_workspace_id uuid;
begin
  perform ihear.consume_rate_limit('workspace_ip_hour', p_ip_hash, 10, 3600);
  perform ihear.consume_rate_limit('workspace_global_hour', extensions.digest('ihear-workspace-global', 'sha256'), 200, 3600);
  insert into ihear.workspaces default values returning id into v_workspace_id;
  insert into ihear.capabilities (workspace_id, kind, token_hash)
  values (v_workspace_id, 'owner', p_owner_token_hash);
  return v_workspace_id;
end;
$$;

create function ihear.assert_event_admission(
  p_ip_hash bytea,
  p_workspace_id uuid,
  p_patient_id uuid
)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_active_jobs integer;
begin
  if not exists (select 1 from ihear.patients where id = p_patient_id and workspace_id = p_workspace_id) then
    raise exception 'patient_not_found' using errcode = 'P0002';
  end if;
  perform ihear.consume_rate_limit('event_ip_hour', p_ip_hash, 60, 3600);
  perform ihear.consume_rate_limit(
    'event_patient_hour', extensions.digest(p_workspace_id::text || ':' || p_patient_id::text, 'sha256'), 30, 3600
  );
  perform ihear.consume_rate_limit('event_global_hour', extensions.digest('ihear-event-global', 'sha256'), 500, 3600);
  select count(*) into v_active_jobs from ihear.jobs
  where kind = 'event_analysis' and status in ('queued', 'running', 'retry');
  if v_active_jobs >= 200 then raise exception 'queue_capacity_exceeded' using errcode = 'P0001'; end if;
end;
$$;

create function ihear.reserve_event_upload(
  p_event_id uuid,
  p_workspace_id uuid,
  p_patient_id uuid,
  p_ip_hash bytea,
  p_kind text,
  p_difficulty text,
  p_environment text,
  p_captured_at timestamptz,
  p_capture jsonb,
  p_audio_object_path text,
  p_audio_sha256 bytea,
  p_request_fingerprint bytea,
  p_audio_bytes integer,
  p_duration_seconds numeric,
  p_pipeline_version integer
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_patient ihear.patients%rowtype;
  v_event ihear.events%rowtype;
  v_inserted boolean := false;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_event_id::text, 0));
  select * into v_patient
  from ihear.patients
  where id = p_patient_id and workspace_id = p_workspace_id
  for share;
  if not found then
    raise exception 'patient_not_found' using errcode = 'P0002';
  end if;

  select * into v_event from ihear.events where id = p_event_id for update;
  if found then
    if v_event.workspace_id <> p_workspace_id
      or v_event.patient_id <> p_patient_id
      or v_event.request_fingerprint <> p_request_fingerprint then
      raise exception 'event_conflict' using errcode = 'P0001';
    end if;
    return jsonb_build_object(
      'eventId', v_event.id, 'disposition', 'existing',
      'status', v_event.status, 'audioObjectPath', v_event.audio_object_path
    );
  end if;

  perform ihear.assert_event_admission(p_ip_hash, p_workspace_id, p_patient_id);

  insert into ihear.events (
    id, workspace_id, patient_id, kind, difficulty, environment, captured_at, capture,
    profile_snapshot, profile_version, audio_object_path, audio_sha256, request_fingerprint,
    audio_bytes, duration_seconds, pipeline_version
  ) values (
    p_event_id, p_workspace_id, p_patient_id, p_kind, p_difficulty, p_environment,
    p_captured_at, p_capture,
    jsonb_build_object(
      'displayName', v_patient.display_name,
      'audiogram', v_patient.audiogram,
      'aids', v_patient.aids,
      'followUpDate', to_char(v_patient.follow_up_date, 'YYYY-MM-DD'),
      'note', v_patient.note,
      'timezone', v_patient.timezone
    ),
    v_patient.profile_version, p_audio_object_path, p_audio_sha256, p_request_fingerprint,
    p_audio_bytes, p_duration_seconds, p_pipeline_version
  )
  returning true into v_inserted;

  select * into v_event from ihear.events where id = p_event_id for update;
  if v_event.workspace_id <> p_workspace_id
    or v_event.patient_id <> p_patient_id
    or v_event.request_fingerprint <> p_request_fingerprint then
    raise exception 'event_conflict' using errcode = 'P0001';
  end if;

  return jsonb_build_object(
    'eventId', v_event.id,
    'disposition', case when v_inserted then 'reserved' else 'existing' end,
    'status', v_event.status,
    'audioObjectPath', v_event.audio_object_path
  );
end;
$$;

create function ihear.finalize_event_upload(
  p_event_id uuid,
  p_workspace_id uuid,
  p_patient_id uuid,
  p_request_fingerprint bytea
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_event ihear.events%rowtype;
  v_job ihear.jobs%rowtype;
  v_message_id bigint;
begin
  select * into v_event
  from ihear.events
  where id = p_event_id and workspace_id = p_workspace_id and patient_id = p_patient_id
  for update;
  if not found then
    raise exception 'event_not_found' using errcode = 'P0002';
  end if;
  if v_event.request_fingerprint <> p_request_fingerprint then
    raise exception 'event_conflict' using errcode = 'P0001';
  end if;

  insert into ihear.jobs (workspace_id, patient_id, event_id, kind, version, payload)
  values (
    v_event.workspace_id, v_event.patient_id, v_event.id, 'event_analysis', v_event.pipeline_version,
    jsonb_build_object('eventId', v_event.id)
  )
  on conflict (event_id, kind, version) where event_id is not null do nothing;

  select * into v_job
  from ihear.jobs
  where event_id = v_event.id and kind = 'event_analysis' and version = v_event.pipeline_version
  for update;

  if v_job.queue_message_id is null and v_job.status in ('queued', 'retry') then
    select pgmq.send(
      'ihear_jobs',
      jsonb_build_object('jobId', v_job.id, 'kind', v_job.kind, 'version', v_job.version)
    ) into v_message_id;
    update ihear.jobs set queue_message_id = v_message_id where id = v_job.id;
  end if;

  if v_event.status = 'uploading' then
    update ihear.events set status = 'queued', error = null where id = v_event.id;
  end if;

  return jsonb_build_object('eventId', v_event.id, 'jobId', v_job.id, 'status', 'queued');
end;
$$;

create function ihear.ensure_report_job(
  p_workspace_id uuid,
  p_patient_id uuid,
  p_report_version integer default 1
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_patient ihear.patients%rowtype;
  v_report ihear.reports%rowtype;
  v_job ihear.jobs%rowtype;
  v_message_id bigint;
begin
  select * into v_patient from ihear.patients
  where id = p_patient_id and workspace_id = p_workspace_id for update;
  if not found then
    raise exception 'patient_not_found' using errcode = 'P0002';
  end if;

  insert into ihear.reports (workspace_id, patient_id, input_revision, report_version)
  values (p_workspace_id, p_patient_id, v_patient.report_revision, p_report_version)
  on conflict (patient_id, input_revision, report_version) do nothing;

  select * into v_report from ihear.reports
  where patient_id = p_patient_id
    and input_revision = v_patient.report_revision
    and report_version = p_report_version
  for update;

  insert into ihear.jobs (workspace_id, patient_id, report_id, kind, version, payload)
  values (
    p_workspace_id, p_patient_id, v_report.id, 'report', p_report_version,
    jsonb_build_object('reportId', v_report.id, 'inputRevision', v_report.input_revision)
  )
  on conflict (report_id, kind, version) where report_id is not null do nothing;

  select * into v_job from ihear.jobs
  where report_id = v_report.id and kind = 'report' and version = p_report_version
  for update;
  if v_job.queue_message_id is null and v_job.status in ('queued', 'retry') then
    select pgmq.send(
      'ihear_jobs',
      jsonb_build_object('jobId', v_job.id, 'kind', v_job.kind, 'version', v_job.version)
    ) into v_message_id;
    update ihear.jobs set queue_message_id = v_message_id where id = v_job.id;
  end if;

  return jsonb_build_object('status', v_report.status, 'reportId', v_report.id);
end;
$$;

create function ihear.claim_job(p_job_id uuid, p_worker_id text, p_lease_seconds integer default 180)
returns setof ihear.jobs
language plpgsql
set search_path = ''
as $$
begin
  if nullif(btrim(p_worker_id), '') is null or p_lease_seconds < 10 or p_lease_seconds > 1800 then
    raise exception 'invalid_job_lease' using errcode = '22023';
  end if;
  return query
  update ihear.jobs
  set status = 'running',
      worker_id = p_worker_id,
      lease_expires_at = now() + make_interval(secs => p_lease_seconds),
      attempt_count = attempt_count + 1,
      last_error = null
  where id = p_job_id
    and attempt_count < max_attempts
    and available_at <= now()
    and (
      status in ('queued', 'retry')
      or (status = 'running' and lease_expires_at <= now())
    )
  returning *;
end;
$$;

create function ihear.persist_analysis(
  p_job_id uuid,
  p_worker_id text,
  p_status text,
  p_result jsonb,
  p_provenance jsonb,
  p_error text default null
)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
  v_analysis_id uuid;
begin
  select * into v_job from ihear.jobs
  where id = p_job_id and kind = 'event_analysis' and status = 'running'
    and worker_id = p_worker_id and lease_expires_at > now()
  for update;
  if not found then raise exception 'job_lease_not_owned' using errcode = 'P0001'; end if;

  insert into ihear.analyses (
    workspace_id, patient_id, event_id, pipeline_version, status, result, provenance, error
  ) values (
    v_job.workspace_id, v_job.patient_id, v_job.event_id, v_job.version,
    p_status, p_result, coalesce(p_provenance, '{}'::jsonb), p_error
  )
  on conflict (event_id, pipeline_version) do update
    set status = excluded.status, result = excluded.result,
        provenance = excluded.provenance, error = excluded.error
  returning id into v_analysis_id;

  update ihear.events
  set status = case when p_status = 'ready' then 'analysing' else 'failed' end,
      error = case when p_status = 'failed' then p_error else null end
  where id = v_job.event_id;
  return v_analysis_id;
end;
$$;

create function ihear.mark_audio_deleted(p_event_id uuid, p_expected_path text)
returns void
language plpgsql
set search_path = ''
as $$
begin
  update ihear.events
  set audio_deleted_at = coalesce(audio_deleted_at, now())
  where id = p_event_id and audio_object_path = p_expected_path;
  if not found then raise exception 'event_audio_not_found' using errcode = 'P0002'; end if;
end;
$$;

create function ihear.reserve_api_budget(
  p_workspace_id uuid,
  p_patient_id uuid,
  p_event_id uuid,
  p_job_id uuid,
  p_kind text,
  p_model text,
  p_maximum_cost_usd numeric,
  p_idempotency_key text,
  p_ambiguous boolean default false,
  p_now timestamptz default now()
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_account ihear.budget_accounts%rowtype;
  v_existing ihear.api_usage%rowtype;
  v_usage_id uuid;
  v_timezone text;
  v_usage_day date;
  v_patient_day date;
  v_total numeric := 0;
  v_daily numeric := 0;
  v_event_count integer := 0;
begin
  if p_ambiguous then return jsonb_build_object('status', 'held_ambiguity'); end if;
  if p_maximum_cost_usd <= 0 then raise exception 'invalid_budget_reservation' using errcode = '22023'; end if;
  if p_kind = 'event_interpretation' and not exists (
    select 1 from ihear.events where id = p_event_id and workspace_id = p_workspace_id and patient_id = p_patient_id
  ) then raise exception 'event_not_found' using errcode = 'P0002'; end if;

  select * into v_account from ihear.budget_accounts
  where account_key = 'astra-global' for update;
  if not found then raise exception 'budget_account_not_found' using errcode = 'P0002'; end if;
  select timezone into v_timezone from ihear.patients
  where id = p_patient_id and workspace_id = p_workspace_id;
  if not found then raise exception 'patient_not_found' using errcode = 'P0002'; end if;

  select * into v_existing from ihear.api_usage
  where workspace_id = p_workspace_id and idempotency_key = p_idempotency_key;
  if found then
    return jsonb_build_object('status', 'existing', 'usageId', v_existing.id, 'state', v_existing.state);
  end if;

  v_usage_day := (p_now at time zone v_account.budget_timezone)::date;
  v_patient_day := (p_now at time zone v_timezone)::date;
  select coalesce(sum(case when state = 'settled' then actual_usd else reserved_usd end), 0)
    into v_total from ihear.api_usage where state in ('reserved', 'settled');
  select coalesce(sum(case when state = 'settled' then actual_usd else reserved_usd end), 0)
    into v_daily from ihear.api_usage
    where usage_day = v_usage_day and state in ('reserved', 'settled');

  if v_total + p_maximum_cost_usd > v_account.total_limit_usd
    or v_daily + p_maximum_cost_usd > v_account.daily_limit_usd then
    return jsonb_build_object('status', 'held_budget');
  end if;

  if p_kind = 'event_interpretation' then
    select count(distinct event_id) into v_event_count from ihear.api_usage
    where patient_id = p_patient_id and patient_day = v_patient_day
      and kind = 'event_interpretation' and state in ('reserved', 'settled');
    if v_event_count >= 5 then return jsonb_build_object('status', 'held_event_limit'); end if;
  end if;

  insert into ihear.api_usage (
    workspace_id, patient_id, event_id, job_id, kind, usage_day, patient_day, state,
    reserved_usd, model, idempotency_key
  ) values (
    p_workspace_id, p_patient_id, p_event_id, p_job_id, p_kind, v_usage_day, v_patient_day,
    'reserved', p_maximum_cost_usd, p_model, p_idempotency_key
  ) returning id into v_usage_id;
  return jsonb_build_object('status', 'reserved', 'usageId', v_usage_id);
end;
$$;

create function ihear.settle_api_budget(p_usage_id uuid, p_actual_cost_usd numeric, p_provider_request_id text default null)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_usage ihear.api_usage%rowtype;
begin
  select u.* into v_usage from ihear.api_usage u
  cross join ihear.budget_accounts b
  where u.id = p_usage_id
  for update of b, u;
  if not found then raise exception 'budget_reservation_not_found' using errcode = 'P0002'; end if;
  if v_usage.state = 'settled' and v_usage.actual_usd = p_actual_cost_usd then return; end if;
  if v_usage.state <> 'reserved' or p_actual_cost_usd < 0 or p_actual_cost_usd > v_usage.reserved_usd then
    raise exception 'invalid_budget_settlement' using errcode = 'P0001';
  end if;
  update ihear.api_usage
  set state = 'settled', actual_usd = p_actual_cost_usd,
      provider_request_id = p_provider_request_id, settled_at = now()
  where id = p_usage_id;
end;
$$;

create function ihear.release_api_budget(p_usage_id uuid)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_usage ihear.api_usage%rowtype;
begin
  select u.* into v_usage from ihear.api_usage u
  cross join ihear.budget_accounts b
  where u.id = p_usage_id
  for update of b, u;
  if not found then raise exception 'budget_reservation_not_found' using errcode = 'P0002'; end if;
  if v_usage.state = 'released' then return; end if;
  if v_usage.state <> 'reserved' then raise exception 'budget_reservation_not_releasable' using errcode = 'P0001'; end if;
  update ihear.api_usage set state = 'released', settled_at = now() where id = p_usage_id;
end;
$$;

create function ihear.persist_interpretation(
  p_job_id uuid,
  p_worker_id text,
  p_analysis_id uuid,
  p_model text,
  p_prompt_version text,
  p_status text,
  p_result jsonb,
  p_provenance jsonb,
  p_error text default null,
  p_api_usage_id uuid default null
)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
  v_interpretation_id uuid;
begin
  select * into v_job from ihear.jobs
  where id = p_job_id and kind = 'event_analysis' and status = 'running'
    and worker_id = p_worker_id and lease_expires_at > now()
  for update;
  if not found then raise exception 'job_lease_not_owned' using errcode = 'P0001'; end if;
  if not exists (
    select 1 from ihear.analyses where id = p_analysis_id and event_id = v_job.event_id
  ) then raise exception 'analysis_not_found' using errcode = 'P0002'; end if;

  insert into ihear.interpretations (
    workspace_id, patient_id, event_id, analysis_id, pipeline_version, model,
    prompt_version, status, result, provenance, error, api_usage_id
  ) values (
    v_job.workspace_id, v_job.patient_id, v_job.event_id, p_analysis_id, v_job.version,
    p_model, p_prompt_version, p_status, p_result, coalesce(p_provenance, '{}'::jsonb),
    p_error, p_api_usage_id
  )
  on conflict (analysis_id, model, prompt_version) do update
    set status = excluded.status, result = excluded.result, provenance = excluded.provenance,
        error = excluded.error, api_usage_id = excluded.api_usage_id
  returning id into v_interpretation_id;
  return v_interpretation_id;
end;
$$;

create function ihear.persist_report_result(
  p_job_id uuid,
  p_worker_id text,
  p_status text,
  p_object_path text default null,
  p_error text default null
)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
begin
  select * into v_job from ihear.jobs
  where id = p_job_id and kind = 'report' and status = 'running'
    and worker_id = p_worker_id and lease_expires_at > now()
  for update;
  if not found then raise exception 'job_lease_not_owned' using errcode = 'P0001'; end if;
  if p_status = 'ready' and p_object_path is distinct from (
    v_job.workspace_id::text || '/' || v_job.patient_id::text || '/' || v_job.report_id::text || '.pdf'
  ) then raise exception 'invalid_report_object_path' using errcode = 'P0001'; end if;
  update ihear.reports
  set status = p_status, object_path = p_object_path, error = p_error
  where id = v_job.report_id;
end;
$$;

create function ihear.finish_job(p_job_id uuid, p_worker_id text, p_result jsonb default '{}'::jsonb)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
begin
  select * into v_job from ihear.jobs
  where id = p_job_id and status = 'running' and worker_id = p_worker_id for update;
  if not found then raise exception 'job_lease_not_owned' using errcode = 'P0001'; end if;
  if v_job.kind = 'event_analysis' then
    update ihear.events set status = 'ready', error = null where id = v_job.event_id;
  end if;
  update ihear.jobs
  set status = 'succeeded', result = coalesce(p_result, '{}'::jsonb),
      lease_expires_at = null, worker_id = null
  where id = v_job.id;
  if v_job.queue_message_id is not null then perform pgmq.archive('ihear_jobs', v_job.queue_message_id); end if;
end;
$$;

create function ihear.retry_job(p_job_id uuid, p_worker_id text, p_error text, p_delay_seconds integer default 30)
returns text
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
  v_message_id bigint;
begin
  if p_delay_seconds < 0 or p_delay_seconds > 86400 then raise exception 'invalid_retry_delay' using errcode = '22023'; end if;
  select * into v_job from ihear.jobs
  where id = p_job_id and status = 'running' and worker_id = p_worker_id for update;
  if not found then raise exception 'job_lease_not_owned' using errcode = 'P0001'; end if;
  if v_job.queue_message_id is not null then perform pgmq.archive('ihear_jobs', v_job.queue_message_id); end if;

  if v_job.attempt_count >= v_job.max_attempts then
    update ihear.jobs set status = 'failed', last_error = p_error,
      lease_expires_at = null, worker_id = null where id = v_job.id;
    if v_job.event_id is not null then update ihear.events set status = 'failed', error = p_error where id = v_job.event_id; end if;
    if v_job.report_id is not null then update ihear.reports set status = 'failed', error = p_error where id = v_job.report_id; end if;
    return 'failed';
  end if;

  select pgmq.send(
    'ihear_jobs',
    jsonb_build_object('jobId', v_job.id, 'kind', v_job.kind, 'version', v_job.version),
    p_delay_seconds
  ) into v_message_id;
  update ihear.jobs set status = 'retry', last_error = p_error,
    available_at = now() + make_interval(secs => p_delay_seconds), queue_message_id = v_message_id,
    lease_expires_at = null, worker_id = null where id = v_job.id;
  return 'retry';
end;
$$;

create function ihear.fail_job(p_job_id uuid, p_worker_id text, p_error text)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
begin
  select * into v_job from ihear.jobs
  where id = p_job_id and status = 'running' and worker_id = p_worker_id for update;
  if not found then raise exception 'job_lease_not_owned' using errcode = 'P0001'; end if;
  update ihear.jobs set status = 'failed', last_error = p_error,
    lease_expires_at = null, worker_id = null where id = v_job.id;
  if v_job.event_id is not null then update ihear.events set status = 'failed', error = p_error where id = v_job.event_id; end if;
  if v_job.report_id is not null then update ihear.reports set status = 'failed', error = p_error where id = v_job.report_id; end if;
  if v_job.queue_message_id is not null then perform pgmq.archive('ihear_jobs', v_job.queue_message_id); end if;
end;
$$;

create function ihear.search_patients(
  p_workspace_id uuid,
  p_query text default null,
  p_status text default null,
  p_difficulty text default null,
  p_follow_up text default null
)
returns table (
  id uuid, workspace_id uuid, display_name text, audiogram jsonb, aids jsonb,
  follow_up_date date, note text, timezone text, profile_version integer,
  report_revision bigint, created_at timestamptz, updated_at timestamptz,
  event_count bigint, latest_status text
)
language sql
stable
set search_path = ''
as $$
  select p.id, p.workspace_id, p.display_name, p.audiogram, p.aids,
    p.follow_up_date, p.note, p.timezone, p.profile_version, p.report_revision,
    p.created_at, p.updated_at,
    count(e.id) as event_count,
    (array_agg(e.status order by e.captured_at desc) filter (where e.id is not null))[1] as latest_status
  from ihear.patients p
  left join ihear.events e on e.patient_id = p.id and e.workspace_id = p.workspace_id
  where p.workspace_id = p_workspace_id
    and (
      nullif(btrim(coalesce(p_query, '')), '') is null
      or p.search_vector @@ websearch_to_tsquery('simple', p_query)
      or exists (
        select 1 from ihear.events se
        where se.patient_id = p.id and se.workspace_id = p.workspace_id
          and se.search_vector @@ websearch_to_tsquery('simple', p_query)
      )
    )
    and (p_status is null or exists (
      select 1 from ihear.events fs where fs.patient_id = p.id and fs.workspace_id = p.workspace_id and fs.status = p_status
    ))
    and (p_difficulty is null or exists (
      select 1 from ihear.events fd where fd.patient_id = p.id and fd.workspace_id = p.workspace_id and fd.difficulty = p_difficulty
    ))
    and (
      p_follow_up is null
      or (p_follow_up = 'overdue' and p.follow_up_date < current_date)
      or (p_follow_up = 'today' and p.follow_up_date = current_date)
      or (p_follow_up = 'upcoming' and p.follow_up_date > current_date)
      or (p_follow_up ~ '^\\d{4}-\\d{2}-\\d{2}$' and p.follow_up_date = p_follow_up::date)
    )
  group by p.id
  order by p.updated_at desc;
$$;

select pgmq.create('ihear_jobs');

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('ihear-audio', 'ihear-audio', false, 2202000, array['audio/wav', 'audio/x-wav']),
  ('ihear-reports', 'ihear-reports', false, 10485760, array['application/pdf'])
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

do $$
declare
  v_table regclass;
begin
  foreach v_table in array array[
    'ihear.workspaces'::regclass, 'ihear.capabilities'::regclass, 'ihear.patients'::regclass,
    'ihear.pairing_tokens'::regclass, 'ihear.events'::regclass, 'ihear.analyses'::regclass,
    'ihear.interpretations'::regclass, 'ihear.reports'::regclass, 'ihear.jobs'::regclass,
    'ihear.budget_accounts'::regclass, 'ihear.api_usage'::regclass,
    'ihear.rate_limit_counters'::regclass
  ] loop
    execute format('alter table %s enable row level security', v_table);
    execute format('alter table %s force row level security', v_table);
    execute format('revoke all on table %s from public, anon, authenticated', v_table);
    execute format('grant all on table %s to service_role', v_table);
  end loop;
end;
$$;

revoke all on all functions in schema ihear from public, anon, authenticated;
grant execute on all functions in schema ihear to service_role;
grant usage, select on all sequences in schema ihear to service_role;

alter default privileges in schema ihear revoke all on tables from public, anon, authenticated;
alter default privileges in schema ihear revoke execute on functions from public, anon, authenticated;
alter default privileges in schema ihear grant all on tables to service_role;
alter default privileges in schema ihear grant execute on functions to service_role;
