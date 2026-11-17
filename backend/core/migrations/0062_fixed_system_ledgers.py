from django.db import migrations

# The six fixed system ledgers every company has (Sidharth, 2026-11-17), as in
# posting/accounts.py on the day: code, name, standard group code. Copied here
# so this migration does not change if that list does.
FIXED = [
    ("grni", "Goods Received but Bills not Received", "other_current_liabilities"),
    (
        "bills_received_goods_not_received",
        "Bills Received but Goods not Received",
        "other_current_assets",
    ),
    ("goods_delivered_not_billed", "Goods Delivered but Bills not Made", "other_current_assets"),
    ("billed_not_delivered", "Bills Made but Goods not Delivered", "other_current_liabilities"),
    ("work_in_progress", "Work in Progress", "stock_in_hand"),
    ("stock_with_job_workers", "Stock with Job Workers", "stock_in_hand"),
]


def add_fixed_ledgers(apps, schema_editor):
    """Give every existing company the fixed ledgers it lacks. A ledger someone
    already made with the same name is taken over, as the posting code does."""
    Company = apps.get_model("core", "Company")
    Ledger = apps.get_model("core", "Ledger")
    LedgerGroup = apps.get_model("core", "LedgerGroup")
    for company in Company.objects.all():
        for code, name, group_code in FIXED:
            if Ledger.objects.filter(company=company, system_code=code).exists():
                continue
            ledger = Ledger.objects.filter(
                company=company, name__iexact=name, system_code=""
            ).first()
            if ledger is None:
                group = LedgerGroup.objects.filter(company=company, code=group_code).first()
                if group is None:
                    continue
                ledger = Ledger(company=company, group=group, name=name)
            ledger.system_code = code
            ledger.is_active = True
            ledger.save()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0061_sales_person_stores"),
    ]

    operations = [
        migrations.RunPython(add_fixed_ledgers, migrations.RunPython.noop),
    ]
