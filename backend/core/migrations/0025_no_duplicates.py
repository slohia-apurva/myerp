"""No duplicate masters (core/duplicates.py).

First tidies the spacing of names already saved ("Acme  Foods " becomes
"Acme Foods"), leaving a name as it is if tidying would make it clash with
another. Then it checks the data for what the new constraints refuse
(two companies with the same name, GSTIN or PAN; two parties with the same
GSTIN; two bank ledgers of a company with the same account number) and, if
any is found, stops with a list of them to fix, rather than a database
error.
"""

import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower

# model -> (name fields, the field that scopes uniqueness or None)
TIDY = {
    "Company": (("name",), None),
    "Branch": (("name",), "company_id"),
    "LedgerGroup": (("name",), "company_id"),
    "Ledger": (("name",), "company_id"),
    "Party": (("name",), None),
    "CreditTerm": (("name",), None),
    "Unit": (("name", "short_name"), None),
    "Item": (("name",), None),
    "Certificate": (("name",), "company_id"),
}


def tidy_names(apps, schema_editor):
    for model_name, (fields, scope) in TIDY.items():
        model = apps.get_model("core", model_name)
        for row in model.objects.all():
            changed = []
            for field in fields:
                value = getattr(row, field)
                tidied = " ".join(value.split())
                if tidied == value:
                    continue
                others = model.objects.exclude(pk=row.pk)
                if scope:
                    others = others.filter(**{scope: getattr(row, scope)})
                if model_name != "Certificate" and others.filter(
                    **{f"{field}__iexact": tidied}
                ).exists():
                    continue  # tidying would clash; leave it for a person to sort out
                setattr(row, field, tidied)
                changed.append(field)
            if changed:
                row.save(update_fields=changed)


def _repeats(qs, *keys, what):
    rows = qs.values(*keys).annotate(n=Count("pk")).filter(n__gt=1)
    return [f"{what}: {', '.join(str(r[k]) for k in keys)}" for r in rows]


def check_duplicates(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    Ledger = apps.get_model("core", "Ledger")
    Party = apps.get_model("core", "Party")
    found = [
        *_repeats(
            Company.objects.annotate(lname=Lower("name")), "lname", what="Company name"
        ),
        *_repeats(Company.objects.exclude(gstin=""), "gstin", what="Company GSTIN"),
        *_repeats(Company.objects.exclude(pan=""), "pan", what="Company PAN"),
        *_repeats(Party.objects.exclude(gstin=""), "gstin", what="Customer/supplier GSTIN"),
        *_repeats(
            Ledger.objects.exclude(account_number="").annotate(
                acct=Lower("account_number")
            ),
            "company_id",
            "acct",
            what="Bank account number (company id, number)",
        ),
    ]
    if found:
        raise RuntimeError(
            "These records are duplicates; change or merge them, then deploy again:\n"
            + "\n".join(found)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_merge_city_item_tabs"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(tidy_names, migrations.RunPython.noop),
        migrations.RunPython(check_duplicates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="company",
            name="name",
            field=models.CharField(max_length=200),
        ),
        migrations.AddConstraint(
            model_name="company",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                name="company_name_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="company",
            constraint=models.UniqueConstraint(
                models.F("gstin"),
                condition=models.Q(("gstin", ""), _negated=True),
                name="company_gstin_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="company",
            constraint=models.UniqueConstraint(
                models.F("pan"),
                condition=models.Q(("pan", ""), _negated=True),
                name="company_pan_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledger",
            constraint=models.UniqueConstraint(
                models.F("company"),
                django.db.models.functions.text.Lower("account_number"),
                condition=models.Q(("account_number", ""), _negated=True),
                name="bank_account_unique_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="party",
            constraint=models.UniqueConstraint(
                models.F("gstin"),
                condition=models.Q(("gstin", ""), _negated=True),
                name="party_gstin_unique",
            ),
        ),
    ]
