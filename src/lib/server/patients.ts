import "server-only";
import type { PoolClient } from "pg";
import type { ListeningEvent, Patient, ProfileInput } from "@/lib/types";
import { query } from "./db";
import { HttpError } from "./http";
import { EVENT_SELECT, eventFromRow, patientFromRow } from "./records";

type Row = Record<string, unknown>;

export async function listPatients(
  workspaceId: string,
  filters: {
    q?: string;
    status?: string;
    difficulty?: string;
    followUp?: string;
  },
): Promise<Patient[]> {
  const rows = await query<Row>(
    "select * from ihear.search_patients($1, $2, $3, $4, $5)",
    [
      workspaceId,
      filters.q || null,
      filters.status || null,
      filters.difficulty || null,
      filters.followUp || null,
    ],
  );
  return rows.map(patientFromRow);
}

export async function createPatient(
  workspaceId: string,
  profile: ProfileInput,
): Promise<Patient> {
  const rows = await query<Row>(
    `
    select * from ihear.create_patient($1, $2, $3, $4, $5, $6, $7)
  `,
    [
      workspaceId,
      profile.displayName,
      profile.audiogram,
      profile.aids,
      profile.followUpDate,
      profile.note,
      profile.timezone,
    ],
  );
  return patientFromRow(rows[0]);
}

export async function getPatient(
  workspaceId: string,
  patientId: string,
  client?: PoolClient,
): Promise<Patient> {
  const result = client
    ? (
        await client.query<Row>(
          "select * from ihear.patients where id = $1 and workspace_id = $2",
          [patientId, workspaceId],
        )
      ).rows
    : await query<Row>(
        "select * from ihear.patients where id = $1 and workspace_id = $2",
        [patientId, workspaceId],
      );
  if (!result[0]) throw new HttpError(404, "Patient not found.");
  return patientFromRow(result[0]);
}

export async function updatePatient(
  workspaceId: string,
  patientId: string,
  profile: ProfileInput,
): Promise<Patient> {
  const rows = await query<Row>(
    `
    select * from ihear.update_patient_profile($2, $1, $3, $4, $5, $6, $7, $8)
  `,
    [
      patientId,
      workspaceId,
      profile.displayName,
      profile.audiogram,
      profile.aids,
      profile.followUpDate,
      profile.note,
      profile.timezone,
    ],
  );
  if (!rows[0]) throw new HttpError(404, "Patient not found.");
  return patientFromRow(rows[0]);
}

export async function listEvents(
  workspaceId: string,
  patientId: string,
): Promise<ListeningEvent[]> {
  const rows = await query<Row>(
    `${EVENT_SELECT}
    where e.workspace_id = $1 and e.patient_id = $2
    order by e.captured_at desc`,
    [workspaceId, patientId],
  );
  return rows.map(eventFromRow);
}

export async function getEvent(
  workspaceId: string,
  patientId: string,
  eventId: string,
): Promise<ListeningEvent> {
  const rows = await query<Row>(
    `${EVENT_SELECT}
    where e.id = $1 and e.workspace_id = $2 and e.patient_id = $3`,
    [eventId, workspaceId, patientId],
  );
  if (!rows[0]) throw new HttpError(404, "Listening event not found.");
  return eventFromRow(rows[0]);
}
