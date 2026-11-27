"""Masters › Reminder Schedule, and the Reminders box on a purchase order
(see buying/auto_reminders.py)."""

from __future__ import annotations

from datetime import date

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from buying import auto_reminders
from buying.api import SUBMIT, _order
from buying.api import _check as _buying_check
from buying.models import ReminderSchedule, ReminderStep
from core.api import EDIT, VIEW, Signed, _check
from core.models import MailTemplate
from tenancy.context import tenant_atomic


def _dmy(d) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def _template(pk) -> MailTemplate | None:
    if pk in (None, ""):
        return None
    t = MailTemplate.objects.filter(pk=pk, used_for=MailTemplate.REMINDER).first()
    if t is None:
        raise ValidationError({"template": ["Pick a reminder mail template."]})
    return t


def _out(s: ReminderSchedule) -> dict:
    steps = list(s.steps.select_related("template"))
    example = date(2026, 12, 15)
    return {
        "is_on": s.is_on,
        "send_hour": s.send_hour,
        "skip_sundays": s.skip_sundays,
        "copy_purchaser": s.copy_purchaser,
        "copy_submitter": s.copy_submitter,
        "repeat_days": s.repeat_days,
        "repeat_max": s.repeat_max,
        "repeat_template": s.repeat_template_id,
        "steps": [
            {"days": st.days, "before": st.before, "template": st.template_id} for st in steps
        ],
        "templates": [
            {"id": t.id, "name": t.name, "is_default": t.is_default, "is_active": t.is_active}
            for t in MailTemplate.objects.filter(used_for=MailTemplate.REMINDER).order_by(
                "-is_default", "name"
            )
        ],
        "example": {
            "expected": _dmy(example),
            "dates": [
                {"on": _dmy(x["on"]), "label": x["label"]}
                for x in auto_reminders.plan(example, s, steps)
            ],
        },
        "id": s.pk,
    }


class _Step(serializers.Serializer):
    days = serializers.IntegerField(min_value=0, max_value=365)
    before = serializers.BooleanField()
    template = serializers.IntegerField(allow_null=True, required=False)


class _Schedule(serializers.Serializer):
    is_on = serializers.BooleanField()
    send_hour = serializers.IntegerField(min_value=0, max_value=23)
    skip_sundays = serializers.BooleanField()
    copy_purchaser = serializers.BooleanField()
    copy_submitter = serializers.BooleanField()
    repeat_days = serializers.IntegerField(min_value=0, max_value=365)
    repeat_max = serializers.IntegerField(min_value=0, max_value=52)
    repeat_template = serializers.IntegerField(allow_null=True, required=False)
    steps = _Step(many=True)


class ScheduleView(APIView):
    """GET: the group's reminder schedule. PUT: change it (masters.edit)."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response(_out(ReminderSchedule.current()))

    @tenant_atomic()
    def put(self, request):
        _check(request, EDIT)
        ser = _Schedule(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if not d["steps"]:
            raise ValidationError({"steps": ["Give at least one step."]})
        s = ReminderSchedule.objects.select_for_update().get(pk=ReminderSchedule.current().pk)
        for f in ("is_on", "send_hour", "skip_sundays", "copy_purchaser", "copy_submitter",
                  "repeat_days", "repeat_max"):  # fmt: skip
            setattr(s, f, d[f])
        s.repeat_template = _template(d.get("repeat_template"))
        s.save()
        s.steps.all().delete()
        for n, st in enumerate(d["steps"], 1):
            ReminderStep.objects.create(
                schedule=s, position=n, days=st["days"], before=st["before"],
                template=_template(st.get("template")),
            )  # fmt: skip
        recorder.touch(s)
        return Response(_out(s))


class OrderRemindersView(APIView):
    """GET: the order's reminders, the next automatic one and whether it is
    left out. PATCH {no_auto_reminders}: leave it out or put it back."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _buying_check(request, SUBMIT)
        o = _order(request, pk)
        return Response(_order_out(o))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _buying_check(request, SUBMIT)
        o = _order(request, pk, lock=True)
        value = request.data.get("no_auto_reminders")
        if not isinstance(value, bool):
            raise ValidationError({"no_auto_reminders": ["Give true or false."]})
        o.no_auto_reminders = value
        o.save(update_fields=["no_auto_reminders"])
        return Response(_order_out(o))


def _order_out(o) -> dict:
    schedule = ReminderSchedule.current()
    nxt = auto_reminders.next_for(o, schedule)
    when = ""
    if nxt is not None:
        when = f"{_dmy(max(nxt['on'], timezone.localdate()))} from {schedule.send_hour}:00"
    return {
        "rows": [
            {
                "sent_at": timezone.localtime(r.sent_at).strftime("%d-%m-%Y %I:%M %p").lower(),
                "how": "Automatic" if r.automatic else f"By {r.by.display_name if r.by else '—'}",
                "template": r.template_name,
                "to": ", ".join(r.sent_to),
                "lines": r.line_count,
                "failed": r.failed,
            }
            for r in o.reminders.select_related("by")
        ],
        "schedule_on": schedule.is_on,
        "no_auto_reminders": o.no_auto_reminders,
        "supplier_left_out": o.supplier.no_auto_reminders,
        "next": {"label": nxt["label"], "when": when} if nxt else None,
    }
