"""The central admin screen: platform admins only, lists the central tables."""

import pytest
from django.test import Client

from accounts.models import User
from tenancy.context import use_tenant
from tenancy.models import Country, GstRate, HsnCode, PinCode

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
    assert again.json() == {
        "added": 0,
        "updated": 0,
        "unchanged": 2,
        "skipped": [],
        "problems": [],
        "repeated": [],
        "saved": True,
    }
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
    assert bad.status_code == 200 and bad.json()["problems"] == [
        "591111: Unknown state name: Nowhere"
    ]
    assert bad.json()["coverage"] == 0
    sheet = _upload(
        client, path, csv.replace("Karnataka,", "Nowhere,"), carrier=carrier.pk, download="1"
    )
    assert "spreadsheetml" in sheet["Content-Type"]


def test_left_out_hsn_rows_come_back_as_an_excel_file(alpha, settings):
    import io

    from openpyxl import load_workbook

    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    client = _client(alpha, "boss@x.in")
    csv = "HSN,Description\n0902,Tea\n30559,Fish dried\n17x,Oops\n0910,\n"
    path = "/api/v1/central/import/hsn/"
    done = _upload(client, path, csv)
    assert done.json()["added"] == 1 and len(done.json()["problems"]) == 2
    assert "rejected" not in done.json()
    assert HsnCode.objects.filter(hsn_code="0902").exists()
    HsnCode.objects.all().delete()
    sheet = _upload(client, path, csv, download="1")  # downloading saves nothing
    assert HsnCode.objects.count() == 0
    rows = list(load_workbook(io.BytesIO(sheet.content)).active.values)
    assert rows[0] == ("HSN code", "Description", "Why it was left out")
    assert [r[0] for r in rows[1:]] == ["30559", "0910"]


def test_only_platform_admins_may_import(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    owner = _client(alpha, "owner@x.in", owner=True)
    assert _upload(owner, "/api/v1/central/import/hsn/", "0902,Tea\n").status_code == 403
    assert _upload(owner, "/api/v1/central/import/pins/", "Pin\n").status_code == 403


def test_platform_admin_creates_a_customer_with_its_owner(alpha, settings, monkeypatch):
    # CREATE DATABASE cannot run inside the test's transaction, so the
    # provisioning step is stood in for by the existing test tenant.
    seen = {}

    def fake_create(slug, name, db_name=None):
        seen.update(slug=slug, name=name)
        return alpha

    monkeypatch.setattr("core.central.create_tenant", fake_create)
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    client = _client(alpha, "boss@x.in")
    body = {
        "slug": "NewCo",
        "name": " New  Co group",
        "owner_email": "Boss@NewCo.in",
        "owner_name": "Nina",
    }
    made = client.post(
        "/api/v1/central/tenants/", body, content_type="application/json", HTTP_HOST=HOST
    )
    assert made.status_code == 201, made.json()
    assert seen == {"slug": "newco", "name": "New Co group"}
    with use_tenant(alpha):
        assert User.objects.get(email="boss@newco.in").is_owner
    taken = {**body, "slug": alpha.slug}
    again = client.post(
        "/api/v1/central/tenants/", taken, content_type="application/json", HTTP_HOST=HOST
    )
    assert again.status_code == 400


def test_creating_a_customer_needs_the_basics_and_an_admin(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    boss = _client(alpha, "boss@x.in")
    for bad in (
        {"slug": "a", "name": "", "owner_email": "a@b.in"},
        {"slug": "Bad Slug!", "name": "X", "owner_email": "a@b.in"},
        {"slug": "okay", "name": "X", "owner_email": "nope"},
    ):
        r = boss.post(
            "/api/v1/central/tenants/", bad, content_type="application/json", HTTP_HOST=HOST
        )
        assert r.status_code == 400
    owner = _client(alpha, "owner@x.in", owner=True)
    r = owner.post(
        "/api/v1/central/tenants/",
        {"slug": "zz", "name": "Z", "owner_email": "a@b.in"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert r.status_code == 403


def test_hsn_can_be_loaded_from_an_excel_file(alpha, settings):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from openpyxl import Workbook

    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    client = _client(alpha, "boss@x.in")
    book = Workbook()
    goods = book.active
    goods.title = "HSN_MSTR"
    goods.append(["HSN_CD", "HSN_Description"])
    goods.append(["0902", "TEA"])
    goods.append(["01011010", "LIVE HORSES"])
    services = book.create_sheet("SAC_MSTR")
    services.append(["SAC_CD", "SAC_Description"])
    services.append([9954, "Construction services"])
    out = io.BytesIO()
    book.save(out)
    file = SimpleUploadedFile("hsn.xlsx", out.getvalue())
    done = client.post("/api/v1/central/import/hsn/", {"file": file}, HTTP_HOST=HOST)
    assert done.status_code == 200, done.json()
    assert done.json()["added"] == 3
    assert HsnCode.objects.get(hsn_code="9954").description == "Construction services"
    assert HsnCode.objects.get(hsn_code="0902").description == "TEA"
    # A description Excel took for a formula is read as the text that was typed.
    sheet = Workbook()
    ws = sheet.active
    ws.append(["HSN_CD", "HSN_Description"])
    ws.append(["52083110", "=--- LUNGI"])
    out2 = io.BytesIO()
    sheet.save(out2)
    lungi = client.post(
        "/api/v1/central/import/hsn/",
        {"file": SimpleUploadedFile("lungi.xlsx", out2.getvalue())},
        HTTP_HOST=HOST,
    )
    assert lungi.status_code == 200, lungi.json()
    assert HsnCode.objects.get(hsn_code="52083110").description == "--- LUNGI"
    bad = SimpleUploadedFile("hsn.xlsx", b"not an excel file")
    assert (
        client.post("/api/v1/central/import/hsn/", {"file": bad}, HTTP_HOST=HOST).status_code == 400
    )


def test_checking_a_file_saves_nothing_and_lists_every_problem(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    client = _client(alpha, "boss@x.in")
    csv = "HSN,Description\n0902,Tea\n30559,Fish\n0910,\n0902,Tea again\n"
    path = "/api/v1/central/import/hsn/"
    checked = _upload(client, path, csv, commit="0")
    body = checked.json()
    assert checked.status_code == 200, body
    assert body["saved"] is False and body["added"] == 1
    assert body["problems"] == ["30559: not 2, 4, 6 or 8 digits", "0910: no description"]
    assert body["repeated"] == ["0902"]
    assert not HsnCode.objects.filter(hsn_code="0902").exists()
    saved = _upload(client, path, csv, commit="1").json()
    assert saved["saved"] is True
    assert HsnCode.objects.get(hsn_code="0902").description == "Tea again"


def test_gst_rates_are_a_central_list_items_pick_from(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    boss = _client(alpha, "boss@x.in")
    owner = _client(alpha, "owner@x.in", owner=True)

    def post(data):
        return boss.post(
            "/api/v1/central/gst-rates/", data, content_type="application/json", HTTP_HOST=HOST
        )

    # The standard slabs are loaded; tenants see only the active ones.
    seen = [r["rate"] for r in owner.get("/api/v1/gst-rates/", HTTP_HOST=HOST).json()]
    assert seen == ["0.00", "0.25", "3.00", "5.00", "18.00"]

    made = post({"rate": "40"})
    assert made.status_code == 201, made.json()
    assert made.json()["label"] == "GST 40%"
    assert "already in the list" in str(post({"rate": "40.00"}).json())
    assert post({"rate": "101"}).status_code == 400

    pk = made.json()["id"]
    off = boss.patch(
        f"/api/v1/central/gst-rates/{pk}/",
        {"is_active": False},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert boss.delete(f"/api/v1/central/gst-rates/{pk}/", HTTP_HOST=HOST).status_code == 405
    seen = [r["rate"] for r in owner.get("/api/v1/gst-rates/", HTTP_HOST=HOST).json()]
    assert "40.00" not in seen

    # Customers read the list but cannot change it.
    assert owner.get("/api/v1/central/gst-rates/", HTTP_HOST=HOST).status_code == 403
    r = owner.post(
        "/api/v1/central/gst-rates/", {"rate": "9"}, content_type="application/json", HTTP_HOST=HOST
    )
    assert r.status_code == 403


def test_customers_request_additions_to_central_lists(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    boss = _client(alpha, "boss@x.in")
    owner = _client(alpha, "owner@x.in", owner=True)

    def ask(data):
        return owner.post(
            "/api/v1/central-requests/", data, content_type="application/json", HTTP_HOST=HOST
        )

    made = ask(
        {"kind": "hsn", "entry": "0902 40 40", "description": "Black tea", "note": "For blends"}
    )
    assert made.status_code == 201, made.json()
    assert made.json()["entry"] == "09024040" and made.json()["status"] == "open"
    assert made.json()["requested_by"] == "owner@x.in"

    # The same entry cannot be asked twice while open; bad entries and listed ones are refused.
    assert "already an open request" in str(ask({"kind": "hsn", "entry": "09024040"}).json())
    assert "2 to 8 digits" in str(ask({"kind": "hsn", "entry": "tea"}).json())
    assert "already in the GST rates" in str(ask({"kind": "gst_rate", "entry": "18"}).json())
    assert ask({"kind": "gst_rate", "entry": "40"}).status_code == 201
    assert ask({"kind": "gst_rate", "entry": "x"}).status_code == 400

    mine = owner.get("/api/v1/central-requests/", HTTP_HOST=HOST).json()
    assert {r["entry"] for r in mine} == {"09024040", "40"}

    # The platform admin sees them with the customer and closes them; a customer cannot.
    seen = boss.get("/api/v1/central/requests/", HTTP_HOST=HOST).json()
    assert {r["entry"] for r in seen} == {"09024040", "40"}
    assert all(r["customer"] for r in seen)
    assert owner.get("/api/v1/central/requests/", HTTP_HOST=HOST).status_code == 403
    pk = made.json()["id"]
    done = boss.patch(
        f"/api/v1/central/requests/{pk}/",
        {"status": "added"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert done.status_code == 200 and done.json()["status"] == "added"
    # Once closed, the customer sees the new status, and may ask again if it is still missing.
    again = owner.get("/api/v1/central-requests/", HTTP_HOST=HOST).json()
    by_entry = {r["entry"]: r for r in again}
    assert by_entry["09024040"]["status"] == "added" and not by_entry["09024040"]["seen"]
    # Approving put the code in the HSN list itself, so it cannot be asked for again.
    assert HsnCode.objects.get(hsn_code="09024040").description == "Black tea"
    assert "already in the HSN list" in str(ask({"kind": "hsn", "entry": "09024040"}).json())
    # The customer dismisses the notice.
    assert owner.post(f"/api/v1/central-requests/{pk}/seen/", HTTP_HOST=HOST).status_code == 200
    again = owner.get("/api/v1/central-requests/", HTTP_HOST=HOST).json()
    assert {r["entry"]: r["seen"] for r in again}["09024040"] is True
    # Approving a GST rate adds it to the rates.
    rate = by_entry["40"]["id"]
    ok = boss.patch(
        f"/api/v1/central/requests/{rate}/",
        {"status": "added"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert ok.status_code == 200 and GstRate.objects.filter(rate=40).exists()


def test_customers_request_countries_and_pin_codes(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    boss = _client(alpha, "boss@x.in")
    owner = _client(alpha, "owner@x.in", owner=True)

    def ask(data):
        return owner.post(
            "/api/v1/central-requests/", data, content_type="application/json", HTTP_HOST=HOST
        )

    assert "2-letter" in str(ask({"kind": "country", "entry": "Kosovo"}).json())
    assert "already in the country" in str(
        ask({"kind": "country", "entry": "india", "description": "ZZ"}).json()
    )
    assert "6 digits" in str(ask({"kind": "pin", "entry": "12"}).json())
    assert "city" in str(ask({"kind": "pin", "entry": "370421", "state_code": "24"}).json())
    assert "state" in str(ask({"kind": "pin", "entry": "370421", "city": "Mundra"}).json())
    country = ask({"kind": "country", "entry": "Kosovo", "description": "xk"})
    pin = ask({"kind": "pin", "entry": "370421", "city": "Mundra", "state_code": "24"})
    assert country.status_code == 201 and pin.status_code == 201, (country.json(), pin.json())
    assert country.json()["description"] == "XK"

    for made in (country, pin):
        r = boss.patch(
            f"/api/v1/central/requests/{made.json()['id']}/",
            {"status": "added"},
            content_type="application/json",
            HTTP_HOST=HOST,
        )
        assert r.status_code == 200, r.json()
    assert Country.objects.get(code="XK").name == "Kosovo"
    row = PinCode.objects.get(pin="370421")
    assert row.city == "Mundra" and row.state.code == "24"
    assert "already in the PIN list" in str(
        ask({"kind": "pin", "entry": "370421", "city": "x", "state_code": "24"}).json()
    )

    # Everyone who can see masters can search the PIN list, by PIN or by words.
    found = owner.get("/api/v1/pin-codes/?q=3704", HTTP_HOST=HOST).json()
    assert [p["pin"] for p in found["results"]] == ["370421"]
    assert found["results"][0]["state_name"] == "Gujarat"
    by_city = owner.get("/api/v1/pin-codes/?q=mundra gujarat&limit=pick", HTTP_HOST=HOST).json()
    assert [p["pin"] for p in by_city["results"]] == ["370421"]


def test_platform_admins_keep_the_dated_tds_sections(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    boss = _client(alpha, "boss@x.in")
    owner = _client(alpha, "owner@x.in", owner=True)
    # The usual sections are loaded; customers see each once.
    seen = [s["code"] for s in owner.get("/api/v1/tds-sections/", HTTP_HOST=HOST).json()]
    assert seen == ["194C", "194H", "194I(a)", "194I(b)", "194IA", "194J(a)", "194J(b)",
                    "194J(ba)", "194Q"]  # fmt: skip
    row = {"code": "194c", "name": "Contractors", "valid_from": "2027-04-01",
           "rate_other": "3", "rate_individual": "1.5", "rate_no_pan": "20",
           "bill_limit": "40000", "year_limit": None}  # fmt: skip
    made = boss.post("/api/v1/central/tds-sections/", row, content_type="application/json",
                     HTTP_HOST=HOST)  # fmt: skip
    assert made.status_code == 201, made.json()
    assert made.json()["code"] == "194C"
    again = boss.post("/api/v1/central/tds-sections/", row, content_type="application/json",
                      HTTP_HOST=HOST)  # fmt: skip
    assert "already has a row" in str(again.json())
    odd = boss.post("/api/v1/central/tds-sections/", {**row, "code": "194j(BA)"},
                    content_type="application/json", HTTP_HOST=HOST)  # fmt: skip
    assert odd.json()["code"] == "194J(ba)", odd.json()
    assert owner.get("/api/v1/central/tds-sections/", HTTP_HOST=HOST).status_code == 403
