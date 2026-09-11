import { NextRequest, NextResponse } from 'next/server';
import { requireOwner } from '@/lib/server/auth';
import { createPatient, listPatients } from '@/lib/server/patients';
import { errorResponse, readJson } from '@/lib/server/http';
import { requireSameOrigin } from '@/lib/server/security';
import { parsePatientFilters, parseProfile } from '@/lib/server/validation';

export async function GET(request: NextRequest) {
  try {
    const auth = await requireOwner(request);
    const patients = await listPatients(auth.workspaceId, parsePatientFilters(request.nextUrl.searchParams));
    return NextResponse.json({ patients });
  } catch (error) {
    return errorResponse(error);
  }
}

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const auth = await requireOwner(request);
    const patient = await createPatient(auth.workspaceId, parseProfile(await readJson(request)));
    return NextResponse.json({ patient }, { status: 201 });
  } catch (error) {
    return errorResponse(error);
  }
}
