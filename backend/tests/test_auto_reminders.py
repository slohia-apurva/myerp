"""Automatic reminders: the group's schedule chases open orders by itself."""

import datetime

import pytest
from django.core import mail as outbox
from django.utils import timezone

from buying import auto_reminders
from buying.models import OrderReminder, PurchaseOrder, ReminderSchedule
from core.models import Ledger, Notification
from tenancy.context import use_tenant
from tests.test_goods_receipts import grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_orders import buyer, call, owner, world  # noqa: F401
from tests.test_supplier_mail import _mailbox, _secrets_key, short  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _at(d: datetime.date, hour=11):
    return timezone.make_aware(datetime.datetime(d.year, d.month, d.day, hour))


def test_plan_counts_from_expected_delivery():
    s = ReminderSchedule(repeat_days=7, repeat_max=2)

    class Step:
        def __init__(self, days, before):
            self.days, self.before, self.template = days, before, None

    p = auto_reminders.plan(datetime.date(2026, 12, 15), s, [Step(2, True), Step(3, False)])
    assert [(x["on"].isoformat(), x["label"]) for x in p] == [
        ("2026-12-13", "1st reminder"),
        ("2026-12-18", "2nd reminder"),
        ("2026-12-25", "3rd reminder"),
        ("2027-01-01", "4th reminder"),
    ]


def test_schedule_screen_and_daily_run(owner, buyer, short, alpha):  # noqa: F811
    got = call(owner, "get", "reminder-schedule/").json()
    assert got["is_on"] is False and [s["days"] for s in got["steps"]] == [2, 3, 7]
    body = {**got, "is_on": True, "send_hour": 10, "skip_sundays": False, "repeat_days": 7,
            "repeat_max": 2, "steps": [{"days": 0, "before": False, "template": None}]}  # fmt: skip
    put = call(owner, "put", "reminder-schedule/", body)
    assert put.status_code == 200, put.json()
    assert [d["on"] for d in put.json()["example"]["dates"]] == [
        "15-12-2026", "22-12-2026", "29-12-2026",
    ]  # fmt: skip
    assert call(buyer, "put", "reminder-schedule/", body).status_code == 403

    with use_tenant(alpha):
        o = PurchaseOrder.objects.get(pk=short["po"])
        due_day = o.expected_date or timezone.localdate()
        PurchaseOrder.objects.filter(pk=o.pk).update(expected_date=due_day)
        s = ReminderSchedule.current()
        assert not auto_reminders.due(s, _at(due_day, 9))  # before the hour
        assert auto_reminders.due(s, _at(due_day, 11))
        # No mailbox yet: nothing goes, the purchase team is told once.
        assert auto_reminders.run(_at(due_day)) == (0, 1)
        assert auto_reminders.run(_at(due_day)) == (0, 1)
        told = Notification.objects.filter(title__startswith="Automatic reminder not sent")
        assert told.count() >= 1
        first_count = told.count()
        auto_reminders.run(_at(due_day))
        assert told.count() == first_count
    _mailbox(alpha, short["company"])
    with use_tenant(alpha):
        assert auto_reminders.run(_at(due_day)) == (1, 0)
        m = outbox.outbox[-1]
        assert m.subject.startswith("Reminder: Pending Supply") and m.to == ["sales@dtt.in"]
        # Once a day only; the next step is a week later.
        assert auto_reminders.run(_at(due_day)) == (0, 0)
        assert auto_reminders.run(_at(due_day + datetime.timedelta(days=3))) == (0, 0)
        assert auto_reminders.run(_at(due_day + datetime.timedelta(days=7))) == (1, 0)
        assert OrderReminder.objects.filter(order=o, automatic=True, failed="").count() == 2

    box = call(buyer, "get", f"purchase-orders/{o.pk}/reminders/").json()
    assert [r["how"] for r in box["rows"] if not r["failed"]] == ["Automatic", "Automatic"]
    assert box["next"]["label"] == "3rd reminder"

    # Leave the order out, then the supplier.
    call(buyer, "patch", f"purchase-orders/{o.pk}/reminders/", {"no_auto_reminders": True})
    with use_tenant(alpha):
        assert auto_reminders.run(_at(due_day + datetime.timedelta(days=14))) == (0, 0)
        PurchaseOrder.objects.filter(pk=o.pk).update(no_auto_reminders=False)
        Ledger.objects.filter(pk=o.supplier_id).update(no_auto_reminders=True)
        assert auto_reminders.run(_at(due_day + datetime.timedelta(days=14))) == (0, 0)
        Ledger.objects.filter(pk=o.supplier_id).update(no_auto_reminders=False)
        PurchaseOrder.objects.filter(pk=o.pk).update(status=PurchaseOrder.CLOSED)
        assert auto_reminders.run(_at(due_day + datetime.timedelta(days=14))) == (0, 0)
