from django.core.management import call_command
from django.core.management.base import BaseCommand

from tenancy.reader import grant_reader
from tenancy.router import PLATFORM_ALIAS


class Command(BaseCommand):
    help = (
        "What the deploy's migration job runs: platform migrations, then every tenant. "
        "Each database then grants the read-only login, if one is set (tenancy/reader.py)."
    )

    def handle(self, *args, **options):
        call_command("migrate", verbosity=options["verbosity"])
        grant_reader(PLATFORM_ALIAS)
        call_command("migrate_tenants", verbosity=options["verbosity"])
