"""Automatic reminders for purchase orders with goods still to come (Sidharth,
2026-11-27, preview po-reminder/5).

The group's ReminderSchedule lists steps counted from each order's Expected
Delivery ("2 days before", "3 days after", …), then a reminder every
`repeat_days`, up to `repeat_max` more. Once a day, from `send_hour`, the
hourly scheduler (tenancy run_scheduled) sends each open order the next step
that has fallen due: at most one reminder per order per day, none on a day a
reminder already went (by hand or not), none on Sundays when skipped. Orders
received in full, closed or cancelled stop by themselves; a supplier (its
ledger) or one order can be left out with "No Automatic Reminders".

The mail uses the step's mail template (else the group's default reminder),
lists only the pending lines, goes from the company's mailbox and is written
to the order's Activity and its Reminders box. When it cannot go (no mailbox,
no supplier address), the purchaser is told once by a bell notice and it is
tried again the next day."""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from audit.models import AuditEntry
from buying import mail_text
from buying.api import person_email
from buying.models import OrderReminder, PurchaseOrder, ReminderSchedule, ReminderStep
from core import mail
from core.mail_templates import templates_for
from core.models import MailTemplate
from core.notifications import notify, people_with_roles


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def plan(expected: date, schedule: ReminderSchedule, steps: list[ReminderStep]) -> list[dict]:
    """Every reminder the schedule makes for an order expected on `expected`."""
    out = []
    for st in steps:
        delta = timedelta(days=st.days)
        out.append(
            {"on": expected - delta if st.before else expected + delta, "template": st.template}
        )
    if out and schedule.repeat_days:
        last = max(x["on"] for x in out)
        for k in range(1, schedule.repeat_max + 1):
            out.append(
                {"on": last + timedelta(days=k * schedule.repeat_days),
                 "template": schedule.repeat_template}
            )  # fmt: skip
    out.sort(key=lambda x: x["on"])
    for n, x in enumerate(out, 1):
        x["step"] = n
        x["label"] = f"{ordinal(n)} reminder"
    return out


def _left_out(o: PurchaseOrder) -> str:
    if o.no_auto_reminders:
        return "this order is left out"
    if o.supplier.no_auto_reminders:
        return "this supplier is left out"
    return ""


def next_for(o: PurchaseOrder, schedule: ReminderSchedule | None = None, steps=None) -> dict | None:
    """The next automatic reminder for the order, or None."""
    schedule = schedule or ReminderSchedule.current()
    steps = list(schedule.steps.select_related("template")) if steps is None else steps
    if not o.expected_date or o.status not in PurchaseOrder.OPEN or not o.number:
        return None
    sent = o.reminders.filter(automatic=True, failed="").count()
    p = plan(o.expected_date, schedule, steps)
    return p[sent] if sent < len(p) else None


def due(schedule: ReminderSchedule, now=None) -> bool:
    now = timezone.localtime(now)
    if not schedule.is_on or now.hour < schedule.send_hour:
        return False
    return schedule.last_run_on != now.date()


def _template(t: MailTemplate | None) -> MailTemplate | None:
    if t is not None and t.is_active and t.used_for == MailTemplate.REMINDER:
        return t
    found = templates_for(MailTemplate.REMINDER)
    return found[0] if found else None


def send_one(o: PurchaseOrder, step: dict, schedule: ReminderSchedule) -> OrderReminder | None:
    """Send the order's reminder for `step`; a row says what happened."""
    from buying.po_reminder import _bodies, pending_lines
    from buying.supplier_mail import _order_file, _supplier_contacts

    lines = pending_lines(o)
    if not lines:
        return None
    contacts = _supplier_contacts(o)
    ticked = [c for c in contacts if c.pk in o.mail_to] or contacts[:1]
    to = [c.email for c in ticked]
    t = _template(step["template"])
    buyer = person_email(o.purchaser)
    cc = []
    if schedule.copy_purchaser and buyer:
        cc.append(buyer)
    if schedule.copy_submitter and o.submitted_by_id and o.submitted_by.email:
        cc.append(o.submitted_by.email)
    cc = [e for i, e in enumerate(cc) if e.lower() not in {x.lower() for x in to + cc[:i]}]
    row = OrderReminder(
        order=o, automatic=True, step=step["step"], template_name=t.name if t else "",
        sent_to=to, line_count=len(lines),
    )  # fmt: skip
    failed = ""
    if not to:
        failed = "the supplier has no contact with an email address"
    elif t is None:
        failed = "there is no active reminder mail template"
    else:
        greeting = ticked[0].name or "Sir/Madam"
        w = mail_text.words(t, mail_text.order_values(o, greeting))
        sender = o.purchaser.name if o.purchaser_id else "Purchase Department"
        signature = f"{sender}\n{o.company.name}"
        text, body = _bodies(greeting, w["opening"], lines, w["closing"], signature)
        try:
            mail.send(
                o.company, to=to, cc=cc, subject=w["subject"], text=text, html=body,
                reply_to=[buyer] if buyer else [],
                files=[_order_file(o)] if t.attach else [],
            )  # fmt: skip
        except mail.NotSetUp:
            failed = "the company's mail account is not set up"
    if failed:
        row.failed = failed[:200]
        told = o.reminders.filter(automatic=True, step=step["step"]).exclude(failed="").exists()
        row.save()
        if not told:
            users = [o.purchaser.user] if o.purchaser_id and o.purchaser.user_id else []
            users = users or people_with_roles(o.company, "purchase", "owner")
            notify(
                users,
                o.company,
                f"Automatic reminder not sent: {o.number}",
                f"The {step['label']} to {o.supplier.name} could not go: {failed}.\n"
                "It will be tried again tomorrow.",
                f"#/companies/{o.company_id}/purchase-orders?view={o.pk}",
            )
        return row
    row.save()
    AuditEntry.objects.create(
        user=None,
        user_name="Automatic",
        company=o.company,
        record_type="purchase_order",
        record_id=o.pk,
        record_name=str(o)[:200],
        action=AuditEntry.UPDATE,
        changes=[
            {
                "field": "po_reminder",
                "label": "Reminder",
                "old": None,
                "new": f'Automatic {step["label"]} ({t.name}): "{w["subject"]}" to '
                + ", ".join(to)
                + (f", copy to {', '.join(cc)}" if cc else "")
                + "; "
                + "; ".join(
                    f"{ln['item_code']} {ln['pending']} {ln['unit']} pending" for ln in lines
                ),
                "to": to,
            }
        ],
    )
    return row


def run(now=None) -> tuple[int, int]:
    """Send today's automatic reminders for this tenant. (sent, failed)."""
    now = timezone.localtime(now)
    today = now.date()
    schedule = ReminderSchedule.current()
    ReminderSchedule.objects.filter(pk=schedule.pk).update(last_run_on=today)
    if schedule.skip_sundays and today.weekday() == 6:
        return 0, 0
    steps = list(schedule.steps.select_related("template"))
    sent = failed = 0
    orders = (
        PurchaseOrder.objects.filter(
            status__in=PurchaseOrder.OPEN, expected_date__isnull=False, no_auto_reminders=False,
            supplier__no_auto_reminders=False,
        )
        .exclude(number="")
        .select_related("company", "supplier", "purchaser__user", "submitted_by")
        .order_by("id")
    )  # fmt: skip
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for o in orders:
        step = next_for(o, schedule, steps)
        if step is None or step["on"] > today:
            continue
        if o.reminders.filter(sent_at__gte=start, failed="").exists():
            continue  # one reminder a day is enough
        row = send_one(o, step, schedule)
        if row is None:
            continue
        if row.failed:
            failed += 1
        else:
            sent += 1
    return sent, failed
