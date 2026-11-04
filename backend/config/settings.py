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
ALLOWED_HOSTS = [MYERP_BASE_DOMAIN, f".{MYERP_BASE_DOMAIN}"]

# Prefix for tenant database names: tenant "apurvam" lives in myerp_tenant_apurvam.
MYERP_TENANT_DB_PREFIX = env("MYERP_TENANT_DB_PREFIX", "myerp_tenant_")

# Paths that work without a tenant (platform-level endpoints).
MYERP_TENANT_EXEMPT_PATHS = ("/api/health/",)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    # Platform side: lives only in the platform database.
    "tenancy",
    # Tenant side: lives only in each tenant's database.
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "tenancy.middleware.TenantMiddleware",
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

REST_FRAMEWORK = {
    # Login arrives in Phase 1; Phase 0 endpoints are read-only probes.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
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
