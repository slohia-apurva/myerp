import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    """Second half of 0014, kept apart because Postgres cannot change a
    table's columns in the same transaction as moving its rows."""

    dependencies = [("core", "0014_shared_parties")]

    operations = [
        migrations.RemoveField(
            model_name="party",
            name="credit_limit",
        ),
        migrations.RemoveField(
            model_name="party",
            name="ledger",
        ),
        migrations.RemoveField(
            model_name="party",
            name="salesman",
        ),
        migrations.RemoveField(
            model_name="creditterm",
            name="company",
        ),
        migrations.AddConstraint(
            model_name="creditterm",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                name="credit_term_name_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledger",
            constraint=models.UniqueConstraint(
                condition=models.Q(("party__isnull", False)),
                fields=("company", "party"),
                name="one_ledger_per_party_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="party",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"), name="party_name_unique"
            ),
        ),
    ]
