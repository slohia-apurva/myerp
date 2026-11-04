from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tenancy.models import Tenant
from tenancy.provisioning import create_tenant, migrate_tenant


class Command(BaseCommand):
    help = (
        "Apply migrations to every active tenant database, oldest tenant first "
        "(Apurvam is the pilot). Run `migrate` for the platform database separately. "
        "If MYERP_FALLBACK_TENANT is set (staging before a domain exists) and that "
        "tenant does not exist yet, it is created first."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Only migrate this tenant slug")

    def handle(self, *args, tenant=None, **options):
        fallback = settings.MYERP_FALLBACK_TENANT
        if fallback and not Tenant.objects.filter(slug=fallback).exists():
            self.stdout.write(f"Creating fallback tenant {fallback}...")
            create_tenant(slug=fallback, name=fallback)

        tenants = Tenant.objects.filter(status=Tenant.Status.ACTIVE)
        if tenant:
            tenants = tenants.filter(slug=tenant)
            if not tenants.exists():
                raise CommandError(f"No active tenant {tenant!r}")
        for item in tenants:
            self.stdout.write(f"Migrating {item.slug} ({item.db_name})...")
            migrate_tenant(item, verbosity=options["verbosity"])
        self.stdout.write(self.style.SUCCESS(f"Migrated {tenants.count()} tenant(s)."))
