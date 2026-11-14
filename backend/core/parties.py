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
from core import duplicates
from core.locks import lock_status, refuse_key_changes
from core.models import (
    BILL_WISE_GROUP_CODES,
    CONTACT_KINDS,
    CreditTerm,
    Item,
    Ledger,
    Party,
    PartyAddress,
    PartyContact,
    PartyItemName,
    PartyProduct,
)
from core.numbering import next_number
from tenancy.models import PinCode


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
            "city",
            "state_code",
            "country",
            "gstin",
            "is_billing",
            "is_shipping",
        ]


class PartyContactSerializer(serializers.ModelSerializer):
    # Besides Main (is_primary): Accounting, Shipping, Purchase, Sales.
    kinds = serializers.ListField(
        child=serializers.ChoiceField(choices=CONTACT_KINDS), required=False
    )

    class Meta:
        model = PartyContact
        fields = ["name", "designation", "phone", "email", "is_primary", "kinds"]


class PartyProductSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    item_number = serializers.CharField(source="item.item_number", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_active = serializers.BooleanField(source="item.is_active", read_only=True)
    # What this party calls the item, kept on the item and shown here read only.
    their_name = serializers.SerializerMethodField()
    their_code = serializers.SerializerMethodField()

    def _theirs(self, row) -> PartyItemName | None:
        cache = self.context.setdefault("_party_item_names", {})
        if row.party_id not in cache:
            cache[row.party_id] = {
                n.item_id: n for n in PartyItemName.objects.filter(party_id=row.party_id)
            }
        return cache[row.party_id].get(row.item_id)

    def get_their_name(self, row) -> str:
        mine = self._theirs(row)
        return mine.name if mine else ""

    def get_their_code(self, row) -> str:
        mine = self._theirs(row)
        return mine.code if mine else ""

    class Meta:
        model = PartyProduct
        fields = ["item", "item_number", "item_name", "item_active", "their_name", "their_code"]


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
    products = PartyProductSerializer(many=True, required=False)
    document_count = serializers.SerializerMethodField()
    lock = serializers.SerializerMethodField()

    def get_lock(self, party) -> dict:
        return lock_status("party", party)

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
            "products",
            "document_count",
            "lock",
        ]

    def get_document_count(self, party) -> int:
        return party.documents.filter(is_active=True).count() if party.pk else 0

    def get_companies(self, party) -> list[dict]:
        """The companies that have a ledger for this party."""
        # Sorted here, not by the database, whose collation varies.
        rows = [
            {
                "id": ledger.company_id,
                "name": ledger.company.name,
                "ledger": ledger.id,
                "side": ledger.party_side,
            }
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
    "products",
    "lock",
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
            ledger.party_side = ""
            ledger.save(update_fields=["party", "party_side"])
        return
    side = side_of(ledger)
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
    if party is not None:
        # One customer ledger and one supplier ledger per party per company.
        twin = (
            party.ledgers.filter(company=ledger.company, party_side=side)
            .exclude(pk=ledger.pk)
            .first()
        )
        if twin is not None:
            duplicates.refuse(
                "party_id",
                f'This company already has the {side} ledger "{twin.name}" for that party.',
                twin,
                "ledger",
            )
    if party is None:
        clash = duplicates.same_name(Party.objects.all(), ledger.name)
        if clash is not None:
            _refuse_party(
                "name",
                f'There is already a customer or supplier named "{clash.name}". '
                'Pick it under "Existing customer or supplier" instead.',
                clash,
            )
        party = Party(name=ledger.name)
        if not data.get("gstin") and not data.get("state_code"):
            # A new local party until told otherwise.
            party.state_code = ledger.company.state_code
    elif party.name != ledger.name and not party.ledgers.exclude(pk=ledger.pk).exists():
        # Renaming the only ledger of a party renames the party.
        clash = duplicates.same_name(Party.objects.all(), ledger.name, exclude=party.pk)
        if clash is not None:
            _refuse_party(
                "name", f'There is already a customer or supplier named "{clash.name}".', clash
            )
        party.name = ledger.name
    addresses = data.pop("addresses", None)
    contacts = data.pop("contacts", None)
    products = data.pop("products", None)
    for field in ("customer_number", "vendor_number"):
        if not data.get(field):
            data.pop(field, None)  # blank keeps the number it has
    if party.pk:
        try:
            refuse_key_changes("party", party, data)
        except ValidationError as exc:
            raise ValidationError({"party": exc.detail}) from exc
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
    if party.gstin:
        clash = Party.objects.filter(gstin=party.gstin).exclude(pk=party.pk).first()
        if clash is not None:
            _refuse_party(
                "gstin",
                f'This GSTIN is already on the customer or supplier "{clash.name}". '
                'Pick it under "Existing customer or supplier" instead (a firm that is '
                "both can have a customer ledger and a supplier ledger).",
                clash,
            )
    _number(ledger, party)
    party.save()
    if addresses is not None:
        _save_addresses(party, addresses)
    if contacts is not None:
        _save_contacts(party, contacts)
    if products is not None:
        _save_products(party, products)
    if ledger.party_id != party.pk or ledger.party_side != side:
        ledger.party = party
        ledger.party_side = side
        ledger.save(update_fields=["party", "party_side"])
    if also_in is not None:
        _add_to_companies(ledger, party, also_in)
    recorder.touch(ledger)


NUMBER_FIELDS = {"sundry_debtors": "customer", "sundry_creditors": "vendor"}


def side_of(ledger: Ledger) -> str:
    """ "customer" for a ledger under Sundry Debtors, "supplier" under Sundry
    Creditors."""
    group = ledger.group
    while group.code not in BILL_WISE_GROUP_CODES:
        group = group.parent
    return "customer" if group.code == "sundry_debtors" else "supplier"


def _refuse_party(field: str, message: str, party: Party) -> None:
    """Refuse, linking to the party's ledger (in the first company that has
    one) so the screen can open it."""
    detail: dict = {"name": [message]} if field == "name" else {"party": {field: [message]}}
    ledger = party.ledgers.select_related("company").order_by("company__name").first()
    if ledger is not None:
        detail["existing"] = duplicates.existing(ledger, "ledger", name=party.name)
    raise ValidationError(detail)


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
            clash = Party.objects.filter(**{field: value}).exclude(pk=party.pk).first()
            _refuse_party(field, f'{value} is already the number of "{clash.name}".', clash)
        if not value and kind == NUMBER_FIELDS[group.code]:
            setattr(party, field, next_number(kind, taken))


def _add_to_companies(ledger: Ledger, party: Party, companies) -> None:
    """Give the party a ledger, under the same standard group, in each of
    these companies that does not have one yet."""
    group = ledger.group
    while group.code not in BILL_WISE_GROUP_CODES:
        group = group.parent
    side = side_of(ledger)
    for company in companies.exclude(pk=ledger.company_id):
        if party.ledgers.filter(company=company, party_side=side).exists():
            continue
        target = company.ledger_groups.filter(code=group.code).first()
        if target is None:
            raise ValidationError({"also_in": [f"{company.name} has no {group.name} group."]})
        name = party.name
        clash = duplicates.same_name(company.ledgers.all(), name)
        if clash is not None and clash.party_id == party.pk:
            # Its ledger on the other side has the plain name.
            name = f"{party.name} ({side.capitalize()})"
            clash = duplicates.same_name(company.ledgers.all(), name)
        if clash is not None:
            message = f'{company.name} already has a ledger named "{clash.name}".'
            duplicates.refuse("also_in", message, clash, "ledger")
        other = Ledger(
            company=company,
            group=target,
            name=name,
            bill_wise=True,
            party=party,
            party_side=side,
        )
        try:
            other.full_clean(validate_constraints=False)
        except DjangoValidationError as exc:
            raise _errors(exc, "also_in") from exc
        other.save()


def _take_place_from_pin(address: PartyAddress, i: int, unchanged: bool) -> None:
    if address.country.strip().lower() not in ("", "india"):
        return
    address.country = "India"
    pin = (
        PinCode.objects.select_related("state").filter(pin=address.pincode, is_active=True).first()
    )
    if pin is None:
        if unchanged:
            return
        raise ValidationError(
            {
                "party": {
                    "addresses": {
                        i: {"pincode": ["Pick the PIN code from the list, or Request Addition."]}
                    }
                }
            }
        )
    address.city = pin.city or address.city
    if pin.state:
        address.state_code = pin.state.code


def _save_addresses(party: Party, addresses: list[dict]) -> None:
    for flag, name in (("is_billing", "billing"), ("is_shipping", "shipping")):
        if sum(1 for a in addresses if a.get(flag)) > 1:
            raise ValidationError(
                {"party": {"addresses": [f"Tick only one default {name} address."]}}
            )
    labels = [a["label"].strip().lower() for a in addresses]
    if len(set(labels)) != len(labels):
        raise ValidationError({"party": {"addresses": ["Give each address its own name."]}})
    # An Indian address takes its PIN from the central list, which gives its city and
    # state. An address saved before that rule, with the same name and PIN, is kept as it is.
    earlier = {(x.label.lower(), x.pincode) for x in party.addresses.all()}
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
        _take_place_from_pin(address, i, (address.label.lower(), address.pincode) in earlier)
        if address.gstin and address.gstin[:2] != address.state_code:
            raise ValidationError(
                {"party": {"addresses": [f"{address.label}: the GSTIN is of another state."]}}
            )
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


def _save_products(party: Party, products: list[dict]) -> None:
    items = [p["item"] for p in products]
    if len({i.pk for i in items}) != len(items):
        raise ValidationError({"party": {"products": ["Each item can be listed only once."]}})
    kept = {p.item_id for p in party.products.all()}
    for item in items:
        if item.pk not in kept and not item.is_active:
            raise ValidationError(
                {"party": {"products": [f"{item.name} is disabled and cannot be added."]}}
            )
    party.products.all().delete()
    PartyProduct.objects.bulk_create([PartyProduct(party=party, item=i) for i in items])


def items_for_party(party: Party | None, side: str):
    """The items that may be sold to a customer (side "customer") or bought
    from a supplier ("supplier"): active items that allow sales or purchase;
    when the party lists products, only those plus items ticked "Offer to
    all". Every quotation, order and bill screen picks items through this."""
    items = Item.objects.filter(is_active=True)
    items = (
        items.filter(allow_sales=True) if side == "customer" else items.filter(allow_purchase=True)
    )
    if party is None or not party.products.exists():
        return items
    from django.db.models import Q

    return items.filter(Q(offer_to_all=True) | Q(party_products__party=party)).distinct()


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
            where = ", ".join(x for x in (a.city, f"{a.pincode} {place}".strip()) if x)
            text = f"{a.label}: {' '.join(a.address.split())}, {where}".strip()
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
            labels = dict(CONTACT_KINDS)
            types = (["main"] if c.is_primary else []) + [labels[k].lower() for k in c.kinds]
            rows.append(text + (f" ({', '.join(types)})" if types else ""))
        return "; ".join(rows) or None

    def product_text(party):
        names = [
            f"{p.item.item_number} {p.item.name}" for p in party.products.select_related("item")
        ]
        return "; ".join(names) or None

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
        "party_products": ("Products", read(product_text)),
    }
