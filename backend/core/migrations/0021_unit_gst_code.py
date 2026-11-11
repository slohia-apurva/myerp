from django.db import migrations, models

# GST unit quantity code for the units the group started with (frozen).
CODES = {
    "nos": "NOS", "packet": "PAC", "inner box": "BOX", "carton": "CTN",
    "pallet": "OTH", "bag": "BAG", "bottle": "BTL", "kilogram": "KGS",
    "gram": "GMS", "tonne": "TON", "litre": "LTR", "millilitre": "MLT",
    "metre": "MTR",
}  # fmt: skip


def fill_codes(apps, schema_editor):
    Unit = apps.get_model("core", "Unit")
    for unit in Unit.objects.all():
        unit.gst_code = CODES.get(unit.name.lower(), "OTH")
        unit.save(update_fields=["gst_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="gst_code",
            field=models.CharField(blank=True, max_length=3),
        ),
        migrations.RunPython(fill_codes, migrations.RunPython.noop),
    ]
