from django.db import migrations, models


def fill_carrier(apps, schema_editor):
    """Point each courier-name row at the Carrier of that name, adding the
    carrier when the list lacks it."""
    Carrier = apps.get_model("tenancy", "Carrier")
    CourierPin = apps.get_model("tenancy", "CourierPin")
    for name in CourierPin.objects.values_list("courier", flat=True).distinct():
        carrier = Carrier.objects.filter(name__iexact=name).first() or Carrier.objects.create(
            name=name
        )
        CourierPin.objects.filter(courier=name).update(carrier=carrier)


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0004_carriers"),
    ]

    operations = [
        migrations.AddField(
            model_name="courierpin",
            name="carrier",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="pins",
                to="tenancy.carrier",
            ),
        ),
        migrations.RunPython(fill_carrier, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="courierpin", name="one_row_per_courier_pin"),
        migrations.RemoveField(model_name="courierpin", name="courier"),
        migrations.AlterField(
            model_name="courierpin",
            name="carrier",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name="pins",
                to="tenancy.carrier",
            ),
        ),
        migrations.AlterModelOptions(
            name="courierpin", options={"ordering": ["carrier__name", "pin_id"]}
        ),
        migrations.AddConstraint(
            model_name="courierpin",
            constraint=models.UniqueConstraint(
                fields=("carrier", "pin"), name="one_row_per_courier_pin"
            ),
        ),
    ]
