"""Daily Stock Check (Sidharth, 2026-11-21): every morning, for a company that
has it on, each branch's short items get draft purchase orders, one per
supplier, and the Purchase people get a bell notice. It runs once a day, and
drafts count as Incoming, so nothing is ordered twice."""

import pytest
from django.core.management import call_command
from django.utils import timezone

from buying import planning
from buying.models import PurchaseOrder, StockCheckRun
from core.models import Company, Item, Notification
from tenancy.context import use_tenant
from tests.test_sales_orders import call, owner, stock_in, world  # noqa: F401  (fixtures)
from tests.test_stock_check import buyer, check, planned  # noqa: F401  (fixtures)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def switch_on(w, on=True, hour=0):
    with use_tenant(w["tenant"]):
        Company.objects.filter(pk=w["company"]).update(
            daily_stock_check=on, daily_stock_check_hour=hour
        )


def test_the_morning_run_makes_drafts_and_tells_purchase_once(owner, buyer, planned):  # noqa: F811
    w = planned
    stock_in(w, "fg", "100")
    call_command("run_scheduled")
    with use_tenant(w["tenant"]):
        assert not PurchaseOrder.objects.exists()  # off until switched on
    switch_on(w)
    call_command("run_scheduled")
    call_command("run_scheduled")  # the next hour: already ran today
    with use_tenant(w["tenant"]):
        [run] = StockCheckRun.objects.all()
        assert run.daily and run.short_count == 1 and run.order_count == 1
        [po] = PurchaseOrder.objects.all()
        assert po.status == "draft" and po.stock_check_run == run
        assert po.notes == "Made by the daily Stock Check." and po.created_by is None
        notice = Notification.objects.filter(title__startswith="Daily Stock Check").first()
        assert notice is not None and "1 draft Purchase Order: Leaf Supplier" in notice.body

    seen = check(buyer, w)
    assert seen["rows"] == []  # the draft is Incoming now
    [draft] = seen["drafts"]
    assert draft["id"] == po.pk and draft["daily"] is True
    assert seen["runs"][0]["order_count"] == 1


def test_an_item_with_no_supplier_is_only_listed(owner, planned):  # noqa: F811
    w = planned
    with use_tenant(w["tenant"]):
        Item.objects.filter(pk=w["tea"]).update(preferred_supplier=None)
    switch_on(w)
    call_command("run_scheduled")
    with use_tenant(w["tenant"]):
        assert not PurchaseOrder.objects.exists()
        notice = Notification.objects.get(title__startswith="Daily Stock Check")
        assert "with no Preferred Supplier: Green Tea 100 g" in notice.body


def test_due_from_its_hour_once_a_day(planned):  # noqa: F811
    w = planned
    switch_on(w, hour=7)
    now = timezone.localtime()
    with use_tenant(w["tenant"]):
        company = Company.objects.get(pk=w["company"])
        assert not planning.due(company, now.replace(hour=6, minute=59))
        assert planning.due(company, now.replace(hour=7, minute=0))
        StockCheckRun.objects.create(company=company, branch_id=w["branch"], daily=True)
        assert not planning.due(company, now.replace(hour=23))
        company.daily_stock_check = False
        assert not planning.due(company, now.replace(hour=8))


def test_only_who_may_change_masters_sets_the_daily_run(owner, buyer, planned):  # noqa: F811
    w = planned
    path = f"companies/{w['company']}/stock-check/daily/"
    assert call(buyer, "put", path, {"on": True, "hour": 7}).status_code == 403
    done = call(owner, "put", path, {"on": True, "hour": 6})
    assert done.status_code == 200, done.json()
    assert done.json() == {"on": True, "hour": 6, "can_change": True}
    assert call(owner, "put", path, {"on": True, "hour": 24}).status_code == 400
