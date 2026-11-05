from django.db import migrations, models


class Migration(migrations.Migration):
    """Separate from 0003: Postgres will not alter a table in the same
    transaction that inserted rows referencing it."""

    dependencies = [("core", "0003_fill_existing_companies")]

    operations = [
        migrations.AlterField(
            model_name="company",
            name="abbr",
            field=models.CharField(max_length=10, unique=True),
        ),
    ]
