from decimal import Decimal

from django.db import migrations, models

# The standard GST slabs; the ones the law has since dropped start disabled.
SLABS = [
    ("0", True),
    ("0.25", True),
    ("3", True),
    ("5", True),
    ("12", False),
    ("18", True),
    ("28", False),
]


def seed(apps, schema_editor):
    GstRate = apps.get_model("tenancy", "GstRate")
    for rate, active in SLABS:
        GstRate.objects.get_or_create(rate=Decimal(rate), defaults={"is_active": active})


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0006_carrier_requests"),
    ]

    operations = [
        migrations.CreateModel(
            name="GstRate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("rate", models.DecimalField(decimal_places=2, max_digits=5, unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["rate"],
            },
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
