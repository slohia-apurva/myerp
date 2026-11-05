from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "What the deploy's migration job runs: platform migrations, then every tenant."

    def handle(self, *args, **options):
        call_command("migrate", verbosity=options["verbosity"])
        call_command("migrate_tenants", verbosity=options["verbosity"])
