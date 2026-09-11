import { NextRequest, NextResponse } from "next/server";
import { requireOwner } from "@/lib/server/auth";
import { errorResponse } from "@/lib/server/http";
import { currentReport, ensureReport } from "@/lib/server/reports";
import { requireSameOrigin } from "@/lib/server/security";
import { parseUuid } from "@/lib/server/validation";

type Context = { params: Promise<{ id: string }> };

export async function POST(request: NextRequest, context: Context) {
  try {
    requireSameOrigin(request);
    const auth = await requireOwner(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Patient ID");
    return NextResponse.json(await ensureReport(auth.workspaceId, id), {
      status: 202,
    });
  } catch (error) {
    return errorResponse(error);
  }
}

export async function GET(request: NextRequest, context: Context) {
  try {
    const auth = await requireOwner(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Patient ID");
    return NextResponse.json(await currentReport(auth.workspaceId, id));
  } catch (error) {
    return errorResponse(error);
  }
}
