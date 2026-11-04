from django.core.management.base import BaseCommand

from tenancy.provisioning import create_tenant


class Command(BaseCommand):
    help = "Create a tenant: its platform record, its own database, and all tenant tables."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Subdomain, e.g. apurvam for apurvam.myerp.in")
        parser.add_argument("name", help="Display name, e.g. 'Apurvam group'")

    def handle(self, *args, slug, name, **options):
        tenant = create_tenant(slug=slug, name=name)
        self.stdout.write(
            self.style.SUCCESS(f"Created tenant {tenant.slug} in database {tenant.db_name}")
        )
