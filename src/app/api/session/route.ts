import { NextRequest, NextResponse } from 'next/server';
import { createOwnerSession, resolveSession } from '@/lib/server/auth';
import { errorResponse } from '@/lib/server/http';
import { setSessionCookie } from '@/lib/server/security';

export async function GET(request: NextRequest) {
  try {
    const current = await resolveSession(request);
    if (current) return NextResponse.json({ workspaceId: current.workspaceId, patient: current.kind === 'patient' ? current.patient : null });
    const created = await createOwnerSession(request);
    const response = NextResponse.json({ workspaceId: created.auth.workspaceId, patient: null });
    setSessionCookie(response, request, 'owner', created.token);
    return response;
  } catch (error) {
    return errorResponse(error);
  }
}
