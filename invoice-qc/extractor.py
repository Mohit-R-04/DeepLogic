# invoice_qc/extractor.py
# very basic pdf -> invoice extractor
# this is not perfect, just some simple rules that work ok for sample files

import re
import json
from pathlib import Path
from typing import List, Optional

import pdfplumber

from .schemas import Invoice, LineItem


def _extract_text_from_pdf(pdf_path: Path) -> str:
    """read all text from pdf, join pages"""
    text_parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


def _parse_float(value: str) -> Optional[float]:
    """
    small helper to turn number text into float.
    tries to handle both 1234.56 and 1.234,56 styles a bit.
    if fails just returns None.
    """
    if not value:
        return None

    s = value.strip()
    # remove spaces in middle like "1 234,56"
    s = s.replace(" ", "")

    # very rough: if it has comma but no dot, assume comma is decimal
    if "," in s and "." not in s:
        s = s.replace(".", "")   # remove thousand sep
        s = s.replace(",", ".")  # use . as decimal

    # also remove currency stuff just in case
    s = re.sub(r"[^\d\.\-]", "", s)

    try:
        return float(s)
    except ValueError:
        return None


def _find_first(pattern: str, text: str, flags=0) -> Optional[str]:
    """return first captured group for regex or None"""
    m = re.search(pattern, text, flags)
    if m:
        # if we have group, return that, else full match
        if m.lastindex:
            return m.group(1)
        return m.group(0)
    return None


def parse_invoice_from_text(text: str, filename: str = "") -> Invoice:
    """
    main parser. this is very heuristic / hacky.
    its ok, its a small assignment, not production.
    """

    # invoice_id - look for something like "Invoice No: XYZ" or "Bestellung AUFNR12345"
    invoice_id = None
    invoice_id = _find_first(r"(?:Invoice\s*No\.?:\s*([A-Za-z0-9\-\./]+))", text)
    if not invoice_id:
        invoice_id = _find_first(r"Bestellung\s+([A-Z]*\d+)", text)

    # invoice_date - look for dd.mm.yyyy or yyyy-mm-dd after "Date" or "vom"
    invoice_date = None
    date_match = _find_first(r"Date\s*:\s*([\d./-]+)", text)
    if not date_match:
        date_match = _find_first(r"vom\s+([\d]{2}\.[\d]{2}\.[\d]{4})", text)
    if date_match:
        # in real code i would properly parse, here we just try to normalize a bit
        d = date_match.strip()
        # transform dd.mm.yyyy -> yyyy-mm-dd
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", d)
        if m:
            day, month, year = m.groups()
            invoice_date = f"{year}-{month}-{day}"
        else:
            # fallback, just keep as-is
            invoice_date = d

    # seller_name - this is tricky, for now just None or first line
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    seller_name = lines[0] if lines else None

    # buyer_name and address - very rough: search for "Kundenanschrift" block or "Bill To"
    buyer_name = None
    buyer_address = None

    buyer_block = None
    m = re.search(r"(Kundenanschrift|Bill To)[:\n](.+?)(?:\n\s*\n|\n{2,})", text, re.DOTALL)
    if m:
        buyer_block = m.group(2).strip()

    if buyer_block:
        block_lines = [l.strip() for l in buyer_block.splitlines() if l.strip()]
        if block_lines:
            buyer_name = block_lines[0]
            # rest as address
            if len(block_lines) > 1:
                buyer_address = ", ".join(block_lines[1:])

    # currency - simple search
    currency = None
    if "EUR" in text:
        currency = "EUR"
    else:
        c = _find_first(r"Currency\s*[:\-]\s*([A-Z]{3})", text)
        currency = c or None

    # totals - we just try some patterns
    net_total = None
    tax_amount = None
    gross_total = None

    # try find "Net total" or "Gesamtwert"
    net_str = _find_first(r"(?:Net\s*Total|Netto|Gesamtwert)[^\d]*([\d\.,]+)", text)
    if net_str:
        net_total = _parse_float(net_str)

    # tax
    tax_str = _find_first(r"(?:Tax|MwSt)[^\d]*([\d\.,]+)", text)
    if tax_str:
        tax_amount = _parse_float(tax_str)

    # gross
    gross_str = _find_first(r"(?:Total\s*Amount|Brutto|Gesamtwert inkl\. MwSt\.?)[^\d]*([\d\.,]+)", text)
    if gross_str:
        gross_total = _parse_float(gross_str)

    # payment terms - just grab line with "Zahlungsbedingungen" or "Payment terms"
    payment_terms = None
    for line in lines:
        if "Zahlungsbedingungen" in line or "Payment" in line:
            payment_terms = line.strip()
            break

    # try to parse line items 
    line_items: List[LineItem] = []

    # we try to find area between a header like "Pos." or "Item" and totals
    items_text = None
    m_items = re.search(r"(Pos\..+?)(Gesamtwert|Net\s*Total|Netto)", text, re.DOTALL)
    if m_items:
        items_text = m_items.group(1)
    else:
        # if not found, maybe english style "Item"
        m_items = re.search(r"(Item.+?)(Total\s*Amount|Net\s*Total)", text, re.DOTALL)
        if m_items:
            items_text = m_items.group(1)

    if items_text:
        # split by lines and try to guess position, description, qty, price, total
        ilines = [l for l in items_text.splitlines() if l.strip()]
        # very dumb parsing: skip header lines that contain Pos or Menge etc
        pos_counter = 1
        for ln in ilines:
            if "Pos" in ln or "Menge" in ln or "Qty" in ln:
                continue

            # we try to take last 3 "words" as qty, price, total, and rest as description
            parts = ln.split()
            if len(parts) < 3:
                # maybe line is just description, we can attach with next line but
                # to keep it simple we skip that logic here
                continue

            # assume last 3 parts numeric-ish
            maybe_total = parts[-1]
            maybe_price = parts[-2]
            maybe_qty = parts[-3]
            desc_parts = parts[:-3]

            qty = _parse_float(maybe_qty)
            unit_price = _parse_float(maybe_price)
            line_total = _parse_float(maybe_total)
            description = " ".join(desc_parts).strip()

            if not description and (qty is None and unit_price is None and line_total is None):
                # nothing useful here
                continue

            item = LineItem(
                position=pos_counter,
                description=description or None,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
            line_items.append(item)
            pos_counter += 1

    invoice = Invoice(
        invoice_id=invoice_id or filename,  # fallback to filename if nothing
        invoice_date=invoice_date,
        seller_name=seller_name,
        buyer_name=buyer_name,
        buyer_address=buyer_address,
        currency=currency,
        net_total=net_total,
        tax_amount=tax_amount,
        gross_total=gross_total,
        payment_terms=payment_terms,
        line_items=line_items,
    )

    return invoice


def extract_invoices_from_dir(pdf_dir: Path) -> List[Invoice]:
    """loop over all pdf files and parse them"""
    invoices: List[Invoice] = []
    for pdf_path in pdf_dir.glob("*.pdf"):
        text = _extract_text_from_pdf(pdf_path)
        inv = parse_invoice_from_text(text, filename=pdf_path.name)
        invoices.append(inv)
    return invoices


def export_invoices_to_json(invoices: List[Invoice], output_path: Path) -> None:
    """save list of invoices as json file"""
    data = [inv.model_dump() for inv in invoices]
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
