import "server-only";
import { createHash } from "node:crypto";
import { HttpError } from "./http";
import { MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS } from "./constants";

export type WavInfo = {
  sampleRate: number;
  dataBytes: number;
  durationSeconds: number;
  sha256: Buffer;
};

export function inspectWav(bytes: Buffer): WavInfo {
  if (bytes.length > MAX_AUDIO_BYTES)
    throw new HttpError(413, "The recording is too large.");
  if (
    bytes.length < 44 ||
    bytes.toString("ascii", 0, 4) !== "RIFF" ||
    bytes.toString("ascii", 8, 12) !== "WAVE"
  ) {
    throw new HttpError(400, "The recording must be a valid WAV file.");
  }
  const declaredSize = bytes.readUInt32LE(4) + 8;
  if (declaredSize !== bytes.length || declaredSize < 44)
    throw new HttpError(400, "The WAV file length does not match its header.");

  let offset = 12;
  let format:
    | {
        audioFormat: number;
        channels: number;
        sampleRate: number;
        byteRate: number;
        blockAlign: number;
        bits: number;
      }
    | undefined;
  let dataBytes: number | undefined;
  while (offset + 8 <= declaredSize) {
    const id = bytes.toString("ascii", offset, offset + 4);
    const size = bytes.readUInt32LE(offset + 4);
    const start = offset + 8;
    const end = start + size;
    if (end > declaredSize)
      throw new HttpError(400, "The WAV file contains a truncated chunk.");
    if (id === "fmt " && size >= 16) {
      format = {
        audioFormat: bytes.readUInt16LE(start),
        channels: bytes.readUInt16LE(start + 2),
        sampleRate: bytes.readUInt32LE(start + 4),
        byteRate: bytes.readUInt32LE(start + 8),
        blockAlign: bytes.readUInt16LE(start + 12),
        bits: bytes.readUInt16LE(start + 14),
      };
    } else if (id === "data" && dataBytes === undefined) dataBytes = size;
    offset = end + (size % 2);
  }
  if (!format || dataBytes === undefined || dataBytes === 0)
    throw new HttpError(400, "The WAV file is missing required audio chunks.");
  if (
    format.audioFormat !== 1 ||
    format.channels !== 1 ||
    format.bits !== 16 ||
    format.blockAlign !== 2 ||
    format.byteRate !== format.sampleRate * 2
  ) {
    throw new HttpError(
      400,
      "The recording must be mono 16-bit PCM WAV audio.",
    );
  }
  const durationSeconds = dataBytes / format.byteRate;
  if (durationSeconds > MAX_AUDIO_SECONDS)
    throw new HttpError(413, "The recording must be 10 seconds or shorter.");
  return {
    sampleRate: format.sampleRate,
    dataBytes,
    durationSeconds,
    sha256: createHash("sha256").update(bytes).digest(),
  };
}

function canonicalize(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalize(record[key])}`)
    .join(",")}}`;
}

export function eventFingerprint(metadata: unknown, audioHash: Buffer): Buffer {
  return createHash("sha256")
    .update(canonicalize(metadata), "utf8")
    .update(audioHash)
    .digest();
}
