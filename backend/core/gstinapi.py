"""GSTIN lookup through gstinapi.in (see core.gstin_lookup).

Set the key in the GSTINAPI_KEY environment variable (a secret, read on the
server only, never sent to the browser). One credit is charged per successful
lookup; 60 requests a minute are allowed per key.
"""

import logging
import os
import time

import requests

from core.gstin_lookup import LookupFailed, NotSetUp

log = logging.getLogger(__name__)

URL = "https://www.gstinapi.in/v1/gstin/{gstin}"
TIMEOUT = 15  # seconds
ATTEMPTS = 3  # only for 429 and 502
BACKOFF = 1.0  # seconds, doubled after each try

# What each failure means to the person at the screen.
MESSAGES = {
    401: "The GST lookup key is missing or wrong. Ask your MyERP admin to check it.",
    402: "The GST lookup has run out of credits. Ask your MyERP admin to top it up.",
    403: "The GST lookup account is deactivated. Ask your MyERP admin.",
    404: "This GSTIN is not registered in the GST database. Check it for a typo.",
    429: "Too many lookups just now. Wait a minute and try again.",
    502: "The GST system is not answering. Try again in a little while.",
}
STATUS_FOR_USER = {401: 503, 402: 503, 403: 503, 404: 404, 429: 429, 502: 502}

TYPES = (("composition", "composition"), ("sez", "sez"), ("regular", "regular"))


def _gst_type(taxpayer_type: str) -> str:
    text = (taxpayer_type or "").lower()
    return next((ours for word, ours in TYPES if word in text), "regular")


def _address(data: dict) -> str:
    """The registered address as one block, built from its parts (blank parts
    left out, a part already inside the text not repeated)."""
    parts = data.get("address_details") or {}
    order = (
        "building_number",
        "building_name",
        "floor",
        "street",
        "locality",
        "landmark",
        "district",
        "city",
    )
    text = ""
    for key in order:
        part = (parts.get(key) or "").strip()
        if part and part.lower() not in text.lower():
            text = f"{text}, {part}" if text else part
    return text or (data.get("address") or "").strip()


def _get(gstin: str, key: str) -> requests.Response:
    delay = BACKOFF
    for attempt in range(1, ATTEMPTS + 1):
        try:
            reply = requests.get(
                URL.format(gstin=gstin),
                params={"include": "profile"},
                headers={"x-api-key": key},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            reply = None
        # Only a rate limit or a provider hiccup is worth another try.
        if reply is not None and reply.status_code not in (429, 502):
            return reply
        if attempt < ATTEMPTS:
            time.sleep(delay)
            delay *= 2
    if reply is None:
        raise LookupFailed(MESSAGES[502], 502)
    return reply


def lookup(gstin: str) -> dict:
    key = os.environ.get("GSTINAPI_KEY", "").strip()
    if not key:
        raise NotSetUp()
    reply = _get(gstin, key)
    if reply.status_code != 200:
        message = MESSAGES.get(reply.status_code)
        if message is None:
            log.warning("gstinapi answered %s", reply.status_code)
            message = "The GST lookup failed. Enter the details by hand."
        raise LookupFailed(message, STATUS_FOR_USER.get(reply.status_code, 502))
    body = reply.json()
    log.info("gstinapi credits_remaining=%s", body.get("credits_remaining"))
    data = body.get("data") or {}
    return {
        "legal_name": data.get("legal_name") or "",
        "trade_name": data.get("trade_name") or "",
        "status": data.get("status") or "",
        "gst_type": _gst_type(data.get("taxpayer_type")),
        "address": _address(data),
        "pincode": data.get("pincode") or "",
    }
