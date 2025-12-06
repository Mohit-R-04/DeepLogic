# Invoice QC Service 

This repo is my small try for doing invoice extraction + some simple quality checks.
The goal was to read PDFs, pull out few important fields (like invoice id, totals etc),
and then run some basic validation rules to see if data looks fine or not.
I didn’t try to over-engineer anything, just made something that works for the example invoices we got.

The project has 3 main parts:

1. PDF → JSON extraction
2. JSON → validation
3. CLI + FastAPI API
   (and small optional upload endpoint which I added because they mentioned bonus)

## What I picked as Invoice Schema 

I didn’t include 20 fields or something big. Just the ones which look really necessary from the sample invoices.

- invoice_id – number from the invoice
- invoice_date – converted to YYYY-MM-DD if possible (or raw)
- seller_name – usually just the first line from pdf text (not perfect but okay)
- buyer_name – taken from “Bill To” or “Kundenanschrift”
- buyer_address – rest of the block text
- currency – EUR or whatever is found in pdf
- net_total – number before tax
- tax_amount – tax value
- gross_total – after tax
- line_items – list with position, description, quantity, unit price, line total

Schema is super small on purpose so it’s easy to understand.

## Validation Rules

I only added basic checks which makes sense for QC:

### Completeness rules

- invoice_id not empty
- invoice_date not empty
- seller_name not empty
- buyer_name not empty
- currency must exist
- net_total / tax_amount / gross_total must exist

### Format rules

- invoice_date should parse as YYYY-MM-DD, if not, mark as error
- currency must be EUR/USD/INR (just small allowed list)
- totals shouldn’t be negative

### Business rules

- net_total + tax_amount ≈ gross_total (some tolerance because rounding)
- sum(line_total) ≈ net_total (if line_total exists)

### Duplicate rule

Checks duplicates based on seller_name + invoice_id + invoice_date.

## Folder Structure

```
invoice_qc/
  __init__.py
  schemas.py
  extractor.py
  validator.py
  cli.py
  main.py
requirements.txt
README.md
```

## How to Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## CLI Usage

```
python -m invoice_qc.cli extract --pdf-dir pdfs --output out.json

python -m invoice_qc.cli validate --input out.json --report report.json

python -m invoice_qc.cli full-run --pdf-dir pdfs --report full.json
```

## API Server

Start server:

```
uvicorn invoice_qc.main:app --reload --port 9000
```

Open docs:

```
http://127.0.0.1:9000/docs
```

### API Endpoints

- GET /health → just returns ok
- POST /validate-json → send invoice JSON list
- POST /extract-and-validate-pdfs → upload PDFs and get extraction + validation (bonus)

## AI Usage Notes

I used ChatGPT for:

- regex ideas
- fastapi boilerplate
- some help with writing README wording

Some AI suggestions were too perfect or too big, so I removed many things and kept schema small and more “human”. Line item parsing is intentionally simple and not full table parser.

## Final Thoughts

This is small assignment level project, not a full production-grade invoice parser.
But it works fine for the sample PDFs and shows the structure of extraction → validation → API.
