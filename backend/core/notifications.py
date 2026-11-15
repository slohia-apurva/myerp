"""Notifications: short messages for a person, shown under the bell in the
top menu. Documents call `notify` (inside their own transaction, so a refused
document sends nothing)."""

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from core.api import Signed
from core.models import Company, Notification
from tenancy.context import tenant_atomic


def people_with_roles(company: Company, *codes: str):
    """Active people holding any of these roles who may work in the company
    (Owners always may)."""
    users = User.objects.filter(is_active=True, roles__code__in=codes).distinct()
    return [
        u
        for u in users.prefetch_related("companies")
        if u.is_owner or not u.companies.exists() or u.companies.filter(pk=company.pk).exists()
    ]


def notify(users, company: Company | None, title: str, body: str = "", link: str = "") -> None:
    Notification.objects.bulk_create(
        [
            Notification(user=u, company=company, title=title[:150], body=body, link=link[:200])
            for u in {u.pk: u for u in users}.values()
        ]
    )


def _out(n: Notification) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "company": n.company_id,
        "created_at": n.created_at,
        "read": n.read_at is not None,
    }


class NotificationListView(APIView):
    """GET: my latest notifications and how many are unread."""

    permission_classes = [Signed]

    def get(self, request):
        rows = Notification.objects.filter(user=request.user)
        unread = rows.filter(read_at__isnull=True).count()
        return Response({"unread": unread, "rows": [_out(n) for n in rows[:30]]})


class NotificationReadView(APIView):
    """POST {"ids": [...]} marks those read; with no ids, all of mine."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request):
        ids = request.data.get("ids") if isinstance(request.data, dict) else None
        rows = Notification.objects.filter(user=request.user, read_at__isnull=True)
        if ids:
            rows = rows.filter(Q(pk__in=[i for i in ids if isinstance(i, int)]))
        rows.update(read_at=timezone.now())
        return Response({"ok": True})
