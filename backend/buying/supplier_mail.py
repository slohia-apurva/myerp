"""Email Supplier (Sidharth, 2026-11-15): one mail to the supplier about a
purchase order's lines that came short, did not come, or came in excess,
drafted from the order and its receipts, changed by the purchaser, and sent
from the company's mailbox (core/mail.py) with copies to whoever they pick.
A copy of what was sent is written to the order's activity."""

from __future__ import annotations

import html

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from audit.models import AuditEntry
from buying.api import SUBMIT, VIEW, _check, _fresh, _order, _plain, person_email
from buying.models import GoodsReceipt, PurchaseOrder
from buying.po_pdf import order_pdf
from buying.supplier_link import make_link
from core import mail, print_mark, printout
from core.api import Signed
from core.models import PartyContact
from tenancy.context import tenant_atomic

SHORT, MISSING, OVER = "short", "not_received", "over"
KIND_LABELS = {SHORT: "Short", MISSING: "Not received", OVER: "Excess"}
SHORT_ASK = "Please confirm when the balance will be sent, or let us know if it will not be sent."
OVER_ASK = (
    "For the excess, please send a revised invoice, or confirm it will be adjusted "
    "against the balance."
)


def _dmy(d) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def differing_lines(o: PurchaseOrder) -> list[dict]:
    """Stock lines whose received quantity is not what was ordered and which
    are not closed (a closed line's balance is settled)."""
    out = []
    for ln in o.lines.select_related("item", "unit"):
        if not ln.item.maintain_stock or ln.closed_at:
            continue
        got, wanted = ln.received_qty, ln.qty
        if got == wanted:
            continue
        kind = OVER if got > wanted else (MISSING if got == 0 else SHORT)
        out.append(
            {
                "id": ln.pk,
                "position": ln.position,
                "item_name": ln.item.name,
                "unit": ln.unit.short_name,
                "ordered": _plain(wanted),
                "received": _plain(got),
                "difference": _plain(abs(got - wanted)),
                "kind": kind,
                "kind_label": KIND_LABELS[kind],
            }
        )
    return out


def _supplier_contacts(o: PurchaseOrder) -> list[PartyContact]:
    return list(
        PartyContact.objects.filter(party_id=o.supplier.party_id)
        .exclude(email="")
        .order_by("-is_primary", "name")
    )


def _people(o: PurchaseOrder) -> list[User]:
    users = User.objects.filter(is_active=True).exclude(email="").prefetch_related("companies")
    return [
        u
        for u in users.order_by("full_name", "email")
        if u.is_owner or not u.companies.exists() or u.companies.filter(pk=o.company_id).exists()
    ]


def _receipts(o: PurchaseOrder):
    return o.receipts.filter(status=GoodsReceipt.SUBMITTED).order_by("-receipt_date", "-id")


def _intro(o: PurchaseOrder, r: GoodsReceipt | None) -> str:
    text = f"Against our purchase order {o.number} dated {_dmy(o.order_date)}, "
    if r is not None:
        challan = f"your challan {r.challan_no}" if r.challan_no else "your goods"
        text += f"we received {challan} on {_dmy(r.receipt_date)} (our receipt {r.number}). "
    return text + "The following did not match the order:"


def _signature(user, o: PurchaseOrder) -> str:
    bits = [o.company.name]
    if user.phone:
        bits.append(user.phone)
    return f"{user.display_name}\n{' · '.join(bits)}"


class SupplierMailView(APIView):
    """GET ?grn=ID: the draft. POST {to, cc, subject, intro, closing, lines,
    grn}: send it."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk)
        receipts = list(_receipts(o))
        wanted = request.query_params.get("grn", "")
        r = next((x for x in receipts if str(x.pk) == wanted), receipts[0] if receipts else None)
        contacts = _supplier_contacts(o)
        ticked = [c for c in contacts if c.pk in o.mail_to] or contacts[:1]
        acct = mail.account_of(o.company)
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
                "cc": [{"name": request.user.display_name, "email": request.user.email}]
                if request.user.email
                else [],
                "cc_options": [
                    {"name": u.display_name, "email": u.email, "of": "Our team"} for u in _people(o)
                ]
                + [{"name": c.name, "email": c.email, "of": "Supplier"} for c in contacts],
                "lines": differing_lines(o),
                "receipts": [
                    {"id": x.pk, "number": x.number, "date": _dmy(x.receipt_date)} for x in receipts
                ],
                "grn": r.pk if r else None,
                "intro": _intro(o, r),
                "intros": {str(x.pk): _intro(o, x) for x in receipts} | {"": _intro(o, None)},
                "short_ask": SHORT_ASK,
                "over_ask": OVER_ASK,
                "signature": _signature(request.user, o),
            }
        )

    def post(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk)
        data = request.data
        to = _emails(data.get("to"), "to")
        if not to:
            raise ValidationError({"to": ["Give at least one address to send to."]})
        cc = [e for e in _emails(data.get("cc"), "cc") if e not in to]
        subject = str(data.get("subject") or "").strip()[:200]
        if not subject:
            raise ValidationError({"subject": ["Give the subject."]})
        intro = str(data.get("intro") or "").strip()
        closing = str(data.get("closing") or "").strip()
        wanted = {int(x) for x in data.get("lines") or [] if str(x).isdigit()}
        lines = [ln for ln in differing_lines(o) if ln["id"] in wanted]
        if not lines:
            raise ValidationError({"lines": ["Tick at least one line for the mail."]})
        r = None
        if grn := data.get("grn"):
            r = _receipts(o).filter(pk=grn).first()
            if r is None:
                raise ValidationError({"grn": ["That receipt is not against this order."]})
        contacts = {c.email.lower(): c.name for c in _supplier_contacts(o)}
        greeting = contacts.get(to[0].lower(), "Sir/Madam")
        signature = _signature(request.user, o)
        text, body = _bodies(greeting, intro, lines, closing, signature)
        files = (
            [(f"{r.number.replace('/', '-')}.pdf", receipt_pdf(r), "application/pdf")] if r else []
        )
        if data.get("attach_order"):
            files.append(_order_file(o))
        reply_to = [request.user.email] if request.user.email else []
        try:
            mail.send(
                o.company,
                to=to,
                cc=cc,
                subject=subject,
                text=text,
                html=body,
                reply_to=reply_to,
                files=files,
            )
        except mail.NotSetUp as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        record = (
            f'Mail to supplier: "{subject}" to {", ".join(to)}'
            + (f", copy to {', '.join(cc)}" if cc else "")
            + "; "
            + "; ".join(
                f"{ln['item_name']} {ln['difference']} {ln['unit']} {ln['kind_label'].lower()}"
                for ln in lines
            )
            + (f"; attached {r.number}" if r else "")
            + (f"; attached {o.number}" if data.get("attach_order") else "")
        )
        AuditEntry.objects.create(
            user=request.user,
            user_name=request.user.display_name[:150],
            company=o.company,
            record_type="purchase_order",
            record_id=o.pk,
            record_name=str(o)[:200],
            action=AuditEntry.UPDATE,
            changes=[{"field": "supplier_mail", "label": "Mail", "old": None, "new": record}],
        )
        return Response({"sent_to": to, "cc": cc})


def _emails(value, field: str) -> list[str]:
    out = []
    for raw in value or []:
        e = str(raw).strip()
        try:
            validate_email(e)
        except DjangoValidationError as exc:
            raise ValidationError({field: [f'"{e}" is not an email address.']}) from exc
        if e.lower() not in {x.lower() for x in out}:
            out.append(e)
    return out


def _bodies(greeting: str, intro: str, lines: list[dict], closing: str, signature: str):
    """The mail as plain text and as HTML with the lines in a grid."""
    width = max(len(ln["item_name"]) for ln in lines)
    rows = [
        f"  {'Item'.ljust(width)}  {'Ordered':>12}  {'Received':>12}  {'Difference':>12}  Remark"
    ]
    for ln in lines:
        u = ln["unit"]
        rows.append(
            f"  {ln['item_name'].ljust(width)}  {ln['ordered'] + ' ' + u:>12}  "
            f"{ln['received'] + ' ' + u:>12}  {ln['difference'] + ' ' + u:>12}  {ln['kind_label']}"
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
    tdr = td.replace('style="', 'style="text-align:right;')
    colour = {"Short": "#7a4b00", "Not received": "#b42318", "Excess": "#155c39"}
    grid = (
        '<table cellspacing="0" style="border-collapse:collapse;'
        'border:1px solid #cbd2d9;margin:8px 0 14px">'
        f"<tr><th {th}>#</th><th {th}>Item</th><th {thr}>Ordered</th><th {thr}>Received</th>"
        f"<th {thr}>Difference</th><th {th}>Remark</th></tr>"
        + "".join(
            f"<tr><td {td}>{n}</td><td {td}>{e(ln['item_name'])}</td>"
            f"<td {tdr}>{e(ln['ordered'])} {e(ln['unit'])}</td>"
            f"<td {tdr}>{e(ln['received'])} {e(ln['unit'])}</td>"
            f"<td {tdr}><b>{e(ln['difference'])} {e(ln['unit'])}</b></td>"
            f'<td {td}><b style="color:{colour[ln["kind_label"]]}">'
            f"{e(ln['kind_label'])}</b></td></tr>"
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


def receipt_pdf(r: GoodsReceipt) -> bytes:
    """The receipt as a PDF to attach: what came and where it was stored. No
    rates or values, as on the printed Goods Receipt Note."""
    lines = list(
        r.lines.select_related("item", "unit", "order_line__order").prefetch_related(
            "putaways__location__parent", "putaways__batch"
        )
    )
    items = []
    stored = []
    for n, ln in enumerate(lines, 1):
        u = ln.unit.short_name
        batches = ", ".join(
            dict.fromkeys(p.batch.number if p.batch else p.batch_number for p in ln.putaways.all())
        )
        items.append(
            [
                str(n),
                ln.item.name,
                batches,
                ln.order_line.order.number,
                f"{_plain(ln.order_line.qty)} {u}",
                f"{_plain(ln.received_qty)} {u}",
                f"{_plain(ln.rejected_qty)} {u}" if ln.rejected_qty else "",
                f"{_plain(ln.accepted_qty)} {u}",
            ]
        )
        for p in ln.putaways.all():
            loc = p.location
            place = f"{loc.parent.name} / {loc.name}" if loc.parent_id else loc.name
            packs = (
                f"{p.packages} {p.package_type or 'Bag'}{'s' if p.packages != 1 else ''}"
                if p.packages
                else ""
            )
            stored.append(
                [
                    place,
                    ln.item.name,
                    p.batch.number if p.batch else p.batch_number,
                    packs,
                    f"{_plain(p.qty)} {u}",
                ]
            )
    bits = [r.company.name, f"Supplier {r.supplier.name}", f"Date {_dmy(r.receipt_date)}"]
    if r.challan_no:
        bits.append(f"Challan {r.challan_no}")
    sheets = [
        {
            "title": "Items Received",
            "columns": [
                "#",
                "Item",
                "Batch",
                "PO No",
                "Ordered",
                "Received",
                "Rejected",
                "Accepted",
            ],
            "rows": items,
        }
    ]
    if stored:
        sheets.append(
            {
                "title": "Bin-wise Storage",
                "columns": ["Bin", "Item", "Batch", "Packages", "Qty"],
                "rows": stored,
            }
        )
    return printout.pdf(
        f"Goods Receipt Note {r.number}", " · ".join(bits), sheets, print_mark.mark(r.company)
    )


# The order itself, as a PDF and by mail ----------------------------------------


def _order_file(o: PurchaseOrder) -> tuple[str, bytes, str]:
    return (
        f"{(o.number or 'draft').replace('/', '-')}.pdf",
        order_pdf(_fresh(o)),
        "application/pdf",
    )


class OrderPdfView(APIView):
    """GET: the order as a PDF file, as it is attached to mail."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        o = _order(request, pk)
        name, data, kind = _order_file(o)
        response = HttpResponse(data, content_type=kind)
        response["Content-Disposition"] = f'inline; filename="{name}"'
        return response


def _order_to(o: PurchaseOrder) -> list[dict]:
    """Who the order goes to: the contacts ticked "Mail" on it (supplier's and
    agent's), and the purchaser agent when ticked; else the supplier's first."""
    found = {c.pk: c for c in PartyContact.objects.filter(pk__in=o.mail_to).exclude(email="")}
    out = [{"name": found[i].name, "email": found[i].email} for i in o.mail_to if i in found]
    if o.mail_agent_user and (email := person_email(o.purchaser)):
        out.append({"name": o.purchaser.name, "email": email})
    if not out:
        out = [{"name": c.name, "email": c.email} for c in _supplier_contacts(o)[:1]]
    return out


def _order_message(o: PurchaseOrder) -> str:
    when = f" dated {_dmy(o.order_date)}"
    text = f"Please find attached our purchase order {o.number}{when}."
    if o.expected_date:
        text += f" The goods are expected by {_dmy(o.expected_date)}."
    return text + " Kindly confirm receipt of the order and the dispatch date."


class OrderMailView(APIView):
    """ "Email PO": GET the draft; POST {to, cc, subject, message} sends the
    order to the supplier with its PDF attached."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk)
        if not o.number:
            raise ValidationError({"detail": "Submit the order before mailing it."})
        contacts = _supplier_contacts(o)
        acct = mail.account_of(o.company)
        agent = (
            list(PartyContact.objects.filter(party_id=o.agent.party_id).exclude(email=""))
            if o.agent_id
            else []
        )
        return Response(
            {
                "order_number": o.number,
                "supplier_name": o.supplier.name,
                "mail_ready": bool(acct and acct.password),
                "from": acct.address if acct else "",
                "to": _order_to(o),
                "to_options": [
                    {"name": c.name, "email": c.email, "of": "Supplier"} for c in contacts
                ]
                + [{"name": c.name, "email": c.email, "of": "Agent"} for c in agent],
                "cc": [{"name": request.user.display_name, "email": request.user.email}]
                if request.user.email
                else [],
                "cc_options": [
                    {"name": u.display_name, "email": u.email, "of": "Our team"} for u in _people(o)
                ]
                + [{"name": c.name, "email": c.email, "of": "Supplier"} for c in contacts],
                "subject": f"Purchase Order No : {o.number}",
                "message": _order_message(o),
                "signature": _signature(request.user, o),
                "attachment": _order_file(o)[0],
            }
        )

    # One transaction: if the mail fails, its link is not kept.
    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk)
        if not o.number or o.status == PurchaseOrder.CANCELLED:
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
        names = {c.email.lower(): c.name for c in _supplier_contacts(o)}
        greeting = names.get(to[0].lower(), "Sir/Madam")
        signature = _signature(request.user, o)
        # The private link for the supplier to accept the order or report an
        # issue (buying/supplier_link.py); a new one for each mailing.
        _link, url = make_link(o, request.user, to, request.build_absolute_uri("/"))
        text = (
            f"Dear {greeting},\n\n{message}\n\n"
            f"To accept the order or report an issue, open:\n{url}\n"
            "(this link is for your firm only and works without signing in)\n\n"
            f"Regards,\n{signature}\n"
        )
        e = html.escape
        para = '<p style="margin:0 0 10px">{}</p>'
        button = (
            f'<p style="margin:14px 0"><a href="{e(url)}" style="background:#2f8f55;'
            "color:#ffffff;padding:10px 18px;border-radius:6px;text-decoration:none;"
            'font-weight:bold;display:inline-block">View and Accept Order</a></p>'
            f'<p style="margin:0 0 10px;font-size:12px;color:#56636e">Or open: {e(url)} '
            "(this link is for your firm only and works without signing in)</p>"
        )
        body = (
            '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1f2933">'
            + "".join(
                para.format(e(p).replace(chr(10), "<br>"))
                for p in [f"Dear {greeting},", *message.split("\n\n")]
                if p.strip()
            )
            + button
            + para.format(e(f"Regards,\n{signature}").replace(chr(10), "<br>"))
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
                files=[_order_file(o)],
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
            record_type="purchase_order",
            record_id=o.pk,
            record_name=str(o)[:200],
            action=AuditEntry.UPDATE,
            changes=[{"field": "order_mail", "label": "Mail", "old": None, "new": record}],
        )
        return Response({"sent_to": to, "cc": cc})
