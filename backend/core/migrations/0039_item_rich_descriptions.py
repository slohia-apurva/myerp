from django.db import migrations, models

from core import richtext


def to_formatted(apps, schema_editor):
    """The old descriptions are plain text: keep their line breaks and make
    sure nothing in them can be read as markup."""
    Item = apps.get_model("core", "Item")
    for item in Item.objects.all():
        changed = False
        for field in ("sales_description", "purchase_description"):
            old = getattr(item, field)
            if old:
                setattr(item, field, richtext.from_text(old))
                changed = True
        if changed:
            item.save(update_fields=["sales_description", "purchase_description"])


class Migration(migrations.Migration):
    dependencies = [("core", "0038_item_delivery_hsn")]

    operations = [
        migrations.AlterField(
            model_name="item", name="sales_description", field=models.TextField(blank=True)
        ),
        migrations.AlterField(
            model_name="item", name="purchase_description", field=models.TextField(blank=True)
        ),
        migrations.RunPython(to_formatted, migrations.RunPython.noop),
    ]
