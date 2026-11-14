"""An amount in words, as printed on documents: Indian style (lakh, crore) for
rupees, thousand and million for other currencies."""

from decimal import ROUND_HALF_UP, Decimal

ONES = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen "
    "Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def _below_thousand(n: int) -> list[str]:
    out = []
    if n >= 100:
        out += [ONES[n // 100], "Hundred"]
        n %= 100
    if n >= 20:
        out.append(TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else ""))
    elif n:
        out.append(ONES[n])
    return out


def _indian(n: int) -> list[str]:
    out = []
    for size, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand")):
        if n >= size:
            # Above 99 crore the crores themselves are read the Indian way.
            out += (_indian(n // size) if size == 10**7 else _below_thousand(n // size)) + [name]
            n %= size
    return out + _below_thousand(n)


def _western(n: int) -> list[str]:
    out = []
    for size, name in ((10**9, "Billion"), (10**6, "Million"), (1000, "Thousand")):
        if n >= size:
            out += _below_thousand(n // size) + [name]
            n %= size
    return out + _below_thousand(n)


def number(n: int, indian: bool = True) -> str:
    return " ".join((_indian if indian else _western)(n)) or "Zero"


def amount(value, currency: str = "INR", currency_name: str = "") -> str:
    """'Rupees Two Lakh Six Thousand One Hundred Thirty-Eight only', or
    'US Dollars Sixteen Thousand One Hundred Ninety-Five and Cents Fifty only'."""
    value = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, cents = int(value), int((value - int(value)) * 100)
    if currency == "INR":
        text = f"Rupees {number(whole)}"
        if cents:
            text += f" and {number(cents)} Paise"
        return text + " only"
    name = (currency_name or currency).strip()
    if name and not name.endswith("s") and name.upper() != name:
        name += "s"
    text = f"{name} {number(whole, indian=False)}"
    if cents:
        text += f" and Cents {number(cents, indian=False)}"
    return text + " only"
