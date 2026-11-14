"""Shipments and courier tracking, build step 1 (spec 06): the central courier
list, courier accounts per company, shipments with statuses typed by hand."""

import datetime

import pytest
from django.db import IntegrityError
from django.test import Client
from django.utils import timezone

from accounts.models import Role, User
from core.companies import create_company
from core.india import gstin_check_char
from core.models import Party
from shipping.models import Shipment, Status, TrackingEvent, check_awb
from tenancy.context import use_tenant
from tenancy.models import Carrier

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"
GSTIN = "07AAACD1234F1Z" + gstin_check_char("07AAACD1234F1Z")  # a transporter in Delhi


def _client(alpha, email, role):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=email.split("@")[0])
        user.roles.set(Role.objects.filter(code=role))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def owner(alpha):
    return _client(alpha, "own@x.in", "owner")


@pytest.fixture
def store(alpha):
    return _client(alpha, "store@x.in", "storekeeper")


@pytest.fixture
def viewer(alpha):
    return _client(alpha, "view@x.in", "viewer")


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


@pytest.fixture
def customer(alpha):
    with use_tenant(alpha):
        return Party.objects.create(name="Fresh Mart", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def carrier(name):
    return Carrier.objects.get(name=name).pk


@pytest.fixture
def b2b(owner, company):
    resp = call(
        owner,
        "post",
        f"companies/{company}/courier-accounts/",
        {
            "carrier_id": carrier("Delhivery"),
            "name": "Delhivery B2B",
            "gstin": GSTIN,
            "service": "b2b",
        },
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


def ship(client, company, account, awb="1234567890", **more):
    body = {"account": account, "awb": awb, "booked_on": str(timezone.localdate()), **more}
    return call(client, "post", f"companies/{company}/shipments/", body)


def test_central_list_has_the_couriers_apurvam_uses(owner):
    names = {c["name"]: c for c in call(owner, "get", "carriers/").json()}
    assert {"Delhivery", "Blue Dart", "DP World", "Shiprocket"} <= set(names)
    assert names["Shiprocket"]["kind"] == "aggregator"


def test_courier_names_are_unique_whatever_the_case(owner):
    with pytest.raises(IntegrityError):
        Carrier.objects.create(name="delhivery")


def test_two_accounts_with_one_courier(owner, company, b2b):
    resp = call(
        owner,
        "post",
        f"companies/{company}/courier-accounts/",
        {
            "carrier_id": carrier("Delhivery"),
            "name": "Delhivery B2C",
            "gstin": GSTIN,
            "service": "b2c",
        },
    )
    assert resp.status_code == 201
    rows = call(owner, "get", f"companies/{company}/courier-accounts/").json()
    assert [(r["name"], r["carrier_name"]) for r in rows] == [
        ("Delhivery B2B", "Delhivery"),
        ("Delhivery B2C", "Delhivery"),
    ]
    same = call(
        owner,
        "post",
        f"companies/{company}/courier-accounts/",
        {"carrier_id": carrier("Blue Dart"), "name": "delhivery b2b", "gstin": GSTIN},
    )
    assert same.status_code == 400 and "name" in same.json()


def test_a_transporter_needs_its_gstin(owner, company):
    path = f"companies/{company}/courier-accounts/"
    none = call(owner, "post", path, {"name": "Local Roadways"})
    assert none.status_code == 400 and "Transporter ID" in str(none.json())
    bad = call(owner, "post", path, {"name": "Local Roadways", "gstin": "07AAACD1234F1Z0"})
    assert bad.status_code == 400 and "gstin" in bad.json()
    ok = call(owner, "post", path, {"name": "Local Roadways", "gstin": GSTIN.lower()})
    assert ok.status_code == 201, ok.json()
    assert ok.json()["gstin"] == GSTIN and ok.json()["state_code"] == "07"
    cleared = call(owner, "patch", f"courier-accounts/{ok.json()['id']}/", {"gstin": ""})
    assert cleared.status_code == 400


def test_a_transporter_may_be_one_that_is_not_in_the_courier_list(owner, store, company):
    made = call(
        owner,
        "post",
        f"companies/{company}/courier-accounts/",
        {
            "name": "Shree Roadlines",
            "gstin": GSTIN,
            "service": "b2b",
            "pincode": "110001",
            "city": "Delhi",
            "contact_person": "Mr Shah",
        },
    )
    assert made.status_code == 201, made.json()
    account = made.json()
    assert account["carrier_id"] is None and account["carrier_name"] == ""
    assert (
        call(
            owner,
            "post",
            f"companies/{company}/courier-accounts/",
            {"name": "Bad PIN", "gstin": GSTIN, "pincode": "12"},
        ).status_code
        == 400
    )
    first = ship(store, company, account["id"])
    assert first.status_code == 201, first.json()
    assert first.json()["carrier_name"] == ""
    again = ship(store, company, account["id"])  # the same LR number, same transporter
    assert again.status_code == 400 and "already entered" in str(again.json())


def test_courier_account_needs_a_courier_from_the_list(owner, company):
    resp = call(
        owner,
        "post",
        f"companies/{company}/courier-accounts/",
        {"carrier_id": 999999, "name": "Mystery", "gstin": GSTIN},
    )
    assert resp.status_code == 400 and "carrier_id" in resp.json()


def test_courier_of_an_account_in_use_cannot_change(owner, company, b2b, store):
    assert ship(store, company, b2b).status_code == 201
    resp = call(owner, "patch", f"courier-accounts/{b2b}/", {"carrier_id": carrier("Blue Dart")})
    assert resp.status_code == 400 and "in use (1 shipment)" in str(resp.json())
    # The name and Disable stay open.
    assert call(owner, "patch", f"courier-accounts/{b2b}/", {"name": "DL B2B"}).status_code == 200
    off = call(owner, "patch", f"courier-accounts/{b2b}/", {"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False


def test_transporter_says_what_uses_it_and_what_is_locked(owner, company, b2b, store):
    rows = call(owner, "get", f"companies/{company}/courier-accounts/").json()
    assert rows[0]["lock"] == {"in_use": [], "locked": []}
    assert ship(store, company, b2b).status_code == 201
    rows = call(owner, "get", f"companies/{company}/courier-accounts/").json()
    assert rows[0]["lock"]["in_use"] == ["1 shipment"]
    assert set(rows[0]["lock"]["locked"]) == {"carrier_id", "service"}


def test_storekeeper_enters_a_shipment_and_it_starts_booked(store, company, b2b, customer):
    resp = ship(
        store,
        company,
        b2b,
        awb=" 1234 567890 ",
        party=customer,
        reference="SINV-0042",
        ship_to_pincode="110001",
        packages=3,
        weight_kg="12.5",
    )
    assert resp.status_code == 201, resp.json()
    s = resp.json()
    assert s["awb"] == "1234567890"
    assert s["status"] == "booked"
    assert s["carrier_name"] == "Delhivery"
    assert s["party_name"] == "Fresh Mart"
    assert [e["status"] for e in s["events"]] == ["booked"]


def test_viewer_sees_but_cannot_enter(viewer, store, company, b2b):
    ship(store, company, b2b)
    assert call(viewer, "get", f"companies/{company}/shipments/?view=all").status_code == 200
    assert ship(viewer, company, b2b, awb="99999999").status_code == 403


def test_same_awb_twice_for_one_courier_is_refused(store, owner, company, b2b):
    assert ship(store, company, b2b).status_code == 201
    again = ship(store, company, b2b)
    assert again.status_code == 400 and "already entered" in str(again.json())
    # Another courier may use the same number.
    other = call(
        owner,
        "post",
        f"companies/{company}/courier-accounts/",
        {"carrier_id": carrier("Blue Dart"), "name": "Blue Dart B2C", "gstin": GSTIN},
    ).json()["id"]
    assert ship(store, company, other).status_code == 201


def test_cancelled_awb_can_be_entered_again(store, company, b2b):
    first = ship(store, company, b2b).json()["id"]
    resp = call(store, "post", f"shipments/{first}/cancel/", {"reason": "Wrong number"})
    assert resp.status_code == 200 and resp.json()["cancelled"] is True
    assert ship(store, company, b2b).status_code == 201


def test_awb_format_checks():
    assert check_awb("12AB-34", None) == ""
    assert "6 to 30" in check_awb("123", None)
    assert "6 to 30" in check_awb("12/34567", None)
    bd = Carrier(name="Blue Dart", awb_pattern=r"\d{11}", awb_hint="11 digits")
    assert check_awb("12345678901", bd) == ""
    assert "11 digits" in check_awb("1234567890", bd)


def test_typed_statuses_move_the_shipment_and_delivery_is_recorded(store, company, b2b):
    sid = ship(store, company, b2b).json()["id"]
    now = timezone.now().replace(microsecond=0)
    for minutes, st in ((50, "picked_up"), (30, "in_transit"), (10, "out_for_delivery")):
        r = call(
            store,
            "post",
            f"shipments/{sid}/events/",
            {"status": st, "at": (now - datetime.timedelta(minutes=minutes)).isoformat()},
        )
        assert r.status_code == 201, r.json()
    assert r.json()["status"] == "out_for_delivery"
    done = call(
        store,
        "post",
        f"shipments/{sid}/events/",
        {"status": "delivered", "at": now.isoformat(), "received_by": "Ramesh", "place": "Delhi"},
    ).json()
    assert done["status"] == "delivered" and done["is_open"] is False
    assert done["received_by"] == "Ramesh"
    assert done["delivered_at"] is not None


def test_an_older_event_typed_late_does_not_change_the_current_status(store, company, b2b):
    sid = ship(store, company, b2b).json()["id"]
    now = timezone.now()
    call(store, "post", f"shipments/{sid}/events/", {"status": "in_transit", "at": now.isoformat()})
    old = (now - datetime.timedelta(hours=5)).isoformat()
    r = call(store, "post", f"shipments/{sid}/events/", {"status": "picked_up", "at": old})
    assert r.json()["status"] == "in_transit"


def test_same_event_twice_is_dropped(store, company, b2b):
    sid = ship(store, company, b2b).json()["id"]
    body = {"status": "in_transit", "at": timezone.now().isoformat()}
    assert call(store, "post", f"shipments/{sid}/events/", body).status_code == 201
    assert call(store, "post", f"shipments/{sid}/events/", body).status_code == 400


def test_future_event_is_refused(store, company, b2b):
    sid = ship(store, company, b2b).json()["id"]
    later = (timezone.now() + datetime.timedelta(hours=2)).isoformat()
    r = call(store, "post", f"shipments/{sid}/events/", {"status": "in_transit", "at": later})
    assert r.status_code == 400


def test_tracking_events_are_never_edited_or_deleted(alpha, store, company, b2b):
    sid = ship(store, company, b2b).json()["id"]
    with use_tenant(alpha):
        event = TrackingEvent.objects.get(shipment_id=sid)
        event.place = "Changed"
        with pytest.raises(Exception, match="cannot be changed"):
            event.save()
        with pytest.raises(Exception, match="cannot be deleted"):
            event.delete()


def test_needs_action_lists_problems(store, company, b2b):
    ok = ship(store, company, b2b, awb="11111111").json()["id"]
    held = ship(store, company, b2b, awb="22222222").json()["id"]
    yesterday = timezone.localdate() - datetime.timedelta(days=1)
    late = ship(
        store,
        company,
        b2b,
        awb="33333333",
        booked_on=str(yesterday - datetime.timedelta(days=2)),
        expected_on=str(yesterday),
    ).json()["id"]
    now = timezone.now().isoformat()
    call(store, "post", f"shipments/{ok}/events/", {"status": "in_transit", "at": now})
    call(store, "post", f"shipments/{held}/events/", {"status": "held", "at": now})
    rows = call(store, "get", f"companies/{company}/shipments/?view=action").json()
    alerts = {r["id"]: r["alerts"] for r in rows}
    assert ok not in alerts
    assert alerts[held] == ["Held"]
    assert "Past expected delivery date" in alerts[late]
    assert "Not picked up" in alerts[late]


def test_no_movement_for_three_days(store, company, b2b):
    booked = str(timezone.localdate() - datetime.timedelta(days=5))
    sid = ship(store, company, b2b, booked_on=booked).json()["id"]
    four_days = (timezone.now() - datetime.timedelta(days=4)).isoformat()
    r = call(store, "post", f"shipments/{sid}/events/", {"status": "in_transit", "at": four_days})
    assert r.json()["status"] == "in_transit"
    assert r.json()["alerts"] == ["No movement for 3 days"]


def test_courier_and_awb_fixed_once_the_courier_has_reported(alpha, store, company, b2b):
    sid = ship(store, company, b2b).json()["id"]
    # Typed statuses do not fix them: a typing mistake can still be corrected.
    assert call(store, "patch", f"shipments/{sid}/", {"awb": "1234567891"}).status_code == 200
    with use_tenant(alpha):
        TrackingEvent.objects.create(
            shipment_id=sid,
            at=timezone.now(),
            status=Status.IN_TRANSIT,
            carrier_code="UD",
            source=TrackingEvent.PULLED,
        )
    resp = call(store, "patch", f"shipments/{sid}/", {"awb": "1234567892"})
    assert resp.status_code == 400 and "fixed" in str(resp.json())
    assert call(store, "patch", f"shipments/{sid}/", {"reference": "SINV-9"}).status_code == 200


def test_cash_on_delivery_needs_an_amount(store, company, b2b):
    resp = ship(store, company, b2b, payment="cod")
    assert resp.status_code == 400 and "cod_amount" in resp.json()
    assert ship(store, company, b2b, payment="cod", cod_amount="1500").status_code == 201


def test_company_without_sales_has_no_shipments(alpha, owner, company):
    with use_tenant(alpha):
        from core.models import Company

        c = Company.objects.get(pk=company)
        c.modules = ["accounts", "stock"]
        c.save()
    assert call(owner, "get", f"companies/{company}/shipments/").status_code == 404


def test_other_tenant_cannot_see_shipments(beta, store, company, b2b, logged_in):
    sid = ship(store, company, b2b).json()["id"]
    other = logged_in("beta", "someone@beta.in")
    assert other.get(f"/api/v1/shipments/{sid}/", HTTP_HOST="beta.localhost").status_code in (
        403,
        404,
    )


def test_reset_entries_clears_shipments(alpha, owner, store, company, b2b, settings):
    settings.ALLOW_DATA_RESET = True
    sid = ship(store, company, b2b).json()["id"]
    with use_tenant(alpha):
        name = __import__("core.models", fromlist=["Company"]).Company.objects.get(pk=company).name
    resp = call(
        owner, "post", "admin/reset/", {"level": "entries", "company": company, "confirm": name}
    )
    assert resp.status_code == 200, resp.json()
    with use_tenant(alpha):
        assert not Shipment.objects.filter(pk=sid).exists()
