-- New PDF cache identity; existing report rows and admission limits remain unchanged.
set lock_timeout = '5s';
set statement_timeout = '30s';

alter table ihear.reports alter column report_version set default 3;

create or replace function ihear.ensure_report_job(
  p_workspace_id uuid,
  p_patient_id uuid,
  p_report_version integer default 3
)
returns jsonb
language sql
set search_path = ''
as $$
  select ihear.ensure_report_job_internal(
    p_workspace_id, p_patient_id, p_report_version, true
  );
$$;

create or replace function ihear.ensure_scheduled_report_job(
  p_workspace_id uuid,
  p_patient_id uuid,
  p_report_version integer default 3
)
returns jsonb
language sql
set search_path = ''
as $$
  select ihear.ensure_report_job_internal(
    p_workspace_id, p_patient_id, p_report_version, false
  );
$$;

-- CREATE OR REPLACE retains the existing function identity and privileges.
reset lock_timeout;
reset statement_timeout;
