import { NextRequest, NextResponse } from "next/server";
import { requirePatient } from "@/lib/server/auth";
import { errorResponse } from "@/lib/server/http";
import { getEvent } from "@/lib/server/patients";
import { patientEvent } from "@/lib/server/records";
import { parseUuid } from "@/lib/server/validation";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, context: Context) {
  try {
    const auth = await requirePatient(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Event ID");
    return NextResponse.json({
      event: patientEvent(await getEvent(auth.workspaceId, auth.patientId, id), auth.patient.aids),
    });
  } catch (error) {
    return errorResponse(error);
  }
}
