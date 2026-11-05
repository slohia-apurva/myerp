import re

from django.db import migrations

from core.ledger_groups import ensure_head_office, seed_standard_groups


def fill_existing(apps, schema_editor):
    """Companies made before this change get a short code, a head office
    branch and the standard ledger groups, like new ones."""
    Company = apps.get_model("core", "Company")
    Branch = apps.get_model("core", "Branch")
    LedgerGroup = apps.get_model("core", "LedgerGroup")
    taken = set()
    for company in Company.objects.order_by("pk"):
        words = re.findall(r"[A-Za-z0-9]+", company.name)
        base = "".join(w[0] for w in words).upper()[:8]
        if len(base) < 2:
            base = (words[0][:3] if words else "CO").upper()
        abbr, n = base, 2
        while abbr in taken:
            abbr, n = f"{base}{n}", n + 1
        taken.add(abbr)
        company.abbr = abbr
        company.save(update_fields=["abbr"])
        ensure_head_office(Branch, company)
        seed_standard_groups(LedgerGroup, company)


class Migration(migrations.Migration):
    dependencies = [("core", "0002_companies_branches_ledger_groups")]

    operations = [migrations.RunPython(fill_existing, migrations.RunPython.noop)]
