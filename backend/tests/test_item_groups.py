"""Item groups: the group's shared tree, and an item's place in it."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

HOST = "alpha.localhost"


@pytest.fixture
def accountant(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("accounts@x.in", full_name="Asha")
        user.roles.set(Role.objects.filter(code="accountant"))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def viewer(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("view@x.in", full_name="Vee")
        user.roles.set(Role.objects.filter(code="viewer"))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def add(client, name, parent=None, **extra):
    return call(client, "post", "item-groups/", {"name": name, "parent": parent, **extra})


def tree(accountant, company):
    raw = add(accountant, "Raw material").json()
    spices = add(accountant, "Spices", raw["id"]).json()
    whole = add(accountant, "Whole spices", spices["id"]).json()
    return raw, spices, whole


def kg(client):
    return next(u["id"] for u in call(client, "get", "units/").json() if u["name"] == "Kilogram")


def test_groups_nest_to_any_depth(accountant, company):
    raw, spices, whole = tree(accountant, company)
    rows = {g["name"]: g for g in call(accountant, "get", "item-groups/").json()}
    assert rows["Raw material"]["parent"] is None
    assert rows["Spices"]["parent"] == raw["id"]
    assert rows["Whole spices"]["parent"] == spices["id"]


def test_names_are_unique_whatever_the_case(accountant, company):
    tree(accountant, company)
    bad = add(accountant, "raw MATERIAL")
    assert bad.status_code == 400
    assert "already an item group" in str(bad.json())


def test_a_group_cannot_move_under_itself_or_below(accountant, company):
    raw, spices, whole = tree(accountant, company)
    for target in (raw["id"], whole["id"]):
        bad = call(accountant, "patch", f"item-groups/{raw['id']}/", {"parent": target})
        assert bad.status_code == 400
        assert "cannot sit under itself" in str(bad.json())
    ok = call(accountant, "patch", f"item-groups/{whole['id']}/", {"parent": raw["id"]})
    assert ok.status_code == 200 and ok.json()["parent"] == raw["id"]


def test_an_item_sits_in_a_group_and_counts_show(accountant, company):
    raw, spices, whole = tree(accountant, company)
    made = call(
        accountant,
        "post",
        "items/",
        {
            "name": "Turmeric finger",
            "stock_unit": kg(accountant),
            "item_group": whole["id"],
            "hsn": "0902",
        },
    )
    assert made.status_code == 201, made.json()
    assert made.json()["item_group_name"] == "Whole spices"
    rows = {g["name"]: g for g in call(accountant, "get", "item-groups/").json()}
    assert rows["Whole spices"]["item_count"] == 1
    assert rows["Spices"]["item_count"] == 0


def test_a_group_with_items_below_it_cannot_move(accountant, company):
    raw, spices, whole = tree(accountant, company)
    other = add(accountant, "Packing").json()
    call(
        accountant,
        "post",
        "items/",
        {
            "name": "Turmeric finger",
            "stock_unit": kg(accountant),
            "item_group": whole["id"],
            "hsn": "0902",
        },
    )
    bad = call(accountant, "patch", f"item-groups/{spices['id']}/", {"parent": other["id"]})
    assert bad.status_code == 400
    assert "1 item" in str(bad.json())
    # Names and notes stay open.
    ok = call(accountant, "patch", f"item-groups/{spices['id']}/", {"name": "Spices and herbs"})
    assert ok.status_code == 200
    # A group with nothing below it can move.
    free = call(accountant, "patch", f"item-groups/{other['id']}/", {"parent": raw["id"]})
    assert free.status_code == 200


def test_a_disabled_group_takes_no_new_items(accountant, company):
    raw, spices, whole = tree(accountant, company)
    call(accountant, "patch", f"item-groups/{whole['id']}/", {"is_active": False})
    bad = call(
        accountant,
        "post",
        "items/",
        {"name": "Cumin", "stock_unit": kg(accountant), "item_group": whole["id"], "hsn": "0902"},
    )
    assert bad.status_code == 400
    assert "disabled" in str(bad.json())
    under = add(accountant, "Sub", whole["id"])
    assert under.status_code == 400


def test_viewers_read_but_cannot_change(viewer, accountant, company):
    tree(accountant, company)
    assert call(viewer, "get", "item-groups/").status_code == 200
    assert add(viewer, "Nope").status_code == 403


def test_groups_import_with_parents_listed_first(alpha, company):
    import csv
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile

    with use_tenant(alpha):
        user = User.objects.create_user("owner@x.in", full_name="Olu")
        user.roles.set(Role.objects.filter(code="owner"))
        owner = Client()
        owner.force_login(user)

    def send(rows, commit):
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        return owner.post(
            "/api/v1/exchange/item-groups/import/",
            {
                "file": SimpleUploadedFile("g.csv", buf.getvalue().encode("utf-8-sig")),
                "commit": "1" if commit else "0",
            },
            HTTP_HOST=HOST,
        )

    header = ["Name", "Under", "Notes", "Active"]
    good = [header, ["Packing", "", "", ""], ["Cartons", "Packing", "", ""]]
    done = send(good, True).json()
    assert done["saved"] is True, done
    rows = {g["name"]: g for g in call(owner, "get", "item-groups/").json()}
    assert rows["Cartons"]["parent"] == rows["Packing"]["id"]
    bad = send([header, ["Tapes", "No such group", "", ""]], False).json()
    assert bad["errors"] and "no item group called" in str(bad["errors"])


def test_items_sit_only_in_groups_without_sub_groups(accountant, company):
    raw, spices, whole = tree(accountant, company)
    body = {"name": "Turmeric finger", "stock_unit": kg(accountant), "hsn": "0902"}
    bad = call(accountant, "post", "items/", {**body, "item_group": raw["id"]})
    assert bad.status_code == 400
    assert "sub-groups" in str(bad.json())
    ok = call(accountant, "post", "items/", {**body, "item_group": whole["id"]})
    assert ok.status_code == 201
    # A group that holds items cannot get a sub-group.
    sub = call(accountant, "post", "item-groups/", {"name": "Fine powder", "parent": whole["id"]})
    assert sub.status_code == 400
    assert "already has items" in str(sub.json())
