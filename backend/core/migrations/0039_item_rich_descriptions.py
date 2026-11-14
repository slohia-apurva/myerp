import html
import re

from django.db import migrations, models


def _from_text(text: str) -> str:
    """Plain text as HTML (core.richtext.from_text, removed when the descriptions
    went back to plain text in 0047)."""
    escaped = html.escape((text or "").strip(), quote=False)
    return re.sub(r"\r\n|\r|\n", "<br>", escaped)


def to_formatted(apps, schema_editor):
    """The old descriptions are plain text: keep their line breaks and make
    sure nothing in them can be read as markup."""
    Item = apps.get_model("core", "Item")
    for item in Item.objects.all():
        changed = False
        for field in ("sales_description", "purchase_description"):
            old = getattr(item, field)
            if old:
                setattr(item, field, _from_text(old))
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
