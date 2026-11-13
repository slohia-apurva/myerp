"""Two real tenant databases, alpha and beta, shared by the whole test session.

Each test runs inside transactions on the platform database and on both tenant
databases (`databases="__all__"`), so anything a test writes is rolled back.
"""

import pytest

from core.companies import create_company
from tenancy.context import use_tenant
from tenancy.models import HsnCode, Tenant
from tenancy.provisioning import create_tenant, drop_tenant_database

TEST_TENANTS = {
    "alpha": ("Alpha Group", "Alpha Foods LLP"),
    "beta": ("Beta Group", "Beta Traders Ltd"),
}


def _test_db_name(slug: str) -> str:
    return f"test_myerp_tenant_{slug}"


@pytest.fixture(scope="session")
def tenants(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        # Clear leftovers from an interrupted earlier run.
        for slug in TEST_TENANTS:
            drop_tenant_database(Tenant(slug=slug, db_name=_test_db_name(slug)))

        created = {}
        for slug, (group_name, company_name) in TEST_TENANTS.items():
            tenant = create_tenant(slug, group_name, db_name=_test_db_name(slug))
            with use_tenant(tenant):
                create_company(name=company_name, state_code="27")
            created[slug] = tenant

    yield created

    with django_db_blocker.unblock():
        for tenant in created.values():
            drop_tenant_database(tenant)


@pytest.fixture
def alpha(tenants):
    return tenants["alpha"]


@pytest.fixture
def beta(tenants):
    return tenants["beta"]


@pytest.fixture
def logged_in(tenants):
    """logged_in("alpha") -> a test client with a user logged in to alpha."""
    from django.test import Client

    from accounts.models import User

    def make(slug: str, email: str = "tester@example.com") -> Client:
        client = Client()
        with use_tenant(tenants[slug]):
            user = User.objects.filter(email=email).first() or User.objects.create_user(email)
            client.force_login(user)
        return client

    return make


@pytest.fixture
def hsn_list(db):
    """A few central HSN codes, rolled back with the test, for tests that make items."""
    for code, text in [
        ("0405", "Butter and ghee"),
        ("0902", "Tea"),
        ("0910", "Ginger, turmeric"),
        ("1701", "Cane or beet sugar"),
    ]:
        HsnCode.objects.get_or_create(hsn_code=code, defaults={"description": text})


@pytest.fixture(autouse=True)
def _items_get_a_default_group(monkeypatch):
    """An item must have an item group and a brand. Most tests are about something else, so
    an item posted without one gets the group "General" (made on first use).
    A test that is about the rule posts `"item_group": None` (or `"brand": None`) to say so."""
    import json

    from django.test import Client

    real_post = Client.post

    def post(self, path, data=None, *args, **kwargs):
        if (
            path == "/api/v1/items/"
            and isinstance(data, dict)
            and "stock_unit" in data
            and "item_group" not in data
        ):
            host = {"HTTP_HOST": kwargs["HTTP_HOST"]} if "HTTP_HOST" in kwargs else {}
            groups = self.get("/api/v1/item-groups/", **host)
            found = (
                [g for g in groups.json() if g["name"] == "General"]
                if groups.status_code == 200
                else []
            )
            if not found and groups.status_code == 200:
                made = real_post(
                    self,
                    "/api/v1/item-groups/",
                    data=json.dumps({"name": "General"}),
                    content_type="application/json",
                    **host,
                )
                found = [made.json()] if made.status_code == 201 else []
            if found:
                data = {**data, "item_group": found[0]["id"]}
        if (
            path == "/api/v1/items/"
            and isinstance(data, dict)
            and "stock_unit" in data
            and "brand" not in data
        ):
            host = {"HTTP_HOST": kwargs["HTTP_HOST"]} if "HTTP_HOST" in kwargs else {}
            brands = self.get("/api/v1/brands/", **host)
            found = (
                [b for b in brands.json() if b["name"] == "General brand"]
                if brands.status_code == 200
                else []
            )
            if not found and brands.status_code == 200:
                made = real_post(
                    self,
                    "/api/v1/brands/",
                    data=json.dumps({"name": "General brand"}),
                    content_type="application/json",
                    **host,
                )
                found = [made.json()] if made.status_code == 201 else []
            if found:
                data = {**data, "brand": found[0]["id"]}
        return real_post(self, path, data, *args, **kwargs)

    monkeypatch.setattr(Client, "post", post)
