"""Django settings for MyERP.

Every value that differs between laptop, staging and production comes from an
environment variable. Defaults are for local development only.
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, "1" if default else "0").lower() in {"1", "true", "yes"}


DEBUG = env_bool("DJANGO_DEBUG", default=True)
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key" if DEBUG else None)

# Tenants are reached at <tenant-slug>.<MYERP_BASE_DOMAIN>, e.g. apurvam.myerp.in.
# Locally that is apurvam.localhost.
MYERP_BASE_DOMAIN = env("MYERP_BASE_DOMAIN", "localhost")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", f"{MYERP_BASE_DOMAIN},.{MYERP_BASE_DOMAIN}").split(",")

# Tenant served on hosts that carry no tenant subdomain (e.g. the bare Cloud Run
# URL on staging before a domain exists). Empty in production.
MYERP_FALLBACK_TENANT = env("MYERP_FALLBACK_TENANT", "")

# Bucket for attachments and exports (Google Cloud Storage); unused until Module 1.
MYERP_FILES_BUCKET = env("MYERP_FILES_BUCKET", "")

# Prefix for tenant database names: tenant "apurvam" lives in myerp_tenant_apurvam.
MYERP_TENANT_DB_PREFIX = env("MYERP_TENANT_DB_PREFIX", "myerp_tenant_")

# Paths that work without a tenant (platform-level endpoints).
MYERP_TENANT_EXEMPT_PATHS = ("/api/health/",)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    # Platform side: lives only in the platform database.
    "tenancy",
    # Tenant side: lives only in each tenant's database.
    "accounts",
    "core",
    "audit",
    "shipping",
    "buying",
    "posting",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves the built React app (index.html and /assets/) before tenant lookup.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "tenancy.middleware.TenantMiddleware",
    # Below the tenant middleware: sessions and users live in the tenant's
    # database, so they must be read and saved while the tenant is selected.
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Records who changed which master (below authentication: needs the user).
    "audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# "default" is the platform database. Tenant databases are added at runtime by
# tenancy.db.register_tenant_database(), copying these connection settings.
DATABASES = {
    "default": dj_database_url.parse(
        env(
            "PLATFORM_DATABASE_URL",
            "postgres://myerp:myerp@localhost:5432/myerp_platform",
        ),
        conn_max_age=60,
    )
}
DATABASE_ROUTERS = ["tenancy.router.TenantRouter"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The production image copies the React build here (see the root Dockerfile).
FRONTEND_DIST = BASE_DIR / "frontend_dist"
STATIC_URL = "static/"
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.is_dir() else None
WHITENOISE_INDEX_FILE = True

# Users and sessions are tenant-side (see accounts/). People sign in with Google.
AUTH_USER_MODEL = "accounts.User"
# OAuth client id from Google Cloud (APIs & Services > Credentials). Not a secret.
MYERP_GOOGLE_CLIENT_ID = env("MYERP_GOOGLE_CLIENT_ID", "")
# GSTIN lookup (core/gstin_lookup.py). The provider reads its own key from the
# GSTINAPI_KEY environment variable; without it the lookup says it is not set up.
GSTIN_LOOKUP_PROVIDER = env("GSTIN_LOOKUP_PROVIDER", "core.gstinapi.lookup")
# The Owner's "Reset data" tool (core/data_reset.py) is refused unless this is
# on. Turn it on for staging and trial runs, never for live books.
ALLOW_DATA_RESET = env_bool("MYERP_ALLOW_DATA_RESET", False)
# Sign-in emails (comma separated) of MyERP platform admins, who alone may open
# the central admin screen (core/central.py). Not the same as a customer's Owner.
MYERP_PLATFORM_ADMINS = env("MYERP_PLATFORM_ADMINS", "")
# The key that locks customers' API secrets (core/secrets.py): a Fernet key kept
# outside the database. Blank in production means secrets cannot be saved yet.
MYERP_SECRETS_KEY = env("MYERP_SECRETS_KEY", "")
# A sign-in lasts a working day; closing the browser does not end it.
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_COOKIE_HTTPONLY = True
# Google's sign-in popup needs to talk back to this page, and its button needs
# to see which site it is on.
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

REST_FRAMEWORK = {
    # JSON only: the browsable API would need templates we don't ship.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # Session login (with CSRF) only; every endpoint needs a logged-in user
    # unless it says otherwise.
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = False
USE_TZ = True

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
