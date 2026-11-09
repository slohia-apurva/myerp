"""Customers and suppliers (decisions 0018, 0020).

A party is shared by every company in the group; each company that deals
with it has its own ledger under Sundry Debtors or Sundry Creditors
(Ledger.party), with its own balance, bills and credit limit.

The ledgers API reads and writes the party as `party` on the ledger, so one
Save on the ledger screen saves both, and the audit log shows the party's
changes in that ledger's entry. `party_id` links a new ledger to a party
another company already has; `also_in` adds the party's ledger to more
companies.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from accounts.models import User
from audit import recorder
from core.models import (
    BILL_WISE_GROUP_CODES,
    CreditTerm,
    Ledger,
    Party,
    PartyAddress,
    PartyContact,
)
from core.numbering import next_number


def _upper(value: str) -> str:
    return value.strip().upper()


class PartyAddressSerializer(serializers.ModelSerializer):
    gstin = serializers.CharField(max_length=15, allow_blank=True, required=False)
    validate_gstin = staticmethod(_upper)

    class Meta:
        model = PartyAddress
        fields = [
            "label",
            "address",
            "pincode",
            "state_code",
            "country",
            "gstin",
            "is_billing",
            "is_shipping",
        ]


class PartyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartyContact
        fields = ["name", "designation", "phone", "email", "is_primary"]


class PartySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    # Kept on the company's ledger; LedgerSerializer adds it to the output.
    credit_limit = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, required=False, write_only=True
    )
    companies = serializers.SerializerMethodField()
    gstin = serializers.CharField(max_length=15, allow_blank=True, required=False)
    pan = serializers.CharField(max_length=10, allow_blank=True, required=False)
    validate_gstin = validate_pan = staticmethod(_upper)
    # Each company's own salesman (customers) or purchaser (suppliers), kept
    # on its ledger; LedgerSerializer adds both to the output.
    salesman = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        allow_null=True,
        required=False,
        write_only=True,
    )
    credit_term = serializers.PrimaryKeyRelatedField(
        queryset=CreditTerm.objects.all(), allow_null=True, required=False
    )
    credit_term_name = serializers.CharField(source="credit_term.name", read_only=True)
    # Given on Save when blank; may be typed over, but stay unique.
    customer_number = serializers.CharField(max_length=20, allow_blank=True, required=False)
    vendor_number = serializers.CharField(max_length=20, allow_blank=True, required=False)
    validate_customer_number = validate_vendor_number = staticmethod(_upper)
    addresses = PartyAddressSerializer(many=True, required=False)
    contacts = PartyContactSerializer(many=True, required=False)

    class Meta:
        model = Party
        fields = [
            "id",
            "name",
            "companies",
            "customer_number",
            "vendor_number",
            "gst_type",
            "gstin",
            "pan",
            "state_code",
            "country",
            "credit_limit",
            "credit_term",
            "credit_term_name",
            "salesman",
            "addresses",
            "contacts",
        ]

    def get_companies(self, party) -> list[dict]:
        """The companies that have a ledger for this party."""
        # Sorted here, not by the database, whose collation varies.
        rows = [
            {"id": ledger.company_id, "name": ledger.company.name, "ledger": ledger.id}
            for ledger in party.ledgers.all()
        ]
        return sorted(rows, key=lambda r: r["name"].casefold())


_NOT_PARTY_FIELDS = (
    "id",
    "name",
    "companies",
    "credit_limit",
    "salesman",
    "credit_term_name",
    "addresses",
    "contacts",
)
PARTY_FIELDS = [f for f in PartySerializer.Meta.fields if f not in _NOT_PARTY_FIELDS]


def is_party_ledger(ledger: Ledger) -> bool:
    return ledger.group.is_under(BILL_WISE_GROUP_CODES)


def _errors(exc: DjangoValidationError, prefix: str = "party") -> ValidationError:
    detail = getattr(exc, "message_dict", None) or {"detail": exc.messages}
    return ValidationError({prefix: detail})


def save_party(
    ledger: Ledger,
    data: dict | None,
    party_id: int | None = None,
    also_in=None,
) -> None:
    """Save the party details given for a customer or supplier ledger.
    Runs inside the ledger's tenant_atomic, so raising undoes the whole
    save. Ledgers outside Sundry Debtors / Creditors keep no party.

    `party_id` links the ledger to a party another company already has.
    `also_in` is a queryset of companies to add the party's ledger to."""
    if not is_party_ledger(ledger):
        if data or party_id or also_in:
            raise ValidationError(
                {"party": ["Only ledgers under Sundry Debtors or Sundry Creditors are parties."]}
            )
        if ledger.party_id:
            ledger.party = None
            ledger.save(update_fields=["party"])
        return
    data = dict(data or {})
    own = []  # what belongs to this company's ledger, not the shared party
    if "credit_limit" in data:
        ledger.credit_limit = data.pop("credit_limit") or 0
        own.append("credit_limit")
    if "salesman" in data:
        ledger.salesman = data.pop("salesman")
        own.append("salesman")
    if own:
        ledger.save(update_fields=own)
    party = ledger.party
    if party is None and party_id:
        party = Party.objects.select_for_update().filter(pk=party_id).first()
        if party is None:
            raise ValidationError({"party_id": ["No such customer or supplier."]})
        if party.ledgers.filter(company=ledger.company).exists():
            raise ValidationError(
                {"party_id": ["This company already has a ledger for that party."]}
            )
    if party is None:
        if Party.objects.filter(name__iexact=ledger.name).exists():
            raise ValidationError(
                {
                    "name": [
                        "Another company already has a customer or supplier by this name. "
                        'Pick it under "Existing customer or supplier" instead.'
                    ]
                }
            )
        party = Party(name=ledger.name)
        if not data.get("gstin") and not data.get("state_code"):
            # A new local party until told otherwise.
            party.state_code = ledger.company.state_code
    elif party.name != ledger.name and not party.ledgers.exclude(pk=ledger.pk).exists():
        # Renaming the only ledger of a party renames the party.
        if Party.objects.filter(name__iexact=ledger.name).exclude(pk=party.pk).exists():
            raise ValidationError(
                {"name": ["Another company already has a customer or supplier by this name."]}
            )
        party.name = ledger.name
    addresses = data.pop("addresses", None)
    contacts = data.pop("contacts", None)
    for field in ("customer_number", "vendor_number"):
        if not data.get(field):
            data.pop(field, None)  # blank keeps the number it has
    for field in PARTY_FIELDS:
        if field in data:
            value = data[field]
            if value is None and field != "credit_term":
                value = ""
            setattr(party, field, value)
    try:
        party.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise _errors(exc) from exc
    _number(ledger, party)
    party.save()
    if addresses is not None:
        _save_addresses(party, addresses)
    if contacts is not None:
        _save_contacts(party, contacts)
    if ledger.party_id != party.pk:
        ledger.party = party
        ledger.save(update_fields=["party"])
    if also_in is not None:
        _add_to_companies(ledger, party, also_in)
    recorder.touch(ledger)


NUMBER_FIELDS = {"sundry_debtors": "customer", "sundry_creditors": "vendor"}


def _number(ledger: Ledger, party: Party) -> None:
    """Give the party a customer or vendor number if this ledger makes it
    one and it has none yet; check a number typed in by hand."""
    group = ledger.group
    while group.code not in NUMBER_FIELDS:
        group = group.parent
    for kind in ("customer", "vendor"):
        field = f"{kind}_number"
        value = getattr(party, field)
        taken = lambda n, f=field: Party.objects.filter(**{f: n}).exclude(pk=party.pk).exists()  # noqa: E731
        if value and taken(value):
            raise ValidationError(
                {"party": {field: [f"{value} is already used by another party."]}}
            )
        if not value and kind == NUMBER_FIELDS[group.code]:
            setattr(party, field, next_number(kind, taken))


def _add_to_companies(ledger: Ledger, party: Party, companies) -> None:
    """Give the party a ledger, under the same standard group, in each of
    these companies that does not have one yet."""
    group = ledger.group
    while group.code not in BILL_WISE_GROUP_CODES:
        group = group.parent
    for company in companies.exclude(pk=ledger.company_id):
        if party.ledgers.filter(company=company).exists():
            continue
        target = company.ledger_groups.filter(code=group.code).first()
        if target is None:
            raise ValidationError({"also_in": [f"{company.name} has no {group.name} group."]})
        if company.ledgers.filter(name__iexact=party.name).exists():
            raise ValidationError(
                {"also_in": [f"{company.name} already has a ledger named {party.name}."]}
            )
        other = Ledger(company=company, group=target, name=party.name, bill_wise=True, party=party)
        try:
            other.full_clean(validate_constraints=False)
        except DjangoValidationError as exc:
            raise _errors(exc, "also_in") from exc
        other.save()


def _save_addresses(party: Party, addresses: list[dict]) -> None:
    for flag, name in (("is_billing", "billing"), ("is_shipping", "shipping")):
        if sum(1 for a in addresses if a.get(flag)) > 1:
            raise ValidationError(
                {"party": {"addresses": [f"Tick only one default {name} address."]}}
            )
    labels = [a["label"].strip().lower() for a in addresses]
    if len(set(labels)) != len(labels):
        raise ValidationError({"party": {"addresses": ["Give each address its own name."]}})
    party.addresses.all().delete()
    for i, a in enumerate(addresses):
        address = PartyAddress(party=party, **{**a, "label": a["label"].strip()})
        if address.gstin and not party.gstin:
            raise ValidationError(
                {"party": {"addresses": ["Give the party's own GSTIN before a branch GSTIN."]}}
            )
        if address.gstin and address.gstin[2:12] != party.pan:
            raise ValidationError(
                {"party": {"addresses": [f"{address.label}: the GSTIN is under another PAN."]}}
            )
        if address.gstin and address.state_code and address.gstin[:2] != address.state_code:
            raise ValidationError(
                {"party": {"addresses": [f"{address.label}: the GSTIN is of another state."]}}
            )
        if address.gstin and not address.state_code:
            address.state_code = address.gstin[:2]
        try:
            address.full_clean(exclude=["party"])
        except DjangoValidationError as exc:
            raise ValidationError({"party": {"addresses": {i: exc.message_dict}}}) from exc
        address.save()


def _save_contacts(party: Party, contacts: list[dict]) -> None:
    if sum(1 for c in contacts if c.get("is_primary")) > 1:
        raise ValidationError({"party": {"contacts": ["Tick only one main contact."]}})
    party.contacts.all().delete()
    for i, c in enumerate(contacts):
        contact = PartyContact(party=party, **{**c, "name": c["name"].strip()})
        try:
            contact.full_clean(exclude=["party"])
        except DjangoValidationError as exc:
            raise ValidationError({"party": {"contacts": {i: exc.message_dict}}}) from exc
        contact.save()


def party_extras() -> dict:
    """What the audit log shows of a ledger's party details, folded into
    the ledger's own entries (see audit.recorder.TRACKED)."""
    from core import india

    def read(getter):
        def value(ledger):
            party = Party.objects.filter(pk=ledger.party_id).first()
            return getter(party) if party is not None else None

        return value

    def address_text(party):
        rows = []
        for a in party.addresses.all():
            flags = [n for n, on in (("billing", a.is_billing), ("shipping", a.is_shipping)) if on]
            place = india.STATES.get(a.state_code, a.country) if a.state_code else a.country
            text = f"{a.label}: {' '.join(a.address.split())}, {a.pincode} {place}".strip()
            if a.gstin:
                text += f", GSTIN {a.gstin}"
            if flags:
                text += f" (default {' and '.join(flags)})"
            rows.append(text)
        return "; ".join(rows) or None

    def contact_text(party):
        rows = []
        for c in party.contacts.all():
            text = ", ".join(v for v in (c.name, c.designation, c.phone, c.email) if v)
            rows.append(text + (" (main)" if c.is_primary else ""))
        return "; ".join(rows) or None

    def blank(value):
        return value if value not in ("", None) else None

    return {
        # On the ledger itself, so it is this company's own.
        "party_salesman": (
            "Salesman or purchaser",
            lambda ledger: ledger.salesman.display_name if ledger.salesman_id else None,
        ),
        "party_customer_number": ("Customer number", read(lambda p: blank(p.customer_number))),
        "party_vendor_number": ("Vendor number", read(lambda p: blank(p.vendor_number))),
        "party_gst_type": ("GST type", read(lambda p: p.get_gst_type_display())),
        "party_gstin": ("GSTIN", read(lambda p: blank(p.gstin))),
        "party_pan": ("PAN", read(lambda p: blank(p.pan))),
        "party_state": (
            "State",
            read(lambda p: india.STATES.get(p.state_code) if p.state_code else None),
        ),
        "party_country": ("Country", read(lambda p: p.country)),
        "party_credit_term": (
            "Credit terms",
            read(lambda p: p.credit_term.name if p.credit_term_id else None),
        ),
        "party_addresses": ("Addresses", read(address_text)),
        "party_contacts": ("Contacts", read(contact_text)),
    }
