from celery import shared_task

from core.models import Company
from tenancy.tasks import tenant_task


@shared_task
@tenant_task
def count_companies() -> int:
    """Example tenant job: call as count_companies.delay("apurvam")."""
    return Company.objects.count()
