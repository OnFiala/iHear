import { NextRequest, NextResponse } from "next/server";
import { requirePatient } from "@/lib/server/auth";
import { errorResponse } from "@/lib/server/http";
import { getEvent } from "@/lib/server/patients";
import { parseUuid } from "@/lib/server/validation";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, context: Context) {
  try {
    const auth = await requirePatient(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Event ID");
    return NextResponse.json({
      event: await getEvent(auth.workspaceId, auth.patientId, id),
    });
  } catch (error) {
    return errorResponse(error);
  }
}
