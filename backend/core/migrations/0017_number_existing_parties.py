from django.db import migrations

# Frozen copy of core.numbering.DEFAULTS and the bill-wise group codes.
KINDS = {"sundry_debtors": ("customer", "customer_number", "CUST-"),
         "sundry_creditors": ("vendor", "vendor_number", "VEND-")}


def kind_of(group):
    while group is not None:
        if group.code in KINDS:
            return KINDS[group.code]
        group = group.parent
    return None


def number_parties(apps, schema_editor):
    Party = apps.get_model("core", "Party")
    Ledger = apps.get_model("core", "Ledger")
    NumberSeries = apps.get_model("core", "NumberSeries")
    last = {}
    for party in Party.objects.order_by("pk"):
        kinds = {
            kind_of(l.group)
            for l in Ledger.objects.filter(party=party).select_related("group")
        } - {None}
        for key, field, prefix in sorted(kinds):
            n = last.get(key, 0) + 1
            last[key] = n
            setattr(party, field, f"{prefix}{n:05d}")
        party.save()
    for key, n in last.items():
        prefix = "CUST-" if key == "customer" else "VEND-"
        NumberSeries.objects.update_or_create(key=key, defaults={"prefix": prefix, "width": 5, "last": n})


class Migration(migrations.Migration):
    dependencies = [("core", "0016_party_numbers")]
    operations = [migrations.RunPython(number_parties, migrations.RunPython.noop)]
