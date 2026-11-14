"""Item descriptions are plain text (Sidharth, 2026-11-15)."""

import importlib

import pytest

from tests.test_items import accountant, call, company, make, unit  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def test_the_description_is_kept_as_typed_lines(accountant, unit):  # noqa: F811
    made = make(accountant, unit, purchase_description="  Assam CTC <BOP>  \n50 kg sacks \n\n")
    assert made.status_code == 201, made.json()
    assert made.json()["purchase_description"] == "Assam CTC <BOP>\n50 kg sacks"
    too_long = make(accountant, unit, name="Long", sales_description="x" * 5001)
    assert too_long.status_code == 400
    assert "too long" in too_long.json()["sales_description"][0]


def test_old_formatted_descriptions_become_plain_lines():
    plain = importlib.import_module("core.migrations.0047_item_plain_descriptions")._to_text
    html = "<p>Fine <b>tea</b> &amp; more</p><ul><li>One</li><li>Two</li></ul>a<br>b"
    assert plain(html) == "Fine tea & more\nOne\nTwo\na\nb"
