"""Sending mail from the company's own mailbox (core.MailAccount).

`send` is what entry screens use (an email to a supplier, say); the views here
let a person with the right to edit companies set the mailbox up and send
themselves a test mail."""

import smtplib

from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import secrets
from core.models import Company, MailAccount
from tenancy.context import tenant_atomic


class NotSetUp(Exception):
    pass


def account_of(company: Company) -> MailAccount | None:
    return MailAccount.objects.filter(company=company).first()


def send(
    company: Company,
    *,
    to: list[str],
    subject: str,
    text: str,
    html: str = "",
    cc: list[str] | None = None,
    reply_to: list[str] | None = None,
    files: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """Send one mail from the company's mailbox. Raises NotSetUp, or
    ValidationError with words a person can act on when the server refuses."""
    acct = account_of(company)
    if acct is None or not acct.password:
        raise NotSetUp(
            "The company's mail account is not set up. An Owner sets it on the "
            'company screen, under "Mail Account".'
        )
    try:
        password = secrets.unlock(acct.password)
    except secrets.SecretsNotSetUp as exc:
        raise NotSetUp(str(exc)) from exc
    sender = f"{acct.from_name} <{acct.address}>" if acct.from_name else acct.address
    connection = get_connection(
        host=acct.host,
        port=acct.port,
        username=acct.username or acct.address,
        password=password,
        use_tls=acct.port == 587,
        use_ssl=acct.port == 465,
        timeout=20,
    )
    msg = EmailMultiAlternatives(
        subject, text, sender, to, cc=cc or [], reply_to=reply_to or [], connection=connection
    )
    if html:
        msg.attach_alternative(html, "text/html")
    for name, data, kind in files or []:
        msg.attach(name, data, kind)
    try:
        msg.send()
    except smtplib.SMTPAuthenticationError as exc:
        raise ValidationError(
            {
                "detail": "The mail server refused the login. Check the address and the "
                "app password on the company's Mail Account."
            }
        ) from exc
    except (TimeoutError, smtplib.SMTPException, OSError) as exc:
        raise ValidationError({"detail": f"The mail could not be sent: {exc}"}) from exc


# Setting it up ------------------------------------------------------------------


class AccountSerializer(serializers.Serializer):
    from_name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    address = serializers.EmailField()
    host = serializers.CharField(max_length=100)
    port = serializers.IntegerField(min_value=1, max_value=65535)
    username = serializers.CharField(max_length=150, allow_blank=True, required=False)
    # Blank keeps the saved password.
    password = serializers.CharField(
        max_length=200, allow_blank=True, required=False, trim_whitespace=False
    )


def _out(acct: MailAccount | None) -> dict:
    if acct is None:
        return {
            "set_up": False,
            "from_name": "",
            "address": "",
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "",
            "has_password": False,
            "updated_by_name": "",
            "updated_at": None,
            "last_test_ok_at": None,
        }
    return {
        "set_up": bool(acct.password),
        "from_name": acct.from_name,
        "address": acct.address,
        "host": acct.host,
        "port": acct.port,
        "username": acct.username,
        "has_password": bool(acct.password),
        "updated_by_name": acct.updated_by.display_name if acct.updated_by_id else "",
        "updated_at": acct.updated_at,
        "last_test_ok_at": acct.last_test_ok_at,
    }


def _company(request, pk: int, lock: bool = False) -> Company:
    from core.api import EDIT, _check
    from core.api import _company as visible

    _check(request, EDIT)
    return visible(request, pk, lock=lock)


class MailAccountView(APIView):
    """GET the company's mail account (never its password); PUT saves it."""

    def get(self, request, pk: int):
        company = _company(request, pk)
        return Response(_out(account_of(company)))

    @tenant_atomic()
    def put(self, request, pk: int):
        company = _company(request, pk, lock=True)
        s = AccountSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        acct = account_of(company) or MailAccount(company=company)
        password = data.pop("password", "")
        if password.strip():
            try:
                acct.password = secrets.lock(password.replace(" ", ""))
            except secrets.SecretsNotSetUp as exc:
                raise ValidationError({"password": [str(exc)]}) from exc
        elif not acct.password:
            raise ValidationError({"password": ["Give the mailbox's app password."]})
        changed = any(getattr(acct, k, None) != v for k, v in data.items()) or bool(password)
        for key, value in data.items():
            setattr(acct, key, value.strip() if isinstance(value, str) else value)
        if changed:
            acct.last_test_ok_at = None
        acct.updated_by = request.user
        acct.save()
        return Response(_out(acct))


class MailTestView(APIView):
    """POST sends a test mail to the person's own address."""

    def post(self, request, pk: int):
        company = _company(request, pk)
        try:
            send(
                company,
                to=[request.user.email],
                subject=f"MyERP test mail from {company.name}",
                text=(
                    f"This is a test mail sent by MyERP from {company.name}'s mail account.\n"
                    "If you can read it, mail from MyERP will reach suppliers too."
                ),
            )
        except NotSetUp as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        acct = account_of(company)
        acct.last_test_ok_at = timezone.now()
        acct.save(update_fields=["last_test_ok_at"])
        return Response({**_out(acct), "sent_to": request.user.email})
