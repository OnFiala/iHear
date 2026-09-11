import { NextRequest, NextResponse } from "next/server";
import { requireOwner } from "@/lib/server/auth";
import { errorResponse } from "@/lib/server/http";
import { issuePairing, revokePairing } from "@/lib/server/pairing";
import { requireSameOrigin } from "@/lib/server/security";
import { parseUuid } from "@/lib/server/validation";

type Context = { params: Promise<{ id: string }> };

export async function POST(request: NextRequest, context: Context) {
  try {
    requireSameOrigin(request);
    const auth = await requireOwner(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Patient ID");
    const pairing = await issuePairing(request, auth.workspaceId, id);
    return NextResponse.json({ pairing }, { status: 201 });
  } catch (error) {
    return errorResponse(error);
  }
}

export async function DELETE(request: NextRequest, context: Context) {
  try {
    requireSameOrigin(request);
    const auth = await requireOwner(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Patient ID");
    await revokePairing(auth.workspaceId, id);
    return NextResponse.json({ revoked: true });
  } catch (error) {
    return errorResponse(error);
  }
}
