-- Finite, conservative ceilings for the public single-host demonstration.
-- Existing rows are never deleted; once a ceiling is reached, new growth is refused.
create table ihear.sandbox_limits (
  singleton boolean primary key default true check (singleton),
  max_workspaces integer not null default 500 check (max_workspaces > 0),
  max_patients_global integer not null default 5000 check (max_patients_global > 0),
  max_patients_workspace integer not null default 100 check (max_patients_workspace > 0),
  max_capabilities_global integer not null default 50000 check (max_capabilities_global > 0),
  max_capabilities_patient integer not null default 50 check (max_capabilities_patient > 0),
  max_pairing_tokens_global integer not null default 25000 check (max_pairing_tokens_global > 0),
  max_pairing_tokens_workspace integer not null default 500 check (max_pairing_tokens_workspace > 0),
  max_pairing_tokens_patient integer not null default 50 check (max_pairing_tokens_patient > 0),
  max_events_global integer not null default 50000 check (max_events_global > 0),
  max_events_workspace integer not null default 5000 check (max_events_workspace > 0),
  max_reports_global integer not null default 20000 check (max_reports_global > 0),
  max_reports_workspace integer not null default 2000 check (max_reports_workspace > 0),
  max_reports_patient integer not null default 100 check (max_reports_patient > 0),
  max_jobs_global integer not null default 70000 check (max_jobs_global > 0),
  max_active_jobs_global integer not null default 200 check (max_active_jobs_global > 0),
  max_pending_reports_global integer not null default 50 check (max_pending_reports_global > 0),
  -- The scheduler may enqueue one 50-report batch in a transaction.
  max_pending_reports_workspace integer not null default 50 check (max_pending_reports_workspace > 0)
);

insert into ihear.sandbox_limits (singleton) values (true);

alter table ihear.sandbox_limits enable row level security;
alter table ihear.sandbox_limits force row level security;
revoke all on table ihear.sandbox_limits from public, anon, authenticated;
grant all on table ihear.sandbox_limits to service_role;

create function ihear.enforce_sandbox_retained_capacity()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_limits ihear.sandbox_limits%rowtype;
  v_count bigint;
  v_subject_hash bytea;
begin
  -- Every retained-row ceiling shares one transaction lock, making count + insert
  -- admission race-safe across concurrent public requests.
  perform pg_advisory_xact_lock(hashtextextended('ihear:sandbox:retained-capacity', 0));
  select * into strict v_limits from ihear.sandbox_limits where singleton;

  case tg_table_name
    when 'workspaces' then
      select count(*) into v_count from ihear.workspaces;
      if v_count >= v_limits.max_workspaces then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
    when 'patients' then
      select count(*) into v_count from ihear.patients;
      if v_count >= v_limits.max_patients_global then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      select count(*) into v_count from ihear.patients where workspace_id = new.workspace_id;
      if v_count >= v_limits.max_patients_workspace then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
    when 'capabilities' then
      select count(*) into v_count from ihear.capabilities;
      if v_count >= v_limits.max_capabilities_global then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      if new.kind = 'patient' then
        select count(*) into v_count from ihear.capabilities
        where workspace_id = new.workspace_id and patient_id = new.patient_id and kind = 'patient';
        if v_count >= v_limits.max_capabilities_patient then
          raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
        end if;
      end if;
    when 'pairing_tokens' then
      v_subject_hash := extensions.digest(new.workspace_id::text || ':' || new.patient_id::text, 'sha256');
      perform ihear.consume_rate_limit('pairing_patient_hour', v_subject_hash, 12, 3600);
      perform ihear.consume_rate_limit(
        'pairing_workspace_hour', extensions.digest(new.workspace_id::text, 'sha256'), 120, 3600
      );
      perform ihear.consume_rate_limit(
        'pairing_global_hour', extensions.digest('ihear-pairing-global', 'sha256'), 500, 3600
      );
      select count(*) into v_count from ihear.pairing_tokens;
      if v_count >= v_limits.max_pairing_tokens_global then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      select count(*) into v_count from ihear.pairing_tokens where workspace_id = new.workspace_id;
      if v_count >= v_limits.max_pairing_tokens_workspace then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      select count(*) into v_count from ihear.pairing_tokens
      where workspace_id = new.workspace_id and patient_id = new.patient_id;
      if v_count >= v_limits.max_pairing_tokens_patient then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
    when 'events' then
      select count(*) into v_count from ihear.events;
      if v_count >= v_limits.max_events_global then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      select count(*) into v_count from ihear.events where workspace_id = new.workspace_id;
      if v_count >= v_limits.max_events_workspace then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      if new.status = 'uploading' then
        select
          (select count(*) from ihear.jobs where status in ('queued', 'running', 'retry'))
          + (select count(*) from ihear.events where status = 'uploading')
        into v_count;
        if v_count >= v_limits.max_active_jobs_global then
          raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
        end if;
      end if;
    when 'reports' then
      select count(*) into v_count from ihear.reports;
      if v_count >= v_limits.max_reports_global then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      select count(*) into v_count from ihear.reports where workspace_id = new.workspace_id;
      if v_count >= v_limits.max_reports_workspace then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      select count(*) into v_count from ihear.reports
      where workspace_id = new.workspace_id and patient_id = new.patient_id;
      if v_count >= v_limits.max_reports_patient then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
    when 'jobs' then
      select count(*) into v_count from ihear.jobs;
      if v_count >= v_limits.max_jobs_global then
        raise exception 'retained_capacity_exceeded' using errcode = 'P0001';
      end if;
      if new.status in ('queued', 'running', 'retry') then
        select
          (select count(*) from ihear.jobs where status in ('queued', 'running', 'retry'))
          + (select count(*) from ihear.events where status = 'uploading')
        into v_count;
        -- Finalizing an uploading event replaces its reserved upload slot with
        -- one job slot, so do not count that same event twice.
        if new.kind = 'event_analysis' and exists (
          select 1 from ihear.events where id = new.event_id and status = 'uploading'
        ) then
          v_count := v_count - 1;
        end if;
        if v_count >= v_limits.max_active_jobs_global then
          raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
        end if;
      end if;
      if new.kind = 'report' and new.status in ('queued', 'running', 'retry') then
        select count(*) into v_count from ihear.jobs
        where kind = 'report' and status in ('queued', 'running', 'retry');
        if v_count >= v_limits.max_pending_reports_global then
          raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
        end if;
        select count(*) into v_count from ihear.jobs
        where workspace_id = new.workspace_id and kind = 'report'
          and status in ('queued', 'running', 'retry');
        if v_count >= v_limits.max_pending_reports_workspace then
          raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
        end if;
      end if;
    else
      raise exception 'invalid_sandbox_capacity_resource' using errcode = '22023';
  end case;
  return new;
end;
$$;

create trigger sandbox_workspace_capacity_trigger before insert on ihear.workspaces
for each row execute function ihear.enforce_sandbox_retained_capacity();
create trigger sandbox_patient_capacity_trigger before insert on ihear.patients
for each row execute function ihear.enforce_sandbox_retained_capacity();
create trigger sandbox_capability_capacity_trigger before insert on ihear.capabilities
for each row execute function ihear.enforce_sandbox_retained_capacity();
create trigger sandbox_pairing_capacity_trigger before insert on ihear.pairing_tokens
for each row execute function ihear.enforce_sandbox_retained_capacity();
create trigger sandbox_event_capacity_trigger before insert on ihear.events
for each row execute function ihear.enforce_sandbox_retained_capacity();
create trigger sandbox_report_capacity_trigger before insert on ihear.reports
for each row execute function ihear.enforce_sandbox_retained_capacity();
create trigger sandbox_job_capacity_trigger before insert on ihear.jobs
for each row execute function ihear.enforce_sandbox_retained_capacity();

create index pairing_tokens_workspace_patient_created_idx
on ihear.pairing_tokens (workspace_id, patient_id, created_at desc);

create function ihear.create_patient(
  p_workspace_id uuid,
  p_display_name text,
  p_audiogram jsonb,
  p_aids jsonb,
  p_follow_up_date date,
  p_note text,
  p_timezone text
)
returns setof ihear.patients
language plpgsql
set search_path = ''
as $$
begin
  if not exists (select 1 from ihear.workspaces where id = p_workspace_id) then
    raise exception 'workspace_not_found' using errcode = 'P0002';
  end if;
  perform ihear.consume_rate_limit(
    'patient_workspace_hour', extensions.digest(p_workspace_id::text, 'sha256'), 30, 3600
  );
  perform ihear.consume_rate_limit(
    'patient_global_hour', extensions.digest('ihear-patient-global', 'sha256'), 200, 3600
  );
  return query
  insert into ihear.patients (
    workspace_id, display_name, audiogram, aids, follow_up_date, note, timezone
  ) values (
    p_workspace_id, p_display_name, p_audiogram, p_aids, p_follow_up_date, p_note, p_timezone
  ) returning *;
end;
$$;

create function ihear.update_patient_profile(
  p_workspace_id uuid,
  p_patient_id uuid,
  p_display_name text,
  p_audiogram jsonb,
  p_aids jsonb,
  p_follow_up_date date,
  p_note text,
  p_timezone text
)
returns setof ihear.patients
language plpgsql
set search_path = ''
as $$
begin
  perform 1 from ihear.patients
  where id = p_patient_id and workspace_id = p_workspace_id for update;
  if not found then
    raise exception 'patient_not_found' using errcode = 'P0002';
  end if;
  perform ihear.consume_rate_limit(
    'profile_patient_hour',
    extensions.digest(p_workspace_id::text || ':' || p_patient_id::text, 'sha256'), 30, 3600
  );
  perform ihear.consume_rate_limit(
    'profile_workspace_hour', extensions.digest(p_workspace_id::text, 'sha256'), 300, 3600
  );
  return query
  update ihear.patients set
    display_name = p_display_name, audiogram = p_audiogram, aids = p_aids,
    follow_up_date = p_follow_up_date, note = p_note, timezone = p_timezone
  where id = p_patient_id and workspace_id = p_workspace_id
  returning *;
end;
$$;

create function ihear.admit_event_upload_request(
  p_ip_hash bytea,
  p_workspace_id uuid,
  p_patient_id uuid
)
returns void
language plpgsql
set search_path = ''
as $$
begin
  if not exists (
    select 1 from ihear.patients where id = p_patient_id and workspace_id = p_workspace_id
  ) then
    raise exception 'patient_not_found' using errcode = 'P0002';
  end if;
  perform ihear.consume_rate_limit('event_upload_ip_hour', p_ip_hash, 120, 3600);
  perform ihear.consume_rate_limit(
    'event_upload_patient_hour',
    extensions.digest(p_workspace_id::text || ':' || p_patient_id::text, 'sha256'), 60, 3600
  );
  perform ihear.consume_rate_limit(
    'event_upload_global_hour', extensions.digest('ihear-event-upload-global', 'sha256'), 1000, 3600
  );
end;
$$;

create or replace function ihear.assert_event_admission(
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
  v_max_active_jobs integer;
begin
  if not exists (select 1 from ihear.patients where id = p_patient_id and workspace_id = p_workspace_id) then
    raise exception 'patient_not_found' using errcode = 'P0002';
  end if;
  perform ihear.consume_rate_limit('event_ip_hour', p_ip_hash, 60, 3600);
  perform ihear.consume_rate_limit(
    'event_patient_hour', extensions.digest(p_workspace_id::text || ':' || p_patient_id::text, 'sha256'), 30, 3600
  );
  perform ihear.consume_rate_limit('event_global_hour', extensions.digest('ihear-event-global', 'sha256'), 500, 3600);
  perform pg_advisory_xact_lock(hashtextextended('ihear:sandbox:retained-capacity', 0));
  select max_active_jobs_global into strict v_max_active_jobs from ihear.sandbox_limits where singleton;
  select
    (select count(*) from ihear.jobs where status in ('queued', 'running', 'retry'))
    + (select count(*) from ihear.events where status = 'uploading')
  into v_active_jobs;
  if v_active_jobs >= v_max_active_jobs then
    raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
  end if;
end;
$$;

create or replace function ihear.ensure_report_job(
  p_workspace_id uuid,
  p_patient_id uuid,
  p_report_version integer default 2
)
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_patient ihear.patients%rowtype;
  v_report ihear.reports%rowtype;
  v_job ihear.jobs%rowtype;
  v_limits ihear.sandbox_limits%rowtype;
  v_count integer;
  v_message_id bigint;
begin
  select * into v_patient from ihear.patients
  where id = p_patient_id and workspace_id = p_workspace_id for update;
  if not found then
    raise exception 'patient_not_found' using errcode = 'P0002';
  end if;

  select * into v_report from ihear.reports
  where patient_id = p_patient_id and workspace_id = p_workspace_id
    and input_revision = v_patient.report_revision and report_version = p_report_version
  for update;

  if not found then
    -- A cached report is read-only and must remain idempotently accessible even
    -- when new report growth is saturated. Request quotas apply before new rows.
    perform ihear.consume_rate_limit(
      'report_request_patient_hour',
      extensions.digest(p_workspace_id::text || ':' || p_patient_id::text, 'sha256'), 60, 3600
    );
    perform ihear.consume_rate_limit(
      'report_request_global_hour', extensions.digest('ihear-report-request-global', 'sha256'), 600, 3600
    );
    perform ihear.consume_rate_limit(
      'report_growth_patient_hour',
      extensions.digest(p_workspace_id::text || ':' || p_patient_id::text, 'sha256'), 6, 3600
    );
    perform ihear.consume_rate_limit(
      'report_growth_workspace_hour', extensions.digest(p_workspace_id::text, 'sha256'), 60, 3600
    );
    perform ihear.consume_rate_limit(
      'report_growth_global_hour', extensions.digest('ihear-report-growth-global', 'sha256'), 200, 3600
    );
    perform pg_advisory_xact_lock(hashtextextended('ihear:sandbox:retained-capacity', 0));
    select * into strict v_limits from ihear.sandbox_limits where singleton;
    select count(*) into v_count from ihear.jobs
    where kind = 'report' and status in ('queued', 'running', 'retry');
    if v_count >= v_limits.max_pending_reports_global then
      raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
    end if;
    select count(*) into v_count from ihear.jobs
    where workspace_id = p_workspace_id and kind = 'report' and status in ('queued', 'running', 'retry');
    if v_count >= v_limits.max_pending_reports_workspace then
      raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
    end if;
    select count(*) into v_count from ihear.jobs where status in ('queued', 'running', 'retry');
    if v_count >= v_limits.max_active_jobs_global then
      raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
    end if;
    insert into ihear.reports (workspace_id, patient_id, input_revision, report_version)
    values (p_workspace_id, p_patient_id, v_patient.report_revision, p_report_version)
    returning * into v_report;
  end if;

  select * into v_job from ihear.jobs
  where report_id = v_report.id and kind = 'report' and version = p_report_version
  for update;
  if not found then
    -- Normally the report and job are created in one transaction. This also keeps
    -- repair of a legacy orphan report behind the same global queue ceiling.
    perform pg_advisory_xact_lock(hashtextextended('ihear:sandbox:retained-capacity', 0));
    select * into strict v_limits from ihear.sandbox_limits where singleton;
    select count(*) into v_count from ihear.jobs where status in ('queued', 'running', 'retry');
    if v_count >= v_limits.max_active_jobs_global then
      raise exception 'queue_capacity_exceeded' using errcode = 'P0001';
    end if;
    insert into ihear.jobs (workspace_id, patient_id, report_id, kind, version, payload)
    values (
      p_workspace_id, p_patient_id, v_report.id, 'report', p_report_version,
      jsonb_build_object('reportId', v_report.id, 'inputRevision', v_report.input_revision)
    ) returning * into v_job;
  end if;

  if v_job.queue_message_id is null and v_job.status in ('queued', 'retry') then
    select pgmq.send(
      'ihear_jobs', jsonb_build_object('jobId', v_job.id, 'kind', v_job.kind, 'version', v_job.version)
    ) into v_message_id;
    update ihear.jobs set queue_message_id = v_message_id where id = v_job.id;
  end if;

  return jsonb_build_object('status', v_report.status, 'reportId', v_report.id);
end;
$$;

revoke all on function ihear.enforce_sandbox_retained_capacity() from public, anon, authenticated;
revoke all on function ihear.create_patient(uuid, text, jsonb, jsonb, date, text, text) from public, anon, authenticated;
revoke all on function ihear.update_patient_profile(uuid, uuid, text, jsonb, jsonb, date, text, text) from public, anon, authenticated;
revoke all on function ihear.admit_event_upload_request(bytea, uuid, uuid) from public, anon, authenticated;
revoke all on function ihear.assert_event_admission(bytea, uuid, uuid) from public, anon, authenticated;
revoke all on function ihear.ensure_report_job(uuid, uuid, integer) from public, anon, authenticated;

grant execute on function ihear.create_patient(uuid, text, jsonb, jsonb, date, text, text) to service_role;
grant execute on function ihear.update_patient_profile(uuid, uuid, text, jsonb, jsonb, date, text, text) to service_role;
grant execute on function ihear.admit_event_upload_request(bytea, uuid, uuid) to service_role;
grant execute on function ihear.assert_event_admission(bytea, uuid, uuid) to service_role;
grant execute on function ihear.ensure_report_job(uuid, uuid, integer) to service_role;
