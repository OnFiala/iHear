import { NextRequest } from "next/server";
import { requireOwner } from "@/lib/server/auth";
import { errorResponse, HttpError } from "@/lib/server/http";
import { reportObjectPath } from "@/lib/server/reports";
import { downloadReport } from "@/lib/server/storage";
import { parseUuid } from "@/lib/server/validation";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, context: Context) {
  try {
    const auth = await requireOwner(request);
    const { id: rawId } = await context.params;
    const id = parseUuid(rawId, "Patient ID");
    const reportIdValue = request.nextUrl.searchParams.get("reportId");
    if (!reportIdValue) throw new HttpError(400, "Report ID is required.");
    const reportId = parseUuid(reportIdValue, "Report ID");
    const objectPath = await reportObjectPath(auth.workspaceId, id, reportId);
    const blob = await downloadReport(objectPath);
    return new Response(blob, {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="ihear-report-${id}.pdf"`,
        "Cache-Control": "private, no-store",
      },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
