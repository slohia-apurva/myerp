"""Role names ignore capitals and extra spaces (core/duplicates.py)."""

import django.db.models.functions.text
from django.db import migrations, models


def tidy_role_names(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    seen = {}
    for role in Role.objects.order_by("pk"):
        tidied = " ".join(role.name.split())
        key = tidied.lower()
        if key in seen:
            raise RuntimeError(
                f'Two roles are both called "{tidied}" (ids {seen[key]} and {role.pk}); '
                "rename one, then deploy again."
            )
        seen[key] = role.pk
        if tidied != role.name:
            role.name = tidied
            role.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_standard_roles"),
    ]

    operations = [
        migrations.RunPython(tidy_role_names, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="role",
            name="name",
            field=models.CharField(max_length=100),
        ),
        migrations.AddConstraint(
            model_name="role",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"), name="role_name_unique"
            ),
        ),
    ]
