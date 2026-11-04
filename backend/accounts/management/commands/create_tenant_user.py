from django.core.management.base import BaseCommand, CommandError

from accounts.links import password_setup_path
from accounts.models import User
from tenancy.context import use_tenant
from tenancy.models import Tenant


class Command(BaseCommand):
    help = (
        "Create a user in a tenant (or, with --reset, reset an existing user's password "
        "and two-factor) and print a one-time link, valid 24 hours, to set the password. "
        "The user sets up the authenticator app at first login."
    )

    def add_arguments(self, parser):
        parser.add_argument("tenant", help="Tenant slug, e.g. apurvam")
        parser.add_argument("username")
        parser.add_argument("--email", default="")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")
        parser.add_argument(
            "--reset", action="store_true", help="Reset an existing user's password and 2FA"
        )

    def handle(self, *args, tenant, username, reset, **options):
        item = Tenant.objects.filter(slug=tenant, status=Tenant.Status.ACTIVE).first()
        if item is None:
            raise CommandError(f"No active tenant {tenant!r}")

        with use_tenant(item):
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User(
                    username=username,
                    email=options["email"],
                    first_name=options["first_name"],
                    last_name=options["last_name"],
                )
                user.full_clean(exclude=["password"])
                action = "Created"
            elif reset:
                user.reset_two_factor()
                user.failed_logins = 0
                user.locked_until = None
                action = "Reset"
            else:
                raise CommandError(f"User {username!r} exists; pass --reset to reset them.")
            user.set_unusable_password()
            user.save()
            path = password_setup_path(user)

        self.stdout.write(f"{action} {username} in {tenant}.")
        self.stdout.write(f"Password link (valid 24 hours, works once): <app address>{path}")
