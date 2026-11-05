from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from tenancy.context import use_tenant
from tenancy.models import Tenant


class Command(BaseCommand):
    help = (
        "Give a person access to a tenant by email address. They then sign in with the "
        "Google account for that address. --deactivate removes access; running it again "
        "without --deactivate restores it."
    )

    def add_arguments(self, parser):
        parser.add_argument("tenant", help="Tenant slug, e.g. apurvam")
        parser.add_argument("email")
        parser.add_argument("--name", default="", help="Full name (optional)")
        parser.add_argument("--deactivate", action="store_true")

    def handle(self, *args, tenant, email, name, deactivate, **options):
        item = Tenant.objects.filter(slug=tenant, status=Tenant.Status.ACTIVE).first()
        if item is None:
            raise CommandError(f"No active tenant {tenant!r}")
        email = email.strip().lower()

        with use_tenant(item):
            user = User.objects.filter(email=email).first()
            if user is None:
                if deactivate:
                    raise CommandError(f"No user {email} in {tenant}")
                User.objects.create_user(email=email, full_name=name)
                self.stdout.write(f"Added {email} to {tenant}. They can sign in with Google now.")
                return
            user.is_active = not deactivate
            if name:
                user.full_name = name
            user.save()
        state = "deactivated" if deactivate else "active"
        self.stdout.write(f"{email} in {tenant} is now {state}.")
