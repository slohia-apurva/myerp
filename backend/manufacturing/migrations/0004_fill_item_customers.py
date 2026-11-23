"""Tag each Customer Provided item with its customer (Sidharth, 2026-11-23,
preview 18) where the data says it clearly: the one customer whose stock of
it was received, else the one customer of the job work BOMs that use it.
Items left open show "Customer not set" until someone picks the customer."""

from django.db import migrations


def fill(apps, schema_editor):
    Item = apps.get_model("core", "Item")
    StockMove = apps.get_model("posting", "StockMove")
    BomLine = apps.get_model("manufacturing", "BomLine")
    for item in Item.objects.filter(default_request_type="customer_provided", customer=None):
        owners = set(
            StockMove.objects.filter(item=item).exclude(owner=None).values_list("owner", flat=True)
        )
        if not owners:
            owners = set(
                BomLine.objects.filter(item=item)
                .exclude(bom__customer=None)
                .values_list("bom__customer", flat=True)
            )
        if len(owners) == 1:
            item.customer_id = owners.pop()
            item.save(update_fields=["customer"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0071_item_customer"),
        ("posting", "0004_stock_move_owner"),
        ("manufacturing", "0003_order_picks"),
    ]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
