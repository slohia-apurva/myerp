"""Import details on a purchase order from an overseas supplier (Sidharth,
2026-11-14): shipment and payment terms printed on the order. The order is in
the supplier ledger's currency; no exchange rate and no rupee value are kept
on it (customs and the bill of entry come later)."""

from rest_framework import serializers

from tenancy.models import Country

INCOTERMS = [
    ("EXW", "EXW - Ex Works"),
    ("FCA", "FCA - Free Carrier"),
    ("FAS", "FAS - Free Alongside Ship"),
    ("FOB", "FOB - Free On Board"),
    ("CFR", "CFR - Cost and Freight"),
    ("CIF", "CIF - Cost, Insurance and Freight"),
    ("CPT", "CPT - Carriage Paid To"),
    ("CIP", "CIP - Carriage and Insurance Paid To"),
    ("DAP", "DAP - Delivered At Place"),
    ("DPU", "DPU - Delivered at Place Unloaded"),
    ("DDP", "DDP - Delivered Duty Paid"),
]
MODES = [
    ("sea_fcl", "Sea (FCL)"),
    ("sea_lcl", "Sea (LCL)"),
    ("air", "Air"),
    ("road", "Road"),
    ("rail", "Rail"),
    ("courier", "Courier"),
]
PAYMENTS = [
    ("advance_tt", "Advance (TT)"),
    ("lc_sight", "LC at sight"),
    ("lc_usance", "LC usance"),
    ("dp", "DP - documents against payment"),
    ("da", "DA - documents against acceptance"),
    ("cad", "CAD - cash against documents"),
]
ALLOWED = [("allowed", "Allowed"), ("not_allowed", "Not allowed")]
INSURANCE_BY = [("seller", "Seller"), ("buyer", "Buyer")]
DOCUMENTS = [
    ("commercial_invoice", "Commercial invoice"),
    ("packing_list", "Packing list"),
    ("bill_of_lading", "Bill of lading / airway bill"),
    ("certificate_of_origin", "Certificate of origin"),
    ("phytosanitary", "Phytosanitary certificate"),
    ("analysis", "Certificate of analysis"),
    ("fumigation", "Fumigation certificate"),
    ("insurance", "Insurance certificate"),
    ("health", "Health certificate"),
]
# The ticks a first order to an overseas supplier starts with.
DEFAULT_DOCUMENTS = ["commercial_invoice", "packing_list", "bill_of_lading"]

CHOICES = {
    "incoterm": INCOTERMS,
    "mode": MODES,
    "payment": PAYMENTS,
    "partial": ALLOWED,
    "transhipment": ALLOWED,
    "insurance_by": INSURANCE_BY,
    "documents": DOCUMENTS,
}


class ImportSerializer(serializers.Serializer):
    incoterm = serializers.ChoiceField(choices=INCOTERMS, required=False, allow_blank=True)
    named_place = serializers.CharField(max_length=80, required=False, allow_blank=True)
    mode = serializers.ChoiceField(choices=MODES, required=False, allow_blank=True)
    port_loading = serializers.CharField(max_length=80, required=False, allow_blank=True)
    port_discharge = serializers.CharField(max_length=80, required=False, allow_blank=True)
    origin = serializers.CharField(max_length=60, required=False, allow_blank=True)
    latest_shipment = serializers.DateField(required=False, allow_null=True)
    payment = serializers.ChoiceField(choices=PAYMENTS, required=False, allow_blank=True)
    partial = serializers.ChoiceField(choices=ALLOWED, required=False, allow_blank=True)
    transhipment = serializers.ChoiceField(choices=ALLOWED, required=False, allow_blank=True)
    insurance_by = serializers.ChoiceField(choices=INSURANCE_BY, required=False, allow_blank=True)
    documents = serializers.ListField(
        child=serializers.ChoiceField(choices=DOCUMENTS), required=False
    )
    packing = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate_origin(self, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        found = Country.objects.filter(name__iexact=value).first()
        if found is None:
            raise serializers.ValidationError("Pick a country from the list.")
        return found.name


def clean(data: dict) -> dict:
    """The details as kept on the order: every key present, dates as text."""
    out = {key: (data.get(key) or "") for key in ImportSerializer().fields}
    out["documents"] = [code for code, _ in DOCUMENTS if code in (data.get("documents") or [])]
    if data.get("latest_shipment"):
        out["latest_shipment"] = data["latest_shipment"].isoformat()
    return out


def labelled(details: dict) -> dict:
    """The details with each choice's label beside its code, for screens and print."""
    if not details:
        return {}
    out = dict(details)
    for key, options in CHOICES.items():
        names = dict(options)
        if key == "documents":
            out["documents_labels"] = [names.get(c, c) for c in details.get("documents") or []]
        elif details.get(key):
            out[f"{key}_label"] = names.get(details[key], details[key])
    return out
