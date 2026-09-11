alter table ihear.reports alter column report_version set default 2;

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
