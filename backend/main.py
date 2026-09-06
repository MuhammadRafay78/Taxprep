from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .explain import LINE_EXPLANATIONS, build_computation, build_flags, build_flow
from .parser import parse_1040

app = FastAPI(title="Taxprep - Understand your tax return")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class LineOverride(BaseModel):
    id: str
    value: float | None = None


class AnalyzeRequest(BaseModel):
    filing_status: str | None = None
    tax_year: int | None = None
    overrides: list[LineOverride] = []


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(400, "Please upload a PDF file.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File is too large (max 20 MB).")
    try:
        result = parse_1040(data)
    except Exception as exc:  # pdfplumber raises various errors on bad PDFs
        raise HTTPException(400, f"Couldn't read this PDF: {exc}") from exc

    return {
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
                "explanation": LINE_EXPLANATIONS.get(ln.id, ""),
            }
            for ln in result.lines
        ],
    }


@app.post("/api/analyze")
async def analyze(payload: AnalyzeRequest):
    values: dict[str, float] = {}
    for override in payload.overrides:
        if override.value is not None:
            values[override.id] = override.value

    flags = build_flags(values, payload.filing_status, payload.tax_year)
    flow = build_flow(values)
    computation = build_computation(values, payload.filing_status, payload.tax_year)

    return {
        "flags": [{"severity": f.severity, "message": f.message} for f in flags],
        "flow": flow,
        "computation": computation,
    }


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
