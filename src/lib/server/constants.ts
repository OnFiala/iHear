import "server-only";

function fixedName(variable: string, expected: string): string {
  const value = process.env[variable] ?? expected;
  if (!/^[a-z0-9][a-z0-9_-]{2,62}$/.test(value))
    throw new Error(`${variable} has an invalid name.`);
  if (value !== expected)
    throw new Error(
      `${variable}=${value} does not match the applied database migration (${expected}).`,
    );
  return value;
}

function fixedVersion(variable: string, expected: number): number {
  const raw = process.env[variable] ?? String(expected);
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < 1)
    throw new Error(`${variable} must be a positive integer.`);
  if (value !== expected)
    throw new Error(
      `${variable}=${value} does not match the applied database migration (${expected}).`,
    );
  return value;
}

export const AUDIO_BUCKET = fixedName("AUDIO_BUCKET", "ihear-audio");
export const REPORT_BUCKET = fixedName("REPORT_BUCKET", "ihear-reports");
export const QUEUE_NAME = fixedName("QUEUE_NAME", "ihear_jobs");
export const PIPELINE_VERSION = fixedVersion("PIPELINE_VERSION", 1);
export const REPORT_VERSION = fixedVersion("REPORT_VERSION", 3);
export const MAX_AUDIO_BYTES = 2_202_000;
export const MAX_AUDIO_SECONDS = 10.1;
export const OWNER_COOKIE = "ihear_owner";
export const PATIENT_COOKIE = "ihear_patient";
export const PAIRING_TTL_MS = 24 * 60 * 60 * 1000;
export const PATIENT_SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000;
