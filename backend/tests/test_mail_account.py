"""The company's mail account: set up by an Owner, password locked, test mail."""

import pytest
from django.core import mail as outbox

from core import mail, secrets
from core.models import Company, MailAccount
from tenancy.context import use_tenant
from tests.test_purchase_orders import (  # noqa: F401  (fixtures)
    buyer,
    call,
    owner,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture(autouse=True)
def _secrets_key(settings):
    from cryptography.fernet import Fernet

    settings.MYERP_SECRETS_KEY = Fernet.generate_key().decode()


def test_an_owner_sets_up_the_mailbox_and_sends_a_test(owner, buyer, world, alpha):  # noqa: F811
    url = f"companies/{world['company']}/mail-account/"
    got = call(owner, "get", url).json()
    assert got["set_up"] is False and got["host"] == "smtp.gmail.com" and got["port"] == 587
    assert call(buyer, "get", url).status_code == 403

    body = {"from_name": "Apurvam Purchase", "address": "purchase@x.in", "host": "smtp.gmail.com",
            "port": 587, "username": ""}  # fmt: skip
    res = call(owner, "put", url, body)
    assert res.status_code == 400 and "app password" in str(res.json())
    res = call(owner, "put", url, {**body, "password": "abcd efgh ijkl mnop"})
    assert res.status_code == 200, res.json()
    saved = res.json()
    assert saved["set_up"] and saved["has_password"] and "password" not in saved
    with use_tenant(alpha):
        acct = MailAccount.objects.get()
        assert "abcd" not in acct.password
        assert secrets.unlock(acct.password) == "abcdefghijklmnop"  # spaces dropped
    # Saving again without a password keeps the one saved.
    assert call(owner, "put", url, {**body, "from_name": "Purchase"}).status_code == 200
    with use_tenant(alpha):
        assert secrets.unlock(MailAccount.objects.get().password) == "abcdefghijklmnop"

    sent = call(owner, "post", url + "test/", {})
    assert sent.status_code == 200, sent.json()
    assert sent.json()["last_test_ok_at"] and sent.json()["sent_to"] == "owner@x.in"
    assert len(outbox.outbox) == 1
    m = outbox.outbox[0]
    assert m.to == ["owner@x.in"] and m.from_email == "Purchase <purchase@x.in>"


def test_sending_without_a_mailbox_says_how_to_set_it_up(world, alpha):  # noqa: F811
    with use_tenant(alpha):
        company = Company.objects.get(pk=world["company"])
        with pytest.raises(mail.NotSetUp, match="Mail Account"):
            mail.send(company, to=["a@b.in"], subject="x", text="y")
