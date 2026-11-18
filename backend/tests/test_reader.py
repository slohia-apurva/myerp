"""The read-only database login (tenancy/reader.py): may read, never change, never see sessions."""

import pytest
from django.db import connections

from tenancy.context import use_tenant
from tenancy.reader import grant_reader
from tenancy.router import PLATFORM_ALIAS

READER = "test_myerp_reader@example.iam"


@pytest.fixture
def reader_role(tenants, django_db_blocker, settings):
    # Roles belong to the whole server and GRANT must see a committed role, so
    # this runs outside the test transactions and cleans up after itself.
    settings.MYERP_READER_DB_USER = READER
    with django_db_blocker.unblock():
        with connections[PLATFORM_ALIAS].cursor() as cursor:
            try:
                cursor.execute(f'DROP ROLE IF EXISTS "{READER}"')  # left by a crashed run
                cursor.execute(f'CREATE ROLE "{READER}" NOLOGIN')
            except Exception as error:  # the test server's login may lack CREATEROLE
                pytest.skip(f"cannot create a role here: {error}")
        try:
            yield READER
        finally:
            for tenant in tenants.values():
                with use_tenant(tenant):
                    _revoke(tenant.db_alias)
            _revoke(PLATFORM_ALIAS)
            with connections[PLATFORM_ALIAS].cursor() as cursor:
                cursor.execute(f'DROP ROLE "{READER}"')


def _revoke(alias):
    with connections[alias].cursor() as cursor:
        cursor.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{READER}"')
        cursor.execute(f'REVOKE ALL ON SCHEMA public FROM "{READER}"')


def _may(alias, table, privilege):
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT has_table_privilege(%s, %s, %s)", [READER, table, privilege])
        return cursor.fetchone()[0]


def test_reader_may_read_tenant_tables_but_not_sessions_or_change_anything(
    reader_role, alpha, django_db_blocker
):
    with django_db_blocker.unblock(), use_tenant(alpha):
        assert grant_reader(alpha.db_alias) is True
        alias = alpha.db_alias
        assert _may(alias, "core_company", "SELECT")
        assert _may(alias, "accounts_user", "SELECT")
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            assert not _may(alias, "core_company", privilege)
        # A session key would let someone sign in as that person.
        assert not _may(alias, "django_session", "SELECT")
        # Every deploy runs it again.
        assert grant_reader(alias) is True


def test_reader_may_read_the_platform_database(reader_role, django_db_blocker):
    with django_db_blocker.unblock():
        assert grant_reader(PLATFORM_ALIAS) is True
        assert _may(PLATFORM_ALIAS, "tenancy_tenant", "SELECT")
        assert not _may(PLATFORM_ALIAS, "tenancy_tenant", "UPDATE")


def test_nothing_is_granted_without_a_reader_or_before_its_login_exists(
    tenants, settings, django_db_blocker
):
    with django_db_blocker.unblock():
        settings.MYERP_READER_DB_USER = ""
        assert grant_reader(PLATFORM_ALIAS) is False
        # Set in Cloud Run before Terraform has made the login: deploys still pass.
        settings.MYERP_READER_DB_USER = "no-such-login@example.iam"
        assert grant_reader(PLATFORM_ALIAS) is False
