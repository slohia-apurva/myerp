"""The sales order as a PDF, and "Email Customer" (Sidharth, 2026-11-19): the
order confirmation sent from the company's mailbox (core/mail.py) with the
PDF attached. A copy of what was sent is written to the order's activity.
WhatsApp to the customer comes later."""

from __future__ import annotations

import html
from decimal import Decimal

from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from buying.po_pdf import order_pdf
from buying.supplier_mail import _dmy, _emails, _people, _signature
from core import mail, payment, print_units
from core.api import Signed
from core.models import Item, PartyContact
from selling.api import SUBMIT, VIEW, _check, _fresh, _order
from selling.models import SalesOrder
from tenancy.context import tenant_atomic


def print_data(o: SalesOrder) -> dict:
    """The order as its print shows it (Sidharth, 2026-11-25): quantities in the
    stock unit with the next unit up under them, rates per stock unit, goods
    shipped to the billing address when the order names no other, and the
    company's bank account and UPI QR to pay into."""
    data = _fresh(o)
    items = {i.pk: i for i in Item.objects.filter(pk__in=[ln["item"] for ln in data["lines"]])}
    data["lines"] = [print_units.in_stock_unit(ln, items[ln["item"]]) for ln in data["lines"]]
    ab = data.get("addresses") or {}
    if not ab.get("ship_to") and ab.get("customer"):
        ab["ship_to"] = {**ab["customer"], "name": o.customer.name}
    data["payment"] = payment.details(o.company, Decimal(data["total"]), o.number or "")
    return data


def order_file(o: SalesOrder) -> tuple[str, bytes, str]:
    return (
        f"{(o.number or 'draft').replace('/', '-')}.pdf",
        order_pdf(print_data(o)),
        "application/pdf",
    )


class OrderPdfView(APIView):
    """GET: the order as a PDF (?download=1 saves it instead of showing it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        o = _order(request, pk)
        name, data, kind = order_file(o)
        response = HttpResponse(data, content_type=kind)
        how = "attachment" if request.query_params.get("download") else "inline"
        response["Content-Disposition"] = f'{how}; filename="{name}"'
        return response


def _contacts(o: SalesOrder) -> list[PartyContact]:
    return list(
        PartyContact.objects.filter(party_id=o.customer.party_id)
        .exclude(email="")
        .order_by("-is_primary", "name")
    )


def _to(o: SalesOrder) -> list[dict]:
    """The contacts ticked "Mail" on the order, else the customer's first."""
    found = {c.pk: c for c in PartyContact.objects.filter(pk__in=o.mail_to).exclude(email="")}
    out = [{"name": found[i].name, "email": found[i].email} for i in o.mail_to if i in found]
    return out or [{"name": c.name, "email": c.email} for c in _contacts(o)[:1]]


def _message(o: SalesOrder) -> str:
    text = "Thank you for your order"
    if o.customer_po_no:
        text += f" {o.customer_po_no}"
        if o.customer_po_date:
            text += f" dated {_dmy(o.customer_po_date)}"
    text += f". Please find attached our order confirmation {o.number} dated {_dmy(o.order_date)}."
    if o.delivery_date:
        text += f" The goods are planned for delivery by {_dmy(o.delivery_date)}."
    return text + " Kindly check the items, rates and quantities, and let us know of any change."


class OrderMailView(APIView):
    """ "Email Customer": GET the draft mail; POST {to, cc, subject, message}
    sends the order confirmation with its PDF attached."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk)
        if not o.number:
            raise ValidationError({"detail": "Submit the order before mailing it."})
        contacts = _contacts(o)
        acct = mail.account_of(o.company)
        held = o.status == SalesOrder.ON_HOLD
        if held:  # the hold mail, to send by hand (selling/hold.py)
            from selling import hold
        return Response(
            {
                "order_number": o.number,
                "party_name": o.customer.name,
                "mail_ready": bool(acct and acct.password),
                "from": acct.address if acct else "",
                "to": hold.recipients(o) if held else _to(o),
                "to_options": [
                    {"name": c.name, "email": c.email, "of": "Customer"} for c in contacts
                ],
                "cc": [{"name": request.user.display_name, "email": request.user.email}]
                if request.user.email
                else [],
                "cc_options": [
                    {"name": u.display_name, "email": u.email, "of": "Our team"} for u in _people(o)
                ]
                + [{"name": c.name, "email": c.email, "of": "Customer"} for c in contacts],
                "subject": hold.subject(o) if held else f"Order Confirmation No : {o.number}",
                "message": hold.message(o) if held else _message(o),
                "signature": _signature(request.user, o),
                "attachment": order_file(o)[0],
            }
        )

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk)
        if not o.number or o.status == SalesOrder.CANCELLED:
            raise ValidationError({"detail": "Only a submitted order can be mailed."})
        data = request.data
        to = _emails(data.get("to"), "to")
        if not to:
            raise ValidationError({"to": ["Give at least one address to send to."]})
        cc = [e for e in _emails(data.get("cc"), "cc") if e not in to]
        subject = str(data.get("subject") or "").strip()[:200]
        if not subject:
            raise ValidationError({"subject": ["Give the subject."]})
        message = str(data.get("message") or "").strip()
        names = {c.email.lower(): c.name for c in _contacts(o)}
        greeting = names.get(to[0].lower(), "Sir/Madam")
        signature = _signature(request.user, o)
        text = f"Dear {greeting},\n\n{message}\n\nRegards,\n{signature}\n"
        e = html.escape
        para = '<p style="margin:0 0 10px">{}</p>'
        body = (
            '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1f2933">'
            + "".join(
                para.format(e(p).replace(chr(10), "<br>"))
                for p in [f"Dear {greeting},", *message.split("\n\n"), f"Regards,\n{signature}"]
                if p.strip()
            )
            + "</div>"
        )
        try:
            mail.send(
                o.company,
                to=to,
                cc=cc,
                subject=subject,
                text=text,
                html=body,
                reply_to=[request.user.email] if request.user.email else [],
                files=[order_file(o)],
            )
        except mail.NotSetUp as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        record = f'Order mailed: "{subject}" to {", ".join(to)}' + (
            f", copy to {', '.join(cc)}" if cc else ""
        )
        AuditEntry.objects.create(
            user=request.user,
            user_name=request.user.display_name[:150],
            company=o.company,
            record_type="sales_order",
            record_id=o.pk,
            record_name=str(o)[:200],
            action=AuditEntry.UPDATE,
            changes=[{"field": "order_mail", "label": "Mail", "old": None, "new": record}],
        )
        return Response({"sent_to": to, "cc": cc})
