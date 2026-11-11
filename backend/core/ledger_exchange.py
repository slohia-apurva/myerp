"""Import, export and print for Ledgers (core/exchange.py). A company's
ledgers, with the customer or supplier details of party ledgers and the
opening bills, on the Ledgers screen of the company being worked in."""

from django.db.models import Q

from accounts.models import User
from core import exchange, india
from core.api import LedgerSerializer, add_ledger, change_ledger


def _user_cell(pk) -> str:
    if pk is None:
        return ""
    user = User.objects.filter(pk=pk).first()
    return user.email if user else str(pk)


def _user_from(text: str) -> int:
    text = text.strip()
    user = (
        User.objects.filter(is_active=True)
        .filter(Q(email__iexact=text) | Q(full_name__iexact=text))
        .first()
    )
    if user is None:
        raise ValueError(f"there is no active user {text!r}")
    return user.pk


def _state_from(text: str) -> str:
    low = text.strip().lower()
    for code, name in india.STATES.items():
        if low in (code, name.lower()):
            return code
    raise ValueError(f"{text!r} is not an Indian state; leave it empty for a party abroad")


STATE = exchange.Codec(
    lambda code: india.STATES.get(code, code or ""),
    _state_from,
    hint="The state's name or its two-digit GST code",
)


def _ledgers(ctx):
    return (
        ctx.company.ledgers.select_related("group", "party", "salesman")
        .prefetch_related(
            "opening_bills", "party__addresses", "party__contacts", "party__ledgers__company"
        )
        .order_by("group__name", "name")
    )


def _save(ctx, ledger, data):
    if ledger is None:
        return add_ledger(ctx.request, ctx.company, data)
    return change_ledger(ctx.request, ledger, data)


exchange.register(
    exchange.Master(
        key="ledgers",
        label="Ledgers",
        noun="ledger",
        serializer=LedgerSerializer,
        queryset=_ledgers,
        save=_save,
        per_company=True,
        report=(
            "name",
            "group",
            "opening_amount",
            "opening_side",
            "currency",
            "party.customer_number",
            "party.vendor_number",
            "party.gst_type",
            "party.gstin",
            "party.state_code",
            "party.credit_term",
            "is_active",
        ),
        exclude=("party_id", "also_in"),
        codecs={
            "party.state_code": STATE,
            "party.addresses.state_code": STATE,
            "party.salesman": exchange.Codec(
                _user_cell, _user_from, hint="The user's email or full name", kind="other"
            ),
        },
        labels={
            "party.customer_number": "Customer number",
            "party.vendor_number": "Vendor number",
            "party.gst_type": "GST type",
            "party.state_code": "State",
            "party.country": "Country",
            "party.credit_term": "Credit terms",
            "party.salesman": "Salesman or purchaser",
            "opening_bills": "Opening bills",
            "opening_bills.ref": "Bill reference",
            "opening_bills.bill_date": "Bill date",
            "opening_bills.due_date": "Due date",
            "opening_bills.amount": "Amount (₹)",
            "opening_bills.side": "Dr/Cr",
            "opening_bills.fc_amount": "Amount (foreign currency)",
            "opening_bills.rate": "Rate",
            "party.addresses": "Addresses",
            "party.addresses.label": "Name",
            "party.addresses.state_code": "State",
            "party.addresses.gstin": "GSTIN at this address",
            "party.addresses.is_billing": "Default billing address",
            "party.addresses.is_shipping": "Default shipping address",
            "party.contacts": "Contacts",
            "party.contacts.is_primary": "Main",
            "party.contacts.kinds": "Types",
        },
        hints={
            "group": "The group's name in this company",
            "party.gst_type": "Customers and suppliers only; leave the customer columns "
            "empty for other ledgers",
            "party.customer_number": "Leave empty and MyERP gives the next number",
            "party.vendor_number": "Leave empty and MyERP gives the next number",
            "opening_bills.amount": "In foreign currency ledgers, give the foreign amount "
            "and rate instead",
        },
    )
)
