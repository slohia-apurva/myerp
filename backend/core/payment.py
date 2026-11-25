"""What prints help the customer pay (Sidharth, 2026-11-25): the company's
bank account (its "Bank Account for Payment" under Printing) and a UPI QR code
that opens the payer's app with the amount and our reference filled in."""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode

from core.models import Company


def _indian(amount: Decimal) -> str:
    from buying.po_pdf import _indian_int

    return _indian_int(f"{amount.quantize(Decimal('0.01')):f}")


def details(company: Company, amount: Decimal | None = None, reference: str = "") -> dict | None:
    """The "Payment Details" box of a print, or None when the company has set
    neither a bank ledger nor a UPI ID."""
    bank = company.payment_ledger
    if bank is None and not company.upi_id:
        return None
    rows = []
    if bank is not None:
        where = ", ".join(x for x in [bank.bank_name, bank.bank_branch] if x)
        rows += [
            ("Account Name", company.name),
            ("Bank", where),
            ("Account No", bank.account_number),
            ("IFSC", bank.ifsc),
        ]
    out = {"rows": rows}
    if company.upi_id:
        rows.append(("UPI ID", company.upi_id))
        query = {"pa": company.upi_id, "pn": company.name[:50], "cu": "INR"}
        if amount and amount > 0:
            query["am"] = f"{amount.quantize(Decimal('0.01')):f}"
        if reference:
            query["tn"] = reference[:50]
        out["upi_url"] = "upi://pay?" + urlencode(query)
        out["upi_note"] = (
            f"Scan to pay ₹{_indian(amount)}" if amount and amount > 0 else "Scan to pay"
        )
    return out
