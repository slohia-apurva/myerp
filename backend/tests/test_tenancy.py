"""Design rule 16: a tenant can only ever reach its own database."""

import pytest
from django.core.exceptions import ValidationError
from django.db import connections

from core.models import Company
from core.tasks import count_companies
from tenancy.context import NoTenantSelected, use_tenant
from tenancy.middleware import tenant_slug_from_host
from tenancy.models import Tenant
from tenancy.provisioning import create_tenant
from tenancy.router import PLATFORM_ALIAS

pytestmark = pytest.mark.django_db(databases="__all__")


def table_names(alias: str) -> set[str]:
    with connections[alias].cursor() as cursor:
        return set(connections[alias].introspection.table_names(cursor))


@pytest.mark.parametrize(
    ("host", "slug"),
    [
        ("apurvam.myerp.in", "apurvam"),
        ("Apurvam.MyERP.in:443", "apurvam"),
        ("myerp.in", None),
        ("a.b.myerp.in", None),
        ("apurvam.example.com", None),
    ],
)
def test_tenant_slug_from_host(host, slug):
    assert tenant_slug_from_host(host, "myerp.in") == slug


def test_health_needs_no_tenant(client, tenants):
    response = client.get("/api/health/", HTTP_HOST="localhost")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_each_subdomain_sees_only_its_own_companies(logged_in):
    alpha = logged_in("alpha").get("/api/whoami/", HTTP_HOST="alpha.localhost").json()
    beta = logged_in("beta").get("/api/whoami/", HTTP_HOST="beta.localhost").json()
    assert alpha == {"tenant": "alpha", "name": "Alpha Group", "companies": ["Alpha Foods LLP"]}
    assert beta == {"tenant": "beta", "name": "Beta Group", "companies": ["Beta Traders Ltd"]}


@pytest.mark.parametrize("host", ["nobody.localhost", "localhost"])
def test_unknown_tenant_gets_404(client, tenants, host):
    response = client.get("/api/whoami/", HTTP_HOST=host)
    assert response.status_code == 404


def test_fallback_tenant_serves_hosts_without_subdomain(logged_in, settings):
    settings.MYERP_FALLBACK_TENANT = "alpha"
    bare = logged_in("alpha").get("/api/whoami/", HTTP_HOST="localhost")
    assert bare.status_code == 200
    assert bare.json()["tenant"] == "alpha"
    # A named subdomain is never redirected to the fallback tenant.
    beta = logged_in("beta")
    assert beta.get("/api/whoami/", HTTP_HOST="nobody.localhost").status_code == 404
    assert beta.get("/api/whoami/", HTTP_HOST="beta.localhost").json()["tenant"] == "beta"


def test_suspended_tenant_gets_404(client, alpha):
    Tenant.objects.filter(pk=alpha.pk).update(status=Tenant.Status.SUSPENDED)
    response = client.get("/api/whoami/", HTTP_HOST="alpha.localhost")
    assert response.status_code == 404


def test_tenant_data_without_a_tenant_raises(tenants):
    with pytest.raises(NoTenantSelected):
        Company.objects.count()


def test_tenant_a_cannot_reach_tenant_b_rows(alpha, beta):
    with use_tenant(alpha):
        assert not Company.objects.filter(name="Beta Traders Ltd").exists()
        Company.objects.create(name="Only In Alpha")
    with use_tenant(beta):
        assert not Company.objects.filter(name="Only In Alpha").exists()


def test_each_tenant_uses_its_own_database(alpha, beta):
    assert connections[alpha.db_alias].settings_dict["NAME"] == alpha.db_name
    assert connections[beta.db_alias].settings_dict["NAME"] == beta.db_name
    assert alpha.db_name != beta.db_name


def test_platform_and_tenant_tables_never_mix(alpha):
    platform_tables = table_names(PLATFORM_ALIAS)
    tenant_tables = table_names(alpha.db_alias)
    assert "tenancy_tenant" in platform_tables
    assert "tenancy_tenant" not in tenant_tables
    assert {"core_company", "accounts_user", "django_session"} <= tenant_tables
    assert not {"core_company", "accounts_user", "django_session"} & platform_tables


def test_background_task_runs_inside_named_tenant(alpha, beta):
    with use_tenant(beta):
        Company.objects.create(name="Second Beta Company")
    assert count_companies("alpha") == 1
    assert count_companies("beta") == 2


@pytest.mark.parametrize("bad_slug", ["A", "ab", "-abc", "has space", "x" * 41])
def test_create_tenant_rejects_bad_slugs(bad_slug):
    with pytest.raises(ValidationError):
        create_tenant(bad_slug, "Bad")
