import { parse1040 } from "./parser";
import { LINE_EXPLANATIONS, buildComputation, buildFlags, buildFlow } from "./explain";

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
    scanned_pages: result.scannedPages,
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

  const filingStatus = payload.filing_status ?? null;
  const taxYear = payload.tax_year ?? null;
  const flags = buildFlags(values, filingStatus, taxYear);
  const flow = buildFlow(values);
  const comp = buildComputation(values, filingStatus, taxYear);

  return Response.json({
    flags: flags.map((f) => ({ severity: f.severity, message: f.message })),
    flow,
    computation: {
      header: {
        filing_status: comp.header.filingStatus,
        tax_year: comp.header.taxYear,
        result_type: comp.header.resultType,
        result_amount: comp.header.resultAmount,
      },
      income_to_agi: comp.incomeToAgi,
      agi_to_taxable: {
        agi: comp.agiToTaxable.agi,
        deduction: comp.agiToTaxable.deduction,
        deduction_note: comp.agiToTaxable.deductionNote,
        qbi: comp.agiToTaxable.qbi,
        taxable_income: comp.agiToTaxable.taxableIncome,
      },
      tax_computation: comp.taxComputation && {
        method: comp.taxComputation.method,
        ordinary_income: comp.taxComputation.ordinaryIncome,
        ordinary_tax: comp.taxComputation.ordinaryTax,
        preferential_income: comp.taxComputation.preferentialIncome,
        preferential_rows: comp.taxComputation.preferentialRows,
        bracket_rows: comp.taxComputation.bracketRows,
        reconstructed_tax: comp.taxComputation.reconstructedTax,
        reported_tax: comp.taxComputation.reportedTax ?? null,
        ties_out: comp.taxComputation.tiesOut,
      },
      tax_to_outcome: comp.taxToOutcome,
      reviewer_notes: comp.reviewerNotes.map((f) => ({ severity: f.severity, message: f.message })),
    },
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
