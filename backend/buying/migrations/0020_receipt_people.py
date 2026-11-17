"""Received By and QC By on a Goods Receipt pick from Masters > People ticked
"Stores" instead of MyERP users (Sidharth, 2026-11-17, preview 88). A receipt
that already names a user keeps that name: the user's person (made, ticked
Stores, if there is none)."""

import django.db.models.deletion
from django.db import migrations, models


def to_people(apps, schema_editor):
    GoodsReceipt = apps.get_model("buying", "GoodsReceipt")
    SalesPerson = apps.get_model("core", "SalesPerson")
    User = apps.get_model("accounts", "User")
    people = {}

    def person_for(user_id):
        if user_id in people:
            return people[user_id]
        user = User.objects.get(pk=user_id)
        person = SalesPerson.objects.filter(user_id=user_id).first()
        if person is None:
            name = (user.full_name or user.email).strip()[:100]
            if SalesPerson.objects.filter(name__iexact=name).exists():
                name = f"{name} ({user.email})"[:100]
            person = SalesPerson.objects.create(
                name=name, email=user.email, user_id=user_id, is_active=user.is_active
            )
        if not person.is_stores:
            person.is_stores = True
            person.save(update_fields=["is_stores"])
        people[user_id] = person.pk
        return person.pk

    for r in GoodsReceipt.objects.exclude(received_by__isnull=True, qc_by__isnull=True):
        r.received_by_person_id = person_for(r.received_by_id) if r.received_by_id else None
        r.qc_by_person_id = person_for(r.qc_by_id) if r.qc_by_id else None
        r.save(update_fields=["received_by_person", "qc_by_person"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_user_phone_signature"),
        ("buying", "0019_po_purchaser"),
        ("core", "0061_sales_person_stores"),
    ]

    operations = [
        migrations.AddField(
            model_name="goodsreceipt",
            name="received_by_person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.salesperson",
            ),
        ),
        migrations.AddField(
            model_name="goodsreceipt",
            name="qc_by_person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.salesperson",
            ),
        ),
        migrations.RunPython(to_people, migrations.RunPython.noop),
        migrations.RemoveField(model_name="goodsreceipt", name="received_by"),
        migrations.RemoveField(model_name="goodsreceipt", name="qc_by"),
        migrations.RenameField("goodsreceipt", "received_by_person", "received_by"),
        migrations.RenameField("goodsreceipt", "qc_by_person", "qc_by"),
    ]
