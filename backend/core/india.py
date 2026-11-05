"""Indian reference data and checks: GST state codes, GSTIN and PAN.

State codes change only when states are reorganised (the last was Ladakh,
38, in 2019), so they live here rather than as dated master data.
"""

import re

from django.core.exceptions import ValidationError

STATES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
}

STATE_CHOICES = sorted(STATES.items(), key=lambda item: item[1])

PAN_RE = re.compile(r"^[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    """The 15th character of a GSTIN, from GSTN's mod-36 checksum."""
    total = 0
    for i, char in enumerate(first14):
        product = _CHARS.index(char) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _CHARS[(36 - total % 36) % 36]


def validate_pan(value: str) -> None:
    if not PAN_RE.match(value):
        raise ValidationError("A PAN is 10 characters like ABCPE1234F.")


def validate_gstin(value: str) -> None:
    if not GSTIN_RE.match(value):
        raise ValidationError("A GSTIN is 15 characters like 27ABCPE1234F1ZB.")
    if value[:2] not in STATES:
        raise ValidationError(f"{value[:2]} is not a GST state code.")
    if gstin_check_char(value[:14]) != value[14]:
        raise ValidationError("This GSTIN's last character does not match; check for a typo.")


def validate_state_code(value: str) -> None:
    if value not in STATES:
        raise ValidationError(f"{value} is not a GST state code.")


PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{5,18}[0-9]$")


def validate_phone(value: str) -> None:
    """Indian or international numbers: digits, spaces and dashes, optional +."""
    if not PHONE_RE.match(value):
        raise ValidationError("Enter a phone number like +91 98200 12345 or 022-2345 6789.")
