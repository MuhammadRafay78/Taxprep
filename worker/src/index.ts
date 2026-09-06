import { parse1040 } from "./parser";
import { LINE_EXPLANATIONS, buildFlags, buildFlow } from "./explain";

export interface Env {
  ASSETS: Fetcher;
}

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024; // 20 MB

interface LineOverride {
  id: string;
  value: number | null;
}

interface AnalyzeRequest {
  filing_status?: string | null;
  tax_year?: number | null;
  overrides?: LineOverride[];
}

function jsonError(status: number, detail: string): Response {
  return Response.json({ detail }, { status });
}

async function handleExtract(request: Request): Promise<Response> {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return jsonError(400, "Expected a multipart form upload with a 'file' field.");
  }
  const file = form.get("file");
  if (!(file instanceof File)) {
    return jsonError(400, "Please upload a PDF file.");
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return jsonError(400, "File is too large (max 20 MB).");
  }

  const bytes = new Uint8Array(await file.arrayBuffer());
  let result;
  try {
    result = await parse1040(bytes);
  } catch (err) {
    return jsonError(400, `Couldn't read this PDF: ${(err as Error).message}`);
  }

  return Response.json({
    filing_status: result.filingStatus,
    tax_year: result.taxYear,
    lines: result.lines.map((ln) => ({
      id: ln.id,
      label: ln.label,
      value: ln.value,
      confidence: ln.confidence,
      group: ln.group,
      explanation: LINE_EXPLANATIONS[ln.id] ?? "",
    })),
  });
}

async function handleAnalyze(request: Request): Promise<Response> {
  let payload: AnalyzeRequest;
  try {
    payload = await request.json();
  } catch {
    return jsonError(400, "Expected a JSON body.");
  }

  const values: Record<string, number> = {};
  for (const override of payload.overrides ?? []) {
    if (override.value !== null && override.value !== undefined) {
      values[override.id] = override.value;
    }
  }

  const flags = buildFlags(values, payload.filing_status ?? null, payload.tax_year ?? null);
  const flow = buildFlow(values);

  return Response.json({
    flags: flags.map((f) => ({ severity: f.severity, message: f.message })),
    flow,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/api/extract" && request.method === "POST") {
        return await handleExtract(request);
      }
      if (url.pathname === "/api/analyze" && request.method === "POST") {
        return await handleAnalyze(request);
      }
    } catch (err) {
      return jsonError(500, `Internal error: ${(err as Error).message}`);
    }
    return env.ASSETS.fetch(request);
  },
};
