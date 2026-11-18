"""Read-only access for the database login named in MYERP_READER_DB_USER.

Staging lets Claude sessions check entries and reports through a Google
service account that may only read (deploy/gcp/README.md, "Read-only access").
Each deploy, after migrating a database, grants that login SELECT on its
tables. Sign-in sessions are left out: a session key would let someone sign in
as that person. Nothing here gives the login any way to change data.
"""

from __future__ import annotations

from django.conf import settings
from django.db import connections
from psycopg import sql

# Tables the reader may never see, in every database.
HIDDEN_TABLES = ("django_session",)


def grant_reader(alias: str) -> bool:
    """Grant the reader SELECT on the database behind `alias`. Idempotent.

    Returns False (and grants nothing) when no reader is set, or the login does
    not exist yet on this server (Terraform creates it; the next deploy grants).
    """
    role = settings.MYERP_READER_DB_USER
    if not role:
        return False
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
        if cursor.fetchone() is None:
            return False
        who = sql.Identifier(role)
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(who))
        cursor.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(who))
        for table in HIDDEN_TABLES:
            cursor.execute("SELECT to_regclass(%s)", [f"public.{table}"])
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    sql.SQL("REVOKE ALL ON {} FROM {}").format(sql.Identifier(table), who)
                )
    return True
