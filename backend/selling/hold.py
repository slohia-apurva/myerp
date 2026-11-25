"""Minimum Order Value (Sidharth, 2026-11-25, previews mockups/sales/20a-20c).

A customer's ledger may carry a Minimum Order Value, before GST. A sales order
whose items come to less is still numbered on Submit, but put "On Hold": it
makes no pick list and no planned orders, and the Stock Check leaves it out.
At once a mail goes to the customer's contacts and the salesman, with the
order's PDF, asking them to increase the order, and the salesman and the
Sales people get a bell notice.

The hold ends when the order is changed ("Edit Order") and submitted again at
or above the minimum, or when someone allowed to cancel orders presses
"Release Hold", which accepts it as it is."""

from __future__ import annotations

import html
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from core import mail
from core.api import Signed
from core.notifications import notify, people_with_roles
from selling.models import SalesOrder
from tenancy.context import tenant_atomic

ZERO = Decimal("0")


def rupees(value) -> str:
    """₹ 8,400.00 in the Indian style."""
    return f"₹ {_indian(Decimal(value))}"


def _indian(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}{whole}.{frac}"


def items_value(o: SalesOrder) -> Decimal:
    """What counts against the minimum: the items' taxable value, before GST.
    Charges such as freight do not count."""
    return o.lines.aggregate(t=Sum("taxable"))["t"] or ZERO


def minimum_of(o: SalesOrder) -> Decimal:
    return o.customer.min_order_value or ZERO


def below_minimum(o: SalesOrder) -> bool:
    least = minimum_of(o)
    return least > 0 and items_value(o) < least


def _salesman(o: SalesOrder):
    return o.salesman or o.customer.salesman


def _record(o: SalesOrder, user, label: str, text: str) -> None:
    AuditEntry.objects.create(
        user=user,
        user_name=user.display_name[:150],
        company=o.company,
        record_type="sales_order",
        record_id=o.pk,
        record_name=str(o)[:200],
        action=AuditEntry.UPDATE,
        changes=[{"field": "hold", "label": label, "old": None, "new": text}],
    )


def subject(o: SalesOrder) -> str:
    return f"Order On Hold: below Minimum Order Value, Order No : {o.number}"


def message(o: SalesOrder) -> str:
    from buying.supplier_mail import _dmy

    value, least = Decimal(o.hold.get("value", "0")), Decimal(o.hold.get("minimum", "0"))
    first = "Thank you for your order"
    if o.customer_po_no:
        first += f" {o.customer_po_no}"
        if o.customer_po_date:
            first += f" dated {_dmy(o.customer_po_date)}"
    first += (
        f". The value of our order confirmation {o.number} is {rupees(value)} before GST, "
        f"which is below your minimum order value of {rupees(least)} "
        f"(short by {rupees(least - value)})."
    )
    second = (
        f"The order is on hold. Kindly increase the order to at least {rupees(least)} "
        "so we can process it. The order as it stands is attached."
    )
    return f"{first}\n\n{second}"


def recipients(o: SalesOrder) -> list[dict]:
    """The contacts ticked "Mail" on the order (else the customer's main
    contact) and the salesman, from the People master."""
    from selling.customer_mail import _to

    out = list(_to(o))
    man = _salesman(o)
    if man and man.email and man.email.lower() not in {r["email"].lower() for r in out}:
        out.append({"name": man.name, "email": man.email})
    return out


def _mail(o: SalesOrder, user) -> tuple[list[str], str]:
    """Send the hold mail. Never stops the order: a mailbox not set up, or a
    server that refuses, is noted on the order instead."""
    from buying.supplier_mail import _signature
    from selling.customer_mail import _to, order_file

    customers = _to(o)
    to = [r["email"] for r in recipients(o)]
    if not to:
        return [], "Nobody has an email address: the customer has no contact with one."
    greeting = (customers[0]["name"] if customers else "") or "Sir/Madam"
    body = message(o)
    signature = _signature(user, o)
    text = f"Dear {greeting},\n\n{body}\n\nRegards,\n{signature}\n"
    e = html.escape
    para = '<p style="margin:0 0 10px">{}</p>'
    rich = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1f2933">'
        + "".join(
            para.format(e(p).replace(chr(10), "<br>"))
            for p in [f"Dear {greeting},", *body.split("\n\n"), f"Regards,\n{signature}"]
        )
        + "</div>"
    )
    cc = [user.email] if user.email and user.email.lower() not in {t.lower() for t in to} else []
    try:
        mail.send(
            o.company,
            to=to,
            cc=cc,
            subject=subject(o),
            text=text,
            html=rich,
            reply_to=[user.email] if user.email else [],
            files=[order_file(o)],
        )
    except mail.NotSetUp as exc:
        return [], str(exc)
    except ValidationError as exc:
        detail = exc.detail.get("detail") if isinstance(exc.detail, dict) else exc.detail
        return [], str(detail[0] if isinstance(detail, list) else detail)
    return to, ""


def put_on_hold(o: SalesOrder, user) -> None:
    """Submit found the order below the customer's minimum: hold it, mail the
    customer and the salesman, and tell the salesman and the Sales people."""
    value, least = items_value(o), minimum_of(o)
    o.status = SalesOrder.ON_HOLD
    o.hold = {
        "value": str(value),
        "minimum": str(least),
        "at": timezone.now().isoformat(),
        "by": user.display_name,
        "mailed_to": [],
        "mail_error": "",
    }
    o.save()
    to, error = _mail(o, user)
    o.hold = {**o.hold, "mailed_to": to, "mail_error": error}
    o.save(update_fields=["hold"])
    short = least - value
    _record(
        o,
        user,
        "Put On Hold",
        f"Below minimum {rupees(least)} ({rupees(value)})"
        + (f"\nMailed to {', '.join(to)}" if to else f"\nNot mailed: {error}"),
    )
    people = people_with_roles(o.company, "sales", "owner")
    man = _salesman(o)
    if man and man.user_id and man.user.is_active:
        people.append(man.user)
    mailed = (
        "• Mailed to the customer and the salesman, with the order PDF."
        if to
        else f'• Not mailed: {error} Use "Email Customer" on the order.'
    )
    notify(
        people,
        o.company,
        f"Sales order {o.number} is On Hold",
        f"{o.customer.name} ordered {rupees(value)} before GST; their minimum is "
        f"{rupees(least)} (short by {rupees(short)}).\n\n"
        f"{mailed}\n"
        f'• Ask the customer to add {rupees(short)} or more, then "Edit Order" and '
        "submit again.",
        f"#/companies/{o.company_id}/sales-orders?view={o.pk}",
    )


def end_hold(o: SalesOrder, user, how: str) -> None:
    """The order goes ahead: it is Ordered, and makes its pick list and plans."""
    o.hold = {**o.hold, "ended": how, "ended_by": user.display_name}
    o.hold["ended_at"] = timezone.now().isoformat()
    o.status = SalesOrder.ORDERED
    o.save()
    _record(o, user, "Hold Ended", how)


class OrderReleaseView(APIView):
    """POST: "Release Hold": accept a held order as it is (people who may
    cancel sales orders)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        from selling.api import CANCEL, _check, _fresh, _order, go_ahead

        _check(request, CANCEL)
        o = _order(request, pk, lock=True)
        if o.status != SalesOrder.ON_HOLD:
            raise ValidationError({"detail": "This order is not on hold."})
        end_hold(o, request.user, f"Released as it is by {request.user.display_name}")
        go_ahead(o, request.user)
        return Response(_fresh(o))
