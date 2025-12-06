from typing import List, Tuple, Dict
from collections import Counter
from datetime import datetime

from .schemas import Invoice, ValidationResult, ValidationSummary


# small settings
ALLOWED_CURRENCIES = ["EUR", "USD", "INR"]
BASE_TOLERANCE = 0.05  # base small tolerance in money


def _calc_tolerance(amount: float) -> float:
    """
    decide how much difference we allow.
    for very small invoices use fixed 0.05,
    for bigger ones allow about 1% difference.
    this is kind of "relaxed" on purpose because extraction is rough.
    """
    if amount is None:
        return BASE_TOLERANCE
    return max(BASE_TOLERANCE, 0.01 * abs(amount))


def _check_completeness(inv: Invoice) -> List[str]:
    """check for missing important fields"""
    errors: List[str] = []

    if not inv.invoice_id or not str(inv.invoice_id).strip():
        errors.append("missing_field: invoice_id")

    if not inv.invoice_date or not str(inv.invoice_date).strip():
        errors.append("missing_field: invoice_date")

    if not inv.seller_name or not str(inv.seller_name).strip():
        errors.append("missing_field: seller_name")

    if not inv.buyer_name or not str(inv.buyer_name).strip():
        errors.append("missing_field: buyer_name")

    if inv.currency is None or not str(inv.currency).strip():
        errors.append("missing_field: currency")

    # totals we want them at least present
    if inv.net_total is None:
        errors.append("missing_field: net_total")

    if inv.tax_amount is None:
        errors.append("missing_field: tax_amount")

    if inv.gross_total is None:
        errors.append("missing_field: gross_total")

    return errors


def _check_format(inv: Invoice) -> List[str]:
    """check type-ish rules like date and currency and negative values"""
    errors: List[str] = []

    # invoice_date, try to parse
    if inv.invoice_date:
        d = str(inv.invoice_date)
        # we expect yyyy-mm-dd usually from extractor
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            # date might be in some weird format, we just mark it
            errors.append("format_error: invoice_date")
    # if it's missing we already added missing_field above

    # currency allowed?
    if inv.currency:
        if inv.currency not in ALLOWED_CURRENCIES:
            errors.append("format_error: currency_not_allowed")

    # totals should not be negative (kind of obvious for normal invoices)
    if inv.net_total is not None and inv.net_total < 0:
        errors.append("format_error: net_total_negative")

    if inv.tax_amount is not None and inv.tax_amount < 0:
        errors.append("format_error: tax_amount_negative")

    if inv.gross_total is not None and inv.gross_total < 0:
        errors.append("format_error: gross_total_negative")

    return errors


def _check_business_rules(inv: Invoice) -> List[str]:
    """check math like totals and sum of line items"""
    errors: List[str] = []

    # net + tax ~ gross
    if (
        inv.net_total is not None
        and inv.tax_amount is not None
        and inv.gross_total is not None
    ):
        expected_gross = inv.net_total + inv.tax_amount
        tolerance = _calc_tolerance(inv.gross_total)
        diff = abs(expected_gross - inv.gross_total)
        if diff > tolerance:
            errors.append("business_rule_failed: totals_mismatch_net_tax_gross")

    # sum(line_total) ~ net_total
    if inv.line_items and inv.net_total is not None:
        line_sum = 0.0
        line_total_count = 0

        for item in inv.line_items:
            if item.line_total is not None:
                line_sum += item.line_total
                line_total_count += 1

        # only check if at least half of the items have a line_total
        if line_total_count > 0 and line_total_count >= len(inv.line_items) / 2:
            tolerance = _calc_tolerance(inv.net_total)
            diff = abs(line_sum - inv.net_total)
            if diff > tolerance:
                errors.append("business_rule_failed: line_total_sum_differs_from_net")
        else:
            # not enough data quality to compare sum vs net
            # so we just skip this rule to avoid too many false errors
            pass

    return errors


def _build_duplicate_key(inv: Invoice) -> str:
    """small helper to identify invoice for duplicate check"""
    # if some parts are None, we still use string "None"
    return f"{inv.seller_name}|{inv.invoice_id}|{inv.invoice_date}"


def validate_invoices(invoices: List[Invoice]) -> Tuple[List[ValidationResult], ValidationSummary]:
    """
    run all validation rules on a list of invoices.

    returns:
      - list of ValidationResult (per invoice)
      - one ValidationSummary (overall)
    """
    results: List[ValidationResult] = []
    error_counter: Counter = Counter()

    seen_keys: Dict[str, int] = {}  # for duplicates

    for inv in invoices:
        inv_errors: List[str] = []

        # completeness and format
        inv_errors.extend(_check_completeness(inv))
        inv_errors.extend(_check_format(inv))

        # business logic rules
        inv_errors.extend(_check_business_rules(inv))

        # duplicate check
        key = _build_duplicate_key(inv)
        if key in seen_keys:
            inv_errors.append("duplicate_invoice: seller_id_date")
        else:
            seen_keys[key] = 1

        # collect for summary count
        for e in inv_errors:
            error_counter[e] += 1

        # create result object
        result = ValidationResult(
            invoice_id=inv.invoice_id,
            is_valid=(len(inv_errors) == 0),
            errors=inv_errors
        )
        results.append(result)

    total = len(invoices)
    valid = sum(1 for r in results if r.is_valid)
    invalid = total - valid

    summary = ValidationSummary(
        total_invoices=total,
        valid_invoices=valid,
        invalid_invoices=invalid,
        error_counts=dict(error_counter)
    )

    return results, summary
