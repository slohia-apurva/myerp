"""Loading PIN codes, and one courier's coverage of them, from the courier's
serviceability CSV (columns Pin, Facility City, Facility State, ODA,
Dispatch Center, Origin Center, Return Center)."""

import csv
import io
import re

from tenancy.models import Carrier, CourierPin, PinCode, State
from tenancy.reference_data import STATE_ALIASES

PIN_RE = re.compile(r"[1-9][0-9]{5}")


def parse(text: str) -> list[dict]:
    """One dict per row with a valid 6-digit PIN; the last row for a PIN wins."""
    found: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        pin = row.get("pin", "").replace(" ", "")
        if not PIN_RE.fullmatch(pin):
            continue
        oda = row.get("oda", "").lower()
        found[pin] = {
            "pin": pin,
            "city": " ".join(row.get("facility city", "").split()),
            "state": row.get("facility state", ""),
            "oda": True if oda == "true" else False if oda == "false" else None,
            "dispatch_center": row.get("dispatch center", ""),
            "origin_center": row.get("origin center", ""),
            "return_center": row.get("return center", ""),
        }
    return list(found.values())


def _state_ids() -> dict[str, int]:
    ids = {s.name.lower(): s.pk for s in State.objects.all()}
    for alias, name in STATE_ALIASES.items():
        if name.lower() in ids:
            ids[alias] = ids[name.lower()]
    return ids


def load(rows: list[dict], courier: str) -> dict:
    """Add PINs we lack (an existing PIN keeps its city, and gets a state if it
    had none) and replace this courier's coverage with the file's."""
    name = courier.strip()
    if not name:
        raise ValueError("Say which courier the file is from.")
    carrier = Carrier.objects.filter(name__iexact=name).first()
    if carrier is None:
        known = ", ".join(Carrier.objects.values_list("name", flat=True))
        raise ValueError(f"No courier called {name} in the courier list (known: {known}).")
    states = _state_ids()
    have = {p.pin: p for p in PinCode.objects.all()}
    new, fill = [], []
    rejected: list[dict] = []
    good: list[dict] = []
    for r in rows:
        state_id = states.get(r["state"].lower())
        if r["state"] and state_id is None:
            rejected.append({**r, "reason": f"Unknown state name: {r['state']}"})
            continue
        good.append(r)
        pin = have.get(r["pin"])
        if pin is None:
            new.append(PinCode(pin=r["pin"], city=r["city"], state_id=state_id))
        elif pin.state_id is None and state_id:
            pin.state_id = state_id
            fill.append(pin)
    PinCode.objects.bulk_create(new)
    PinCode.objects.bulk_update(fill, ["state"])
    ids = dict(PinCode.objects.values_list("pin", "pk"))
    removed, _ = CourierPin.objects.filter(carrier=carrier).delete()
    CourierPin.objects.bulk_create(
        [
            CourierPin(
                carrier=carrier,
                pin_id=ids[r["pin"]],
                oda=r["oda"],
                dispatch_center=r["dispatch_center"],
                origin_center=r["origin_center"],
                return_center=r["return_center"],
            )
            for r in good
        ]
    )
    return {
        "pins_added": len(new),
        "state_filled": len(fill),
        "coverage": len(good),
        "replaced": removed,
        "problems": [f"{r['pin']}: {r['reason']}" for r in rejected],
        "rejected": rejected,
    }
