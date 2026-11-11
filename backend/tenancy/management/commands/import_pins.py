from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenancy import pin_import


class Command(BaseCommand):
    help = (
        "Load PIN codes and one courier's coverage from the courier's serviceability "
        "CSV (Pin, Facility City, Facility State, ODA, ... columns). PINs we lack are "
        "added; the courier's earlier coverage is replaced by the file's. A bad state "
        "name stops the whole load."
    )

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--courier", required=True, help='for example "Delhivery"')

    def handle(self, *args, file, courier, **options):
        try:
            with open(file, encoding="utf-8-sig") as f:
                text = f.read()
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        rows = pin_import.parse(text)
        if not rows:
            raise CommandError("No PIN rows found in the file.")
        try:
            with transaction.atomic():
                done = pin_import.load(rows, courier)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"{done['pins_added']} PIN codes added, {done['state_filled']} given a state; "
            f"{courier} now covers {done['coverage']} (replaced {done['replaced']})."
        )
