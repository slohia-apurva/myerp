from django.db import migrations, models


def branches_to_no_stock(apps, schema_editor):
    """Branches keep their meaning: those ticked "Warehouse" hold stock, the others are
    "No stock". Every stock-holding branch gets its default store."""
    Branch = apps.get_model("core", "Branch")
    Location = apps.get_model("core", "WarehouseLocation")
    for branch in Branch.objects.all():
        branch.no_stock = not branch.is_warehouse
        branch.save(update_fields=["no_stock"])
        if branch.no_stock:
            continue
        name = f"{branch.name} Store"[:60]
        if Location.objects.filter(
            branch=branch, kind="area", parent__isnull=True, name__iexact=name
        ).exists():
            name = f"{name[:50]} (default)"
        Location.objects.create(
            branch=branch, kind="area", name=name, purpose="storage", is_default=True
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0042_item_group_accounts"),
    ]

    operations = [
        migrations.AddField(
            model_name="branch",
            name="no_stock",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="warehouselocation",
            name="is_default",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="warehouselocation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("branch",),
                name="one_default_store_per_branch",
            ),
        ),
        migrations.RunPython(branches_to_no_stock, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="branch",
            name="is_warehouse",
        ),
    ]
