"""The central admin screen: platform admins only, lists the central tables."""

import pytest
from django.test import Client

from accounts.models import User
from tenancy.context import use_tenant
from tenancy.models import HsnCode

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def _client(alpha, email, owner=False):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name="Pat")
        if owner:
            from accounts.models import Role

            user.roles.set(Role.objects.filter(code="owner"))
        client = Client()
        client.force_login(user)
    return client


def test_platform_admin_sees_tables_and_tenants(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "Boss@x.in, other@x.in"
    HsnCode.objects.create(hsn_code="0910", description="Ginger, turmeric")
    client = _client(alpha, "boss@x.in")
    resp = client.get("/api/v1/central/", HTTP_HOST=HOST)
    assert resp.status_code == 200
    tables = {t["key"]: t for t in resp.json()["tables"]}
    assert tables["hsn"]["count"] == HsnCode.objects.count() >= 1
    assert tables["tenants"]["count"] >= 1
    assert "alpha" in [t["slug"] for t in resp.json()["tenants"]]


def test_session_says_who_is_platform_admin(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    assert (
        _client(alpha, "boss@x.in")
        .get("/api/auth/session/", HTTP_HOST=HOST)
        .json()["user"]["is_platform_admin"]
    )
    assert (
        not _client(alpha, "pat@x.in")
        .get("/api/auth/session/", HTTP_HOST=HOST)
        .json()["user"]["is_platform_admin"]
    )


def test_owner_and_others_are_refused(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    assert (
        _client(alpha, "own@x.in", owner=True).get("/api/v1/central/", HTTP_HOST=HOST).status_code
        == 403
    )


def test_nobody_is_admin_when_the_setting_is_empty(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = ""
    assert _client(alpha, "boss@x.in").get("/api/v1/central/", HTTP_HOST=HOST).status_code == 403


def test_platform_admins_add_couriers_everyone_can_pick(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    boss = _client(alpha, "boss@x.in")
    owner = _client(alpha, "owner@x.in", owner=True)
    body = {
        "name": "  Gati  Express ",
        "kind": "courier",
        "awb_pattern": r"\d{9}",
        "awb_hint": "9 digits",
        "tracking_url": "https://gati.example/track?awb={awb}",
    }
    made = boss.post(
        "/api/v1/central/carriers/", body, content_type="application/json", HTTP_HOST=HOST
    )
    assert made.status_code == 201, made.json()
    assert made.json()["name"] == "Gati Express"
    # Every customer sees it in their list of couriers.
    names = [c["name"] for c in owner.get("/api/v1/carriers/", HTTP_HOST=HOST).json()]
    assert "Gati Express" in names

    def bad(data):
        r = boss.post(
            "/api/v1/central/carriers/", data, content_type="application/json", HTTP_HOST=HOST
        )
        assert r.status_code == 400, r.json()
        return str(r.json())

    assert "already a courier" in bad({**body, "name": "gati express"})
    assert "valid pattern" in bad({**body, "name": "X", "awb_pattern": "("})
    assert "{awb}" in bad({**body, "name": "Y", "tracking_url": "https://x.example/"})

    pk = made.json()["id"]
    off = boss.patch(
        f"/api/v1/central/carriers/{pk}/",
        {"is_active": False},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert boss.delete(f"/api/v1/central/carriers/{pk}/", HTTP_HOST=HOST).status_code == 405


def test_only_platform_admins_manage_couriers(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    owner = _client(alpha, "owner@x.in", owner=True)
    assert owner.get("/api/v1/central/carriers/", HTTP_HOST=HOST).status_code == 403
    r = owner.post(
        "/api/v1/central/carriers/",
        {"name": "Mine", "kind": "courier"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert r.status_code == 403


def test_a_transporter_not_in_the_list_asks_the_central_team(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    boss = _client(alpha, "boss@x.in")
    owner = _client(alpha, "owner@x.in", owner=True)
    from core.models import Company

    with use_tenant(alpha):
        company = Company.objects.create(name="Co", abbr="CO")
    body = {
        "name": "Shree Roadlines",
        "gstin": "27AAACR5055K1Z7",
        "note_for_central": "Used for Pune loads",
    }
    r = owner.post(
        f"/api/v1/companies/{company.pk}/courier-accounts/",
        body,
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert r.status_code == 201, r.json()
    rows = boss.get("/api/v1/central/carrier-requests/", HTTP_HOST=HOST).json()
    assert [(x["name"], x["note"], x["status"]) for x in rows] == [
        ("Shree Roadlines", "Used for Pune loads", "open")
    ]
    # Saving again does not pile up a second request.
    owner.patch(
        f"/api/v1/courier-accounts/{r.json()['id']}/",
        {"note_for_central": "Pune and Nashik"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    rows = boss.get("/api/v1/central/carrier-requests/", HTTP_HOST=HOST).json()
    assert len(rows) == 1 and rows[0]["note"] == "Pune and Nashik"
    assert owner.get("/api/v1/central/carrier-requests/", HTTP_HOST=HOST).status_code == 403
    done = boss.patch(
        f"/api/v1/central/carrier-requests/{rows[0]['id']}/",
        {"status": "added"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert done.status_code == 200 and done.json()["status"] == "added"


def _upload(client, path, text, **extra):
    from django.core.files.uploadedfile import SimpleUploadedFile

    file = SimpleUploadedFile("list.csv", text.encode(), content_type="text/csv")
    return client.post(path, {"file": file, **extra}, HTTP_HOST=HOST)


def test_platform_admin_loads_hsn_from_a_file(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    client = _client(alpha, "boss@x.in")
    csv = 'HSN,Description\n0902,Tea\n0910,"Ginger, turmeric"\n'
    first = _upload(client, "/api/v1/central/import/hsn/", csv)
    assert first.status_code == 200, first.json()
    assert first.json()["added"] == 2
    assert HsnCode.objects.get(hsn_code="0902").description == "Tea"
    again = _upload(client, "/api/v1/central/import/hsn/", csv)
    assert again.json() == {"added": 0, "updated": 0, "unchanged": 2}
    empty = _upload(client, "/api/v1/central/import/hsn/", "nothing here\n")
    assert empty.status_code == 400


def test_platform_admin_loads_pins_for_a_courier(alpha, settings):
    from tenancy.models import Carrier, CourierPin, PinCode, State

    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    client = _client(alpha, "boss@x.in")
    carrier = Carrier.objects.create(name="Delhivery Test", kind="courier")
    State.objects.get_or_create(name="Karnataka")
    csv = "Pin,Facility City,Facility State,ODA\n591111,Saundatti,Karnataka,True\n"
    path = "/api/v1/central/import/pins/"
    assert _upload(client, path, csv).status_code == 400  # no courier chosen
    done = _upload(client, path, csv, carrier=carrier.pk)
    assert done.status_code == 200, done.json()
    assert PinCode.objects.filter(pin="591111").exists()
    assert CourierPin.objects.filter(carrier=carrier).count() == 1
    bad = _upload(client, path, csv.replace("Karnataka,", "Nowhere,"), carrier=carrier.pk)
    assert bad.status_code == 400


def test_only_platform_admins_may_import(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    owner = _client(alpha, "owner@x.in", owner=True)
    assert _upload(owner, "/api/v1/central/import/hsn/", "0902,Tea\n").status_code == 403
    assert _upload(owner, "/api/v1/central/import/pins/", "Pin\n").status_code == 403
