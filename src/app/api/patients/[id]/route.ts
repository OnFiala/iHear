import { NextRequest, NextResponse } from "next/server";
import { requireOwner } from "@/lib/server/auth";
import { getPatient, listEvents, updatePatient } from "@/lib/server/patients";
import { errorResponse, readJson } from "@/lib/server/http";
import { requireSameOrigin } from "@/lib/server/security";
import { parseProfile, parseUuid } from "@/lib/server/validation";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, context: Context) {
  try {
    const auth = await requireOwner(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Patient ID");
    const [patient, events] = await Promise.all([
      getPatient(auth.workspaceId, id),
      listEvents(auth.workspaceId, id),
    ]);
    return NextResponse.json({ patient, events, pairing: null });
  } catch (error) {
    return errorResponse(error);
  }
}

export async function PATCH(request: NextRequest, context: Context) {
  try {
    requireSameOrigin(request);
    const auth = await requireOwner(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Patient ID");
    const patient = await updatePatient(
      auth.workspaceId,
      id,
      parseProfile(await readJson(request)),
    );
    return NextResponse.json({ patient });
  } catch (error) {
    return errorResponse(error);
  }
}
