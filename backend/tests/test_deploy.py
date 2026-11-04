"""Behaviour the staging deploy relies on."""

import pytest
from django.core.management import call_command

from tenancy.models import Tenant
from tenancy.provisioning import drop_tenant_database

BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


@pytest.mark.django_db(databases="__all__")
def test_api_answers_json_when_a_browser_opens_it(client, tenants):
    response = client.get("/api/whoami/", HTTP_HOST="alpha.localhost", HTTP_ACCEPT=BROWSER_ACCEPT)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"


# No django_db mark: CREATE DATABASE cannot run inside the test transaction,
# so this test commits and cleans up after itself.
def test_migrate_tenants_creates_missing_fallback_tenant(settings, tenants, django_db_blocker):
    settings.MYERP_FALLBACK_TENANT = "gamma"
    settings.MYERP_TENANT_DB_PREFIX = "test_myerp_tenant_"
    with django_db_blocker.unblock():
        try:
            _run_twice_and_check()
        finally:
            Tenant.objects.filter(slug="gamma").delete()
            drop_tenant_database(Tenant(slug="gamma", db_name="test_myerp_tenant_gamma"))


def _run_twice_and_check():
    call_command("migrate_tenants", verbosity=0)
    gamma = Tenant.objects.get(slug="gamma")
    assert gamma.db_name == "test_myerp_tenant_gamma"
    # Running again (every deploy) must not create it twice or fail.
    call_command("migrate_tenants", verbosity=0)
    assert Tenant.objects.filter(slug="gamma").count() == 1
