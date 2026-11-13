"""Central states, countries and PIN codes: seed, courier file import, lookup."""

import io

import pytest
from django.core.management import CommandError, call_command
from django.test import Client

from accounts.models import Role, User
from tenancy import pin_import
from tenancy.context import use_tenant
from tenancy.models import Country, CourierPin, PinCode, State

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"

CSV = """,Pin,Dispatch Center,Origin Center,Return Center,Facility City,Facility State,ODA
0,605755,Thiru_D (Tamil Nadu),Thiru_D (Tamil Nadu),Thiru_D (Tamil Nadu),Thirukoilure,Tamil Nadu,True
1,751001,Bbsr_H (Odisha),NSZ,Bbsr_H (Odisha),Bhubaneswar,Orissa,False
2,190001,Srinagar_H,Srinagar_H,Srinagar_H,Srinagar,Jammu & Kashmir,
3,12345,Bad,Bad,Bad,Nowhere,Kerala,False
4,400001,X,X,X,Mumbai,,False
"""


@pytest.fixture
def viewer(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("view@x.in", full_name="Vee")
        user.roles.set(Role.objects.filter(code="viewer"))
        client = Client()
        client.force_login(user)
    return client


def test_states_and_countries_are_seeded():
    assert State.objects.get(code="27").name == "Maharashtra"
    assert State.objects.count() >= 36
    assert Country.objects.get(code="IN").name == "India"
    assert Country.objects.count() >= 240


def test_parse_skips_bad_pins():
    assert [r["pin"] for r in pin_import.parse(CSV)] == ["605755", "751001", "190001", "400001"]


def test_import_maps_state_names_and_keeps_courier_rows():
    rows = pin_import.parse(CSV)
    done = pin_import.load(rows, "Delhivery")
    assert done["pins_added"] == 4 and done["coverage"] == 4
    assert PinCode.objects.get(pin="751001").state.name == "Odisha"
    assert PinCode.objects.get(pin="190001").state.name == "Jammu and Kashmir"
    assert PinCode.objects.get(pin="400001").state is None
    assert CourierPin.objects.get(carrier__name="Delhivery", pin__pin="190001").oda is None
    assert CourierPin.objects.get(carrier__name="Delhivery", pin__pin="751001").oda is False


def test_second_load_replaces_that_couriers_rows_and_keeps_cities():
    pin_import.load(pin_import.parse(CSV), "Delhivery")
    other = (
        "Pin,Facility City,Facility State,ODA\n"
        "751001,Other Town,Odisha,True\n"
        "110001,Delhi,Delhi,False\n"
    )
    pin_import.load(pin_import.parse(other), "Blue Dart")
    assert PinCode.objects.get(pin="751001").city == "Bhubaneswar"
    assert CourierPin.objects.filter(pin__pin="751001").count() == 2
    pin_import.load(pin_import.parse(CSV)[:1], "Delhivery")
    assert CourierPin.objects.filter(carrier__name="Delhivery").count() == 1
    assert CourierPin.objects.filter(carrier__name="Blue Dart").count() == 2


def test_unknown_state_rows_are_left_out_and_named():
    bad = "Pin,Facility City,Facility State\n751001,X,Atlantis\n"
    done = pin_import.load(pin_import.parse(bad), "Delhivery")
    assert done["coverage"] == 0 and done["rejected"][0]["reason"].endswith("Atlantis")
    with pytest.raises(ValueError, match="courier"):
        pin_import.load(pin_import.parse(CSV), " ")
    with pytest.raises(ValueError, match="No courier called Acme"):
        pin_import.load(pin_import.parse(CSV), "Acme")


def test_command_needs_rows(tmp_path):
    empty = tmp_path / "e.csv"
    empty.write_text("Pin,Facility City\n")
    with pytest.raises(CommandError):
        call_command("import_pins", str(empty), courier="Delhivery")
    good = tmp_path / "g.csv"
    good.write_text(CSV)
    out = io.StringIO()
    call_command("import_pins", str(good), courier="Delhivery", stdout=out)
    assert "4 PIN codes added" in out.getvalue()


def test_pin_lookup(viewer):
    pin_import.load(pin_import.parse(CSV), "Delhivery")
    data = viewer.get("/api/v1/pin/751001/", HTTP_HOST=HOST).json()
    assert data == {
        "pin": "751001",
        "city": "Bhubaneswar",
        "state_code": "21",
        "state_name": "Odisha",
        "couriers": [{"courier": "Delhivery", "oda": False}],
    }
    assert viewer.get("/api/v1/pin/999999/", HTTP_HOST=HOST).status_code == 404
    assert viewer.get("/api/v1/pin/abc/", HTTP_HOST=HOST).status_code == 404


def test_countries_list(viewer):
    rows = viewer.get("/api/v1/countries/", HTTP_HOST=HOST).json()
    assert {"code": "IN", "name": "India"} in rows
