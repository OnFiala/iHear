import { NextRequest, NextResponse } from "next/server";
import { errorResponse, readJson, HttpError } from "@/lib/server/http";
import { previewPairing, redeemPairing } from "@/lib/server/pairing";
import { requireSameOrigin, setSessionCookie } from "@/lib/server/security";

type Context = { params: Promise<{ token: string }> };

export async function GET(_request: NextRequest, context: Context) {
  try {
    const { token } = await context.params;
    return NextResponse.json(await previewPairing(token));
  } catch (error) {
    return errorResponse(error);
  }
}

export async function POST(request: NextRequest, context: Context) {
  try {
    requireSameOrigin(request);
    const body = await readJson(request);
    if (
      !body ||
      typeof body !== "object" ||
      (body as { acknowledged?: unknown }).acknowledged !== true
    ) {
      throw new HttpError(400, "Pairing acknowledgement is required.");
    }
    const { token } = await context.params;
    const result = await redeemPairing(token);
    const response = NextResponse.json({ patient: result.patient });
    setSessionCookie(
      response,
      request,
      "patient",
      result.capability,
      result.expiresAt,
    );
    return response;
  } catch (error) {
    return errorResponse(error);
  }
}
