"""Mail Templates (Sidharth, 2026-11-27): the wording of the mails "Email
Supplier" sends from a purchase order, kept as a master so it can be changed
without a new release. One list for the whole group; {Our Company} fills in
with the company sending the mail.

A template is used for one kind of mail ("Used For"), which decides the lines
grid and the attachment the mail carries and when the template is offered.
The subject, opening and closing may hold fields in braces, such as {PO No};
an unknown field is refused on save, so a typing slip never reaches a
supplier. One template of each use is the default, listed first.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import refuse_key_changes
from core.models import MailTemplate
from tenancy.context import tenant_atomic

PO, SHORT, REMINDER = MailTemplate.PURCHASE_ORDER, MailTemplate.SHORT_EXCESS, MailTemplate.REMINDER

# The fields each use may hold, in the order the form lists them.
COMMON = [
    "PO No", "PO Date", "Supplier", "Contact Name", "Expected Delivery", "Days Late",
    "Our Company", "Purchaser",
]  # fmt: skip
FIELDS: dict[str, list[str]] = {
    PO: COMMON,
    SHORT: [*COMMON, "GRN No", "GRN Date", "Challan No", "Short or Excess"],
    REMINDER: COMMON,
}
ATTACHES = {
    PO: "Purchase Order (PDF)",
    SHORT: "Goods Receipt (PDF)",
    REMINDER: "Purchase Order (PDF)",
}
_FIELD = re.compile(r"\{([^{}]*)\}")

# The ready-made templates every group starts with (migration 0076 and
# `ensure_defaults`); the wording the mails used before templates existed.
DEFAULTS = [
    {
        "name": "Purchase Order",
        "used_for": PO,
        "subject": "Purchase Order No : {PO No}",
        "opening": "Please find attached our purchase order {PO No} dated {PO Date}. "
        "The goods are expected by {Expected Delivery}. "
        "Kindly confirm receipt of the order and the dispatch date.",
        "closing": "",
    },
    {
        "name": "Short / Excess Supply",
        "used_for": SHORT,
        "subject": "{Short or Excess} Supply against PO No : {PO No}",
        "opening": "Against our purchase order {PO No} dated {PO Date}, we received your "
        "challan {Challan No} on {GRN Date} (our receipt {GRN No}). "
        "The following did not match the order:",
        "closing": "Please confirm when the balance will be sent, or let us know if it will "
        "not be sent. For any excess, please send a revised invoice, or confirm it will be "
        "adjusted against the balance.",
    },
    {
        "name": "Reminder for Pending Supply",
        "used_for": REMINDER,
        "subject": "Reminder: Pending Supply against PO No : {PO No}",
        "opening": "This is a reminder about our purchase order {PO No} dated {PO Date}. "
        "The following quantities are still to be supplied:",
        "closing": "Please let us know by when the pending quantity will be supplied. If any "
        "item cannot be supplied, please tell us so that we can plan accordingly.",
    },
]


def unknown_fields(text: str, used_for: str) -> list[str]:
    allowed = {f.casefold() for f in FIELDS.get(used_for, [])}
    return [m for m in _FIELD.findall(text) if " ".join(m.split()).casefold() not in allowed]


def fill(text: str, values: dict[str, str]) -> str:
    """Put the values in the braces; a field with no value leaves nothing."""
    lookup = {k.casefold(): v for k, v in values.items()}
    return _FIELD.sub(lambda m: str(lookup.get(" ".join(m.group(1).split()).casefold(), "")), text)


def templates_for(used_for: str) -> list[MailTemplate]:
    """The active templates of one use, the default first."""
    return list(
        MailTemplate.objects.filter(used_for=used_for, is_active=True).order_by(
            "-is_default", "name"
        )
    )


class MailTemplateSerializer(serializers.ModelSerializer):
    used_for_label = serializers.CharField(source="get_used_for_display", read_only=True)
    attaches = serializers.SerializerMethodField()

    class Meta:
        model = MailTemplate
        fields = [
            "id", "name", "used_for", "used_for_label", "subject", "opening", "closing",
            "attach", "attaches", "is_default", "is_active", "notes",
        ]  # fmt: skip

    def get_attaches(self, t) -> str:
        return ATTACHES.get(t.used_for, "")


def _text(value: str) -> str:
    return "\n".join(line.rstrip() for line in (value or "").strip().splitlines())


def save_template(t: MailTemplate, data: dict) -> MailTemplate:
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        duplicates.check_name(
            MailTemplate.objects.all(),
            data["name"],
            exclude=t.pk,
            kind="mail_template",
            message='There is already a mail template named "{name}".',
        )
    if "subject" in data:
        data["subject"] = duplicates.tidy(data["subject"])
    for f in ("opening", "closing"):
        if f in data:
            data[f] = _text(data[f])
    refuse_key_changes("mail_template", t, data)
    for field in ("name", "used_for", "subject", "opening", "closing", "attach", "is_default",
                  "is_active", "notes"):  # fmt: skip
        if field in data:
            setattr(t, field, data[field])
    if not t.is_active:
        t.is_default = False
    errors = {}
    for f in ("subject", "opening", "closing"):
        if bad := unknown_fields(getattr(t, f), t.used_for):
            names = ", ".join("{" + b + "}" for b in bad)
            errors[f] = [f"{names} is not a field this template can use."]
    if errors:
        raise ValidationError(errors)
    try:
        t.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    if t.is_default:
        # The old default of this use gives way.
        for old in MailTemplate.objects.filter(used_for=t.used_for, is_default=True).exclude(
            pk=t.pk
        ):
            old.is_default = False
            old.save(update_fields=["is_default"])
    t.save()
    return t


exchange.register(
    exchange.Master(
        key="mail_templates",
        label="Mail Templates",
        noun="mail template",
        serializer=MailTemplateSerializer,
        queryset=lambda ctx: MailTemplate.objects.order_by("name"),
        save=lambda ctx, t, data: save_template(t or MailTemplate(), data),
        exclude=("used_for_label", "attaches"),
        labels={"is_default": "Default"},
    )
)


class MailTemplateListView(APIView):
    """GET: every template, and the fields each use may hold. POST: add one."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        rows = MailTemplate.objects.order_by("name")
        return Response(
            {
                "templates": MailTemplateSerializer(rows, many=True).data,
                "uses": [
                    {"value": v, "label": label, "fields": FIELDS[v], "attaches": ATTACHES[v]}
                    for v, label in MailTemplate.USES
                ],
            }
        )

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = MailTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        t = save_template(MailTemplate(), dict(serializer.validated_data))
        return Response(MailTemplateSerializer(t).data, status=status.HTTP_201_CREATED)


class MailTemplateDetailView(APIView):
    """Edit only: templates are never deleted, only disabled."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        t = MailTemplate.objects.select_for_update().filter(pk=pk).first()
        if t is None:
            raise NotFound("No such mail template.")
        serializer = MailTemplateSerializer(t, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        save_template(t, dict(serializer.validated_data))
        return Response(MailTemplateSerializer(t).data)
