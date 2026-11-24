"""Choose Columns: each person keeps their own columns per list (Sidharth, 2026-11-24)."""

import pytest
from django.test import Client

from accounts.models import Role, User
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def person(alpha, email):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=email)
        user.roles.set(Role.objects.filter(code="viewer"))
        client = Client()
        client.force_login(user)
    return client


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def test_each_person_keeps_their_own_columns(alpha):
    asha, vee = person(alpha, "asha@x.in"), person(alpha, "vee@x.in")
    assert call(asha, "get", "my-columns/items/").json() == {"columns": []}

    saved = call(asha, "put", "my-columns/items/", {"columns": ["hsn", "brand", "hsn"]})
    assert saved.status_code == 200, saved.json()
    assert saved.json() == {"columns": ["hsn", "brand"]}
    assert call(asha, "get", "my-columns/items/").json() == {"columns": ["hsn", "brand"]}
    # someone else, and another list, keep the standard columns
    assert call(vee, "get", "my-columns/items/").json() == {"columns": []}
    assert call(asha, "get", "my-columns/units/").json() == {"columns": []}
    # Reset
    call(asha, "put", "my-columns/items/", {"columns": []})
    assert call(asha, "get", "my-columns/items/").json() == {"columns": []}


def test_columns_are_checked(alpha):
    asha = person(alpha, "asha@x.in")
    assert call(asha, "put", "my-columns/items/", {"columns": "hsn"}).status_code == 400
    assert call(asha, "put", "my-columns/items/", {"columns": ["<b>"]}).status_code == 400
    assert call(Client(), "get", "my-columns/items/").status_code == 403
