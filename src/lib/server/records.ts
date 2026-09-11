import "server-only";
import type { ListeningEvent, Patient, ProfileInput } from "@/lib/types";

type Row = Record<string, unknown>;

function iso(value: unknown): string {
  return value instanceof Date ? value.toISOString() : String(value);
}

export function patientFromRow(row: Row): Patient {
  return {
    id: String(row.id),
    workspaceId: String(row.workspace_id),
    displayName: String(row.display_name),
    audiogram: row.audiogram as ProfileInput["audiogram"],
    aids: row.aids as ProfileInput["aids"],
    followUpDate: iso(row.follow_up_date).slice(0, 10),
    note: String(row.note ?? ""),
    timezone: String(row.timezone),
    createdAt: iso(row.created_at),
    ...(row.event_count !== undefined
      ? { eventCount: Number(row.event_count) }
      : {}),
    ...(row.latest_status ? { latestStatus: String(row.latest_status) } : {}),
  };
}

export function eventFromRow(row: Row): ListeningEvent {
  const interpretationStatus = row.interpretation_status;
  return {
    id: String(row.id),
    patientId: String(row.patient_id),
    kind: row.kind as ListeningEvent["kind"],
    difficulty: row.difficulty === null ? null : String(row.difficulty),
    environment: row.environment === null ? null : String(row.environment),
    capturedAt: iso(row.captured_at),
    createdAt: iso(row.created_at),
    status: String(row.status),
    capture: row.capture as Record<string, unknown>,
    profileSnapshot: row.profile_snapshot as ProfileInput,
    analysis: (row.analysis_result ?? null) as ListeningEvent["analysis"],
    interpretation: interpretationStatus
      ? {
          status: String(interpretationStatus),
          result: (row.interpretation_result ?? null) as NonNullable<
            ListeningEvent["interpretation"]
          >["result"],
        }
      : null,
    error:
      row.error === null || row.error === undefined ? null : String(row.error),
  };
}

export const EVENT_SELECT = `
  select e.id, e.patient_id, e.kind, e.difficulty, e.environment, e.captured_at,
    e.created_at, e.status, e.capture, e.profile_snapshot, e.error,
    a.result as analysis_result,
    i.status as interpretation_status, i.result as interpretation_result
  from ihear.events e
  left join lateral (
    select result from ihear.analyses
    where event_id = e.id and status = 'ready'
    order by pipeline_version desc limit 1
  ) a on true
  left join lateral (
    select status, result from ihear.interpretations
    where event_id = e.id
    order by created_at desc limit 1
  ) i on true
`;
