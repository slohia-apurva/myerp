"""GET /api/v1/audit/: the change log.

- ?company=ID lists changes to that company's masters (needs masters.view
  and access to the company). Add &type=ledger&id=5 for one record.
- With no company it lists changes to group-wide records: users and roles
  (needs users.manage), or with &type=credit_term or &type=unit those masters (needs
  masters.view).
- &before=ENTRY_ID gives the next page.
"""

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from audit.recorder import TYPE_LABELS
from core.companies import visible_companies

PAGE = 50
GROUP_TYPES = ("user", "role")
SHARED_MASTER_TYPES = ("credit_term", "unit", "item", "hsn")  # group-wide masters


def _int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: ["Give a number."]}) from None


class AuditLogView(APIView):
    def get(self, request):
        params = request.query_params
        record_type = params.get("type", "")
        if record_type and record_type not in TYPE_LABELS:
            raise ValidationError({"type": ["Unknown record type."]})
        if "company" in params:
            if not request.user.can("masters.view"):
                raise PermissionDenied("Your role does not allow this.")
            company = visible_companies(request.user).filter(pk=_int(params["company"], "company"))
            if not company.exists():
                raise NotFound("No such company.")
            entries = AuditEntry.objects.filter(company_id=params["company"])
        elif record_type in SHARED_MASTER_TYPES:
            if not request.user.can("masters.view"):
                raise PermissionDenied("Your role does not allow this.")
            entries = AuditEntry.objects.filter(company=None)
        else:
            if not request.user.can("users.manage"):
                raise PermissionDenied("Your role does not allow this.")
            entries = AuditEntry.objects.filter(company=None, record_type__in=GROUP_TYPES)
        if record_type:
            entries = entries.filter(record_type=record_type)
        if "id" in params:
            entries = entries.filter(record_id=_int(params["id"], "id"))
        if "before" in params:
            entries = entries.filter(id__lt=_int(params["before"], "before"))
        page = list(entries.order_by("-id")[: PAGE + 1])
        return Response(
            {
                "entries": [
                    {
                        "id": e.id,
                        "at": e.at,
                        "user_name": e.user_name,
                        "type": e.record_type,
                        "type_label": TYPE_LABELS.get(e.record_type, e.record_type),
                        "record_id": e.record_id,
                        "record_name": e.record_name,
                        "action": e.action,
                        "action_label": e.get_action_display(),
                        "changes": e.changes,
                    }
                    for e in page[:PAGE]
                ],
                "more": len(page) > PAGE,
            }
        )
