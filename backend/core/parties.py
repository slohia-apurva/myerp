"""Customers and suppliers: the party details kept beside a ledger under
Sundry Debtors or Sundry Creditors (decision 0018).

The ledgers API reads and writes them as `party` on the ledger, so one Save
on the ledger screen saves both, and the audit log shows them in the
ledger's one entry.
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
    gstin = serializers.CharField(max_length=15, allow_blank=True, required=False)
    pan = serializers.CharField(max_length=10, allow_blank=True, required=False)
    validate_gstin = validate_pan = staticmethod(_upper)
    salesman = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), allow_null=True, required=False
    )
    salesman_name = serializers.CharField(source="salesman.display_name", read_only=True)
    credit_term = serializers.PrimaryKeyRelatedField(
        queryset=CreditTerm.objects.all(), allow_null=True, required=False
    )
    credit_term_name = serializers.CharField(source="credit_term.name", read_only=True)
    addresses = PartyAddressSerializer(many=True, required=False)
    contacts = PartyContactSerializer(many=True, required=False)

    class Meta:
        model = Party
        fields = [
            "gst_type",
            "gstin",
            "pan",
            "state_code",
            "country",
            "credit_limit",
            "credit_term",
            "credit_term_name",
            "salesman",
            "salesman_name",
            "addresses",
            "contacts",
        ]


_NOT_PARTY_FIELDS = ("salesman_name", "credit_term_name", "addresses", "contacts")
PARTY_FIELDS = [f for f in PartySerializer.Meta.fields if f not in _NOT_PARTY_FIELDS]


def is_party_ledger(ledger: Ledger) -> bool:
    return ledger.group.is_under(BILL_WISE_GROUP_CODES)


def _errors(exc: DjangoValidationError, prefix: str = "party") -> ValidationError:
    detail = getattr(exc, "message_dict", None) or {"detail": exc.messages}
    return ValidationError({prefix: detail})


def save_party(ledger: Ledger, data: dict | None) -> None:
    """Save the party details given for a customer or supplier ledger.
    Runs inside the ledger's tenant_atomic, so raising undoes the whole
    save. Ledgers outside Sundry Debtors / Creditors keep no party."""
    if not is_party_ledger(ledger):
        if data:
            raise ValidationError(
                {"party": ["Only ledgers under Sundry Debtors or Sundry Creditors are parties."]}
            )
        return
    party = Party.objects.filter(ledger=ledger).first()
    if data is None and party is not None:
        return  # nothing sent: keep what is there
    data = dict(data or {})
    if party is None:
        party = Party(ledger=ledger)
        if not data.get("gstin") and not data.get("state_code"):
            # A new local party until told otherwise.
            party.state_code = ledger.company.state_code
    addresses = data.pop("addresses", None)
    contacts = data.pop("contacts", None)
    for field in PARTY_FIELDS:
        if field in data:
            value = data[field]
            if value is None and field not in ("credit_term", "salesman"):
                value = ""
            setattr(party, field, value)
    try:
        party.full_clean(exclude=["ledger"])
    except DjangoValidationError as exc:
        raise _errors(exc) from exc
    party.save()
    if addresses is not None:
        _save_addresses(party, addresses)
    if contacts is not None:
        _save_contacts(party, contacts)
    recorder.touch(ledger)


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
            party = Party.objects.filter(ledger=ledger).first()
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
        "party_gst_type": ("GST type", read(lambda p: p.get_gst_type_display())),
        "party_gstin": ("GSTIN", read(lambda p: blank(p.gstin))),
        "party_pan": ("PAN", read(lambda p: blank(p.pan))),
        "party_state": (
            "State",
            read(lambda p: india.STATES.get(p.state_code) if p.state_code else None),
        ),
        "party_country": ("Country", read(lambda p: p.country)),
        "party_credit_limit": (
            "Credit limit (₹)",
            read(lambda p: str(p.credit_limit) if p.credit_limit else None),
        ),
        "party_credit_term": (
            "Credit terms",
            read(lambda p: p.credit_term.name if p.credit_term_id else None),
        ),
        "party_salesman": (
            "Salesman",
            read(lambda p: p.salesman.display_name if p.salesman_id else None),
        ),
        "party_addresses": ("Addresses", read(address_text)),
        "party_contacts": ("Contacts", read(contact_text)),
    }
