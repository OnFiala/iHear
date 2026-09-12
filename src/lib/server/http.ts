import "server-only";
import { NextResponse } from "next/server";

export class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export const MAX_JSON_BYTES = 65_536;

function logClassification(error: unknown): "database" | "configuration" | "unexpected" {
  if (error && typeof error === "object") {
    const value = error as { code?: unknown; message?: unknown };
    if (typeof value.code === "string" && /^[0-9A-Z]{5}$/.test(value.code))
      return "database";
    if (
      typeof value.message === "string" &&
      (value.message.endsWith(" is not configured.") ||
        value.message.includes(" must be an integer"))
    )
      return "configuration";
  }
  return "unexpected";
}

export function errorResponse(error: unknown): NextResponse<{ error: string }> {
  if (error instanceof HttpError)
    return NextResponse.json(
      { error: error.message },
      { status: error.status },
    );
  if (error && typeof error === "object") {
    const value = error as { code?: string; message?: string };
    if (value.message === "event_conflict")
      return NextResponse.json(
        { error: "This event ID was already used with different content." },
        { status: 409 },
      );
    if (
      value.message === "rate_limit_exceeded" ||
      value.message === "queue_capacity_exceeded" ||
      value.message === "retained_capacity_exceeded"
    ) {
      return NextResponse.json(
        { error: "The service is busy. Please try again later." },
        { status: 429 },
      );
    }
    if (value.code === "23505")
      return NextResponse.json(
        { error: "That record already exists." },
        { status: 409 },
      );
  }
  console.error(
    JSON.stringify({
      event: "ihear_api_error",
      classification: logClassification(error),
    }),
  );
  return NextResponse.json(
    { error: "The server could not complete the request." },
    { status: 500 },
  );
}

export async function readJson(request: Request): Promise<unknown> {
  try {
    const body = await readBoundedBody(request, MAX_JSON_BYTES);
    const text = new TextDecoder("utf-8", { fatal: true }).decode(body);
    return JSON.parse(text);
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(400, "The request body must be valid JSON.");
  }
}

export async function readBoundedBody(
  request: Request,
  maximumBytes: number,
): Promise<Buffer> {
  const declared = request.headers.get("content-length");
  if (declared !== null) {
    const value = Number(declared);
    if (!Number.isSafeInteger(value) || value < 0)
      throw new HttpError(400, "Content-Length is invalid.");
    if (value > maximumBytes)
      throw new HttpError(413, "The request body is too large.");
  }
  if (!request.body) throw new HttpError(400, "The request body is required.");
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maximumBytes) {
      await reader.cancel();
      throw new HttpError(413, "The request body is too large.");
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks, total);
}
