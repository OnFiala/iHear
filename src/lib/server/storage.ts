import "server-only";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { AUDIO_BUCKET, REPORT_BUCKET } from "./constants";

let client: SupabaseClient | undefined;

function storage(): SupabaseClient {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key)
    throw new Error("Supabase Storage server credentials are not configured.");
  client ??= createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return client;
}

export async function uploadAudio(path: string, bytes: Buffer): Promise<void> {
  const { error } = await storage()
    .storage.from(AUDIO_BUCKET)
    .upload(path, bytes, { contentType: "audio/wav", upsert: true });
  if (error) throw new Error(`Audio storage failed: ${error.message}`);
}

export async function downloadReport(path: string): Promise<Blob> {
  const { data, error } = await storage()
    .storage.from(REPORT_BUCKET)
    .download(path);
  if (error || !data)
    throw new Error(
      `Report storage failed: ${error?.message ?? "object unavailable"}`,
    );
  return data;
}
