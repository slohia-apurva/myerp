"""Send Reminder (Sidharth, 2026-11-27): a mail to the supplier of an open
purchase order asking when the quantity still to come will be supplied, with a
grid of those lines (item code, item, ordered, received, pending, expected
delivery). Drafted from the order, changed by the purchaser, sent from the
company's mailbox (core/mail.py); each reminder is written to the order's
activity, which is also where the "last reminder" note is read from."""

from __future__ import annotations

import html
from datetime import date

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from buying import mail_text
from buying.api import SUBMIT, _check, _order, _plain, person_email
from buying.models import OrderReminder, PurchaseOrder
from buying.supplier_mail import (
    _dmy,
    _emails,
    _named,
    _order_file,
    _people,
    _signature,
    _supplier_contacts,
)
from core import mail
from core.api import Signed
from core.models import MailTemplate

FIELD = "po_reminder"
ASK = (
    "Please let us know by when the pending quantity will be supplied. If any item "
    "cannot be supplied, please tell us so that we can plan accordingly."
)


def pending_lines(o: PurchaseOrder, today: date | None = None) -> list[dict]:
    """Stock lines with goods still to come: not closed, received less than
    ordered."""
    today = today or timezone.localdate()
    late = (today - o.expected_date).days if o.expected_date else 0
    out = []
    for ln in o.lines.select_related("item", "unit").order_by("position"):
        if not ln.item.maintain_stock or ln.closed_at or ln.received_qty >= ln.qty:
            continue
        out.append(
            {
                "id": ln.pk,
                "position": ln.position,
                "item_code": ln.item.item_number,
                "item_name": ln.item.name,
                "unit": ln.unit.short_name,
                "ordered": _plain(ln.qty),
                "received": _plain(ln.received_qty),
                "pending": _plain(ln.qty - ln.received_qty),
                "expected": _dmy(o.expected_date),
                "days_late": max(late, 0),
            }
        )
    return out


def _intro(o: PurchaseOrder) -> str:
    return (
        f"This is a reminder about our purchase order {o.number} dated "
        f"{_dmy(o.order_date)}. The following quantities are still to be supplied:"
    )


def _sent_before(o: PurchaseOrder) -> list[AuditEntry]:
    return list(
        AuditEntry.objects.filter(
            record_type="purchase_order", record_id=o.pk, changes__contains=[{"field": FIELD}]
        ).order_by("-at")
    )


def _late_words(days: int) -> str:
    return f"{days} day{'s' if days != 1 else ''} late" if days else ""


def _bodies(greeting: str, intro: str, lines: list[dict], closing: str, signature: str):
    """The mail as plain text and as HTML with the lines in a grid."""
    width = max(len(ln["item_name"]) for ln in lines)
    rows = [
        f"  {'Item Code':<10}  {'Item'.ljust(width)}  {'Ordered':>14}  {'Received':>14}  "
        f"{'Pending':>14}  Expected Delivery"
    ]
    for ln in lines:
        u = ln["unit"]
        late = f" ({_late_words(ln['days_late'])})" if ln["days_late"] else ""
        rows.append(
            f"  {ln['item_code']:<10}  {ln['item_name'].ljust(width)}  "
            f"{ln['ordered'] + ' ' + u:>14}  {ln['received'] + ' ' + u:>14}  "
            f"{ln['pending'] + ' ' + u:>14}  {ln['expected']}{late}"
        )
    text = (
        f"Dear {greeting},\n\n{intro}\n\n"
        + "\n".join(rows)
        + f"\n\n{closing}\n\nRegards,\n{signature}\n"
    )

    e = html.escape
    th = 'style="background:#155c39;color:#fff;text-align:left;padding:6px 10px;font-size:13px"'
    thr = th.replace("text-align:left", "text-align:right")
    td = 'style="padding:6px 10px;border-bottom:1px solid #dfe7e2;font-size:13px"'
    tdr = td.replace('style="', 'style="text-align:right;white-space:nowrap;')

    def when(ln: dict) -> str:
        if not ln["expected"]:
            return ""
        if not ln["days_late"]:
            return e(ln["expected"])
        return (
            f'<b style="color:#b42318">{e(ln["expected"])}</b><br>'
            f'<span style="color:#b42318;font-size:12px">{_late_words(ln["days_late"])}</span>'
        )

    grid = (
        '<table cellspacing="0" style="border-collapse:collapse;'
        'border:1px solid #cbd2d9;margin:8px 0 14px">'
        f"<tr><th {th}>#</th><th {th}>Item Code</th><th {th}>Item</th>"
        f"<th {thr}>Ordered</th><th {thr}>Received</th><th {thr}>Pending</th>"
        f"<th {th}>Expected Delivery</th></tr>"
        + "".join(
            f"<tr><td {td}>{n}</td><td {td}>{e(ln['item_code'])}</td>"
            f"<td {td}>{e(ln['item_name'])}</td>"
            f"<td {tdr}>{e(ln['ordered'])} {e(ln['unit'])}</td>"
            f"<td {tdr}>{e(ln['received'])} {e(ln['unit'])}</td>"
            f"<td {tdr}><b>{e(ln['pending'])} {e(ln['unit'])}</b></td>"
            f"<td {td}>{when(ln)}</td></tr>"
            for n, ln in enumerate(lines, 1)
        )
        + "</table>"
    )

    def para(t: str) -> str:
        return "".join(
            f'<p style="margin:0 0 10px">{e(p).replace(chr(10), "<br>")}</p>'
            for p in t.split("\n\n")
            if p.strip()
        )

    body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1f2933">'
        f"{para('Dear ' + greeting + ',')}{para(intro)}{grid}{para(closing)}"
        f"{para('Regards,' + chr(10) + signature)}</div>"
    )
    return text, body


def _open(request, pk: int) -> PurchaseOrder:
    o = _order(request, pk)
    if o.status not in PurchaseOrder.OPEN or not o.number:
        raise ValidationError({"detail": "Only an order with goods still to come can be chased."})
    return o


class ReminderView(APIView):
    """GET: the draft reminder. POST {to, cc, subject, intro, closing, lines,
    attach_order}: send it."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, SUBMIT)
        o = _open(request, pk)
        contacts = _supplier_contacts(o)
        ticked = [c for c in contacts if c.pk in o.mail_to] or contacts[:1]
        acct = mail.account_of(o.company)
        cc = []
        if request.user.email:
            cc.append({"name": request.user.display_name, "email": request.user.email})
        buyer = person_email(o.purchaser)
        if buyer and buyer.lower() not in {p["email"].lower() for p in cc}:
            cc.append({"name": f"{o.purchaser.name} (Purchaser)", "email": buyer})
        t = mail_text.chosen(request, MailTemplate.REMINDER)
        if t is not None:
            w = mail_text.words(t, mail_text.order_values(o, ticked[0].name if ticked else ""))
        else:
            w = {
                "subject": f"Reminder: Pending Supply against PO No : {o.number}",
                "opening": _intro(o),
                "closing": ASK,
            }
        before = _sent_before(o)
        last = None
        if before:
            b = before[0]
            local = timezone.localtime(b.at)
            last = {
                "date": local.strftime("%d-%m-%Y"),
                "by": b.user_name,
                "to": b.changes[0].get("to", []) if b.changes else [],
            }
        return Response(
            {
                "order": o.pk,
                "order_number": o.number,
                "supplier_name": o.supplier.name,
                "mail_ready": bool(acct and acct.password),
                "from": acct.address if acct else "",
                "to": [{"name": c.name, "email": c.email} for c in ticked],
                "to_options": [
                    {"name": c.name, "email": c.email, "of": "Supplier"} for c in contacts
                ],
                "cc": cc,
                "cc_options": [
                    {"name": u.display_name, "email": u.email, "of": "Our team"} for u in _people(o)
                ]
                + [{"name": c.name, "email": c.email, "of": "Supplier"} for c in contacts],
                "lines": pending_lines(o),
                "template": t.pk if t else None,
                "template_name": t.name if t else "",
                "attach_default": t.attach if t else True,
                "subject": w["subject"],
                "intro": w["opening"],
                "closing": w["closing"],
                "signature": _signature(request.user, o),
                "attachment": _order_file(o)[0],
                "last": last,
                "count": len(before),
            }
        )

    def post(self, request, pk: int):
        _check(request, SUBMIT)
        o = _open(request, pk)
        data = request.data
        to = _emails(data.get("to"), "to")
        if not to:
            raise ValidationError({"to": ["Give at least one address to send to."]})
        cc = [e for e in _emails(data.get("cc"), "cc") if e.lower() not in {t.lower() for t in to}]
        subject = str(data.get("subject") or "").strip()[:200]
        if not subject:
            raise ValidationError({"subject": ["Give the subject."]})
        intro = str(data.get("intro") or "").strip()
        closing = str(data.get("closing") or "").strip()
        wanted = {int(x) for x in data.get("lines") or [] if str(x).isdigit()}
        lines = [ln for ln in pending_lines(o) if ln["id"] in wanted]
        if not lines:
            raise ValidationError({"lines": ["Tick at least one line for the reminder."]})
        names = {c.email.lower(): c.name for c in _supplier_contacts(o)}
        greeting = names.get(to[0].lower(), "Sir/Madam")
        text, body = _bodies(greeting, intro, lines, closing, _signature(request.user, o))
        files = [_order_file(o)] if data.get("attach_order") else []
        try:
            mail.send(
                o.company,
                to=to,
                cc=cc,
                subject=subject,
                text=text,
                html=body,
                reply_to=[request.user.email] if request.user.email else [],
                files=files,
            )
        except mail.NotSetUp as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        record = (
            f'Reminder sent to supplier{_named(data)}: "{subject}" to {", ".join(to)}'
            + (f", copy to {', '.join(cc)}" if cc else "")
            + "; "
            + "; ".join(f"{ln['item_code']} {ln['pending']} {ln['unit']} pending" for ln in lines)
            + ("; PO attached" if files else "")
        )
        AuditEntry.objects.create(
            user=request.user,
            user_name=request.user.display_name[:150],
            company=o.company,
            record_type="purchase_order",
            record_id=o.pk,
            record_name=str(o)[:200],
            action=AuditEntry.UPDATE,
            changes=[{"field": FIELD, "label": "Reminder", "old": None, "new": record, "to": to}],
        )
        raw = data.get("template")
        t = MailTemplate.objects.filter(pk=raw).first() if str(raw or "").isdigit() else None
        OrderReminder.objects.create(
            order=o,
            template_name=t.name if t else "",
            sent_to=to,
            line_count=len(lines),
            by=request.user,
        )
        return Response({"sent_to": to, "cc": cc})
