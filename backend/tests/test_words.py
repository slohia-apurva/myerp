"""Amounts in words on printed documents (core/words.py)."""

from core import words


def test_rupees_read_in_lakh_and_crore():
    assert words.amount("206138") == "Rupees Two Lakh Six Thousand One Hundred Thirty-Eight only"
    assert words.amount("12500000.50") == "Rupees One Crore Twenty-Five Lakh and Fifty Paise only"
    assert words.amount("0") == "Rupees Zero only"


def test_other_currencies_read_in_thousand_and_million():
    assert (
        words.amount("16195", "USD", "US Dollar")
        == "US Dollars Sixteen Thousand One Hundred Ninety-Five only"
    )
    assert words.amount("1250000.25", "EUR", "Euro") == (
        "Euros One Million Two Hundred Fifty Thousand and Cents Twenty-Five only"
    )
