import datetime
from decimal import Decimal

from django.db import migrations, models

# The Income-tax Act 2025 (in force from 1 April 2026) moves TDS into section
# 393; each old section becomes a serial of its table and gets a payment code
# for the challan and the return. New rows from 1 April 2026 carry both
# numbers, so a bill before that date keeps the old row and its old number.
# 194IA and 194J(ba) are added to both Acts. To be confirmed by a CA.
# code, new Act reference, payment code (company / firm / others), payment
# code (individual / HUF, blank = the same), name, company/firm %,
# individual/HUF %, no PAN %, one bill over, year over, above the limit only, goods
SECTIONS = [
    ("194C", "393(1) Sl. 6(i)", "1024", "1023",
     "Contractors (work, AMC, repairs, courier, transport, printing, manpower supply)",
     "2", "1", "20", "30000", "100000", False, False),
    ("194H", "393(1) Sl. 1(ii)", "1006", "", "Commission or brokerage",
     "2", "2", "20", None, "20000", False, False),
    ("194I(a)", "393(1) Sl. 2(ii)", "1008", "", "Rent: plant, machinery, equipment",
     "2", "2", "20", "50000", None, False, False),
    ("194I(b)", "393(1) Sl. 2(ii)", "1009", "", "Rent: land, building, furniture, fittings",
     "10", "10", "20", "50000", None, False, False),
    ("194IA", "393(1) Sl. 3(i)", "Form 141", "",
     "Purchase of land or building (not agricultural land)",
     "1", "1", "20", "5000000", None, False, False),
    ("194J(a)", "393(1) Sl. 6(iii)", "1026", "", "Technical services, call centre, film royalty",
     "2", "2", "20", None, "50000", False, False),
    ("194J(b)", "393(1) Sl. 6(iii)", "1027", "",
     "Professional fees (CA, lawyer, consultant), royalty, non-compete",
     "10", "10", "20", None, "50000", False, False),
    ("194J(ba)", "393(1) Sl. 6(iii)", "1028", "", "Director's fees or commission (not salary)",
     "10", "10", "20", None, None, False, False),
    ("194Q", "393(1) Sl. 8(ii)", "1031", "", "Purchase of goods",
     "0.1", "0.1", "5", None, "5000000", True, True),
]  # fmt: skip

OLD = datetime.date(2025, 4, 1)
NEW = datetime.date(2026, 4, 1)


def seed(apps, schema_editor):
    TdsSection = apps.get_model("tenancy", "TdsSection")
    for row in SECTIONS:
        code, new_code, pay, pay_ind, name, other, ind, no_pan, bill, year, above, goods = row
        values = {
            "name": name,
            "rate_other": Decimal(other),
            "rate_individual": Decimal(ind),
            "rate_no_pan": Decimal(no_pan),
            "bill_limit": Decimal(bill) if bill else None,
            "year_limit": Decimal(year) if year else None,
            "above_limit_only": above,
            "for_goods": goods,
        }
        # The old Act's row, for bills before 1 April 2026 (added where missing).
        TdsSection.objects.get_or_create(code=code, valid_from=OLD, defaults=values)
        TdsSection.objects.get_or_create(
            code=code,
            valid_from=NEW,
            defaults={
                **values,
                "new_code": new_code,
                "payment_code": pay,
                "payment_code_individual": pay_ind,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0011_tds_sections"),
    ]

    operations = [
        migrations.AddField(
            model_name="tdssection",
            name="payment_code",
            field=models.CharField(blank=True, max_length=12),
        ),
        migrations.AddField(
            model_name="tdssection",
            name="payment_code_individual",
            field=models.CharField(blank=True, max_length=12),
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
