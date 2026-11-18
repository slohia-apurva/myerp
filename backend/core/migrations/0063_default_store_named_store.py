from django.db import migrations


def name_default_stores_store(apps, schema_editor):
    """Default stores were named after their branch ("Apurvam Organics LLP (Sankrail-2)
    Store"); they are now just "Store" (Sidharth, 2026-11-18). A store renamed by hand,
    or a branch that already has another area called "Store", is left as it is."""
    Location = apps.get_model("core", "WarehouseLocation")
    for store in Location.objects.filter(is_default=True).select_related("branch"):
        if store.name.lower() != f"{store.branch.name} Store"[:60].lower():
            continue
        clash = (
            Location.objects.filter(
                branch=store.branch, kind=store.kind, parent__isnull=True, name__iexact="Store"
            )
            .exclude(pk=store.pk)
            .exists()
        )
        if not clash:
            store.name = "Store"
            store.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0062_fixed_system_ledgers"),
    ]

    operations = [
        migrations.RunPython(name_default_stores_store, migrations.RunPython.noop),
    ]
