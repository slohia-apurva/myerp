"""Mail Templates: the group's shared wording for mails to suppliers."""

import pytest

from core.mail_templates import fill
from tests.test_brands import accountant, call, company, viewer  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def test_three_ready_made_defaults(accountant, company):  # noqa: F811
    got = call(accountant, "get", "mail-templates/").json()
    rows = {t["used_for"]: t for t in got["templates"]}
    assert set(rows) == {"purchase_order", "short_excess", "reminder"}
    assert all(t["is_default"] and t["is_active"] for t in rows.values())
    assert rows["reminder"]["subject"] == "Reminder: Pending Supply against PO No : {PO No}"
    uses = {u["value"]: u for u in got["uses"]}
    assert "GRN No" in uses["short_excess"]["fields"]
    assert "GRN No" not in uses["reminder"]["fields"]


def test_add_a_second_reminder_and_make_it_default(accountant, company):  # noqa: F811
    body = {
        "name": "Second Reminder (firm)",
        "used_for": "reminder",
        "subject": "2nd Reminder: PO No : {po no}",
        "opening": "Our order {PO No} is {Days Late} days late.",
        "closing": "Please reply today.",
    }
    made = call(accountant, "post", "mail-templates/", body)
    assert made.status_code == 201, made.json()
    pk = made.json()["id"]
    assert made.json()["is_default"] is False
    call(accountant, "patch", f"mail-templates/{pk}/", {"is_default": True})
    rows = call(accountant, "get", "mail-templates/").json()["templates"]
    defaults = [t["name"] for t in rows if t["used_for"] == "reminder" and t["is_default"]]
    assert defaults == ["Second Reminder (firm)"]

    dup = call(accountant, "post", "mail-templates/", {**body, "name": "second reminder  (FIRM)"})
    assert dup.status_code == 400 and "already a mail template" in str(dup.json())
    off = call(accountant, "patch", f"mail-templates/{pk}/", {"is_active": False}).json()
    assert off["is_active"] is False and off["is_default"] is False


def test_unknown_fields_are_refused(accountant, company):  # noqa: F811
    bad = call(
        accountant,
        "post",
        "mail-templates/",
        {"name": "X", "used_for": "reminder", "subject": "{PO Nmuber}", "opening": "{GRN No}"},
    )
    assert bad.status_code == 400
    errors = bad.json()
    assert "{PO Nmuber}" in str(errors["subject"]) and "{GRN No}" in str(errors["opening"])


def test_viewers_cannot_change_templates(viewer, company):  # noqa: F811
    assert call(viewer, "get", "mail-templates/").status_code == 200
    body = {"name": "X", "used_for": "reminder", "subject": "s", "opening": "o"}
    assert call(viewer, "post", "mail-templates/", body).status_code == 403


def test_fill_puts_values_in_braces():
    text = "PO {PO No} for {our  company}; {Days Late} late"
    assert fill(text, {"PO No": "A/1", "Our Company": "Apurvam"}) == "PO A/1 for Apurvam;  late"
