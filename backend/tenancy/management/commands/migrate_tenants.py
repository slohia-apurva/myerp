from django.core.management.base import BaseCommand, CommandError

from tenancy.models import Tenant
from tenancy.provisioning import migrate_tenant


class Command(BaseCommand):
    help = (
        "Apply migrations to every active tenant database, oldest tenant first "
        "(Apurvam is the pilot). Run `migrate` for the platform database separately."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Only migrate this tenant slug")

    def handle(self, *args, tenant=None, **options):
        tenants = Tenant.objects.filter(status=Tenant.Status.ACTIVE)
        if tenant:
            tenants = tenants.filter(slug=tenant)
            if not tenants.exists():
                raise CommandError(f"No active tenant {tenant!r}")
        for item in tenants:
            self.stdout.write(f"Migrating {item.slug} ({item.db_name})...")
            migrate_tenant(item, verbosity=options["verbosity"])
        self.stdout.write(self.style.SUCCESS(f"Migrated {tenants.count()} tenant(s)."))
