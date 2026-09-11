import { NextRequest, NextResponse } from 'next/server';
import { requirePatient } from '@/lib/server/auth';
import { acceptEvent } from '@/lib/server/events';
import { errorResponse, HttpError, readBoundedBody } from '@/lib/server/http';
import { listEvents } from '@/lib/server/patients';
import { requireSameOrigin } from '@/lib/server/security';
import { parseEventMetadata } from '@/lib/server/validation';

const MAX_MULTIPART_BYTES = 2_300_000;

export async function GET(request: NextRequest) {
  try {
    const auth = await requirePatient(request);
    return NextResponse.json({ events: await listEvents(auth.workspaceId, auth.patientId) });
  } catch (error) {
    return errorResponse(error);
  }
}

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const auth = await requirePatient(request);
    const body = await readBoundedBody(request, MAX_MULTIPART_BYTES);
    const headers = new Headers(request.headers);
    headers.set('content-length', String(body.byteLength));
    const form = await new Request(request.url, { method: 'POST', headers, body: Uint8Array.from(body) }).formData();
    const metadataValue = form.get('metadata');
    const audioValue = form.get('audio');
    if (typeof metadataValue !== 'string') throw new HttpError(400, 'Event metadata is required.');
    if (metadataValue.length > 65_536) throw new HttpError(413, 'Event metadata is too large.');
    if (!(audioValue instanceof Blob)) throw new HttpError(400, 'A WAV recording is required.');
    let parsed: unknown;
    try { parsed = JSON.parse(metadataValue); } catch { throw new HttpError(400, 'Event metadata must be valid JSON.'); }
    const event = await acceptEvent(request, auth.workspaceId, auth.patientId, parseEventMetadata(parsed), Buffer.from(await audioValue.arrayBuffer()));
    return NextResponse.json({ event }, { status: 202 });
  } catch (error) {
    return errorResponse(error);
  }
}
