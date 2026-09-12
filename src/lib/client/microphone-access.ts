export type MicrophonePermissionState = PermissionState | "unsupported";

const CONSENT_PREFIX = "ihear-microphone-consent-v1:";

type ConsentStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function consentKey(patientId: string): string {
  return CONSENT_PREFIX + patientId;
}

export function hasMicrophoneConsent(
  patientId: string,
  storage: ConsentStorage = window.localStorage,
): boolean {
  try {
    return storage.getItem(consentKey(patientId)) === "yes";
  } catch {
    return false;
  }
}

export function rememberMicrophoneConsent(
  patientId: string,
  storage: ConsentStorage = window.localStorage,
): void {
  try {
    storage.setItem(consentKey(patientId), "yes");
  } catch {}
}

export function forgetMicrophoneConsent(
  patientId: string,
  storage: ConsentStorage = window.localStorage,
): void {
  try {
    storage.removeItem(consentKey(patientId));
  } catch {}
}

export function shouldAutoAcquireMicrophone(
  consented: boolean,
  permission: MicrophonePermissionState,
  visibility: DocumentVisibilityState,
): boolean {
  return (
    consented &&
    (permission === "granted" || permission === "unsupported") &&
    visibility === "visible"
  );
}

export async function queryMicrophonePermission(): Promise<
  PermissionStatus | null
> {
  if (!navigator.permissions?.query) return null;
  try {
    return await navigator.permissions.query({
      name: "microphone" as PermissionName,
    });
  } catch {
    return null;
  }
}
