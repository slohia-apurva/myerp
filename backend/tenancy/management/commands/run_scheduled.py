import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from tenancy.context import tenant_atomic, use_tenant
from tenancy.models import Tenant

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Scheduled work, run every hour by Cloud Scheduler (deploy/terraform, job "
        "myerp-scheduled). Each piece checks for itself whether it is due, so a "
        "missed or repeated hour does no harm. Now: the daily Stock Check of each "
        "company that has it on (buying/planning.py), and the automatic reminders "
        "to suppliers (buying/auto_reminders.py)."
    )

    def handle(self, *args, **options):
        from buying import auto_reminders, planning
        from buying.models import ReminderSchedule
        from core.models import Company

        now = timezone.now()
        failed = 0
        for tenant in Tenant.objects.filter(status=Tenant.Status.ACTIVE).order_by("id"):
            with use_tenant(tenant):
                for company in Company.objects.filter(daily_stock_check=True).order_by("id"):
                    if not planning.due(company, now):
                        continue
                    try:
                        with tenant_atomic():
                            runs = planning.daily_run(company, now)
                    except Exception:
                        failed += 1
                        log.exception("Daily Stock Check failed: %s / %s", tenant.slug, company)
                        continue
                    made = sum(r.order_count for r in runs)
                    self.stdout.write(
                        f"{tenant.slug} / {company.name}: {len(runs)} branch(es), {made} draft(s)"
                    )
                if auto_reminders.due(ReminderSchedule.current(), now):
                    try:
                        sent, missed = auto_reminders.run(now)
                    except Exception:
                        failed += 1
                        log.exception("Automatic reminders failed: %s", tenant.slug)
                        continue
                    self.stdout.write(f"{tenant.slug}: {sent} reminder(s) sent, {missed} not sent")
        if failed:
            # Logged at ERROR, so the error alerts see it; other companies still ran.
            self.stderr.write(f"{failed} scheduled run(s) failed.")
