create function ihear.renew_job_lease(p_job_id uuid, p_worker_id text, p_lease_seconds integer default 180)
returns boolean
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
  v_message pgmq.message_record;
begin
  if nullif(btrim(p_worker_id), '') is null or p_lease_seconds < 10 or p_lease_seconds > 1800 then
    raise exception 'invalid_job_lease' using errcode = '22023';
  end if;
  select * into v_job from ihear.jobs
  where id = p_job_id and status = 'running' and worker_id = p_worker_id
    and lease_expires_at > now()
  for update;
  if not found then return false; end if;
  if v_job.queue_message_id is null then raise exception 'job_queue_message_not_found' using errcode = 'P0002'; end if;
  select * into v_message from pgmq.set_vt('ihear_jobs', v_job.queue_message_id, p_lease_seconds);
  if v_message.msg_id is null then raise exception 'job_queue_message_not_found' using errcode = 'P0002'; end if;
  update ihear.jobs
  set lease_expires_at = now() + make_interval(secs => p_lease_seconds)
  where id = v_job.id;
  return true;
end;
$$;

create or replace function ihear.persist_report_result(
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
  v_input_revision bigint;
  v_current_revision bigint;
begin
  select * into v_job from ihear.jobs
  where id = p_job_id and kind = 'report' and status = 'running'
    and worker_id = p_worker_id and lease_expires_at > now()
  for update;
  if not found then raise exception 'job_lease_not_owned' using errcode = 'P0001'; end if;
  select r.input_revision, p.report_revision into v_input_revision, v_current_revision
  from ihear.reports r
  join ihear.patients p on p.id = r.patient_id and p.workspace_id = r.workspace_id
  where r.id = v_job.report_id
  for update of r, p;
  if v_input_revision is distinct from v_current_revision then
    raise exception 'report_input_stale' using errcode = 'P0001';
  end if;
  if p_status = 'ready' and p_object_path is distinct from (
    v_job.workspace_id::text || '/' || v_job.patient_id::text || '/' || v_job.report_id::text || '.pdf'
  ) then raise exception 'invalid_report_object_path' using errcode = 'P0001'; end if;
  update ihear.reports
  set status = p_status, object_path = p_object_path, error = p_error
  where id = v_job.report_id;
end;
$$;

create or replace function ihear.finish_job(p_job_id uuid, p_worker_id text, p_result jsonb default '{}'::jsonb)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
begin
  select * into v_job from ihear.jobs
  where id = p_job_id and status = 'running' and worker_id = p_worker_id
    and lease_expires_at > now() for update;
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

create or replace function ihear.retry_job(p_job_id uuid, p_worker_id text, p_error text, p_delay_seconds integer default 30)
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
  where id = p_job_id and status = 'running' and worker_id = p_worker_id
    and lease_expires_at > now() for update;
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

create or replace function ihear.fail_job(p_job_id uuid, p_worker_id text, p_error text)
returns void
language plpgsql
set search_path = ''
as $$
declare
  v_job ihear.jobs%rowtype;
begin
  select * into v_job from ihear.jobs
  where id = p_job_id and status = 'running' and worker_id = p_worker_id
    and lease_expires_at > now() for update;
  if not found then raise exception 'job_lease_not_owned' using errcode = 'P0001'; end if;
  update ihear.jobs set status = 'failed', last_error = p_error,
    lease_expires_at = null, worker_id = null where id = v_job.id;
  if v_job.event_id is not null then update ihear.events set status = 'failed', error = p_error where id = v_job.event_id; end if;
  if v_job.report_id is not null then update ihear.reports set status = 'failed', error = p_error where id = v_job.report_id; end if;
  if v_job.queue_message_id is not null then perform pgmq.archive('ihear_jobs', v_job.queue_message_id); end if;
end;
$$;

revoke all on function ihear.renew_job_lease(uuid, text, integer) from public, anon, authenticated;
grant execute on function ihear.renew_job_lease(uuid, text, integer) to service_role;
