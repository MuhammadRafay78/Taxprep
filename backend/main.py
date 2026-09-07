from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import explain, explain_990, explain_1065, explain_1120s
from .parser import detect_form_type, parse_1040
from .parser_990 import parse_990
from .parser_1065 import parse_1065
from .parser_1120s import parse_1120s

app = FastAPI(title="Taxprep - Understand your tax return")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

# Every supported form type registers itself here: a parser (pdf bytes ->
# ExtractionResult) plus the three explain.py-shaped functions that turn its
# line values into flags/flow/computation. Each additional form type adds
# its own row alongside its own parser_<type>.py/explain_<type>.py modules,
# without changing this dispatch shape.
FORM_TYPES: dict[str, dict] = {
    "1040": {
        "parse": parse_1040,
        "build_flags": explain.build_flags,
        "build_flow": explain.build_flow,
        "build_computation": explain.build_computation,
        "line_explanations": explain.LINE_EXPLANATIONS,
    },
    "990": {
        "parse": parse_990,
        "build_flags": explain_990.build_flags_990,
        "build_flow": explain_990.build_flow_990,
        "build_computation": explain_990.build_computation_990,
        "line_explanations": explain_990.LINE_EXPLANATIONS_990,
    },
    "1065": {
        "parse": parse_1065,
        "build_flags": explain_1065.build_flags_1065,
        "build_flow": explain_1065.build_flow_1065,
        "build_computation": explain_1065.build_computation_1065,
        "line_explanations": explain_1065.LINE_EXPLANATIONS_1065,
    },
    "1120s": {
        "parse": parse_1120s,
        "build_flags": explain_1120s.build_flags_1120s,
        "build_flow": explain_1120s.build_flow_1120s,
        "build_computation": explain_1120s.build_computation_1120s,
        "line_explanations": explain_1120s.LINE_EXPLANATIONS_1120S,
    },
}


class LineOverride(BaseModel):
    id: str
    value: float | None = None


class AnalyzeRequest(BaseModel):
    filing_status: str | None = None
    tax_year: int | None = None
    form_type: str = "1040"
    overrides: list[LineOverride] = []


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(400, "Please upload a PDF file.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File is too large (max 20 MB).")
    try:
        form_type = detect_form_type(data)
        result = FORM_TYPES[form_type]["parse"](data)
    except Exception as exc:  # pdfplumber raises various errors on bad PDFs
        raise HTTPException(400, f"Couldn't read this PDF: {exc}") from exc

    line_explanations = FORM_TYPES[form_type]["line_explanations"]
    return {
        "form_type": form_type,
        "filing_status": result.filing_status,
        "tax_year": result.tax_year,
        "scanned_pages": result.scanned_pages,
        "ocr_pages": result.ocr_pages,
        "lines": [
            {
                "id": ln.id,
                "label": ln.label,
                "value": ln.value,
                "confidence": ln.confidence,
                "group": ln.group,
                "via_ocr": ln.via_ocr,
                "explanation": line_explanations.get(ln.id, ""),
            }
            for ln in result.lines
        ],
    }


@app.post("/api/analyze")
async def analyze(payload: AnalyzeRequest):
    if payload.form_type not in FORM_TYPES:
        raise HTTPException(400, f"Unsupported form_type: {payload.form_type!r}")
    funcs = FORM_TYPES[payload.form_type]

    values: dict[str, float] = {}
    for override in payload.overrides:
        if override.value is not None:
            values[override.id] = override.value

    flags = funcs["build_flags"](values, payload.filing_status, payload.tax_year)
    flow = funcs["build_flow"](values)
    computation = funcs["build_computation"](values, payload.filing_status, payload.tax_year)

    return {
        "flags": [{"severity": f.severity, "message": f.message} for f in flags],
        "flow": flow,
        "computation": computation,
    }


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
