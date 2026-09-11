import { openDB } from "idb";
import { api } from "./api";
import type { CapturedAudio } from "./audio";
export type PendingEvent = {
  id: string;
  patientId: string;
  kind: "understood" | "difficult";
  difficulty: string | null;
  environment: string | null;
  capturedAt: string;
  capture: CapturedAudio["capture"];
  audio: Blob;
  state: "saved locally" | "uploading" | "failed";
  error?: string;
  needsAnswers?: boolean;
};
const db = () =>
  openDB("ihear-pending", 1, {
    upgrade(db) {
      db.createObjectStore("events", { keyPath: "id" });
    },
  });
export async function savePending(event: PendingEvent) {
  await (await db()).put("events", event);
}
export async function pendingFor(patientId: string): Promise<PendingEvent[]> {
  return (await (await db()).getAll("events")).filter(
    (x: PendingEvent) => x.patientId === patientId,
  );
}
export async function removePending(id: string) {
  await (await db()).delete("events", id);
}
let uploading = false;
export async function flushPending(patientId: string, onChange: () => void) {
  if (uploading || !navigator.onLine) return;
  uploading = true;
  try {
    for (const event of await pendingFor(patientId)) {
      if (event.needsAnswers) continue;
      await savePending({ ...event, state: "uploading" });
      onChange();
      const { audio, state, error, needsAnswers, ...metadata } = event;
      void state;
      void error;
      void needsAnswers;
      const form = new FormData();
      form.set("metadata", JSON.stringify(metadata));
      form.set("audio", audio, "moment.wav");
      try {
        await api("/api/events", { method: "POST", body: form });
        await removePending(event.id);
      } catch (e) {
        await savePending({
          ...event,
          state: "saved locally",
          error:
            e instanceof Error
              ? e.message
              : "Upload could not finish. Your moment is saved on this device.",
        });
      }
      onChange();
    }
  } finally {
    uploading = false;
  }
}
