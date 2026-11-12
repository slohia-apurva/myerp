from django.db import migrations, models


def shelf_life_into_best_before(apps, schema_editor):
    """The Stock tab's shelf life (days) becomes Best before, in days."""
    apps.get_model("core", "Item").objects.filter(shelf_life_days__isnull=False).update(
        best_before_value=models.F("shelf_life_days"), best_before_unit="days"
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0034_item_maintain_stock")]

    operations = [
        migrations.AddField(
            model_name="item",
            name="mrp",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="item",
            name="usp",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="item",
            name="best_before_value",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="item",
            name="best_before_unit",
            field=models.CharField(
                choices=[("days", "Days"), ("months", "Months")], default="days", max_length=6
            ),
        ),
        migrations.AddField(
            model_name="item",
            name="batch_no",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="item",
            name="lead_time_days",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="item",
            name="safety_stock_qty",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="item",
            name="min_order_qty",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="item",
            name="max_stock_qty",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True),
        ),
        migrations.RunPython(shelf_life_into_best_before, migrations.RunPython.noop),
        migrations.RemoveField(model_name="item", name="shelf_life_days"),
        migrations.RemoveField(model_name="item", name="sales_name"),
        migrations.RemoveField(model_name="item", name="purchase_name"),
    ]
