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

from audit.models import AuditEntry
from buying import imports
from buying.models import GoodsReceipt, PurchaseOrder, PurchaseOrderCharge, PurchaseOrderLine
from core import attachments, fiscal, india, numbering, paging, print_mark, words
from core.api import Signed
from core.api import _company as _visible_company
from core.companies import visible_companies
from core.items import gst_rate_on, picked
from core.models import (
    Branch,
    Certificate,
    Company,
    CreditTerm,
    Currency,
    Item,
    ItemUnit,
    Ledger,
    LedgerGroup,
    Party,
    PartyAddress,
    PartyContact,
    PartyItemName,
    PriceList,
    SalesPerson,
    TermsSet,
)
from core.parties import items_for_party, picked_ledgers
from core.price_lists import find_rate
from core.terms import terms_for
from insurance import api as insurance
from insurance.models import InsurancePolicy
from shipping.models import CourierAccount
from tenancy.context import tenant_atomic
from tenancy.models import GstRate

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


def _symbol(code: str) -> str:
    """₹ for rupees, else the currency's symbol (its code when it has none)."""
    if code == "INR":
        return "₹"
    found = Currency.objects.filter(code=code).first()
    return (found.symbol if found else "") or code


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


def branch_title(company: str, branch: str) -> str:
    """The heading for one of our branches: "Company (Branch)", or the branch's
    name alone when it already holds the company's name, so that a branch
    called "Apurvam Organics LLP (Sankrail-2)" does not read twice."""
    if not branch or " ".join(company.lower().split()) in " ".join(branch.lower().split()):
        return branch or company
    return f"{company} ({branch})"


def _branch_address(b: Branch) -> dict:
    """A branch of ours as an address block: its own details, else the company's."""
    c = b.company
    return {
        "name": c.name,
        "label": b.name,
        "title": branch_title(c.name, b.name),
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


def _letterhead(c: Company) -> dict:
    """The company as the print's heading shows it: registered office and numbers."""
    today = timezone.localdate()
    wide = {
        k: n
        for k, n, until in Certificate.objects.filter(
            company=c, branch__isnull=True, kind__in=(Certificate.FSSAI, Certificate.IEC)
        ).values_list("kind", "number", "valid_until")
        if _valid(today, until)
    }
    return {
        "name": c.name,
        "address": c.address,
        "city": c.city,
        "pincode": c.pincode,
        "state": india.STATES.get(c.state_code, ""),
        "state_code": c.state_code,
        "phone": c.phone,
        "email": c.email,
        "gstin": c.gstin,
        "pan": c.pan,
        "cin": c.cin,
        "fssai": wide.get(Certificate.FSSAI, ""),
        "iec": wide.get(Certificate.IEC, ""),
        # The image at the top centre of page 1, when the company prints one.
        "mark": print_mark.mark_url(c),
    }


def _supplier_contact(o: PurchaseOrder) -> dict:
    """Contact, phone and email in the supplier's box: the supplier's people the
    order goes to, else its main contact (or its purchase contacts)."""
    party = o.supplier.party
    if party is None:
        return {}
    picked = [*o.mail_to, *o.whatsapp_to]
    people = list(party.contacts.filter(pk__in=picked)) if picked else []
    if not people:
        every = list(party.contacts.all())
        people = [c for c in every if c.is_primary] or [
            c for c in every if "purchase" in (c.kinds or [])
        ]
    # One person and their phone (the first); every email the order goes to.
    return {
        "contact": next((c.name for c in people if c.name), ""),
        "phone": next((c.phone for c in people if c.phone), ""),
        "email": ", ".join(c.email for c in people if c.email),
    }


def _addresses_out(o: PurchaseOrder) -> dict:
    """Bill To, Ship To and the supplier's address, as the order shows and prints them."""
    party = o.supplier.party
    kept = o.supplier_address or {}
    supplier = {
        "name": o.supplier.name,
        **kept,
        "gstin": kept.get("gstin") or (party.gstin if party else ""),
        "fssai": _party_fssai(party, kept.get("label", "")),
        **_supplier_contact(o),
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
        "pending_qty": _plain(
            Decimal("0") if ln.closed_at else max(ln.qty - ln.received_qty, Decimal("0"))
        ),
        "stock": ln.item.maintain_stock,
        "closed_at": ln.closed_at.isoformat() if ln.closed_at else None,
        "closed_by_name": ln.closed_by.display_name if ln.closed_by_id else "",
        "close_reason": ln.close_reason,
    }


def _charge_out(c: PurchaseOrderCharge) -> dict:
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
        "add_to_stock": c.add_to_stock,
        "add_to_stock_label": c.get_add_to_stock_display(),
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


def person_email(p: SalesPerson | None) -> str:
    """A purchaser's own email, else the one they sign in with."""
    if p is None:
        return ""
    return p.email or (p.user.email if p.user_id else "")


def _with_purchaser(o: PurchaseOrder, rows: list[dict]) -> list[dict]:
    p = o.purchaser
    if p is None or not o.mail_agent_user:
        return rows
    me = {"id": None, "name": p.name, "designation": "Purchaser", "phone": p.mobile}
    me |= {"email": person_email(p), "is_primary": False, "kinds": [], "of": "Agent"}
    return [*rows, {**me, "mail": True, "whatsapp": False}]


def insurance_out(o: PurchaseOrder) -> dict:
    """An order's transit insurance, as the order, its receipts and bills show it."""
    p = o.insurance_policy
    return {
        "insured_by": o.insured_by,
        "insured_by_label": o.get_insured_by_display(),
        "insurance_policy": o.insurance_policy_id,
        "insurance_policy_label": (
            f"{p.number} · {p.insurer.name} · {p.get_kind_display()}" if p else ""
        ),
        "insured_value": str(o.insured_value),
    }


def orders_insurance(orders) -> list[dict]:
    """The transit insurance of the orders behind a receipt or a bill, one row
    per order that names who insures it."""
    return [
        {"order": o.number, **insurance_out(o)}
        for o in sorted(orders, key=lambda o: o.number)
        if o.insured_by != PurchaseOrder.NOT_INSURED
    ]


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
        **insurance_out(o),
        "agent": o.agent_id,
        "agent_name": o.agent.name if o.agent else "",
        "purchaser": o.purchaser_id,
        "purchaser_name": o.purchaser.name if o.purchaser else "",
        "mail_agent_user": o.mail_agent_user,
        "mail_to": o.mail_to,
        "whatsapp_to": o.whatsapp_to,
        "mail_contacts": _with_purchaser(o, _mail_contacts(o)),
        "supplier_ref": o.supplier_ref,
        "currency": o.currency,
        "currency_symbol": _symbol(o.currency),
        "import_details": imports.labelled(o.import_details),
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
        "submitted_by_name": o.submitted_by.display_name if o.submitted_by else "",
        "created_by_email": o.created_by.email if o.created_by else "",
        "created_by_phone": o.created_by.phone if o.created_by else "",
        "line_count": len(o.lines.all()),
        "supplier_status": o.supplier_status,
        "supplier_status_label": o.supplier_status_label(),
    }
    if lines:
        data["lines"] = [_line_out(ln) for ln in o.lines.all()]
        # Printed above "Authorised Signatory"; a draft is never signed.
        data["submitted_by_signature"] = (
            o.submitted_by.signature_url() if o.submitted_by and o.status != "draft" else ""
        )
        # The supplier's own code for each item, printed as "Your code …".
        codes = dict(
            PartyItemName.objects.filter(party=o.supplier.party_id)
            .exclude(code="")
            .values_list("item_id", "code")
        )
        for row in data["lines"]:
            row["supplier_code"] = codes.get(row["item"], "")
        data["charges"] = [_charge_out(c) for c in o.charges.all()]
        data["addresses"] = _addresses_out(o)
        data["letterhead"] = _letterhead(o.company)
        name = Currency.objects.filter(code=o.currency).values_list("name", flat=True).first()
        data["amount_words"] = words.amount(o.total, o.currency, name or "")
        from buying.supplier_link import response_box

        data["supplier_response"] = response_box(o)
    return data


def _orders(company):
    return (
        PurchaseOrder.objects.filter(company=company)
        .select_related(
            "supplier__party",
            "agent",
            "purchaser__user",
            "submitted_by",
            "branch__company",
            "bill_to__company",
            "credit_term",
            "transporter",
            "insurance_policy__insurer",
            "terms_set",
            "created_by",
        )
        .prefetch_related("lines__item", "lines__unit", "lines__closed_by", "charges__item")
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


class ChargeSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    basis = serializers.ChoiceField(choices=PurchaseOrderCharge.BASES)
    # The amount for Fixed, the percent for "% of items", the rate for "Per unit".
    rate = serializers.DecimalField(max_digits=18, decimal_places=6)
    # Left out: the item's GST rate on the order date.
    gst_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )
    # Left out: the item's own setting.
    add_to_stock = serializers.ChoiceField(choices=Item.STOCK_COST, required=False)


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
    purchaser = serializers.PrimaryKeyRelatedField(
        queryset=SalesPerson.objects.all(), required=False, allow_null=True
    )
    # Left out: "Not insured".
    insured_by = serializers.ChoiceField(
        choices=PurchaseOrder.INSURED_BY, required=False, default=PurchaseOrder.NOT_INSURED
    )
    insurance_policy = serializers.PrimaryKeyRelatedField(
        queryset=InsurancePolicy.objects.all(), required=False, allow_null=True
    )
    mail_to = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    whatsapp_to = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    mail_agent_user = serializers.BooleanField(required=False, default=False)
    supplier_ref = serializers.CharField(max_length=80, required=False, allow_blank=True)
    # For an overseas supplier only; ignored otherwise.
    import_details = imports.ImportSerializer(required=False)
    # Left out: the supplier's set, else the company's default, with its text
    # when no text is sent.
    terms_set = serializers.PrimaryKeyRelatedField(
        queryset=TermsSet.objects.all(), allow_null=True, required=False
    )
    terms = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = LineSerializer(many=True)
    charges = ChargeSerializer(many=True, required=False)
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
    purchaser = data.get("purchaser")
    if purchaser is not None:
        if agent is not None:
            errors["purchaser"] = ["Pick one agent: a supplier firm or a purchaser."]
        elif purchaser.pk != o.purchaser_id and not (
            purchaser.is_active and purchaser.is_purchaser
        ):
            errors["purchaser"] = [f"{purchaser.name} is not an active purchaser."]
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
    insured_by = data.get("insured_by") or PurchaseOrder.NOT_INSURED
    policy = data.get("insurance_policy") if insured_by == PurchaseOrder.US else None
    if insured_by == PurchaseOrder.US:
        if policy is None:
            errors["insurance_policy"] = ['Pick the policy, or set "Insured By" to another choice.']
        else:
            why = insurance.check_pick(
                policy, o.company_id, "purchase", data["order_date"], o.insurance_policy_id
            )
            if why:
                errors["insurance_policy"] = [why]
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
    # "Receive By" is required on every save (Sidharth, 2026-11-17).
    if not expected:
        errors["expected_date"] = ["Give the date the goods should be received by."]
    elif expected < data["order_date"]:
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
    if line_errors:
        raise ValidationError({"lines": line_errors})
    charges = _charges(data.get("charges") or [], rows, o, with_gst, interstate, data)

    o.supplier, o.branch = supplier, branch
    o.order_date, o.expected_date = data["order_date"], expected
    o.credit_term = term
    o.transporter = transporter
    o.insured_by, o.insurance_policy = insured_by, policy
    o.bill_to = bill_to
    o.supplier_address = _party_address(place) if place else {}
    o.terms_set = terms_set
    overseas = party is not None and party.gst_type == Party.OVERSEAS
    o.currency = supplier.currency.code if overseas and supplier.currency_id else "INR"
    if overseas and "import_details" in data:
        o.import_details = imports.clean(data["import_details"])
    elif not overseas:
        o.import_details = {}
    o.agent, o.mail_to, o.whatsapp_to = agent, mail_to, whatsapp_to
    o.purchaser = purchaser
    o.mail_agent_user = bool(purchaser and data.get("mail_agent_user"))
    for field in ("supplier_ref", "terms", "notes"):
        setattr(o, field, data.get(field, "").strip())
    o.interstate = interstate
    o.taxable_total = sum((r.taxable for r in rows), Decimal("0")) + sum(
        (c.amount for c in charges), Decimal("0")
    )
    both = [*rows, *charges]
    o.cgst_total = sum((r.cgst for r in both), Decimal("0"))
    o.sgst_total = sum((r.sgst for r in both), Decimal("0"))
    o.igst_total = sum((r.igst for r in both), Decimal("0"))
    exact = o.taxable_total + o.cgst_total + o.sgst_total + o.igst_total
    # A rupee order rounds to the rupee; a foreign currency order is not rounded.
    o.total = exact.quantize(RUPEE, rounding=ROUND_HALF_UP) if o.currency == "INR" else exact
    o.round_off = o.total - exact
    if policy is not None and o.currency != "INR":
        raise ValidationError(
            {"insurance_policy": ["Our marine policies insure rupee orders; this one is not."]}
        )
    o.insured_value = insurance.insured_value(policy, o.total) if policy else Decimal("0")
    o.save()
    o.lines.all().delete()
    for r in rows:
        r.order = o
    PurchaseOrderLine.objects.bulk_create(rows)
    o.charges.all().delete()
    for c in charges:
        c.order = o
    PurchaseOrderCharge.objects.bulk_create(charges)


def _charges(
    given: list[dict], rows: list, o: PurchaseOrder, with_gst: bool, interstate: bool, data
) -> list[PurchaseOrderCharge]:
    """Work out the order's charges: each a service item marked as a purchase
    charge, its amount from its basis, and GST at the rate picked (else the
    item's own) when the supplier charges GST."""
    items_value = sum((r.taxable for r in rows), Decimal("0"))
    units = {r.unit_id for r in rows}
    total_qty = sum((r.qty for r in rows), Decimal("0"))
    allowed_rates = set(GstRate.objects.filter(is_active=True).values_list("rate", flat=True))
    out, errors = [], []
    for n, ch in enumerate(given, start=1):
        item, basis, rate = ch["item"], ch["basis"], ch["rate"]
        problems = []
        old = o.pk and o.charges.filter(item=item).exists()
        if not (item.purchase_charge and item.item_type == Item.SERVICE) and not old:
            problems.append(f'{item.name} is not a service marked "Use as Purchase Charge".')
        elif not item.is_active and not old:
            problems.append(f"{item.name} is disabled.")
        if rate < 0:
            problems.append("The amount or rate cannot be below zero.")
        amount = Decimal("0")
        if basis == PurchaseOrderCharge.FIXED:
            amount = _money(rate)
        elif basis == PurchaseOrderCharge.PERCENT:
            amount = _money(items_value * rate / 100)
        elif len(units) > 1:
            problems.append('"Per unit" needs every item line in the same unit.')
        else:
            amount = _money(total_qty * rate)
        gst = Decimal("0")
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
        tax = _money(amount * gst / 100)
        cgst = sgst = igst = Decimal("0")
        if interstate:
            igst = tax
        else:
            cgst = _money(tax / 2)
            sgst = tax - cgst
        out.append(
            PurchaseOrderCharge(
                position=n,
                item=item,
                basis=basis,
                rate=rate,
                amount=amount,
                gst_rate=gst,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                add_to_stock=ch.get("add_to_stock") or item.add_to_stock,
            )
        )
    if errors:
        raise ValidationError({"charges": errors})
    return out


def _submit(o: PurchaseOrder, user) -> None:
    if not user.can(SUBMIT):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    attachments.require_file(o, "purchase_order")
    # A draft may be saved with no items yet, to finish later; an order needs one.
    if not o.lines.exists():
        raise ValidationError({"lines": ["Add at least one item before submitting."]})
    # An older draft saved before "Receive By" was required.
    if not o.expected_date:
        raise ValidationError({"expected_date": ["Give the date the goods should be received by."]})
    fiscal.assert_open(o.company, o.order_date)
    if o.insured_by == PurchaseOrder.US and o.insurance_policy is None:
        raise ValidationError({"insurance_policy": ["Pick the policy the goods travel under."]})
    o.number = numbering.next_document_number(o.company, "purchase_order", o.order_date, o.branch)
    o.status = PurchaseOrder.ORDERED
    insurance.on_submit(o)
    o.submitted_at = timezone.now()
    o.submitted_by = user
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
            if refused := attachments.refuse_submit(o, "purchase_order"):
                return refused
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
            if refused := attachments.refuse_submit(o, "purchase_order"):
                return refused
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


class OrderLineCloseView(APIView):
    """POST {reason} closes a line whose balance will not come (Sidharth,
    2026-11-15); POST {"reopen": true} opens it again."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int, line: int):
        from buying.receipts import order_status  # receipts imports this module

        _check(request, SUBMIT)
        o = _order(request, pk, lock=True)
        ln = o.lines.select_related("item", "unit").filter(pk=line).first()
        if ln is None:
            raise NotFound("No such line on this order.")
        if o.status not in (*PurchaseOrder.OPEN, PurchaseOrder.RECEIVED, PurchaseOrder.CLOSED):
            raise ValidationError({"detail": "Only a submitted order's lines can be closed."})
        reopen = bool(request.data.get("reopen"))
        if reopen:
            if not ln.closed_at:
                raise ValidationError({"detail": "This line is not closed."})
            change = ("Open", f"Line {ln.position} {ln.item.name} reopened")
            ln.closed_at, ln.closed_by, ln.close_reason = None, None, ""
        else:
            if ln.closed_at:
                raise ValidationError({"detail": "This line is already closed."})
            if not ln.item.maintain_stock or ln.received_qty >= ln.qty:
                raise ValidationError({"detail": "Nothing is pending on this line."})
            reason = str(request.data.get("reason", "")).strip()
            if not reason:
                raise ValidationError({"reason": ["Say why the rest will not come."]})
            draft = (
                GoodsReceipt.objects.filter(status=GoodsReceipt.DRAFT, lines__order_line=ln)
                .values_list("pk", flat=True)
                .first()
            )
            if draft:
                raise ValidationError(
                    {
                        "detail": "A draft goods receipt has this line. Submit it or take "
                        "the line off it first."
                    }
                )
            unit = ln.unit.short_name
            change = (
                "Closed",
                f"Line {ln.position} {ln.item.name} closed, "
                f"{_plain(ln.qty - ln.received_qty)} {unit} not coming: {reason[:200]}",
            )
            ln.closed_at, ln.closed_by, ln.close_reason = timezone.now(), request.user, reason[:200]
        ln.save(update_fields=["closed_at", "closed_by", "close_reason"])
        order_status(o)
        AuditEntry.objects.create(
            user=request.user,
            user_name=request.user.display_name[:150],
            company=o.company,
            record_type="purchase_order",
            record_id=o.pk,
            record_name=str(o)[:200],
            action=AuditEntry.UPDATE,
            changes=[{"field": "line_closed", "label": "Line", "old": None, "new": change[1]}],
        )
        return Response(_fresh(o))


# What the form needs ----------------------------------------------------------


class OrderSetupView(APIView):
    """GET: the company's suppliers, branches and credit terms, for the form's pickers."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        suppliers = (
            picked_ledgers(
                Ledger.objects.filter(company=company, party_side="supplier", party__isnull=False),
                request.query_params,
            )
            .select_related("party__credit_term", "party__purchase_terms", "currency")
            .prefetch_related("party__contacts", "party__addresses")
            .order_by("name")
        )
        today = timezone.localdate()
        last_import: dict[int, dict] = {}
        for o in (
            PurchaseOrder.objects.filter(company=company)
            .exclude(import_details={})
            .order_by("-order_date", "-pk")
            .only("supplier_id", "import_details")
        ):
            last_import.setdefault(o.supplier_id, {**o.import_details, "latest_shipment": ""})
        return Response(
            {
                "company_name": company.name,
                # Service items offered under "Charges", with their GST rate today.
                "charge_items": [
                    {
                        "id": i.pk,
                        "name": i.name,
                        "sac": i.hsn,
                        "add_to_stock": i.add_to_stock,
                        "gst_rate": _plain(r) if (r := gst_rate_on(i, today)) is not None else None,
                    }
                    for i in Item.objects.filter(
                        purchase_charge=True, item_type=Item.SERVICE, is_active=True
                    ).order_by("name")
                ],
                "gst_rates": [
                    _plain(r)
                    for r in GstRate.objects.filter(is_active=True).values_list("rate", flat=True)
                ],
                "import_choices": {
                    key: [list(c) for c in options] for key, options in imports.CHOICES.items()
                },
                "default_documents": imports.DEFAULT_DOCUMENTS,
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
                        # The supplier's Purchaser in this company: the order's agent to start.
                        "purchaser": s.salesman_id,
                        "currency": s.currency.code if s.currency_id else "INR",
                        "currency_symbol": _symbol(s.currency.code if s.currency_id else "INR"),
                        "overseas": s.party.gst_type == Party.OVERSEAS,
                        # An import starts with the details of the supplier's last order.
                        "last_import": last_import.get(s.pk) or {},
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
                # Masters > Salesmen and Purchasers: the people ticked Purchaser.
                "purchasers": []
                if paging.lean_setup(request.query_params)
                else [
                    {"id": p.pk, "name": p.name, "email": person_email(p), "is_active": p.is_active}
                    for p in SalesPerson.objects.filter(is_purchaser=True).select_related("user")
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
                # Masters > Insurance Policies: the marine policies covering purchases.
                "insurance_policies": insurance.picker_rows(company, "purchase"),
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
        items = picked(
            items_for_party(supplier.party, "supplier"), request.query_params
        ).prefetch_related("units__unit", "gst_rates")
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
