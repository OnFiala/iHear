import "server-only";
import type { NextRequest } from "next/server";
import type { Patient } from "@/lib/types";
import { query, transaction } from "./db";
import { HttpError } from "./http";
import { patientFromRow } from "./records";
import { hashCapability, randomCapability, requestIpHash } from "./security";
import { OWNER_COOKIE, PATIENT_COOKIE } from "./constants";

type CapabilityRow = Record<string, unknown> & {
  kind: "owner" | "patient";
  workspace_id: string;
  patient_id: string | null;
};

export type OwnerAuth = { kind: "owner"; workspaceId: string };
export type PatientAuth = {
  kind: "patient";
  workspaceId: string;
  patientId: string;
  patient: Patient;
};
export type SessionAuth = OwnerAuth | PatientAuth;

async function resolveCapability(
  request: NextRequest,
  cookieName: string,
  expectedKind: "owner" | "patient",
): Promise<SessionAuth | null> {
  const token = request.cookies.get(cookieName)?.value;
  if (!token || token.length > 128) return null;
  const rows = await query<CapabilityRow>(
    `
    select c.kind, c.workspace_id, c.patient_id,
      p.id, p.display_name, p.audiogram, p.aids, p.follow_up_date,
      p.note, p.timezone, p.created_at
    from ihear.capabilities c
    left join ihear.patients p on p.id = c.patient_id and p.workspace_id = c.workspace_id
    where c.token_hash = $1 and c.kind = $2 and c.revoked_at is null
      and (c.expires_at is null or c.expires_at > now())
    limit 1
  `,
    [hashCapability(token), expectedKind],
  );
  const row = rows[0];
  if (!row) return null;
  await query(
    "update ihear.capabilities set last_used_at = now() where token_hash = $1",
    [hashCapability(token)],
  );
  if (row.kind === "owner")
    return { kind: "owner", workspaceId: row.workspace_id };
  if (!row.patient_id || !row.id) return null;
  return {
    kind: "patient",
    workspaceId: row.workspace_id,
    patientId: row.patient_id,
    patient: patientFromRow(row),
  };
}

export async function resolveOwnerSession(
  request: NextRequest,
): Promise<OwnerAuth | null> {
  return (await resolveCapability(
    request,
    OWNER_COOKIE,
    "owner",
  )) as OwnerAuth | null;
}

export async function resolvePatientSession(
  request: NextRequest,
): Promise<PatientAuth | null> {
  return (await resolveCapability(
    request,
    PATIENT_COOKIE,
    "patient",
  )) as PatientAuth | null;
}

export async function resolveSession(
  request: NextRequest,
): Promise<SessionAuth | null> {
  return (
    (await resolvePatientSession(request)) ??
    (await resolveOwnerSession(request))
  );
}

export async function createOwnerSession(
  request: NextRequest,
): Promise<{ auth: OwnerAuth; token: string }> {
  const token = randomCapability();
  const workspaceId = await transaction(async (client) => {
    const result = await client.query<{ workspace_id: string }>(
      "select ihear.create_workspace_with_capability($1, $2) as workspace_id",
      [requestIpHash(request), hashCapability(token)],
    );
    return result.rows[0].workspace_id;
  });
  return { auth: { kind: "owner", workspaceId }, token };
}

export async function requireOwner(request: NextRequest): Promise<OwnerAuth> {
  const auth = await resolveOwnerSession(request);
  if (!auth) throw new HttpError(401, "Your workspace session is unavailable.");
  return auth;
}

export async function requirePatient(
  request: NextRequest,
): Promise<PatientAuth> {
  const auth = await resolvePatientSession(request);
  if (!auth) throw new HttpError(401, "Your patient session is unavailable.");
  return auth;
}
