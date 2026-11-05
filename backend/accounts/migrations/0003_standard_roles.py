from django.db import migrations

from accounts.roles import OWNER, create_missing_standard_roles


def seed(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    User = apps.get_model("accounts", "User")
    create_missing_standard_roles(Role)
    # People added before roles existed were the tenant's admins (on Apurvam,
    # only Sidharth). Make them Owners so someone can manage the others.
    owner = Role.objects.get(code=OWNER)
    for user in User.objects.filter(is_active=True):
        if not user.roles.exists():
            user.roles.add(owner)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_roles")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
