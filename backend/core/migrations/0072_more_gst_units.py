"""Add a unit for every other GST unit code (Sidharth, 2026-11-23), so items
brought across from ERPNext find their units. A unit the group already has
by that name or short name is left alone."""

from django.db import migrations

# Frozen copy of the list added to core.units.STANDARD_UNITS that day.
MORE_UNITS = [
    ("Bale", "bal", True, "BAL"),
    ("Box", "box", True, "BOX"),
    ("Buckle", "bkl", True, "BKL"),
    ("Bundle", "bdl", True, "BDL"),
    ("Bunch", "bun", True, "BUN"),
    ("Billion Units", "bou", False, "BOU"),
    ("Can", "can", True, "CAN"),
    ("Centimetre", "cm", False, "CMS"),
    ("Cubic Centimetre", "ccm", False, "CCM"),
    ("Cubic Metre", "cbm", False, "CBM"),
    ("Dozen", "doz", True, "DOZ"),
    ("Drum", "drm", True, "DRM"),
    ("Great Gross", "ggr", True, "GGR"),
    ("Gross", "grs", True, "GRS"),
    ("Gross Yard", "gyd", False, "GYD"),
    ("Kilolitre", "klr", False, "KLR"),
    ("Kilometre", "km", False, "KME"),
    ("Metric Ton", "mts", False, "MTS"),
    ("Pair", "prs", True, "PRS"),
    ("Pieces", "pcs", True, "PCS"),
    ("Quintal", "qtl", False, "QTL"),
    ("Roll", "rol", True, "ROL"),
    ("Set", "set", True, "SET"),
    ("Square Foot", "sqft", False, "SQF"),
    ("Square Metre", "sqm", False, "SQM"),
    ("Square Yard", "sqyd", False, "SQY"),
    ("Tablet", "tbs", True, "TBS"),
    ("Ten Gross", "tgm", True, "TGM"),
    ("Thousand", "thd", True, "THD"),
    ("Tube", "tub", True, "TUB"),
    ("Unit", "unt", True, "UNT"),
    ("US Gallon", "gal", False, "UGS"),
    ("Yard", "yd", False, "YDS"),
]


def add_units(apps, schema_editor):
    Unit = apps.get_model("core", "Unit")
    have = {n.lower() for n in Unit.objects.values_list("name", flat=True)}
    have_short = {n.lower() for n in Unit.objects.values_list("short_name", flat=True)}
    for name, short, whole, code in MORE_UNITS:
        if name.lower() in have or short.lower() in have_short:
            continue
        Unit.objects.create(name=name, short_name=short, whole_numbers=whole, gst_code=code)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0071_item_customer"),
    ]

    operations = [
        migrations.RunPython(add_units, migrations.RunPython.noop),
    ]
