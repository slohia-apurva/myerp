"""Sales orders (Entry > Sales > Sales Order).

Who may do what (standard roles, accounts/roles.py):
- `sales.view` sees the orders; `sales.create` makes and changes drafts;
  `sales.submit` submits (numbers and fixes) them; `sales.cancel` cancels.
- All of it needs the company's Sales module (decision 0014).

Nothing here posts to the ledgers. Approved previews: mockups/sales 4 and 5
(Sidharth, 2026-11-19).
"""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from buying.api import (
    _branch_address,
    _contact_out,
    _letterhead,
    _money,
    _party_address,
    _party_fssai,
    _plain,
)
from core import attachments, fiscal, numbering, paging, words
from core.api import Signed
from core.api import _company as _visible_company
from core.companies import visible_companies
from core.items import gst_rate_on, picked
from core.models import (
    Branch,
    CreditTerm,
    Item,
    ItemUnit,
    Ledger,
    LedgerGroup,
    Party,
    PartyContact,
    PartyItemName,
    PriceList,
    SalesPerson,
    TermsSet,
    WarehouseLocation,
)
from core.parties import items_for_party, picked_ledgers
from core.price_lists import TYPED, check_rate, find_rate, is_locked
from core.price_lists import source_words as price_source_words
from core.terms import terms_for
from posting.models import GLEntry
from selling import stock
from selling.models import PickList, SalesOrder, SalesOrderCharge, SalesOrderLine
from shipping.models import CourierAccount
from tenancy.context import tenant_atomic
from tenancy.models import GstRate

VIEW, CREATE, SUBMIT, CANCEL = (f"sales.{a}" for a in ("view", "create", "submit", "cancel"))
RUPEE = Decimal("1")
ZERO = Decimal("0")


def _check(request, code: str) -> None:
    if not request.user.can(code):
        raise PermissionDenied("Your role does not allow this.")


def _company(request, pk: int):
    company = _visible_company(request, pk)
    if "sales" not in company.modules:
        raise NotFound("This company does not use the Sales module.")
    return company


def charges_gst(party: Party | None) -> bool:
    """Every sale in India carries GST; an export (overseas customer) goes
    without it, under the company's LUT."""
    return party is not None and party.gst_type != Party.OVERSEAS


def place_state(party_state: str, bill_address: dict) -> str:
    """The place of supply: the state of the customer's billing address."""
    return (bill_address or {}).get("state_code") or party_state


# Credit limit --------------------------------------------------------------------


def balances(ledgers) -> dict[int, Decimal]:
    """Each ledger's balance today (debit positive): its opening balance plus its
    entries, in one query."""
    ledgers = list(ledgers)
    sums = {
        r["ledger"]: (r["d"] or ZERO) - (r["c"] or ZERO)
        for r in GLEntry.objects.filter(ledger__in=ledgers)
        .values("ledger")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    }
    return {lg.pk: lg.opening_signed + sums.get(lg.pk, ZERO) for lg in ledgers}


def credit_note(customer: Ledger, total: Decimal) -> str:
    """The warning when this order takes the customer past its credit limit
    (Sidharth, 2026-11-19: warn, but the order may still be saved and submitted)."""
    if not customer.credit_limit:
        return ""
    owing = balances([customer])[customer.pk]
    if owing + total <= customer.credit_limit:
        return ""
    return (
        f"Outstanding ₹{_money(owing)} of credit limit ₹{customer.credit_limit}; this order "
        f"takes it to ₹{_money(owing + total)}. You can still save and submit."
    )


# Reading --------------------------------------------------------------------------


def despatch_label(o: SalesOrder) -> str:
    """ "Sankrail-2 › Finished Goods", or the branch alone."""
    return f"{o.branch.name} › {o.area.name}" if o.area_id else o.branch.name


def _line_out(ln: SalesOrderLine, held: dict[int, Decimal] | None = None) -> dict:
    out = {
        "id": ln.pk,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "item_number": ln.item.item_number,
        "hsn": ln.item.hsn,
        "description": ln.description,
        "unit": ln.unit_id,
        "unit_name": ln.unit.short_name or ln.unit.name,
        "qty": _plain(ln.qty),
        "rate": _plain(ln.rate),
        "rate_source": ln.rate_source,
        "rate_locked": is_locked(ln.rate_source),
        "taxable": str(ln.taxable),
        "gst_rate": _plain(ln.gst_rate),
        "cgst": str(ln.cgst),
        "sgst": str(ln.sgst),
        "igst": str(ln.igst),
        "amount": str(ln.amount),
        "delivered_qty": _plain(ln.delivered_qty),
        "pending_qty": _plain(ZERO if ln.closed_at else max(ln.qty - ln.delivered_qty, ZERO)),
        "stock": ln.item.maintain_stock,
        "closed_at": ln.closed_at.isoformat() if ln.closed_at else None,
        "closed_by_name": ln.closed_by.display_name if ln.closed_by_id else "",
        "close_reason": ln.close_reason,
    }
    if held is not None and ln.item.maintain_stock:
        out["in_stock"] = _plain(
            stock.in_unit(ln.item, held.get(ln.item_id, ZERO), ln.unit_id).quantize(
                Decimal("0.001")
            )
        )
    return out


def _charge_out(c: SalesOrderCharge) -> dict:
    return {
        "id": c.pk,
        "item": c.item_id,
        "item_name": c.item.name,
        "sac": c.item.hsn,
        "basis": c.basis,
        "basis_label": c.get_basis_display(),
        "rate": _plain(c.rate),
        "amount": str(c.amount),
        "gst_rate": _plain(c.gst_rate),
        "cgst": str(c.cgst),
        "sgst": str(c.sgst),
        "igst": str(c.igst),
    }


def _mail_contacts(o: SalesOrder) -> list[dict]:
    found = {c.pk: c for c in PartyContact.objects.filter(pk__in=o.mail_to)}
    return [_contact_out(found[i]) for i in o.mail_to if i in found]


def _addresses_out(o: SalesOrder) -> dict:
    party = o.customer.party
    contacts = _mail_contacts(o)
    who = {
        "contact": next((c["name"] for c in contacts if c["name"]), ""),
        "phone": next((c["phone"] for c in contacts if c["phone"]), ""),
        "email": ", ".join(c["email"] for c in contacts if c["email"]),
    }
    bill = o.bill_address or {}
    ship = o.ship_address or {}
    return {
        "bill_from": _branch_address(o.bill_from) if o.bill_from else None,
        "customer": {
            "name": o.customer.name,
            **bill,
            "gstin": bill.get("gstin") or (party.gstin if party else ""),
            "fssai": _party_fssai(party, bill.get("label", "")),
            **who,
        },
        "ship_to": {"name": o.customer.name, **ship} if ship else None,
    }


def _order_out(o: SalesOrder, lines: bool = True) -> dict:
    party = o.customer.party
    data = {
        "id": o.pk,
        "company": o.company_id,
        "number": o.number,
        "status": o.status,
        "status_label": o.get_status_display(),
        # Why Submit held it, below the customer's Minimum Order Value (selling/hold.py).
        "hold": o.hold or None,
        "min_order_value": str(o.customer.min_order_value),
        "customer": o.customer_id,
        "customer_name": o.customer.name,
        "customer_gstin": party.gstin if party else "",
        "branch": o.branch_id,
        "branch_name": o.branch.name,
        "area": o.area_id,
        "area_name": o.area.name if o.area_id else "",
        "despatch_from": despatch_label(o),
        "bill_from": o.bill_from_id,
        "bill_from_name": o.bill_from.name if o.bill_from else "",
        "bill_address": o.bill_address,
        "ship_address": o.ship_address,
        "order_date": o.order_date,
        "delivery_date": o.delivery_date,
        "credit_term": o.credit_term_id,
        "credit_term_name": o.credit_term.name if o.credit_term else "",
        "transporter": o.transporter_id,
        "transporter_name": o.transporter.name if o.transporter else "By Customer",
        "salesman": o.salesman_id,
        "salesman_name": o.salesman.name if o.salesman else "",
        "mail_to": o.mail_to,
        "customer_po_no": o.customer_po_no,
        "customer_po_date": o.customer_po_date,
        "terms_set": o.terms_set_id,
        "terms_set_name": o.terms_set.name if o.terms_set else "",
        "terms": o.terms,
        "notes": o.notes,
        "interstate": o.interstate,
        "taxable_total": str(o.taxable_total),
        "cgst_total": str(o.cgst_total),
        "sgst_total": str(o.sgst_total),
        "igst_total": str(o.igst_total),
        "round_off": str(o.round_off),
        "total": str(o.total),
        "currency": "INR",
        "currency_symbol": "₹",
        "cancel_reason": o.cancel_reason,
        "created_by_name": o.created_by.display_name if o.created_by else "",
        "created_by_email": o.created_by.email if o.created_by else "",
        "created_by_phone": o.created_by.phone if o.created_by else "",
        "created_at": o.created_at,
        "submitted_at": o.submitted_at,
        "submitted_by_name": o.submitted_by.display_name if o.submitted_by else "",
        "line_count": len(o.lines.all()),
    }
    if lines:
        held = stock.on_hand([ln.item_id for ln in o.lines.all()], o.branch, o.area)
        data["lines"] = [_line_out(ln, held) for ln in o.lines.all()]
        codes = dict(
            PartyItemName.objects.filter(party=o.customer.party_id)
            .exclude(code="")
            .values_list("item_id", "code")
        )
        for row in data["lines"]:
            row["customer_code"] = codes.get(row["item"], "")
        data["charges"] = [_charge_out(c) for c in o.charges.all()]
        data["mail_contacts"] = _mail_contacts(o)
        data["addresses"] = _addresses_out(o)
        data["letterhead"] = _letterhead(o.company)
        data["amount_words"] = words.amount(o.total, "INR", "Indian Rupee")
        data["submitted_by_signature"] = (
            o.submitted_by.signature_url() if o.submitted_by and o.status != "draft" else ""
        )
        from selling.pick_lists import brief

        data["pick_lists"] = [brief(p) for p in o.pick_lists.order_by("id")]
        from selling.delivery import brief as note_brief

        data["delivery_notes"] = [note_brief(n) for n in o.delivery_notes.order_by("id")]
        planned = _planned(o, data["lines"])
        data["purchase_orders"], data["shortages"], data["stock_transfers"] = planned
        data["credit_warning"] = (
            credit_note(o.customer, o.total)
            if o.status in (SalesOrder.DRAFT, SalesOrder.ON_HOLD, *SalesOrder.OPEN)
            else ""
        )
    return data


def _planned(o: SalesOrder, lines: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """The draft purchase orders and stock transfers Submit (or "Purchase Orders
    for Shortages") made for this order, its shortage notes, and on each stock
    line its Expected (in the line's unit) and what covers a shortage."""
    pos = list(o.purchase_orders.select_related("supplier").prefetch_related("lines"))
    by_item = {}
    for po in pos:
        if po.status == "cancelled":
            continue
        for ln in po.lines.all():
            by_item.setdefault(ln.item_id, po)
    moves = {}
    transfers = list(o.stock_transfers.select_related("from_branch").prefetch_related("lines"))
    for t in transfers:
        if t.status == "cancelled":
            continue
        for ln in t.lines.all():
            moves.setdefault(ln.item_id, t)
    notes = {n["item"]: n for n in (o.shortages or [])}
    items = {ln.item_id: ln.item for ln in o.lines.all()}
    for row in lines:
        note = notes.get(row["item"])
        if note is None or not row["stock"]:
            continue
        row["expected"] = _plain(
            stock.in_unit(items[row["item"]], Decimal(note["expected"]), row["unit"]).quantize(
                Decimal("0.001")
            )
        )
        po = by_item.get(row["item"])
        moved = moves.get(row["item"])
        if moved is not None:
            row["cover"] = {
                "kind": "st",
                "text": moved.number or "Draft ST",
                "order": None,
                "transfer": moved.pk,
                "supplier": f"From {moved.from_branch.name}",
            }
        elif po is not None:
            label = po.number or "Draft PO"
            row["cover"] = {
                "kind": "po",
                "text": label,
                "order": po.pk,
                "supplier": po.supplier.name,
            }
        elif note["action"] != "ok":
            short = stock.in_unit(items[row["item"]], Decimal(note["short"]), row["unit"])
            text = {
                "make": f"To make {_plain(short.quantize(Decimal('0.001')))}",
                "transfer": "To transfer",
                "no_supplier": "No supplier",
                "failed": "No PO made",
                "unplanned": "Short, not planned",
                "po": "PO cancelled",
            }.get(note["action"], "")
            row["cover"] = {"kind": note["action"], "text": text, "order": None}
        else:
            row["cover"] = {"kind": "ok", "text": "In stock", "order": None}
    briefs = [
        {
            "id": po.pk,
            "number": po.number,
            "status": po.status,
            "status_label": po.get_status_display(),
            "supplier_name": po.supplier.name,
            "expected_date": po.expected_date,
        }
        for po in pos
    ]
    transfer_briefs = [
        {
            "id": t.pk,
            "number": t.number,
            "status": t.status,
            "status_label": t.get_status_display(),
            "from_branch_name": t.from_branch.name,
            "expected_date": t.expected_date,
        }
        for t in transfers
    ]
    return briefs, list(o.shortages or []), transfer_briefs


def _orders(company):
    return (
        SalesOrder.objects.filter(company=company)
        .select_related(
            "customer__party",
            "salesman",
            "submitted_by",
            "branch__company",
            "area",
            "bill_from__company",
            "credit_term",
            "transporter",
            "terms_set",
            "created_by",
        )
        .prefetch_related("lines__item__units", "lines__unit", "lines__closed_by", "charges__item")
    )


# Saving ---------------------------------------------------------------------------


class LineSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    # Left out: the item's sales description.
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=5000, trim_whitespace=False
    )
    unit = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6)
    rate = serializers.DecimalField(max_digits=18, decimal_places=6)
    rate_source = serializers.CharField(required=False, allow_blank=True, max_length=80)


class ChargeSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    basis = serializers.ChoiceField(choices=SalesOrderCharge.BASES)
    rate = serializers.DecimalField(max_digits=18, decimal_places=6)
    gst_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )


class OrderSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Ledger.objects.all())
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    area = serializers.PrimaryKeyRelatedField(
        queryset=WarehouseLocation.objects.all(), required=False, allow_null=True
    )
    order_date = serializers.DateField()
    delivery_date = serializers.DateField(required=False, allow_null=True)
    credit_term = serializers.PrimaryKeyRelatedField(
        queryset=CreditTerm.objects.all(), required=False, allow_null=True
    )
    transporter = serializers.PrimaryKeyRelatedField(
        queryset=CourierAccount.objects.all(), required=False, allow_null=True
    )
    salesman = serializers.PrimaryKeyRelatedField(
        queryset=SalesPerson.objects.all(), required=False, allow_null=True
    )
    # Left out: the despatch branch.
    bill_from = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True
    )
    # The names ("label") of the customer's addresses; left out: its billing one
    # and its shipping one.
    bill_address = serializers.CharField(required=False, allow_blank=True, max_length=60)
    ship_address = serializers.CharField(required=False, allow_blank=True, max_length=60)
    mail_to = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    customer_po_no = serializers.CharField(max_length=60, required=False, allow_blank=True)
    customer_po_date = serializers.DateField(required=False, allow_null=True)
    terms_set = serializers.PrimaryKeyRelatedField(
        queryset=TermsSet.objects.all(), allow_null=True, required=False
    )
    terms = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = LineSerializer(many=True)
    charges = ChargeSerializer(many=True, required=False)
    submit = serializers.BooleanField(required=False, default=False)


def _description(typed: str | None, item: Item) -> str:
    text = item.sales_description if typed is None else typed
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _split(tax: Decimal, interstate: bool) -> tuple[Decimal, Decimal, Decimal]:
    if interstate:
        return ZERO, ZERO, tax
    cgst = _money(tax / 2)
    return cgst, tax - cgst, ZERO


def _pick_address(places, wanted: str, flag: str):
    """The customer's address of that name; left out, the one ticked as its
    billing (shipping) address, else the first."""
    wanted = (wanted or "").strip().lower()
    if wanted:
        return next((a for a in places if a.label.lower() == wanted), None), True
    return next((a for a in places if getattr(a, flag)), places[0] if places else None), False


def _save_order(o: SalesOrder, data: dict) -> None:
    """Check and store a draft: header, lines, charges and totals."""
    errors: dict = {}
    customer, branch = data["customer"], data["branch"]
    if (
        customer.company_id != o.company_id
        or customer.party_side != "customer"
        or customer.party_id is None
    ):
        errors["customer"] = ["Pick a customer of this company."]
    elif not customer.is_active and customer.pk != o.customer_id:
        errors["customer"] = ["This customer is disabled."]
    if branch.company_id != o.company_id:
        errors["branch"] = ["Pick a branch of this company."]
    elif not branch.is_active and branch.pk != o.branch_id:
        errors["branch"] = ["This branch is closed."]
    elif branch.no_stock:
        errors["branch"] = [f"{branch.name} keeps no stock; pick a branch goods go out from."]
    area = data.get("area")
    if area is not None:
        if area.branch_id != branch.pk or area.kind != WarehouseLocation.AREA:
            errors["branch"] = ["Pick an area of the branch."]
        elif not area.is_active and area.pk != o.area_id:
            errors["branch"] = [f"The area {area.name} is disabled."]
    if errors:
        raise ValidationError(errors)
    party = customer.party
    salesman = data.get("salesman")
    if salesman is not None and salesman.pk != o.salesman_id:
        if not (salesman.is_active and salesman.is_salesman):
            errors["salesman"] = [f"{salesman.name} is not an active salesman."]
    mail_to = list(dict.fromkeys(data.get("mail_to") or []))
    known = PartyContact.objects.filter(pk__in=mail_to, party=party)
    if len(known) != len(mail_to):
        errors["mail_to"] = ["Pick contacts of the customer."]
    elif any(not c.email for c in known):
        errors["mail_to"] = ["A contact without an email cannot be mailed."]
    term = data.get("credit_term")
    if term is not None and not term.is_active and term.pk != o.credit_term_id:
        errors["credit_term"] = ["These credit terms are disabled."]
    transporter = data.get("transporter")
    if transporter is not None:
        if transporter.company_id != o.company_id:
            errors["transporter"] = ["Pick a transporter of this company."]
        elif not transporter.is_active and transporter.pk != o.transporter_id:
            errors["transporter"] = [f"{transporter.name} is disabled."]
    bill_from = data.get("bill_from") or branch
    if bill_from.company_id != o.company_id:
        errors["bill_from"] = ["Pick a branch of this company."]
    elif not bill_from.is_active and bill_from.pk != o.bill_from_id:
        errors["bill_from"] = ["This branch is closed."]
    places = list(party.addresses.all())
    bill_place, asked = _pick_address(places, data.get("bill_address"), "is_billing")
    if asked and bill_place is None:
        errors["bill_address"] = ["Pick one of the customer's addresses."]
    ship_place, asked = _pick_address(places, data.get("ship_address"), "is_shipping")
    if asked and ship_place is None:
        errors["ship_address"] = ["Pick one of the customer's addresses."]
    if "terms_set" in data:
        terms_set = data["terms_set"]
        if terms_set is not None and terms_set.kind != TermsSet.SALES:
            errors["terms_set"] = ["Pick a set of sales terms."]
        elif terms_set is not None and not terms_set.is_active and terms_set.pk != o.terms_set_id:
            errors["terms_set"] = ["These terms and conditions are disabled."]
    elif o.pk:
        terms_set = o.terms_set
    else:
        terms_set = terms_for(o.company, party, TermsSet.SALES)
        if terms_set is not None and "terms" not in data:
            data["terms"] = terms_set.text
    wanted = data.get("delivery_date")
    if not wanted:
        errors["delivery_date"] = ["Give the date the customer wants the goods by."]
    elif wanted < data["order_date"]:
        errors["delivery_date"] = ["The delivery date is before the order date."]
    if errors:
        raise ValidationError(errors)

    with_gst = charges_gst(party)
    bill = _party_address(bill_place) if bill_place else {}
    supply = place_state(party.state_code, bill)
    interstate = with_gst and (party.gst_type == Party.SEZ or supply != bill_from.state_code)
    allowed = set(items_for_party(party, "customer").values_list("pk", flat=True))
    rows, line_errors = [], []
    for n, line in enumerate(data["lines"], start=1):
        item = line["item"]
        problems = []
        unit_row = ItemUnit.objects.filter(item=item, unit_id=line["unit"]).first()
        if item.pk not in allowed and not (o.pk and o.lines.filter(item=item).exists()):
            problems.append(f"{item.name} is not sold to this customer.")
        if unit_row is None:
            problems.append(f"Pick one of the units of {item.name}.")
        if line["qty"] <= 0:
            problems.append("The quantity must be more than zero.")
        elif unit_row and unit_row.whole_numbers and line["qty"] != line["qty"].to_integral():
            problems.append(f"{unit_row.unit} is counted in whole numbers.")
        if line["rate"] < 0:
            problems.append("The rate cannot be below zero.")
        source = TYPED
        if unit_row is not None and line["qty"] > 0 and line["rate"] >= 0:
            # A rate from the customer's own price or price list is locked (Sidharth, 2026-11-26).
            source, locked = check_rate(
                party, item, unit_row.unit, line["qty"], data["order_date"], PriceList.SELLING,
                line["rate"],
            )  # fmt: skip
            if locked:
                problems.append(locked[0].upper() + locked[1:])
        gst = ZERO
        if with_gst:
            found = gst_rate_on(item, data["order_date"])
            if found is None:
                problems.append(
                    f"{item.name} has no GST rate on {data['order_date']:%d-%m-%Y}; "
                    "add one on the item."
                )
            else:
                gst = found
        if problems:
            line_errors.append(f"Line {n}: " + " ".join(problems))
            continue
        taxable = _money(line["qty"] * line["rate"])
        tax = _money(taxable * gst / 100)
        cgst, sgst, igst = _split(tax, interstate)
        rows.append(
            SalesOrderLine(
                position=n,
                item=item,
                description=_description(line.get("description"), item),
                unit_id=line["unit"],
                qty=line["qty"],
                rate=line["rate"],
                rate_source=source[:80],
                taxable=taxable,
                gst_rate=gst,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                amount=taxable + tax,
            )
        )
    if line_errors:
        raise ValidationError({"lines": line_errors})
    charges = _charges(data.get("charges") or [], rows, o, with_gst, interstate, data)

    o.customer, o.branch, o.area = customer, branch, area
    o.order_date, o.delivery_date = data["order_date"], wanted
    o.credit_term, o.transporter, o.salesman = term, transporter, salesman
    o.bill_from = bill_from
    o.bill_address = bill
    o.ship_address = _party_address(ship_place) if ship_place else {}
    o.terms_set = terms_set
    o.mail_to = mail_to
    o.customer_po_date = data.get("customer_po_date")
    for field in ("customer_po_no", "terms", "notes"):
        setattr(o, field, data.get(field, "").strip())
    o.interstate = interstate
    both = [*rows, *charges]
    o.taxable_total = sum((r.taxable for r in rows), ZERO) + sum((c.amount for c in charges), ZERO)
    o.cgst_total = sum((r.cgst for r in both), ZERO)
    o.sgst_total = sum((r.sgst for r in both), ZERO)
    o.igst_total = sum((r.igst for r in both), ZERO)
    exact = o.taxable_total + o.cgst_total + o.sgst_total + o.igst_total
    o.total = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    o.round_off = o.total - exact
    o.save()
    o.lines.all().delete()
    for r in rows:
        r.order = o
    SalesOrderLine.objects.bulk_create(rows)
    o.charges.all().delete()
    for c in charges:
        c.order = o
    SalesOrderCharge.objects.bulk_create(charges)


def _charges(given, rows, o: SalesOrder, with_gst: bool, interstate: bool, data):
    """The order's charges: each a service item marked as a sales charge, its
    amount from its basis, and GST at the rate picked (else the item's own)."""
    items_value = sum((r.taxable for r in rows), ZERO)
    units = {r.unit_id for r in rows}
    total_qty = sum((r.qty for r in rows), ZERO)
    allowed_rates = set(GstRate.objects.filter(is_active=True).values_list("rate", flat=True))
    out, errors = [], []
    for n, ch in enumerate(given, start=1):
        item, basis, rate = ch["item"], ch["basis"], ch["rate"]
        problems = []
        old = o.pk and o.charges.filter(item=item).exists()
        if not (item.sales_charge and item.item_type == Item.SERVICE) and not old:
            problems.append(f'{item.name} is not a service marked "Use as Sales Charge".')
        elif not item.is_active and not old:
            problems.append(f"{item.name} is disabled.")
        if rate < 0:
            problems.append("The amount or rate cannot be below zero.")
        amount = ZERO
        if basis == SalesOrderCharge.FIXED:
            amount = _money(rate)
        elif basis == SalesOrderCharge.PERCENT:
            amount = _money(items_value * rate / 100)
        elif len(units) > 1:
            problems.append('"Per unit" needs every item line in the same unit.')
        else:
            amount = _money(total_qty * rate)
        gst = ZERO
        if with_gst:
            if ch.get("gst_rate") is not None:
                gst = ch["gst_rate"]
                if gst not in allowed_rates:
                    problems.append(f"{gst.normalize():f}% is not a GST rate in the list.")
            else:
                found = gst_rate_on(item, data["order_date"])
                if found is None:
                    problems.append(f"{item.name} has no GST rate; pick one.")
                else:
                    gst = found
        if problems:
            errors.append(f"Charge {n}: " + " ".join(problems))
            continue
        cgst, sgst, igst = _split(_money(amount * gst / 100), interstate)
        out.append(
            SalesOrderCharge(
                position=n,
                item=item,
                basis=basis,
                rate=rate,
                amount=amount,
                gst_rate=gst,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
            )
        )
    if errors:
        raise ValidationError({"charges": errors})
    return out


def _submit(o: SalesOrder, user) -> None:
    if not user.can(SUBMIT):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    attachments.require_file(o, "sales_order")
    if not o.lines.exists():
        raise ValidationError({"lines": ["Add at least one item before submitting."]})
    if not o.delivery_date:
        raise ValidationError({"delivery_date": ["Give the date the customer wants the goods by."]})
    fiscal.assert_open(o.company, o.order_date)
    was_held = o.status == SalesOrder.ON_HOLD
    if not o.number:  # a held order keeps the number it was given
        o.number = numbering.next_document_number(o.company, "sales_order", o.order_date, o.branch)
    o.submitted_at = timezone.now()
    o.submitted_by = user
    # Below the customer's Minimum Order Value: On Hold (Sidharth, 2026-11-25).
    from selling import hold

    if hold.below_minimum(o):
        hold.put_on_hold(o, user)
        return
    if was_held:
        hold.end_hold(o, user, "Submitted again at or above the minimum")
    else:
        o.status = SalesOrder.ORDERED
        o.save()
    go_ahead(o, user)


def go_ahead(o: SalesOrder, user) -> None:
    """What an order sets going once it is Ordered."""
    # The stores' pick list, with bins and batches chosen (Sidharth, 2026-11-19).
    from selling import picking

    picking.make(o, user)
    # Draft purchase orders for what the branch buys and will run short of
    # (Sidharth, 2026-11-21); items to make are noted until manufacturing is built.
    from buying import planning

    planning.for_sales_order(o, user)


def _order(request, pk: int, lock: bool = False) -> SalesOrder:
    rows = SalesOrder.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    o = rows.select_related("company").first()
    if o is None or "sales" not in o.company.modules:
        raise NotFound("No such sales order.")
    return o


def _fresh(o: SalesOrder) -> dict:
    return _order_out(_orders(o.company).get(pk=o.pk))


def order_status(o: SalesOrder) -> None:
    """Ordered, part delivered or delivered, from the stock lines; a line closed
    counts as done. Delivery notes call this when they are built."""
    if o.status not in (*SalesOrder.OPEN, SalesOrder.DELIVERED, SalesOrder.CLOSED):
        return
    lines = [ln for ln in o.lines.select_related("item") if ln.item.maintain_stock]
    done = all(ln.closed_at or ln.delivered_qty >= ln.qty for ln in lines)
    some = any(ln.delivered_qty > 0 for ln in lines)
    if done and lines and any(ln.closed_at for ln in lines) and not some:
        o.status = SalesOrder.CLOSED
    elif done and lines:
        o.status = SalesOrder.DELIVERED
    elif some:
        o.status = SalesOrder.PART_DELIVERED
    else:
        o.status = SalesOrder.ORDERED
    o.save(update_fields=["status"])


VIEWS = {"open", "draft", "hold", "done", "cancelled", "all"}


class OrderListView(APIView):
    """GET ?view=open|draft|done|cancelled|all. POST makes a draft (or, with
    "submit": true, an order)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = _orders(company)
        view = request.query_params.get("view", "open")
        if view == "open":
            rows = rows.filter(status__in=[SalesOrder.DRAFT, SalesOrder.ON_HOLD, *SalesOrder.OPEN])
        elif view == "hold":
            rows = rows.filter(status=SalesOrder.ON_HOLD)
        elif view == "draft":
            rows = rows.filter(status=SalesOrder.DRAFT)
        elif view == "done":
            rows = rows.filter(status__in=[SalesOrder.DELIVERED, SalesOrder.CLOSED])
        elif view == "cancelled":
            rows = rows.filter(status=SalesOrder.CANCELLED)
        return Response([_order_out(o, lines=False) for o in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CREATE)
        company = _company(request, pk)
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        o = SalesOrder(company=company, created_by=request.user)
        _save_order(o, data)
        if data.get("submit"):
            if refused := attachments.refuse_submit(o, "sales_order"):
                return refused
            _submit(o, request.user)
        return Response(_fresh(o), status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    """GET one order; PATCH a draft or an order On Hold (with "submit": true,
    also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(_fresh(_order(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        o = _order(request, pk, lock=True)
        if o.status not in (SalesOrder.DRAFT, SalesOrder.ON_HOLD):
            raise ValidationError(
                {"detail": "A submitted order cannot be changed. Cancel it and make a new one."}
            )
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save_order(o, data)
        if data.get("submit"):
            if refused := attachments.refuse_submit(o, "sales_order"):
                return refused
            _submit(o, request.user)
        return Response(_fresh(o))


class OrderSubmitView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk, lock=True)
        if o.status not in (SalesOrder.DRAFT, SalesOrder.ON_HOLD):
            raise ValidationError({"detail": "This order is already submitted."})
        if refused := attachments.refuse_submit(o, "sales_order"):
            return refused
        _submit(o, request.user)
        return Response(_fresh(o))


class OrderPlanView(APIView):
    """POST: "Purchase Orders for Shortages" on a submitted order: the check
    Submit runs, again (e.g. after a line is added or a draft PO was cancelled).
    Goods already on order count as Incoming, so nothing is ordered twice."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk, lock=True)
        if o.status not in SalesOrder.OPEN:
            raise ValidationError({"detail": "Only an open, submitted order is planned."})
        from buying import planning

        planning.for_sales_order(o, request.user)
        return Response(_fresh(o))


class OrderCancelView(APIView):
    """POST {reason}. A draft, or an order nothing has been delivered against."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CANCEL)
        o = _order(request, pk, lock=True)
        if o.status == SalesOrder.CANCELLED:
            raise ValidationError({"detail": "This order is already cancelled."})
        if o.status not in (SalesOrder.DRAFT, SalesOrder.ON_HOLD, SalesOrder.ORDERED):
            raise ValidationError(
                {"detail": "Goods have gone out against this order; it cannot be cancelled."}
            )
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        o.status = SalesOrder.CANCELLED
        o.cancel_reason = reason[:200]
        o.save()
        # Its pick lists free the stock they kept aside.
        from selling.pick_lists import cancel

        for p in o.pick_lists.filter(status__in=PickList.HOLDING):
            cancel(p, request.user, "The sales order was cancelled.")
        return Response(_fresh(o))


class OrderLineCloseView(APIView):
    """POST {reason} closes a line whose balance will not be sent; POST
    {"reopen": true} opens it again."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int, line: int):
        _check(request, SUBMIT)
        o = _order(request, pk, lock=True)
        ln = o.lines.select_related("item", "unit").filter(pk=line).first()
        if ln is None:
            raise NotFound("No such line on this order.")
        if o.status not in (*SalesOrder.OPEN, SalesOrder.DELIVERED, SalesOrder.CLOSED):
            raise ValidationError({"detail": "Only a submitted order's lines can be closed."})
        if request.data.get("reopen"):
            if not ln.closed_at:
                raise ValidationError({"detail": "This line is not closed."})
            change = f"Line {ln.position} {ln.item.name} reopened"
            ln.closed_at, ln.closed_by, ln.close_reason = None, None, ""
        else:
            if ln.closed_at:
                raise ValidationError({"detail": "This line is already closed."})
            if not ln.item.maintain_stock or ln.delivered_qty >= ln.qty:
                raise ValidationError({"detail": "Nothing is pending on this line."})
            reason = str(request.data.get("reason", "")).strip()
            if not reason:
                raise ValidationError({"reason": ["Say why the rest will not be sent."]})
            change = (
                f"Line {ln.position} {ln.item.name} closed, "
                f"{_plain(ln.qty - ln.delivered_qty)} {ln.unit.short_name} not going: "
                f"{reason[:200]}"
            )
            ln.closed_at, ln.closed_by, ln.close_reason = timezone.now(), request.user, reason[:200]
        ln.save(update_fields=["closed_at", "closed_by", "close_reason"])
        order_status(o)
        AuditEntry.objects.create(
            user=request.user,
            user_name=request.user.display_name[:150],
            company=o.company,
            record_type="sales_order",
            record_id=o.pk,
            record_name=str(o)[:200],
            action=AuditEntry.UPDATE,
            changes=[{"field": "line_closed", "label": "Line", "old": None, "new": change}],
        )
        return Response(_fresh(o))


# What the form needs ----------------------------------------------------------------


def _despatch_places(company) -> list[dict]:
    """Each stock-holding branch, then its areas (Sidharth, 2026-11-19): the
    "Despatch From" picker's rows."""
    out = []
    rows = WarehouseLocation.objects.filter(branch__company=company, kind=WarehouseLocation.AREA)
    racks = {}
    for r in WarehouseLocation.objects.filter(
        branch__company=company, kind=WarehouseLocation.RACK, is_active=True
    ).exclude(parent=None):
        racks[r.parent_id] = racks.get(r.parent_id, 0) + 1
    for b in company.branches.filter(no_stock=False).order_by("name"):
        out.append(
            {"value": f"b{b.pk}", "branch": b.pk, "area": None, "label": b.name,
             "hint": "whole branch", "is_active": b.is_active}
        )  # fmt: skip
        for a in sorted((a for a in rows if a.branch_id == b.pk), key=lambda a: a.name.lower()):
            n = racks.get(a.pk, 0)
            out.append(
                {
                    "value": f"a{a.pk}",
                    "branch": b.pk,
                    "area": a.pk,
                    "label": f"{b.name} › {a.name}",
                    "hint": f"area, {n} rack{'s' if n != 1 else ''}" if n else "area",
                    "is_active": a.is_active and b.is_active,
                }
            )
    return out


class OrderSetupView(APIView):
    """GET: the company's customers, branches and areas, salesmen and the rest,
    for the form's pickers."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        customers = list(
            picked_ledgers(
                Ledger.objects.filter(company=company, party_side="customer", party__isnull=False),
                request.query_params,
            )
            .select_related("party__credit_term", "party__sales_terms")
            .prefetch_related("party__contacts", "party__addresses")
            .order_by("name")
        )
        owing = balances(customers)
        today = timezone.localdate()
        return Response(
            {
                "company_name": company.name,
                "charge_items": [
                    {
                        "id": i.pk,
                        "name": i.name,
                        "sac": i.hsn,
                        "gst_rate": _plain(r) if (r := gst_rate_on(i, today)) is not None else None,
                    }
                    for i in Item.objects.filter(
                        sales_charge=True, item_type=Item.SERVICE, is_active=True
                    ).order_by("name")
                ],
                "gst_rates": [
                    _plain(r)
                    for r in GstRate.objects.filter(is_active=True).values_list("rate", flat=True)
                ],
                # Where "Create …" in the customer picker adds a new customer's ledger.
                "customer_group": LedgerGroup.objects.filter(company=company, code="sundry_debtors")
                .values_list("pk", flat=True)
                .first(),
                "customers": [
                    {
                        "id": c.pk,
                        "name": c.name,
                        "is_active": c.is_active,
                        "customer_number": c.party.customer_number,
                        "gstin": c.party.gstin,
                        "gst_type": c.party.gst_type,
                        "gst_type_label": c.party.get_gst_type_display(),
                        "state_code": c.party.state_code,
                        "credit_term": c.party.credit_term_id,
                        "transporter": c.preferred_transporter_id,
                        "salesman": c.salesman_id,
                        "credit_limit": str(c.credit_limit),
                        "min_order_value": str(c.min_order_value),
                        "outstanding": str(_money(owing.get(c.pk, ZERO))),
                        "terms_set": c.party.sales_terms_id
                        if c.party.sales_terms and c.party.sales_terms.is_active
                        else None,
                        "charges_gst": charges_gst(c.party),
                        "contacts": [_contact_out(x) for x in c.party.contacts.all()],
                        "addresses": [
                            {
                                **_party_address(a),
                                "is_billing": a.is_billing,
                                "is_shipping": a.is_shipping,
                            }
                            for a in c.party.addresses.all()
                        ],
                    }
                    for c in customers
                ],
                "despatch": _despatch_places(company),
                "branches": [
                    {
                        "id": b.pk,
                        "name": b.name,
                        "state_code": b.state_code,
                        "is_active": b.is_active,
                        "no_stock": b.no_stock,
                        "address_block": _branch_address(b),
                    }
                    for b in Branch.objects.filter(company=company).select_related("company")
                ],
                "salesmen": []
                if paging.lean_setup(request.query_params)
                else [
                    {"id": p.pk, "name": p.name, "is_active": p.is_active}
                    for p in SalesPerson.objects.filter(is_salesman=True)
                ],
                "credit_terms": [
                    {"id": t.pk, "name": t.name, "is_active": t.is_active}
                    for t in CreditTerm.objects.all()
                ],
                "transporters": []
                if paging.lean_setup(request.query_params)
                else [
                    {"id": t.pk, "name": t.name, "is_active": t.is_active}
                    for t in company.courier_accounts.order_by("name")
                ],
                "terms_sets": [
                    {"id": t.pk, "name": t.name, "is_active": t.is_active, "text": t.text}
                    for t in TermsSet.objects.filter(kind=TermsSet.SALES)
                ],
                "default_terms": company.sales_terms_id
                if company.sales_terms and company.sales_terms.is_active
                else None,
            }
        )


def _customer(company, value) -> Ledger:
    try:
        return Ledger.objects.select_related("party").get(
            pk=int(value), company=company, party_side="customer", party__isnull=False
        )
    except (TypeError, ValueError, Ledger.DoesNotExist):
        raise ValidationError({"customer": ["Pick a customer of this company."]}) from None


def _day(value) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value) if value else timezone.localdate()
    except ValueError:
        raise ValidationError({"date": ["Give the date as YYYY-MM-DD."]}) from None


def _place(company, params) -> tuple[Branch | None, WarehouseLocation | None]:
    """?branch=ID&area=ID: where stock is counted."""
    branch = Branch.objects.filter(company=company, pk=params.get("branch") or 0).first()
    area = None
    if branch is not None and params.get("area"):
        area = WarehouseLocation.objects.filter(
            branch=branch, kind=WarehouseLocation.AREA, pk=params.get("area") or 0
        ).first()
    return branch, area


class OrderItemsView(APIView):
    """GET ?customer=LEDGER&date=YYYY-MM-DD&branch=ID&area=ID: the items that may be
    sold to the customer, with their units, GST rate on the date, the customer's
    own name, and the stock at the branch or area (in the stock unit)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        customer = _customer(company, request.query_params.get("customer"))
        day = _day(request.query_params.get("date"))
        branch, area = _place(company, request.query_params)
        items = list(
            picked(items_for_party(customer.party, "customer"), request.query_params)
            .select_related("sales_unit", "stock_unit")
            .prefetch_related("units__unit", "gst_rates")
        )
        held = stock.on_hand(items, branch, area) if branch else {}
        theirs = {
            n.item_id: n
            for n in PartyItemName.objects.filter(party=customer.party).only(
                "item_id", "name", "code"
            )
        }
        out = []
        for i in items:
            rates = [r for r in i.gst_rates.all() if r.valid_from <= day]
            rate = max(rates, key=lambda r: r.valid_from).rate if rates else None
            name = theirs.get(i.pk)
            units = list(i.units.all())
            out.append(
                {
                    "id": i.pk,
                    "name": i.name,
                    "item_number": i.item_number,
                    "hsn": i.hsn,
                    "description": i.sales_description,
                    "maintain_stock": i.maintain_stock,
                    "sales_unit": i.sales_unit_id or i.stock_unit_id,
                    "units": [
                        {
                            "unit": u.unit_id,
                            "name": u.unit.short_name or u.unit.name,
                            "whole_numbers": u.whole_numbers,
                            "factor": _plain(u.factor),
                        }
                        for u in units
                    ],
                    "gst_rate": _plain(rate) if rate is not None else None,
                    # In the stock unit; the screen shows it in the line's unit.
                    "in_stock": _plain(held.get(i.pk, ZERO)) if i.maintain_stock else None,
                    "customer_name": name.name if name else "",
                    "customer_code": name.code if name else "",
                }
            )
        return Response(out)


def find_sale_rate(party, item, unit_row, qty, day) -> tuple[Decimal | None, str]:
    """The customer's own price, else its price list, else none: the rate is then
    typed (Sidharth, 2026-11-26: MRP never comes to a sales order). The source is
    "own", the list's name or ""."""
    return find_rate(party, item, unit_row.unit, qty, day, PriceList.SELLING)


def source_words(source: str) -> str:
    return price_source_words(source, PriceList.SELLING)


class OrderRateView(APIView):
    """GET ?customer=LEDGER&item=ID&unit=ID&qty=N&date=YYYY-MM-DD: the rate and
    where it came from."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        customer = _customer(company, request.query_params.get("customer"))
        params = request.query_params
        item = Item.objects.filter(pk=params.get("item", "0") or 0).first()
        unit_row = ItemUnit.objects.filter(item=item, unit_id=params.get("unit") or 0).first()
        if item is None or unit_row is None:
            raise ValidationError({"item": ["Pick an item and one of its units."]})
        try:
            qty = Decimal(params.get("qty") or "1")
        except ArithmeticError:
            raise ValidationError({"qty": ["Give a number."]}) from None
        rate, source = find_sale_rate(
            customer.party, item, unit_row, max(qty, ZERO), _day(params.get("date"))
        )
        return Response(
            {
                "rate": _plain(rate) if rate is not None else None,
                "source": source,
                "source_label": source_words(source),
                "locked": rate is not None,
            }
        )


class CreditView(APIView):
    """GET ?customer=LEDGER&total=N: the credit limit warning for an order of
    that total, or "" (Sidharth, 2026-11-19: a warning, never a refusal)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        customer = _customer(company, request.query_params.get("customer"))
        try:
            total = Decimal(request.query_params.get("total") or "0")
        except ArithmeticError:
            total = ZERO
        return Response({"warning": credit_note(customer, total)})
