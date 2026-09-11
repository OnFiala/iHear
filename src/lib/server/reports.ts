import 'server-only';
import { query } from './db';
import { HttpError } from './http';
import { REPORT_VERSION } from './constants';

type ReportRow = { id: string; status: string; object_path: string | null };

export async function ensureReport(workspaceId: string, patientId: string): Promise<{ status: string; reportId: string }> {
  const rows = await query<{ result: { status: string; reportId: string } }>(
    'select ihear.ensure_report_job($1, $2, $3) as result',
    [workspaceId, patientId, REPORT_VERSION],
  );
  return rows[0].result;
}

export async function currentReport(workspaceId: string, patientId: string): Promise<{ status: string; reportId?: string; url?: string }> {
  const rows = await query<ReportRow>(`
    select r.id, r.status, r.object_path
    from ihear.patients p
    left join ihear.reports r on r.patient_id = p.id and r.workspace_id = p.workspace_id
      and r.input_revision = p.report_revision and r.report_version = $3
    where p.id = $1 and p.workspace_id = $2
    order by r.created_at desc nulls last limit 1
  `, [patientId, workspaceId, REPORT_VERSION]);
  if (!rows[0]) throw new HttpError(404, 'Patient not found.');
  if (!rows[0].id) return { status: 'not_requested' };
  return {
    status: rows[0].status,
    reportId: rows[0].id,
    ...(rows[0].status === 'ready' ? { url: `/api/patients/${patientId}/report/download?reportId=${rows[0].id}` } : {}),
  };
}

export async function reportObjectPath(workspaceId: string, patientId: string, reportId: string): Promise<string> {
  const rows = await query<ReportRow>(`
    select id, status, object_path from ihear.reports
    where id = $1 and workspace_id = $2 and patient_id = $3
  `, [reportId, workspaceId, patientId]);
  if (!rows[0] || rows[0].status !== 'ready' || !rows[0].object_path) throw new HttpError(404, 'Report not found.');
  return rows[0].object_path;
}
