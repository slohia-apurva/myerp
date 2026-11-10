"""The gstinapi.in provider: statuses, retries, address and type mapping."""

import logging

import pytest
import requests

from core import gstinapi
from core.gstin_lookup import LookupFailed, NotSetUp

NUMBER = "27AAPFU0939F1ZV"


class Reply:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("GSTINAPI_KEY", "test-key")


@pytest.fixture
def calls(monkeypatch):
    """Queue replies; returns the list of requests made and sleeps taken."""
    made = {"get": [], "sleep": [], "queue": []}

    def fake_get(url, **kwargs):
        made["get"].append((url, kwargs))
        item = made["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(gstinapi.requests, "get", fake_get)
    monkeypatch.setattr(gstinapi.time, "sleep", made["sleep"].append)
    return made


OK = {
    "credits_remaining": 41,
    "data": {
        "legal_name": "FRESH MART PRIVATE LIMITED",
        "trade_name": "Fresh Mart",
        "status": "Active",
        "taxpayer_type": "Regular",
        "pincode": "411004",
        "address": "ignored when parts exist",
        "address_details": {
            "building_number": "12",
            "building_name": None,
            "street": "MG Road",
            "locality": "Camp",
            "district": "Pune",
            "city": "Pune",
        },
    },
}


def test_no_key_means_not_set_up(monkeypatch):
    monkeypatch.setenv("GSTINAPI_KEY", "")
    with pytest.raises(NotSetUp):
        gstinapi.lookup(NUMBER)


def test_success_maps_details_and_sends_the_key(key, calls, caplog):
    calls["queue"].append(Reply(200, OK))
    with caplog.at_level(logging.INFO, logger="core.gstinapi"):
        got = gstinapi.lookup(NUMBER)
    url, kwargs = calls["get"][0]
    assert url.endswith(f"/v1/gstin/{NUMBER}")
    assert kwargs["headers"] == {"x-api-key": "test-key"}
    assert kwargs["params"] == {"include": "profile"}
    assert got["legal_name"] == "FRESH MART PRIVATE LIMITED"
    assert got["gst_type"] == "regular"
    assert got["address"] == "12, MG Road, Camp, Pune"
    assert got["pincode"] == "411004"
    assert "credits_remaining=41" in caplog.text


def test_address_falls_back_to_the_text_and_type_maps():
    data = {"address": "Plot 5, Pune", "taxpayer_type": "Composition Dealer"}
    assert gstinapi._address(data) == "Plot 5, Pune"
    assert gstinapi._gst_type(data["taxpayer_type"]) == "composition"
    assert gstinapi._gst_type("SEZ Unit") == "sez"
    assert gstinapi._gst_type(None) == "regular"


@pytest.mark.parametrize(
    "status,shown,word",
    [
        (401, 503, "key"),
        (402, 503, "credits"),
        (403, 503, "deactivated"),
        (404, 404, "not registered"),
        (400, 502, "failed"),
    ],
)
def test_failures_are_not_retried(key, calls, status, shown, word):
    calls["queue"].append(Reply(status))
    with pytest.raises(LookupFailed) as err:
        gstinapi.lookup(NUMBER)
    assert err.value.status_code == shown
    assert word in str(err.value.detail)
    assert len(calls["get"]) == 1
    assert calls["sleep"] == []


def test_rate_limit_retries_then_succeeds(key, calls):
    calls["queue"] += [Reply(429), Reply(502), Reply(200, OK)]
    assert gstinapi.lookup(NUMBER)["trade_name"] == "Fresh Mart"
    assert len(calls["get"]) == 3
    assert calls["sleep"] == [1.0, 2.0]


def test_gives_up_after_three_attempts(key, calls):
    calls["queue"] += [Reply(502), Reply(502), Reply(502)]
    with pytest.raises(LookupFailed) as err:
        gstinapi.lookup(NUMBER)
    assert err.value.status_code == 502
    assert len(calls["get"]) == 3


def test_network_error_is_retried(key, calls):
    calls["queue"] += [requests.ConnectionError(), requests.Timeout(), Reply(200, OK)]
    assert gstinapi.lookup(NUMBER)["status"] == "Active"
    assert len(calls["get"]) == 3
