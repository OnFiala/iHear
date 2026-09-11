import 'server-only';
import type { NextRequest } from 'next/server';
import type { ListeningEvent } from '@/lib/types';
import { query } from './db';
import { HttpError } from './http';
import { PIPELINE_VERSION } from './constants';
import type { EventMetadata } from './validation';
import { eventFingerprint, inspectWav } from './wav';
import { requestIpHash } from './security';
import { uploadAudio } from './storage';
import { getEvent } from './patients';

type Reservation = { eventId: string; disposition: 'reserved' | 'existing'; status: string; audioObjectPath: string };

export async function acceptEvent(request: NextRequest, workspaceId: string, patientId: string, metadata: EventMetadata, audio: Buffer): Promise<ListeningEvent> {
  if (metadata.patientId !== patientId) throw new HttpError(403, 'The event is outside this patient session.');
  const wav = inspectWav(audio);
  if (wav.sampleRate !== metadata.capture.sampleRate) throw new HttpError(400, 'The WAV sample rate does not match the capture metadata.');
  const fingerprint = eventFingerprint(metadata, wav.sha256);
  const objectPath = `${workspaceId}/${patientId}/${metadata.id}.wav`;
  const rows = await query<{ reservation: Reservation }>(`
    select ihear.reserve_event_upload(
      $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
    ) as reservation
  `, [
    metadata.id, workspaceId, patientId, requestIpHash(request), metadata.kind,
    metadata.difficulty, metadata.environment, metadata.capturedAt, metadata.capture,
    objectPath, wav.sha256, fingerprint, audio.length, wav.durationSeconds, PIPELINE_VERSION,
  ]);
  const reservation = rows[0].reservation;
  if (reservation.status !== 'uploading') {
    return getEvent(workspaceId, patientId, metadata.id);
  }
  await uploadAudio(objectPath, audio);
  await query('select ihear.finalize_event_upload($1, $2, $3, $4)', [metadata.id, workspaceId, patientId, fingerprint]);
  return getEvent(workspaceId, patientId, metadata.id);
}
