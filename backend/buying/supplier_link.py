"""The supplier's link (Sidharth, 2026-11-15): every purchase order mailed
with "Email PO" carries a private link made for that mailing. The supplier
opens it without signing in, sees the order, and can "Accept Order" (with an
expected dispatch date) or "Report an Issue" with a comment, and come back
later to add comments. Each reply is kept on the order ("Supplier Response"),
written to its activity, and sent as a bell notice to whoever mailed it, the
Purchase team and the Owner. The supplier can never change the order.

The link is a long random code; only its SHA-256 is stored, so the code lives
in the mail alone. A link works for 90 days and never on a cancelled order;
once the order is received or closed the page only shows it."""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from buying.api import _fresh
from buying.models import PurchaseOrder, SupplierLink, SupplierResponse
from core.notifications import notify, people_with_roles
from tenancy.context import tenant_atomic

VALID_DAYS = 90
PAGE = "#/po-reply/"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def make_link(o: PurchaseOrder, user, to: list[str], base_url: str) -> tuple[SupplierLink, str]:
    """A new link for this mailing; returns it and the address to put in the mail."""
    token = secrets.token_urlsafe(32)
    link = SupplierLink.objects.create(
        order=o,
        token_hash=_hash(token),
        mailed_to=", ".join(to)[:500],
        created_by=user,
        expires_at=timezone.now() + timedelta(days=VALID_DAYS),
    )
    if o.supplier_status == "":
        o.supplier_status = "sent"
        o.save(update_fields=["supplier_status"])
    return link, base_url.rstrip("/") + "/" + PAGE + token


def _dmy(d) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def response_box(o: PurchaseOrder) -> dict:
    """The order's "Supplier Response" box: each mailing and each reply, oldest first."""
    rows = []
    for link in o.links.select_related("created_by").prefetch_related("responses"):
        rows.append(
            {
                "kind": "mailed",
                "at": link.created_at,
                "to": link.mailed_to,
                "by": link.created_by.display_name if link.created_by else "",
                "opened_at": link.opened_at,
            }
        )
        rows += [
            {
                "kind": r.kind,
                "at": r.created_at,
                "name": r.name,
                "dispatch_date": r.dispatch_date,
                "comment": r.comment,
            }
            for r in link.responses.all()
        ]
    rows.sort(key=lambda r: r["at"])
    accepted = [r for r in rows if r["kind"] == SupplierResponse.ACCEPTED]
    return {
        "status": o.supplier_status,
        "status_label": o.get_supplier_status_display(),
        "dispatch_date": accepted[-1]["dispatch_date"] if accepted else None,
        "rows": rows,
    }


def _link(token: str, lock: bool = False) -> SupplierLink:
    rows = SupplierLink.objects.filter(token_hash=_hash(token or ""))
    if lock:
        rows = rows.select_for_update(of=("self",))
    link = rows.select_related("order__company").first()
    if link is None or "purchase" not in link.order.company.modules:
        raise NotFound("This link is not valid. Please ask the buyer for a new one.")
    return link


def _state(link: SupplierLink) -> str:
    """open: replies allowed; done: the order is complete, page shows only;
    cancelled; expired."""
    o = link.order
    if o.status == PurchaseOrder.CANCELLED:
        return "cancelled"
    if link.expires_at <= timezone.now():
        return "expired"
    if o.status in PurchaseOrder.OPEN:
        return "open"
    return "done"


def _page(link: SupplierLink) -> dict:
    """What the supplier sees: the order as printed for them, nothing internal."""
    state = _state(link)
    out = {"state": state, "supplier_status": link.order.supplier_status}
    if state in ("cancelled", "expired"):
        out["company_name"] = link.order.company.name
        out["number"] = link.order.number
        return out
    d = _fresh(link.order)
    out |= {
        "company_name": d["letterhead"]["name"],
        "company_city": d["letterhead"]["city"],
        "company_mark": d["letterhead"]["mark"],
        "supplier_name": d["supplier_name"],
        "number": d["number"],
        "order_date": d["order_date"],
        "expected_date": d["expected_date"],
        "deliver_to": d["branch_name"],
        "currency_symbol": d["currency_symbol"],
        "total": d["total"],
        "lines": [
            {
                "item_name": ln["item_name"],
                "description": ln["description"],
                "qty": ln["qty"],
                "unit_name": ln["unit_name"],
                "rate": ln["rate"],
                "taxable": ln["taxable"],
            }
            for ln in d["lines"]
        ],
        "replies": [
            {
                "kind": r.kind,
                "name": r.name,
                "at": r.created_at,
                "dispatch_date": r.dispatch_date,
                "comment": r.comment,
            }
            for r in SupplierResponse.objects.filter(order=link.order)
        ],
    }
    return out


def _date(value) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError({"dispatch_date": ["Give a valid date."]}) from exc


class PublicOrderView(APIView):
    """The supplier's page (no sign-in). GET the order; POST {kind: accepted |
    issue | comment, name, dispatch_date, comment} records a reply."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @tenant_atomic()
    def get(self, request, token: str):
        link = _link(token, lock=True)
        if link.opened_at is None and _state(link) != "expired":
            link.opened_at = timezone.now()
            link.save(update_fields=["opened_at"])
            o = link.order
            if o.supplier_status == "sent":
                o.supplier_status = "opened"
                o.save(update_fields=["supplier_status"])
        return Response(_page(link))

    @tenant_atomic()
    def post(self, request, token: str):
        link = _link(token, lock=True)
        o = PurchaseOrder.objects.select_for_update().get(pk=link.order_id)
        link.order = o
        state = _state(link)
        if state == "cancelled":
            raise ValidationError({"detail": "This order has been cancelled."})
        if state == "expired":
            raise ValidationError(
                {"detail": "This link has expired. Please ask the buyer for a new one."}
            )
        data = request.data if isinstance(request.data, dict) else {}
        kind = str(data.get("kind") or "")
        if kind not in dict(SupplierResponse.KINDS):
            raise ValidationError({"detail": "Choose Accept Order or Report an Issue."})
        if kind != SupplierResponse.COMMENT and state != "open":
            raise ValidationError(
                {"detail": "This order is already complete; you can still add a comment."}
            )
        name = " ".join(str(data.get("name") or "").split())[:100]
        if not name:
            raise ValidationError({"name": ["Give your name."]})
        comment = str(data.get("comment") or "").strip()[:2000]
        if kind != SupplierResponse.ACCEPTED and not comment:
            raise ValidationError({"comment": ["Write your comment."]})
        dispatch = _date(data.get("dispatch_date")) if kind == SupplierResponse.ACCEPTED else None
        if dispatch and dispatch < o.order_date:
            raise ValidationError(
                {"dispatch_date": ["The dispatch date cannot be before the order date."]}
            )
        reply = SupplierResponse.objects.create(
            link=link, order=o, kind=kind, name=name, dispatch_date=dispatch, comment=comment
        )
        if kind != SupplierResponse.COMMENT:
            o.supplier_status = kind
            o.save(update_fields=["supplier_status"])
        _tell(link, o, reply)
        return Response(_page(link))


def _tell(link: SupplierLink, o: PurchaseOrder, r: SupplierResponse) -> None:
    who = f"{r.name} ({o.supplier.name})"
    if r.kind == SupplierResponse.ACCEPTED:
        title = f"Supplier accepted {o.number}"
        text = f"{who} accepted the order."
        if r.dispatch_date:
            text += f"\nDispatch expected: {_dmy(r.dispatch_date)}"
        if r.comment:
            text += f'\n\n"{r.comment}"'
    else:
        label = "issue" if r.kind == SupplierResponse.ISSUE else "comment"
        title = f"Supplier {label} on {o.number}"
        text = f'{who}:\n\n"{r.comment}"'
    people = people_with_roles(o.company, "purchase", "owner")
    if link.created_by and link.created_by.is_active:
        people.append(link.created_by)
    page = f"#/companies/{o.company_id}/purchase-orders?view={o.pk}"
    notify(people, o.company, title, text, page)
    AuditEntry.objects.create(
        user=None,
        user_name=f"{r.name} (supplier)"[:150],
        company=o.company,
        record_type="purchase_order",
        record_id=o.pk,
        record_name=str(o)[:200],
        action=AuditEntry.UPDATE,
        changes=[{"field": "supplier_" + r.kind, "label": title, "old": None, "new": text}],
    )


class PublicOrderPdfView(APIView):
    """GET: the order as a PDF, for the supplier's "Download PDF"."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request, token: str):
        from buying.supplier_mail import _order_file

        link = _link(token)
        if _state(link) in ("cancelled", "expired"):
            raise NotFound("This order is no longer available.")
        name, data, kind = _order_file(link.order)
        response = HttpResponse(data, content_type=kind)
        response["Content-Disposition"] = f'inline; filename="{name}"'
        return response
