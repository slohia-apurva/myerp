"""A firm that is both customer and supplier may have one ledger under
Sundry Debtors and one under Sundry Creditors in the same company
(Sidharth, 2026-11-11). Ledger.party_side says which; existing party
ledgers get it from their group. Until now a party had at most one ledger
per company, so the new constraint holds for existing data."""

from django.conf import settings
from django.db import migrations, models


def fill_party_side(apps, schema_editor):
    Ledger = apps.get_model("core", "Ledger")
    for ledger in Ledger.objects.exclude(party=None).select_related("group"):
        group = ledger.group
        while group.code not in ("sundry_debtors", "sundry_creditors"):
            group = group.parent
        ledger.party_side = "customer" if group.code == "sundry_debtors" else "supplier"
        ledger.save(update_fields=["party_side"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_no_duplicates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="ledger",
            name="one_ledger_per_party_per_company",
        ),
        migrations.AddField(
            model_name="ledger",
            name="party_side",
            field=models.CharField(
                blank=True,
                choices=[("customer", "Customer"), ("supplier", "Supplier")],
                max_length=8,
            ),
        ),
        migrations.RunPython(fill_party_side, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="ledger",
            constraint=models.UniqueConstraint(
                condition=models.Q(("party__isnull", False)),
                fields=("company", "party", "party_side"),
                name="one_ledger_per_party_side_per_company",
            ),
        ),
    ]
