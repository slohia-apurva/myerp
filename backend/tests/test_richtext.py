"""Formatted descriptions: only the allowed formatting is kept."""

import pytest

from core import richtext
from tests.test_items import accountant, call, company, make, unit  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def test_formatting_is_kept():
    html = "<p>Fine <b>tea</b> in <i>25 kg</i> bags</p><ul><li>One</li><li><u>Two</u></li></ul>"
    assert richtext.clean(html) == html


def test_font_and_size_only_from_the_lists():
    kept = richtext.clean('<span style="font-family: Georgia, serif; font-size: large">Hi</span>')
    assert kept == '<span style="font-family: georgia; font-size: large">Hi</span>'
    style = "font-family: Evil; background: url(x); color: red"
    assert richtext.clean(f'<span style="{style}">Hi</span>') == "<span>Hi</span>"


def test_scripts_attributes_and_links_are_removed():
    dirty = (
        '<script>alert(1)</script><p onclick="x()">Hello</p>'
        '<a href="javascript:alert(1)">link</a><img src=x onerror=alert(1)>'
        "<style>p{}</style><b>bold"
    )
    cleaned = richtext.clean(dirty)
    assert cleaned == "<p>Hello</p>link<b>bold</b>"


def test_empty_editor_is_empty():
    assert richtext.clean("<div><br></div>") == ""
    assert richtext.clean("   ") == ""


def test_text_to_and_from_plain():
    assert richtext.from_text("a < b\nsecond") == "a &lt; b<br>second"
    assert richtext.to_text("<p>One</p><p>Two &amp; three</p>") == "One\nTwo & three"
    assert richtext.to_text(richtext.from_text("x <y>\nz")) == "x <y>\nz"


def test_item_saves_cleaned_description(accountant, unit):  # noqa: F811
    made = make(
        accountant,
        unit,
        sales_description='<p onclick="x()">Sweet <b>jaggery</b></p><script>bad()</script>',
        purchase_description="<div><br></div>",
    )
    assert made.status_code == 201, made.json()
    item = made.json()
    assert item["sales_description"] == "<p>Sweet <b>jaggery</b></p>"
    assert item["purchase_description"] == ""

    too_long = make(accountant, unit, name="Long", sales_description="<p>" + "x" * 5000 + "</p>")
    assert too_long.status_code == 400
    assert "too long" in too_long.json()["sales_description"][0]
