"""Purchase orders (Entry > Purchase > Purchase Order).

Who may do what (standard roles, accounts/roles.py):
- `purchase.view` sees the orders; `purchase.create` makes and changes drafts;
  `purchase.submit` submits (numbers and fixes) them; `purchase.cancel` cancels.
- All of it needs the company's Purchase module (decision 0014).

Nothing here posts to the ledgers.
"""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from buying.models import PurchaseOrder, PurchaseOrderLine
from core import fiscal, india, numbering
from core.api import Signed
from core.api import _company as _visible_company
from core.companies import visible_companies
from core.items import gst_rate_on
from core.models import (
    Branch,
    Certificate,
    CreditTerm,
    Item,
    ItemUnit,
    Ledger,
    LedgerGroup,
    Party,
    PartyAddress,
    PartyContact,
    PartyItemName,
    PriceList,
    TermsSet,
)
from core.parties import items_for_party
from core.price_lists import find_rate
from core.terms import terms_for
from shipping.models import CourierAccount
from tenancy.context import tenant_atomic

VIEW, CREATE, SUBMIT, CANCEL = (f"purchase.{a}" for a in ("view", "create", "submit", "cancel"))
PAISE = Decimal("0.01")
RUPEE = Decimal("1")


def _check(request, code: str) -> None:
    if not request.user.can(code):
        raise PermissionDenied("Your role does not allow this.")


def _company(request, pk: int):
    company = _visible_company(request, pk)
    if "purchase" not in company.modules:
        raise NotFound("This company does not use the Purchase module.")
    return company


def _money(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def _plain(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def charges_gst(party: Party | None) -> bool:
    """A regular registered supplier charges GST on its bill; an unregistered or
    composition supplier does not, and an import pays IGST at customs."""
    return party is not None and party.gst_type == Party.REGULAR


# Reading --------------------------------------------------------------------


# Addresses ---------------------------------------------------------------------


def _valid(today: datetime.date, valid_until) -> bool:
    return valid_until is None or valid_until >= today


def _branch_fssai(b: Branch) -> str:
    """The branch's own FSSAI licence, else the company-wide one (not lapsed)."""
    today = timezone.localdate()
    rows = Certificate.objects.filter(company_id=b.company_id, kind=Certificate.FSSAI).filter(
        Q(branch=b) | Q(branch__isnull=True)
    )
    found = sorted(
        (c for c in rows if _valid(today, c.valid_until)), key=lambda c: c.branch_id is None
    )
    return found[0].number if found else ""


def _party_fssai(party: Party | None, label: str = "") -> str:
    """The party's FSSAI licence: the one for this address if any, else its main one."""
    if party is None:
        return ""
    today = timezone.localdate()
    rows = [
        d
        for d in party.documents.filter(kind="fssai", is_active=True)
        if d.number and _valid(today, d.valid_until)
    ]
    rows.sort(key=lambda d: (d.address_label.lower() != label.lower(), d.address_label != ""))
    return rows[0].number if rows else ""


def _branch_address(b: Branch) -> dict:
    """A branch of ours as an address block: its own details, else the company's."""
    c = b.company
    return {
        "name": c.name,
        "label": b.name,
        "address": b.address or c.address,
        "city": b.city or (c.city if not b.address else ""),
        "pincode": b.pincode or (c.pincode if not b.address else ""),
        "state_code": b.state_code,
        "state": india.STATES.get(b.state_code, ""),
        "country": "India",
        "gstin": b.gstin or c.gstin,
        "fssai": _branch_fssai(b),
        "contact": b.contact_person or c.contact_person,
        "phone": b.phone or c.phone,
        "email": b.email or c.email,
    }


def _party_address(a: PartyAddress) -> dict:
    """A supplier's address as kept on the order."""
    return {
        "label": a.label,
        "address": a.address,
        "city": a.city,
        "pincode": a.pincode,
        "state_code": a.state_code,
        "state": india.STATES.get(a.state_code, ""),
        "country": a.country,
        "gstin": a.gstin,
    }


def _default_bill_to(company_id: int) -> Branch | None:
    branches = Branch.objects.filter(company_id=company_id, is_active=True)
    return (
        branches.filter(default_billing=True).first()
        or branches.filter(is_head_office=True).first()
    )


def _addresses_out(o: PurchaseOrder) -> dict:
    """Bill To, Ship To and the supplier's address, as the order shows and prints them."""
    party = o.supplier.party
    kept = o.supplier_address or {}
    supplier = {
        "name": o.supplier.name,
        **kept,
        "gstin": kept.get("gstin") or (party.gstin if party else ""),
        "fssai": _party_fssai(party, kept.get("label", "")),
    }
    return {
        "bill_to": _branch_address(o.bill_to) if o.bill_to else None,
        "ship_to": _branch_address(o.branch),
        "supplier": supplier,
    }


def _line_out(ln: PurchaseOrderLine) -> dict:
    return {
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
        "discount_pct": _plain(ln.discount_pct),
        "taxable": str(ln.taxable),
        "gst_rate": _plain(ln.gst_rate),
        "cgst": str(ln.cgst),
        "sgst": str(ln.sgst),
        "igst": str(ln.igst),
        "amount": str(ln.amount),
        "received_qty": _plain(ln.received_qty),
    }


def _contact_out(c: PartyContact) -> dict:
    return {
        "id": c.pk,
        "name": c.name,
        "designation": c.designation,
        "phone": c.phone,
        "email": c.email,
        "is_primary": c.is_primary,
        "kinds": c.kinds,
    }


def _mail_contacts(o: PurchaseOrder) -> list[dict]:
    """The contacts ticked for mail or WhatsApp as they are now, in the order they
    were ticked, each saying which of the two it gets."""
    ids = list(dict.fromkeys([*o.mail_to, *o.whatsapp_to]))
    if not ids:
        return []
    found = {c.pk: c for c in PartyContact.objects.filter(pk__in=ids)}
    out = []
    for pk in ids:
        if c := found.get(pk):
            agent = o.agent is not None and c.party_id == o.agent.party_id
            out.append(
                {
                    **_contact_out(c),
                    "of": "Agent" if agent else "Supplier",
                    "mail": pk in o.mail_to,
                    "whatsapp": pk in o.whatsapp_to,
                }
            )
    return out


def _with_agent_user(o: PurchaseOrder, rows: list[dict]) -> list[dict]:
    u = o.agent_user
    if u is None or not o.mail_agent_user:
        return rows
    me = {"id": None, "name": u.display_name, "designation": "Employee", "phone": ""}
    me |= {"email": u.email, "is_primary": False, "kinds": [], "of": "Agent"}
    return [*rows, {**me, "mail": True, "whatsapp": False}]


def _order_out(o: PurchaseOrder, lines: bool = True) -> dict:
    party = o.supplier.party
    data = {
        "id": o.pk,
        "company": o.company_id,
        "number": o.number,
        "status": o.status,
        "status_label": o.get_status_display(),
        "supplier": o.supplier_id,
        "supplier_name": o.supplier.name,
        "supplier_gstin": party.gstin if party else "",
        "branch": o.branch_id,
        "branch_name": o.branch.name,
        "bill_to": o.bill_to_id,
        "bill_to_name": o.bill_to.name if o.bill_to else "",
        "supplier_address": o.supplier_address,
        "order_date": o.order_date,
        "expected_date": o.expected_date,
        "credit_term": o.credit_term_id,
        "credit_term_name": o.credit_term.name if o.credit_term else "",
        "transporter": o.transporter_id,
        "transporter_name": o.transporter.name if o.transporter else "By Supplier",
        "agent": o.agent_id,
        "agent_name": o.agent.name if o.agent else "",
        "agent_user": o.agent_user_id,
        "agent_user_name": o.agent_user.display_name if o.agent_user else "",
        "mail_agent_user": o.mail_agent_user,
        "mail_to": o.mail_to,
        "whatsapp_to": o.whatsapp_to,
        "mail_contacts": _with_agent_user(o, _mail_contacts(o)),
        "supplier_ref": o.supplier_ref,
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
        "cancel_reason": o.cancel_reason,
        "created_by_name": o.created_by.display_name if o.created_by else "",
        "created_at": o.created_at,
        "submitted_at": o.submitted_at,
        "line_count": len(o.lines.all()),
    }
    if lines:
        data["lines"] = [_line_out(ln) for ln in o.lines.all()]
        data["addresses"] = _addresses_out(o)
    return data


def _orders(company):
    return (
        PurchaseOrder.objects.filter(company=company)
        .select_related(
            "supplier__party",
            "agent",
            "agent_user",
            "branch__company",
            "bill_to__company",
            "credit_term",
            "transporter",
            "terms_set",
            "created_by",
        )
        .prefetch_related("lines__item", "lines__unit")
    )


# Saving ---------------------------------------------------------------------


class LineSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    # Left out: the item's purchase description.
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=5000, trim_whitespace=False
    )
    unit = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6)
    rate = serializers.DecimalField(max_digits=18, decimal_places=6)
    discount_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=Decimal("0")
    )


class OrderSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Ledger.objects.all())
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    order_date = serializers.DateField()
    expected_date = serializers.DateField(required=False, allow_null=True)
    credit_term = serializers.PrimaryKeyRelatedField(
        queryset=CreditTerm.objects.all(), required=False, allow_null=True
    )
    transporter = serializers.PrimaryKeyRelatedField(
        queryset=CourierAccount.objects.all(), required=False, allow_null=True
    )
    # Left out: the company's default billing branch.
    bill_to = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True
    )
    # The name ("label") of one of the supplier's addresses; left out: its billing one.
    supplier_address = serializers.CharField(required=False, allow_blank=True, max_length=60)
    agent = serializers.PrimaryKeyRelatedField(
        queryset=Ledger.objects.all(), required=False, allow_null=True
    )
    agent_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True
    )
    mail_to = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    whatsapp_to = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    mail_agent_user = serializers.BooleanField(required=False, default=False)
    supplier_ref = serializers.CharField(max_length=80, required=False, allow_blank=True)
    # Left out: the supplier's set, else the company's default, with its text
    # when no text is sent.
    terms_set = serializers.PrimaryKeyRelatedField(
        queryset=TermsSet.objects.all(), allow_null=True, required=False
    )
    terms = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = LineSerializer(many=True)
    # true: submit straight after saving (the "Submit" button on a new order).
    submit = serializers.BooleanField(required=False, default=False)


def _description(typed: str | None, item: Item) -> str:
    """The line's description as plain lines; the item's own when none is sent."""
    text = item.purchase_description if typed is None else typed
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _save_order(o: PurchaseOrder, data: dict) -> None:
    """Check and store a draft: header, lines and totals."""
    errors: dict = {}
    supplier, branch = data["supplier"], data["branch"]
    if (
        supplier.company_id != o.company_id
        or supplier.party_side != "supplier"
        or supplier.party_id is None
    ):
        errors["supplier"] = ["Pick a supplier of this company."]
    elif not supplier.is_active and supplier.pk != o.supplier_id:
        errors["supplier"] = ["This supplier is disabled."]
    if branch.company_id != o.company_id:
        errors["branch"] = ["Pick a branch of this company."]
    elif not branch.is_active and branch.pk != o.branch_id:
        errors["branch"] = ["This branch is closed."]
    agent = data.get("agent")
    if agent is not None:
        if (
            agent.company_id != o.company_id
            or agent.party_side != "supplier"
            or agent.party_id is None
        ):
            errors["agent"] = ["Pick the agent from this company's suppliers."]
        elif agent.pk == supplier.pk:
            errors["agent"] = ["The agent is not the supplier itself."]
        elif not agent.is_active and agent.pk != o.agent_id:
            errors["agent"] = ["This agent is disabled."]
    agent_user = data.get("agent_user")
    if agent_user is not None:
        if agent is not None:
            errors["agent_user"] = ["Pick one agent: a supplier firm or an employee."]
        elif not agent_user.is_active and agent_user.pk != o.agent_user_id:
            errors["agent_user"] = ["This employee no longer has access."]
    mail_to = list(dict.fromkeys(data.get("mail_to") or []))
    parties = [p for p in (supplier.party_id, agent.party_id if agent else None) if p]
    known = PartyContact.objects.filter(pk__in=mail_to, party_id__in=parties)
    if len(known) != len(mail_to):
        errors["mail_to"] = ["Pick contacts of the supplier or the agent."]
    elif any(not c.email for c in known):
        errors["mail_to"] = ["A contact without an email cannot be mailed."]
    whatsapp_to = list(dict.fromkeys(data.get("whatsapp_to") or []))
    known = PartyContact.objects.filter(pk__in=whatsapp_to, party_id__in=parties)
    if len(known) != len(whatsapp_to):
        errors["whatsapp_to"] = ["Pick contacts of the supplier or the agent."]
    elif any(not c.phone for c in known):
        errors["whatsapp_to"] = ["A contact without a phone number cannot get WhatsApp."]
    term = data.get("credit_term")
    if term is not None and not term.is_active and term.pk != o.credit_term_id:
        errors["credit_term"] = ["These credit terms are disabled."]
    transporter = data.get("transporter")
    if transporter is not None:
        if transporter.company_id != o.company_id:
            errors["transporter"] = ["Pick a transporter of this company."]
        elif not transporter.is_active and transporter.pk != o.transporter_id:
            errors["transporter"] = [f"{transporter.name} is disabled."]
    bill_to = data.get("bill_to") or _default_bill_to(o.company_id)
    if bill_to is not None:
        if bill_to.company_id != o.company_id:
            errors["bill_to"] = ["Pick a branch of this company."]
        elif not bill_to.is_active and bill_to.pk != o.bill_to_id:
            errors["bill_to"] = ["This branch is closed."]
    places = list(supplier.party.addresses.all()) if supplier.party_id else []
    wanted = (data.get("supplier_address") or "").strip().lower()
    place = next((a for a in places if a.label.lower() == wanted), None) if wanted else None
    if wanted and place is None:
        errors["supplier_address"] = ["Pick one of the supplier's addresses."]
    elif place is None:
        place = next((a for a in places if a.is_billing), places[0] if places else None)
    if "terms_set" in data:
        terms_set = data["terms_set"]
        if terms_set is not None and terms_set.kind != TermsSet.PURCHASE:
            errors["terms_set"] = ["Pick a set of purchase terms."]
        elif terms_set is not None and not terms_set.is_active and terms_set.pk != o.terms_set_id:
            errors["terms_set"] = ["These terms and conditions are disabled."]
    elif o.pk:
        terms_set = o.terms_set
    else:
        terms_set = terms_for(o.company, supplier.party, TermsSet.PURCHASE)
        if terms_set is not None and "terms" not in data:
            data["terms"] = terms_set.text
    expected = data.get("expected_date")
    if expected and expected < data["order_date"]:
        errors["expected_date"] = ["The expected delivery date is before the order date."]
    if errors:
        raise ValidationError(errors)

    party = supplier.party
    with_gst = charges_gst(party)
    interstate = with_gst and party.state_code != branch.state_code
    allowed = set(items_for_party(party, "supplier").values_list("pk", flat=True))
    rows, line_errors = [], []
    for n, line in enumerate(data["lines"], start=1):
        item = line["item"]
        problems = []
        unit_row = ItemUnit.objects.filter(item=item, unit_id=line["unit"]).first()
        if item.pk not in allowed and not o.lines.filter(item=item).exists():
            problems.append(f"{item.name} is not bought from this supplier.")
        if unit_row is None:
            problems.append(f"Pick one of the units of {item.name}.")
        if line["qty"] <= 0:
            problems.append("The quantity must be more than zero.")
        elif unit_row and unit_row.whole_numbers and line["qty"] != line["qty"].to_integral():
            problems.append(f"{unit_row.unit} is counted in whole numbers.")
        if line["rate"] < 0:
            problems.append("The rate cannot be below zero.")
        if not 0 <= line["discount_pct"] <= 100:
            problems.append("The discount is between 0 and 100%.")
        gst = Decimal("0")
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
        gross = line["qty"] * line["rate"]
        taxable = _money(gross - gross * line["discount_pct"] / 100)
        tax = _money(taxable * gst / 100)
        cgst = sgst = igst = Decimal("0")
        if interstate:
            igst = tax
        else:
            cgst = _money(tax / 2)
            sgst = tax - cgst
        rows.append(
            PurchaseOrderLine(
                position=n,
                item=item,
                description=_description(line.get("description"), item),
                unit_id=line["unit"],
                qty=line["qty"],
                rate=line["rate"],
                discount_pct=line["discount_pct"],
                taxable=taxable,
                gst_rate=gst,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                amount=taxable + tax,
            )
        )
    if not data["lines"]:
        line_errors.append("Add at least one item.")
    if line_errors:
        raise ValidationError({"lines": line_errors})

    o.supplier, o.branch = supplier, branch
    o.order_date, o.expected_date = data["order_date"], expected
    o.credit_term = term
    o.transporter = transporter
    o.bill_to = bill_to
    o.supplier_address = _party_address(place) if place else {}
    o.terms_set = terms_set
    o.agent, o.mail_to, o.whatsapp_to = agent, mail_to, whatsapp_to
    o.agent_user = agent_user
    o.mail_agent_user = bool(agent_user and data.get("mail_agent_user"))
    for field in ("supplier_ref", "terms", "notes"):
        setattr(o, field, data.get(field, "").strip())
    o.interstate = interstate
    o.taxable_total = sum((r.taxable for r in rows), Decimal("0"))
    o.cgst_total = sum((r.cgst for r in rows), Decimal("0"))
    o.sgst_total = sum((r.sgst for r in rows), Decimal("0"))
    o.igst_total = sum((r.igst for r in rows), Decimal("0"))
    exact = sum((r.amount for r in rows), Decimal("0"))
    o.total = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    o.round_off = o.total - exact
    o.save()
    o.lines.all().delete()
    for r in rows:
        r.order = o
    PurchaseOrderLine.objects.bulk_create(rows)


def _submit(o: PurchaseOrder, user) -> None:
    if not user.can(SUBMIT):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    fiscal.assert_open(o.company, o.order_date)
    o.number = numbering.next_document_number(o.company, "purchase_order", o.order_date, o.branch)
    o.status = PurchaseOrder.ORDERED
    o.submitted_at = timezone.now()
    o.save()


def _order(request, pk: int, lock: bool = False) -> PurchaseOrder:
    rows = PurchaseOrder.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    o = rows.select_related("company").first()
    if o is None or "purchase" not in o.company.modules:
        raise NotFound("No such purchase order.")
    return o


def _fresh(o: PurchaseOrder) -> dict:
    return _order_out(_orders(o.company).get(pk=o.pk))


VIEWS = {
    "open": "Open",
    "draft": "Drafts",
    "done": "Received or closed",
    "cancelled": "Cancelled",
    "all": "All",
}


class OrderListView(APIView):
    """GET ?view=open|draft|done|cancelled|all&q=text&branch=ID. POST makes a draft
    (or, with "submit": true, an order)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = _orders(company)
        view = request.query_params.get("view", "open")
        if view == "open":
            rows = rows.filter(status__in=[PurchaseOrder.DRAFT, *PurchaseOrder.OPEN])
        elif view == "draft":
            rows = rows.filter(status=PurchaseOrder.DRAFT)
        elif view == "done":
            rows = rows.filter(status__in=[PurchaseOrder.RECEIVED, PurchaseOrder.CLOSED])
        elif view == "cancelled":
            rows = rows.filter(status=PurchaseOrder.CANCELLED)
        if branch := request.query_params.get("branch"):
            rows = rows.filter(branch_id=branch) if branch.isdigit() else rows.none()
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(supplier__name__icontains=word)
                | Q(supplier_ref__icontains=word)
                | Q(lines__item__name__icontains=word)
            ).distinct()
        return Response([_order_out(o, lines=False) for o in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CREATE)
        company = _company(request, pk)
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        o = PurchaseOrder(company=company, created_by=request.user)
        _save_order(o, data)
        if data.get("submit"):
            _submit(o, request.user)
        return Response(_fresh(o), status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    """GET one order; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        o = _order(request, pk)
        return Response(_fresh(o))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        o = _order(request, pk, lock=True)
        if o.status != PurchaseOrder.DRAFT:
            raise ValidationError(
                {"detail": "A submitted order cannot be changed. Cancel it and make a new one."}
            )
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save_order(o, data)
        if data.get("submit"):
            _submit(o, request.user)
        return Response(_fresh(o))


class OrderSubmitView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk, lock=True)
        if o.status != PurchaseOrder.DRAFT:
            raise ValidationError({"detail": "This order is already submitted."})
        _submit(o, request.user)
        return Response(_fresh(o))


class OrderCancelView(APIView):
    """POST {reason}. A draft or an order nothing has been received against."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CANCEL)
        o = _order(request, pk, lock=True)
        if o.status == PurchaseOrder.CANCELLED:
            raise ValidationError({"detail": "This order is already cancelled."})
        if o.status != PurchaseOrder.DRAFT and o.status != PurchaseOrder.ORDERED:
            raise ValidationError(
                {"detail": "Goods have been received against this order; it cannot be cancelled."}
            )
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        o.status = PurchaseOrder.CANCELLED
        o.cancel_reason = reason[:200]
        o.save()
        return Response(_fresh(o))


# What the form needs ----------------------------------------------------------


class OrderSetupView(APIView):
    """GET: the company's suppliers, branches and credit terms, for the form's pickers."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        suppliers = (
            Ledger.objects.filter(company=company, party_side="supplier", party__isnull=False)
            .select_related("party__credit_term", "party__purchase_terms")
            .prefetch_related("party__contacts", "party__addresses")
            .order_by("name")
        )
        return Response(
            {
                "company_name": company.name,
                # Where "Create …" in the supplier picker adds a new supplier's ledger.
                "supplier_group": LedgerGroup.objects.filter(
                    company=company, code="sundry_creditors"
                )
                .values_list("pk", flat=True)
                .first(),
                "suppliers": [
                    {
                        "id": s.pk,
                        "name": s.name,
                        "is_active": s.is_active,
                        "vendor_number": s.party.vendor_number,
                        "gstin": s.party.gstin,
                        "gst_type": s.party.gst_type,
                        "gst_type_label": s.party.get_gst_type_display(),
                        "state_code": s.party.state_code,
                        "credit_term": s.party.credit_term_id,
                        "transporter": s.preferred_transporter_id,
                        "terms_set": s.party.purchase_terms_id
                        if s.party.purchase_terms and s.party.purchase_terms.is_active
                        else None,
                        "charges_gst": charges_gst(s.party),
                        "contacts": [_contact_out(c) for c in s.party.contacts.all()],
                        "addresses": [
                            {**_party_address(a), "is_billing": a.is_billing}
                            for a in s.party.addresses.all()
                        ],
                    }
                    for s in suppliers
                ],
                "branches": [
                    {
                        "id": b.pk,
                        "name": b.name,
                        "state_code": b.state_code,
                        "is_active": b.is_active,
                        "no_stock": b.no_stock,
                        "default_billing": b.default_billing,
                        "is_head_office": b.is_head_office,
                        "address_block": _branch_address(b),
                        "store": next(
                            (loc.name for loc in b.locations.all() if loc.is_default), ""
                        ),
                        "receiving": next(
                            (
                                loc.name
                                for loc in b.locations.all()
                                if loc.purpose == "receiving" and loc.is_active
                            ),
                            "",
                        ),
                    }
                    for b in Branch.objects.filter(company=company)
                    .select_related("company")
                    .prefetch_related("locations")
                ],
                "employees": [
                    {"id": u.pk, "name": u.display_name, "email": u.email}
                    for u in User.objects.filter(is_active=True).order_by("full_name", "email")
                ],
                "credit_terms": [
                    {"id": t.pk, "name": t.name, "is_active": t.is_active}
                    for t in CreditTerm.objects.all()
                ],
                "transporters": [
                    {"id": t.pk, "name": t.name, "is_active": t.is_active}
                    for t in company.courier_accounts.order_by("name")
                ],
                # The sets of purchase terms, and the company's default set.
                "terms_sets": [
                    {"id": t.pk, "name": t.name, "is_active": t.is_active, "text": t.text}
                    for t in TermsSet.objects.filter(kind=TermsSet.PURCHASE)
                ],
                "default_terms": company.purchase_terms_id
                if company.purchase_terms and company.purchase_terms.is_active
                else None,
            }
        )


def _supplier(request, company, value) -> Ledger:
    try:
        return Ledger.objects.select_related("party").get(
            pk=int(value), company=company, party_side="supplier", party__isnull=False
        )
    except (TypeError, ValueError, Ledger.DoesNotExist):
        raise ValidationError({"supplier": ["Pick a supplier of this company."]}) from None


def _day(value) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value) if value else timezone.localdate()
    except ValueError:
        raise ValidationError({"date": ["Give the date as YYYY-MM-DD."]}) from None


class OrderItemsView(APIView):
    """GET ?supplier=LEDGER&date=YYYY-MM-DD: the items that may be bought from the
    supplier, with their units, GST rate on the date and the supplier's own name."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        supplier = _supplier(request, company, request.query_params.get("supplier"))
        day = _day(request.query_params.get("date"))
        items = items_for_party(supplier.party, "supplier").prefetch_related(
            "units__unit", "gst_rates"
        )
        theirs = {
            n.item_id: n
            for n in PartyItemName.objects.filter(party=supplier.party).only(
                "item_id", "name", "code"
            )
        }
        out = []
        for i in items.select_related("purchase_unit", "stock_unit"):
            rates = [r for r in i.gst_rates.all() if r.valid_from <= day]
            rate = max(rates, key=lambda r: r.valid_from).rate if rates else None
            name = theirs.get(i.pk)
            out.append(
                {
                    "id": i.pk,
                    "name": i.name,
                    "item_number": i.item_number,
                    "hsn": i.hsn,
                    "description": i.purchase_description,
                    "item_type": i.item_type,
                    "maintain_stock": i.maintain_stock,
                    "customer_provided": i.default_request_type == Item.CUSTOMER_PROVIDED,
                    "purchase_unit": i.purchase_unit_id or i.stock_unit_id,
                    "units": [
                        {
                            "unit": u.unit_id,
                            "name": u.unit.short_name or u.unit.name,
                            "whole_numbers": u.whole_numbers,
                        }
                        for u in i.units.all()
                    ],
                    "gst_rate": _plain(rate) if rate is not None else None,
                    "supplier_name": name.name if name else "",
                    "supplier_code": name.code if name else "",
                }
            )
        return Response(out)


class OrderRateView(APIView):
    """GET ?supplier=LEDGER&item=ID&unit=ID&qty=N&date=YYYY-MM-DD: the supplier's rate,
    and where it came from (its own Item Prices, or its buying price list)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        supplier = _supplier(request, company, request.query_params.get("supplier"))
        params = request.query_params
        item = Item.objects.filter(pk=params.get("item", "0") or 0).first()
        unit_row = ItemUnit.objects.filter(item=item, unit_id=params.get("unit") or 0).first()
        if item is None or unit_row is None:
            raise ValidationError({"item": ["Pick an item and one of its units."]})
        try:
            qty = Decimal(params.get("qty") or "1")
        except ArithmeticError:
            raise ValidationError({"qty": ["Give a number."]}) from None
        rate, source = find_rate(
            supplier.party, item, unit_row.unit, max(qty, Decimal("0")), _day(params.get("date")),
            PriceList.BUYING,
        )  # fmt: skip
        if source == "own":
            said = "From supplier's own price"
        elif source:
            said = f'From price list "{source}"'
        else:
            said = ""
        return Response({"rate": _plain(rate) if rate is not None else None, "source": said})
