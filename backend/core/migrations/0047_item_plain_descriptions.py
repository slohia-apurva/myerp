"""Item descriptions back to plain text (Sidharth, 2026-11-15): the formatting
is taken off and each paragraph, line break or list item becomes its own line."""

import html
import re

from django.db import migrations

_BLOCK_END = re.compile(r"</(p|div|li)>|<br\s*/?>", re.I)


def _to_text(value: str) -> str:
    text = _BLOCK_END.sub("\n", value or "")
    text = re.sub(r"<[^>]*>", "", text)
    lines = [line.rstrip() for line in html.unescape(text).splitlines()]
    return "\n".join(lines).strip()


def to_plain(apps, schema_editor):
    Item = apps.get_model("core", "Item")
    fields = ("sales_description", "purchase_description")
    for item in Item.objects.exclude(sales_description="", purchase_description=""):
        for field in fields:
            setattr(item, field, _to_text(getattr(item, field)))
        item.save(update_fields=list(fields))


class Migration(migrations.Migration):
    dependencies = [("core", "0046_purchase_prices")]

    operations = [migrations.RunPython(to_plain, migrations.RunPython.noop)]
