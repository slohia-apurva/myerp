"""The posting service: GL and stock ledger rules every document relies on."""

from datetime import date
from decimal import Decimal as D

import pytest
from django.db import connections
from django.db.utils import DatabaseError, InternalError
from rest_framework.exceptions import ValidationError

from core.companies import create_company
from core.models import (
    Batch,
    Branch,
    FiscalPeriod,
    Item,
    ItemGroup,
    ItemGroupAccount,
    Ledger,
    LedgerGroup,
    Unit,
    WarehouseLocation,
)
from posting import accounts
from posting.models import GLEntry, StockLot, StockMove
from posting.service import GLLine, StockLine, Voucher, cancel, gl_balance, on_hand, post
from tenancy.context import tenant_atomic, use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

D1, D2, D3 = date(2026, 5, 4), date(2026, 5, 10), date(2026, 5, 20)


@pytest.fixture
def books(alpha):
    with use_tenant(alpha):
        company = create_company(
            name="Apurvam Organics LLP", state_code="27", books_start=date(2026, 4, 1)
        )
        branch = Branch.objects.get(company=company, is_head_office=True)
        store = WarehouseLocation.objects.get(branch=branch, is_default=True)
        rack = WarehouseLocation.objects.create(branch=branch, kind="rack", name="F01")
        bin_a = WarehouseLocation.objects.create(
            branch=branch, kind="bin", name="A-02", parent=rack
        )
        group = ItemGroup.objects.create(name="Raw material")
        sub = ItemGroup.objects.create(name="Tea", parent=group)
        inventories = LedgerGroup.objects.get(company=company, code="stock_in_hand")
        stock_ledger = Ledger.objects.create(company=company, group=inventories, name="Stock RM")
        ItemGroupAccount.objects.create(group=group, company=company, stock_ledger=stock_ledger)
        kg = Unit.objects.get(name="Kilogram")
        tea = Item.objects.create(
            item_number="ITEM-90001", name="Assam CTC", stock_unit=kg, item_group=sub
        )
        green = Item.objects.create(
            item_number="ITEM-90002",
            name="Green tea",
            stock_unit=kg,
            item_group=sub,
            batch_tracked=True,
        )
        b1234 = Batch.objects.create(item=green, number="1234")
        yield {
            "tenant": alpha,
            "company": company,
            "branch": branch,
            "store": store,
            "rack": rack,
            "bin": bin_a,
            "tea": tea,
            "green": green,
            "b1234": b1234,
            "stock_ledger": stock_ledger,
        }


def voucher(b, n, day=D1, kind="test_receipt"):
    return Voucher(b["company"], b["branch"], day, kind, n, f"T-{n}")


def receive(b, n, qty, rate, day=D1, item="tea", where="store", batch=None):
    """A goods receipt as the GRN will post it: Dr Stock, Cr GRNI."""
    grni = accounts.system_ledger(b["company"], accounts.GRNI)
    line = StockLine(b[item], b[where], D(qty), D(rate), batch=b[batch] if batch else None)

    def gl(values):
        return [
            GLLine(b["stock_ledger"], debit=values[0]),
            GLLine(grni, credit=values[0]),
        ]

    return post(voucher(b, n, day), stock=[line], gl=gl)


def issue(b, n, qty, day=D3, item="tea", where="store", batch=None):
    adj = accounts.system_ledger(b["company"], accounts.STOCK_ADJUSTMENT)
    line = StockLine(b[item], b[where], -D(qty), batch=b[batch] if batch else None)

    def gl(values):
        return [GLLine(adj, debit=-values[0]), GLLine(b["stock_ledger"], credit=-values[0])]

    return post(voucher(b, n, day, "test_issue"), stock=[line], gl=gl)


def test_a_receipt_posts_stock_and_balanced_gl(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        done = receive(b, 1, "600", "250.333333")
        assert done.stock_values == [D("150200.00")]
        assert on_hand(b["tea"], b["store"]) == D("600")
        grni = accounts.system_ledger(b["company"], accounts.GRNI)
        assert grni.name == "Goods Received but Bills not Received"
        assert grni.group.code == "other_current_liabilities"
        assert gl_balance(b["stock_ledger"]) == D("150200.00")
        assert gl_balance(grni) == D("-150200.00")


def test_fifo_issue_uses_the_oldest_lots(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "100", "10", D1)
        receive(b, 2, "100", "12", D2)
        out = issue(b, 3, "150")
        assert out.stock_values == [D("-1600.00")]  # 100 x 10 + 50 x 12
        lots = list(StockLot.objects.filter(item=b["tea"]).order_by("date"))
        assert [lot.qty_left for lot in lots] == [D("0"), D("50")]
        assert gl_balance(b["stock_ledger"]) == D("600.00")


def test_the_last_of_a_lot_takes_its_exact_value(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "3", "33.333333")  # value 100.00
        issue(b, 2, "1")
        issue(b, 3, "1")
        last = issue(b, 4, "1")
        assert last.stock_values == [D("-33.34")]
        assert gl_balance(b["stock_ledger"]) == D("0.00")


def test_stock_cannot_go_below_zero(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "10", "5")
        with pytest.raises(ValidationError, match="Only 10"):
            issue(b, 2, "11")


def test_an_issue_cannot_use_lots_received_after_it(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "10", "5", D3)
        with pytest.raises(ValidationError, match="not enough valued stock"):
            issue(b, 2, "5", D2)


def test_backdated_entries_before_an_issue_are_refused(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "10", "5", D1)
        issue(b, 2, "5", D3)
        with pytest.raises(ValidationError, match="already been issued"):
            receive(b, 3, "10", "6", D2)
        receive(b, 4, "10", "6", D3)  # the same day or later is fine


def test_batches_and_bins(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        with pytest.raises(ValidationError, match="give the batch"):
            receive(b, 1, "10", "5", item="green")
        with pytest.raises(ValidationError, match="does not keep batches"):
            receive(b, 2, "10", "5", batch="b1234")
        with pytest.raises(ValidationError, match="is a rack"):
            receive(b, 3, "10", "5", where="rack")
        receive(b, 4, "300", "5", item="green", where="bin", batch="b1234")
        receive(b, 5, "300", "5", item="green", where="store", batch="b1234")
        assert on_hand(b["green"], b["bin"], b["b1234"]) == D("300")
        with pytest.raises(ValidationError, match="Only 300"):
            issue(b, 6, "301", item="green", where="bin", batch="b1234")


def test_gl_must_balance(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        grni = accounts.system_ledger(b["company"], accounts.GRNI)
        with pytest.raises(ValidationError, match="does not balance"):
            post(
                voucher(b, 1),
                gl=[GLLine(b["stock_ledger"], debit=D("10")), GLLine(grni, credit=D("9.99"))],
            )


def test_the_database_refuses_an_unbalanced_voucher(books):
    b = books
    with use_tenant(b["tenant"]):
        alias = b["tenant"].db_alias
        with pytest.raises((DatabaseError, InternalError), match="do not balance"):
            with tenant_atomic():
                with connections[alias].cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                GLEntry.objects.create(
                    company=b["company"],
                    branch=b["branch"],
                    date=D1,
                    ledger=b["stock_ledger"],
                    debit=D("5"),
                    voucher_type="raw",
                    voucher_id=1,
                    voucher_no="R-1",
                )


def test_posted_rows_cannot_be_changed_or_deleted(books):
    b = books
    with use_tenant(b["tenant"]):
        with tenant_atomic():
            receive(b, 1, "10", "5")
        move = StockMove.objects.get(voucher_id=1, voucher_type="test_receipt")
        for change in (
            lambda: StockMove.objects.filter(pk=move.pk).update(qty=D("11")),
            lambda: GLEntry.objects.filter(voucher_id=1).delete(),
        ):
            with pytest.raises((DatabaseError, InternalError), match="cannot be changed"):
                with tenant_atomic():
                    change()


def test_locked_months_take_no_postings(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        FiscalPeriod.objects.filter(year__company=b["company"], start_date=date(2026, 5, 1)).update(
            is_locked=True
        )
        with pytest.raises(ValidationError, match="locked"):
            receive(b, 1, "10", "5")


def test_cancel_reverses_exactly(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "100", "10", D1)
        issue(b, 2, "40")
        cancel("test_issue", 2)
        assert on_hand(b["tea"], b["store"]) == D("100")
        assert StockLot.objects.get(item=b["tea"]).qty_left == D("100")
        cancel("test_receipt", 1)
        assert on_hand(b["tea"], b["store"]) == D("0")
        assert gl_balance(b["stock_ledger"]) == D("0.00")
        with pytest.raises(ValidationError, match="already been cancelled"):
            cancel("test_receipt", 1)


def test_a_receipt_already_used_cannot_be_cancelled(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "100", "10")
        issue(b, 2, "1")
        with pytest.raises(ValidationError, match="cancel those entries first"):
            cancel("test_receipt", 1)


def test_customer_goods_move_quantity_only(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        line = StockLine(b["tea"], b["store"], D("50"), valued=False)
        done = post(voucher(b, 1), stock=[line])
        assert done.stock_values == [D("0")] and done.gl == []
        assert on_hand(b["tea"], b["store"]) == D("50")
        assert not StockLot.objects.filter(item=b["tea"]).exists()


def test_a_voucher_posts_once_and_items_lock(books):
    b = books
    from core.locks import uses

    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "10", "5")
        with pytest.raises(ValidationError, match="already been posted"):
            receive(b, 1, "10", "5")
        assert uses("item", b["tea"]) == ["1 stock posting"]
        assert uses("ledger", b["stock_ledger"]) == ["1 entry"]


def test_missing_stock_ledger_is_named(books):
    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        ItemGroupAccount.objects.all().delete()
        with pytest.raises(ValidationError, match='Set the "Stock Ledger" of item group Raw'):
            accounts.stock_ledger(b["company"], b["tea"])


def test_system_ledgers_cannot_be_disabled(books, logged_in):
    b = books
    with use_tenant(b["tenant"]):
        grni = accounts.system_ledger(b["company"], accounts.GRNI)
        assert accounts.system_ledger(b["company"], accounts.GRNI).pk == grni.pk
    from accounts.models import Role, User

    client = logged_in("alpha", "owner-posting@x.in")
    with use_tenant(b["tenant"]):
        User.objects.get(email="owner-posting@x.in").roles.set(Role.objects.filter(code="owner"))
    res = client.patch(
        f"/api/v1/ledgers/{grni.pk}/",
        data={"is_active": False},
        content_type="application/json",
        HTTP_HOST="alpha.localhost",
    )
    assert res.status_code == 400 and "cannot be disabled" in str(res.json())


FIXED_GROUPS = {
    "Goods Received but Bills not Received": "Other Current Liabilities",
    "Bills Received but Goods not Received": "Other Current Assets",
    "Goods Delivered but Bills not Made": "Other Current Assets",
    "Bills Made but Goods not Delivered": "Other Current Liabilities",
    "Work in Progress": "Stock-in-Hand",
    "Stock with Job Workers": "Stock-in-Hand",
}


def test_new_company_has_the_six_fixed_ledgers(books):
    b = books
    with use_tenant(b["tenant"]):
        fixed = Ledger.objects.filter(company=b["company"], system_code__in=accounts.FIXED)
        assert {x.name: x.group.name for x in fixed} == FIXED_GROUPS
        # The posting rules find the same ledgers, not new ones.
        assert accounts.system_ledger(b["company"], accounts.WIP).name == "Work in Progress"
        assert Ledger.objects.filter(company=b["company"], name="Work in Progress").count() == 1


def test_fixed_ledger_keeps_its_name_but_may_change_group_in_use(books, logged_in):
    from accounts.models import Role, User

    b = books
    with use_tenant(b["tenant"]):
        grni = accounts.system_ledger(b["company"], accounts.GRNI)
        with tenant_atomic():
            receive(b, 1, "10", "10")
        provisions = LedgerGroup.objects.get(company=b["company"], code="provisions")
    client = logged_in("alpha", "owner-fixed@x.in")
    with use_tenant(b["tenant"]):
        User.objects.get(email="owner-fixed@x.in").roles.set(Role.objects.filter(code="owner"))

    def patch(data):
        return client.patch(
            f"/api/v1/ledgers/{grni.pk}/",
            data=data,
            content_type="application/json",
            HTTP_HOST="alpha.localhost",
        )

    res = patch({"name": "GRNI"})
    assert res.status_code == 400 and "name cannot be changed" in str(res.json())
    res = patch({"group": provisions.pk})
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["group_name"] == provisions.name and body["system"] == "fixed"
    assert "name" in body["lock"]["locked"] and "group" not in body["lock"]["locked"]
    with use_tenant(b["tenant"]):
        # The entry moved with the ledger.
        assert GLEntry.objects.get(ledger=grni).ledger.group_id == provisions.pk


def test_other_ledgers_in_use_still_keep_their_group(books, logged_in):
    from accounts.models import Role, User

    b = books
    with use_tenant(b["tenant"]):
        with tenant_atomic():
            receive(b, 2, "10", "10")
        other = LedgerGroup.objects.get(company=b["company"], code="other_current_assets")
    client = logged_in("alpha", "owner-stock@x.in")
    with use_tenant(b["tenant"]):
        User.objects.get(email="owner-stock@x.in").roles.set(Role.objects.filter(code="owner"))
    res = client.patch(
        f"/api/v1/ledgers/{b['stock_ledger'].pk}/",
        data={"group": other.pk},
        content_type="application/json",
        HTTP_HOST="alpha.localhost",
    )
    assert res.status_code == 400 and "Cannot change the group" in str(res.json())


def test_data_reset_clears_postings(books, settings):
    from accounts.models import User
    from core import data_reset

    b = books
    with use_tenant(b["tenant"]), tenant_atomic():
        receive(b, 1, "10", "5")
        issue(b, 2, "4")
        user = User.objects.create_user("reset-posting@x.in")
        data_reset.run("entries", b["company"], user)
        assert not GLEntry.objects.filter(company=b["company"]).exists()
        assert not StockMove.objects.filter(company=b["company"]).exists()
        assert not StockLot.objects.filter(company=b["company"]).exists()
        receive(b, 1, "10", "5")  # the same voucher may post again on a clean start
        with pytest.raises((DatabaseError, InternalError), match="cannot be changed"):
            with tenant_atomic():
                GLEntry.objects.filter(company=b["company"]).delete()
