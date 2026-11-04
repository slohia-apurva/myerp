"""Two real tenant databases, alpha and beta, shared by the whole test session.

Each test runs inside transactions on the platform database and on both tenant
databases (`databases="__all__"`), so anything a test writes is rolled back.
"""

import pytest

from core.models import Company
from tenancy.context import use_tenant
from tenancy.models import Tenant
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
                Company.objects.create(name=company_name, state_code="27")
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

    def make(slug: str, username: str = "tester") -> Client:
        client = Client()
        with use_tenant(tenants[slug]):
            user, _ = User.objects.get_or_create(username=username)
            client.force_login(user)
        return client

    return make
