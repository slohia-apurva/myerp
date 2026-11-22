"""USP becomes the Unit Selling Price in rupees, per a unit (Sidharth,
2026-11-23). Old text that is a plain amount ("1.20", "₹ 1.20") is kept as the
amount; any other text is added to the item's Notes, so nothing is lost."""

import re
from decimal import Decimal, InvalidOperation

import django.db.models.deletion
from django.db import migrations, models

AMOUNT = re.compile(r"^(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:/-)?$", re.I)


def convert(apps, schema_editor):
    Item = apps.get_model("core", "Item")
    for item in Item.objects.exclude(usp_text=""):
        text = " ".join(item.usp_text.split())
        m = AMOUNT.match(text)
        amount = None
        if m:
            try:
                amount = Decimal(m[1].replace(",", "")).quantize(Decimal("0.01"))
            except InvalidOperation:
                amount = None
        if amount is not None:
            item.usp = amount
        else:
            note = f"USP: {text}"
            item.notes = f"{item.notes} · {note}" if item.notes else note
            item.notes = item.notes[:200]
        item.save(update_fields=["usp", "notes"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0069_alter_warehouselocation_purpose"),
    ]

    operations = [
        migrations.RenameField(model_name="item", old_name="usp", new_name="usp_text"),
        migrations.AddField(
            model_name="item",
            name="usp",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="item",
            name="usp_per",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.unit",
            ),
        ),
        migrations.RunPython(convert, migrations.RunPython.noop),
        migrations.RemoveField(model_name="item", name="usp_text"),
    ]
