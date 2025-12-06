from typing import List, Optional, Dict
from pydantic import BaseModel


class LineItem(BaseModel):
    # just simple thing to identify line inside invoice
    position: Optional[int] = None   # 1,2,3 ... this is enough
    description: Optional[str] = None  # name of product
    quantity: Optional[float] = None   # how many
    unit_price: Optional[float] = None # price of one
    line_total: Optional[float] = None # total for this line



class Invoice(BaseModel):
    # main invoice info, one per pdf / json
    invoice_id: Optional[str] = None      # invoice number
    invoice_date: Optional[str] = None    # we keep as yyyy-mm-dd string

    seller_name: Optional[str] = None     # who is issuing the invoice
    buyer_name: Optional[str] = None      # who is paying
    buyer_address: Optional[str] = None   # address of buyer

    currency: Optional[str] = None        # EUR, USD, etc

    net_total: Optional[float] = None     # total before tax
    tax_amount: Optional[float] = None    # tax value
    gross_total: Optional[float] = None   # total after tax

    payment_terms: Optional[str] = None   # text like "30 days", can be free form

    # list of items in the invoice
    line_items: List[LineItem] = []


class ValidationResult(BaseModel):
    # validation result for one invoice
    invoice_id: Optional[str] = None
    is_valid: bool = False
    errors: List[str] = []  # store error codes / messages here


class ValidationSummary(BaseModel):
    # overall summary for one run
    total_invoices: int
    valid_invoices: int
    invalid_invoices: int
    error_counts: Dict[str, int]  # error -> how many times
