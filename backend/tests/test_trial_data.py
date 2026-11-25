"""Trial data: thousands of TRIAL records to try long lists on staging, and one
button that removes them all (Sidharth, 2026-11-25)."""

import pytest

from core import trial_data
from core.models import Ledger, Party, SalesPerson
from shipping.models import CourierAccount
from tenancy.context import use_tenant
from tests.test_data_reset import accountant, call, company, on, owner  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

URL = "admin/trial-data/"


@pytest.fixture
def small(monkeypatch):
    monkeypatch.setattr(
        trial_data, "COUNTS", {"customers": 30, "suppliers": 20, "transporters": 15, "people": 12}
    )


def test_load_and_remove(owner, company, alpha, on, small):  # noqa: F811
    assert call(owner, "get", URL).json()["counts"]["customers"] == 0
    made = call(owner, "post", URL, {"action": "load", "company": company})
    assert made.status_code == 200, made.json()
    assert made.json()["counts"] == {
        "customers": 30, "suppliers": 20, "transporters": 15, "people": 12,
    }  # fmt: skip
    with use_tenant(alpha):
        assert Ledger.objects.filter(company_id=company, name__startswith="TRIAL ").count() == 50
        assert not Party.objects.exclude(name__startswith="TRIAL ").exists()
        assert Party.objects.filter(customer_number="TCUST-00001").exists()
        registered = Party.objects.exclude(gstin="").first()
        assert registered.gstin[2:12] == registered.pan
    again = call(owner, "post", URL, {"action": "load", "company": company})
    assert again.status_code == 400  # only once until removed
    gone = call(owner, "post", URL, {"action": "remove"})
    assert gone.status_code == 200
    assert set(gone.json()["counts"].values()) == {0}
    with use_tenant(alpha):
        assert not Party.objects.exists()
        assert not Ledger.objects.filter(name__startswith="TRIAL ").exists()
        assert not CourierAccount.objects.exists()
        assert not SalesPerson.objects.exists()


def test_remove_leaves_real_records(owner, company, alpha, on, small):  # noqa: F811
    with use_tenant(alpha):
        SalesPerson.objects.create(name="TRIAL run lead")  # a real one, no "Trial data" note
    call(owner, "post", URL, {"action": "load", "company": company})
    call(owner, "post", URL, {"action": "remove"})
    with use_tenant(alpha):
        assert list(SalesPerson.objects.values_list("name", flat=True)) == ["TRIAL run lead"]


def test_owner_only_and_never_on_live_books(owner, accountant, company, settings):  # noqa: F811
    assert call(accountant, "get", URL).status_code == 403
    settings.ALLOW_DATA_RESET = False
    refused = call(owner, "post", URL, {"action": "load", "company": company})
    assert refused.status_code == 403
