import "server-only";
import type { ListeningEvent, Patient, ProfileInput } from "@/lib/types";

type Row = Record<string, unknown>;

function iso(value: unknown): string {
  return value instanceof Date ? value.toISOString() : String(value);
}

// PostgreSQL DATE is a calendar day; node-postgres parses it at local midnight.
// Converting that value to UTC can move a follow-up to the preceding day.
function calendarDate(value: unknown): string {
  if (!(value instanceof Date)) return String(value).slice(0, 10);
  return [value.getFullYear(), String(value.getMonth() + 1).padStart(2, "0"), String(value.getDate()).padStart(2, "0")].join("-");
}

export function patientFromRow(row: Row): Patient {
  return {
    id: String(row.id),
    workspaceId: String(row.workspace_id),
    displayName: String(row.display_name),
    audiogram: row.audiogram as ProfileInput["audiogram"],
    aids: row.aids as ProfileInput["aids"],
    followUpDate: calendarDate(row.follow_up_date),
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
          promptVersion: String(row.interpretation_prompt_version ?? "ihear-event-v1"),
          model: String(row.interpretation_model ?? "gpt-6-astra"),
          result: (row.interpretation_result ?? null) as NonNullable<
            ListeningEvent["interpretation"]
          >["result"],
        }
      : null,
    error:
      row.error === null || row.error === undefined ? null : String(row.error),
  };
}

export function patientEvent(event: ListeningEvent, currentAids: ProfileInput["aids"]): ListeningEvent {
  const interpretation = event.interpretation;
  if (!interpretation?.result) return { ...event, currentAids };
  const result = interpretation.result;
  return {
    ...event,
    currentAids,
    interpretation: {
      ...interpretation,
      result: {
        patient_summary: result.patient_summary,
        tip_ids: result.tip_ids,
        device_action_ids: result.device_action_ids,
      },
    },
  };
}

export const EVENT_SELECT = `
  select e.id, e.patient_id, e.kind, e.difficulty, e.environment, e.captured_at,
    e.created_at, e.status, e.capture, e.profile_snapshot, e.error,
    a.result as analysis_result,
    i.status as interpretation_status, i.result as interpretation_result,
    i.prompt_version as interpretation_prompt_version, i.model as interpretation_model
  from ihear.events e
  left join lateral (
    select id, result from ihear.analyses
    where event_id = e.id and pipeline_version = e.pipeline_version and status = 'ready'
    order by created_at desc, id desc limit 1
  ) a on true
  left join lateral (
    select status, result, prompt_version, model from ihear.interpretations
    where event_id = e.id and analysis_id = a.id and model = 'gpt-6-astra'
      and prompt_version in ('ihear-event-v1', 'ihear-event-v2')
    order by case prompt_version when 'ihear-event-v2' then 2 else 1 end desc,
      created_at desc, id desc limit 1
  ) i on true
`;
