from typing import List
from pathlib import Path
import tempfile

from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel

from .schemas import Invoice, ValidationResult, ValidationSummary
from .validator import validate_invoices
from .extractor import _extract_text_from_pdf, parse_invoice_from_text


app = FastAPI(
    title="Invoice QC Service",
    description="small service for invoice extraction & validation",
    version="0.1.0",
)
# allow simple frontend to call api from browser (localhost, file:// etc)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for assignment ok, in real life restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



class ValidationResponse(BaseModel):
    # wrapper for /validate-json response
    summary: ValidationSummary
    invoices: List[ValidationResult]


@app.get("/health")
def health():
    # simple health check, nothing fancy
    return {"status": "ok"}


@app.post("/validate-json", response_model=ValidationResponse)
def validate_json(invoices: List[Invoice]):
    """
    take list of invoice objects (already json),
    run validation and return result.
    """
    results, summary = validate_invoices(invoices)
    resp = ValidationResponse(
        summary=summary,
        invoices=results,
    )
    return resp

@app.post("/extract-and-validate-pdfs")
async def extract_and_validate_pdfs(files: List[UploadFile] = File(...)):
    """
    user uploads one or more pdf files,
    we extract invoice data and then run validation.
    """
    invoices: List[Invoice] = []

    for file in files:
        # save uploaded file to temp so PyPDF2 can read it by path
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            file_bytes = await file.read()
            tmp.write(file_bytes)
            temp_path = Path(tmp.name)

        # get text from pdf and parse into invoice
        text = _extract_text_from_pdf(temp_path)
        inv = parse_invoice_from_text(text, filename=file.filename)
        invoices.append(inv)

        # try remove temp file, if it fails we don't crash the whole thing
        try:
            temp_path.unlink()
        except Exception:
            pass

    # now run normal validation on the extracted invoices
    results, summary = validate_invoices(invoices)

    # IMPORTANT: shape must match /validate-json -> { summary, invoices }
    return {
        "summary": summary.model_dump(),
        "invoices": [r.model_dump() for r in results],
        # raw extracted invoices if someone wants to inspect
        "raw": [inv.model_dump() for inv in invoices],
    }
