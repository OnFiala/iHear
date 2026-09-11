create or replace function ihear.claim_job(
  p_job_id uuid,
  p_worker_id text,
  p_lease_seconds integer default 180
)
returns setof ihear.jobs
language plpgsql
set search_path = ''
as $$
begin
  if nullif(btrim(p_worker_id), '') is null
    or p_worker_id is distinct from btrim(p_worker_id)
    or p_lease_seconds < 10
    or p_lease_seconds > 1800
  then
    raise exception 'invalid_job_lease' using errcode = '22023';
  end if;

  begin
    perform p_worker_id::uuid;
  exception
    when invalid_text_representation then
      raise exception 'invalid_job_lease' using errcode = '22023';
  end;

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
    v_job.workspace_id::text || '/' || v_job.patient_id::text || '/' ||
    v_job.report_id::text || '/' || v_job.worker_id || '.pdf'
  ) then
    raise exception 'invalid_report_object_path' using errcode = 'P0001';
  end if;

  update ihear.reports
  set status = p_status, object_path = p_object_path, error = p_error
  where id = v_job.report_id;
end;
$$;

revoke all on function ihear.claim_job(uuid, text, integer) from public, anon, authenticated;
revoke all on function ihear.persist_report_result(uuid, text, text, text, text) from public, anon, authenticated;
grant execute on function ihear.claim_job(uuid, text, integer) to service_role;
grant execute on function ihear.persist_report_result(uuid, text, text, text, text) to service_role;
