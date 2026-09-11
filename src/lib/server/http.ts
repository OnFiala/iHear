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
      value.message === "queue_capacity_exceeded"
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
  console.error("iHear API error", error);
  return NextResponse.json(
    { error: "The server could not complete the request." },
    { status: 500 },
  );
}

export async function readJson(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
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
