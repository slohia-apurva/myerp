from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenancy import hsn_import


class Command(BaseCommand):
    help = (
        "Load the central HSN / SAC list from a CSV or tab-separated file "
        "(code in the first column, description in the second). New codes are "
        "added and descriptions of existing ones refreshed; a bad row stops "
        "the whole load."
    )

    def add_arguments(self, parser):
        parser.add_argument("file")

    def handle(self, *args, file, **options):
        try:
            with open(file, encoding="utf-8-sig") as f:
                text = f.read()
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        rows = hsn_import.parse(text) if text.strip() else []
        if not rows:
            raise CommandError("No HSN rows found in the file.")
        try:
            with transaction.atomic():
                done = hsn_import.load(rows)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"{done['added']} added, {done['updated']} updated, {done['unchanged']} unchanged."
        )
