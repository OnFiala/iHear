import "server-only";
import type { NextRequest } from "next/server";
import type { Pairing, Patient } from "@/lib/types";
import { transaction } from "./db";
import { HttpError } from "./http";
import { patientFromRow } from "./records";
import { PAIRING_TTL_MS, PATIENT_SESSION_TTL_MS } from "./constants";
import {
  displayPairingToken,
  hashCapability,
  normalizePairingToken,
  randomCapability,
  randomPairingToken,
} from "./security";

type Row = Record<string, unknown>;

export async function issuePairing(
  request: NextRequest,
  workspaceId: string,
  patientId: string,
): Promise<Pairing> {
  const token = randomPairingToken();
  const expiresAt = new Date(Date.now() + PAIRING_TTL_MS);
  await transaction(async (client) => {
    await client.query("select ihear.lock_sandbox_capacity()");
    const patient = await client.query(
      "select 1 from ihear.patients where id = $1 and workspace_id = $2 for update",
      [patientId, workspaceId],
    );
    if (!patient.rowCount) throw new HttpError(404, "Patient not found.");
    await client.query(
      "update ihear.pairing_tokens set revoked_at = now() where patient_id = $1 and workspace_id = $2 and revoked_at is null",
      [patientId, workspaceId],
    );
    await client.query(
      "update ihear.capabilities set revoked_at = now() where kind = 'patient' and patient_id = $1 and workspace_id = $2 and revoked_at is null",
      [patientId, workspaceId],
    );
    await client.query(
      "insert into ihear.pairing_tokens (workspace_id, patient_id, token_hash, expires_at) values ($1, $2, $3, $4)",
      [workspaceId, patientId, hashCapability(token), expiresAt],
    );
  });
  const origin = process.env.APP_PUBLIC_ORIGIN
    ? new URL(process.env.APP_PUBLIC_ORIGIN).origin
    : request.nextUrl.origin;
  return {
    url: `${origin}/pair/${token}`,
    code: displayPairingToken(token),
    expiresAt: expiresAt.toISOString(),
  };
}

export async function revokePairing(
  workspaceId: string,
  patientId: string,
): Promise<void> {
  await transaction(async (client) => {
    await client.query("select ihear.lock_sandbox_capacity()");
    const patient = await client.query(
      "select 1 from ihear.patients where id = $1 and workspace_id = $2 for update",
      [patientId, workspaceId],
    );
    if (!patient.rowCount) throw new HttpError(404, "Patient not found.");
    await client.query(
      "update ihear.pairing_tokens set revoked_at = now() where patient_id = $1 and workspace_id = $2 and revoked_at is null",
      [patientId, workspaceId],
    );
    await client.query(
      "update ihear.capabilities set revoked_at = now() where kind = 'patient' and patient_id = $1 and workspace_id = $2 and revoked_at is null",
      [patientId, workspaceId],
    );
  });
}

export async function previewPairing(
  rawToken: string,
): Promise<{ displayName: string; expiresAt: string }> {
  const token = normalizePairingToken(rawToken);
  return transaction(async (client) => {
    const result = await client.query<Row>(
      `
      select p.display_name, pt.expires_at
      from ihear.pairing_tokens pt
      join ihear.patients p on p.id = pt.patient_id and p.workspace_id = pt.workspace_id
      where pt.token_hash = $1 and pt.revoked_at is null and pt.expires_at > now()
      limit 1
    `,
      [hashCapability(token)],
    );
    if (!result.rows[0])
      throw new HttpError(404, "This pairing code is invalid or has expired.");
    return {
      displayName: String(result.rows[0].display_name),
      expiresAt: new Date(result.rows[0].expires_at as string).toISOString(),
    };
  });
}

export async function redeemPairing(
  rawToken: string,
): Promise<{ patient: Patient; capability: string; expiresAt: Date }> {
  const token = normalizePairingToken(rawToken);
  const capability = randomCapability();
  const expiresAt = new Date(Date.now() + PATIENT_SESSION_TTL_MS);
  const patient = await transaction(async (client) => {
    await client.query("select ihear.lock_sandbox_capacity()");
    const result = await client.query<Row>(
      `
      select pt.id as pairing_id, pt.workspace_id, pt.patient_id,
        p.id, p.display_name, p.audiogram, p.aids, p.follow_up_date, p.note, p.timezone, p.created_at
      from ihear.pairing_tokens pt
      join ihear.patients p on p.id = pt.patient_id and p.workspace_id = pt.workspace_id
      where pt.token_hash = $1 and pt.revoked_at is null and pt.expires_at > now()
      for update of pt
    `,
      [hashCapability(token)],
    );
    const row = result.rows[0];
    if (!row)
      throw new HttpError(404, "This pairing code is invalid or has expired.");
    await client.query(
      `
      insert into ihear.capabilities (workspace_id, patient_id, kind, token_hash, expires_at)
      values ($1, $2, 'patient', $3, $4)
    `,
      [row.workspace_id, row.patient_id, hashCapability(capability), expiresAt],
    );
    await client.query(
      "update ihear.pairing_tokens set last_redeemed_at = now(), redemption_count = redemption_count + 1 where id = $1",
      [row.pairing_id],
    );
    return patientFromRow(row);
  });
  return { patient, capability, expiresAt };
}
