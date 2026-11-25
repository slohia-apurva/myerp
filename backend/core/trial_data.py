"""Trial data for trying long lists on staging (Sidharth, 2026-11-25): thousands
of made-up customers, suppliers, transporters and people, so paging, column
search and loading times can be tried before real data grows that large.

Every trial record is easy to tell apart and to remove:
* its name starts with "TRIAL " (shown on every screen and print);
* customers and suppliers get their own numbers, TCUST-00001 and TVEND-00001,
  so the real CUST-/VEND- series are not used up;
* transporters and people carry the note "Trial data".

`load` makes them for one company (each customer and supplier gets its ledger
in that company, with no opening balance); `remove` deletes every trial record
again, and stops with a list if any is already on an entry. Both only run where
settings.ALLOW_DATA_RESET is on (staging and trial runs, never live books), for
an Owner, from Admin > Reset data.
"""

from __future__ import annotations

import random

from django.db.models import ProtectedError
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import india
from core.api import Signed
from core.models import Company, Ledger, LedgerGroup, Party, PartyAddress, SalesPerson
from shipping.models import CourierAccount
from tenancy.context import tenant_atomic

PREFIX = "TRIAL "
NOTE = "Trial data"
COUNTS = {"customers": 6000, "suppliers": 4000, "transporters": 5000, "people": 5000}

_FIRST = (
    "Shree Ganesh", "Laxmi", "Balaji", "Sai", "Krishna", "Om", "Jai Ambe", "Mahalaxmi",
    "Shiv Shakti", "Radhe", "Gayatri", "Annapurna", "Ganga", "Himalaya", "Sunrise",
    "Green Leaf", "Royal", "Golden", "Silver Oak", "Blue Hill", "Everest", "Nilgiri",
    "Assam Valley", "Darjeeling", "Kangra", "Munnar", "Sahyadri", "Narmada", "Kaveri",
)  # fmt: skip
_TRADE = (
    "Traders", "Enterprises", "Agencies", "Stores", "Distributors", "Tea House",
    "Mart", "Suppliers", "Corporation", "& Sons", "Exports", "Packaging", "Foods",
)  # fmt: skip
_CARRIER = ("Roadways", "Logistics", "Transport Co", "Carriers", "Express", "Movers", "Cargo")
_PEOPLE = (
    "Amit", "Rahul", "Priya", "Neha", "Suresh", "Ramesh", "Anita", "Kavita", "Vijay",
    "Sanjay", "Pooja", "Deepak", "Manoj", "Sunita", "Rakesh", "Meena", "Arjun", "Divya",
)  # fmt: skip
_SURNAMES = (
    "Sharma", "Verma", "Gupta", "Agarwal", "Patel", "Shah", "Mehta", "Iyer", "Nair",
    "Reddy", "Singh", "Das", "Bose", "Jain", "Kulkarni", "Joshi", "Rao", "Pillai",
)  # fmt: skip
_CITIES = {
    "27": ("Mumbai", "Pune", "Nagpur", "Nashik", "Thane"),
    "07": ("New Delhi", "Dwarka", "Rohini"),
    "19": ("Kolkata", "Siliguri", "Howrah"),
    "18": ("Guwahati", "Dibrugarh", "Jorhat"),
    "24": ("Ahmedabad", "Surat", "Vadodara"),
    "29": ("Bengaluru", "Mysuru", "Hubballi"),
    "33": ("Chennai", "Coimbatore", "Madurai"),
    "09": ("Lucknow", "Kanpur", "Noida"),
}


def _allowed(user) -> None:
    from django.conf import settings

    if not user.is_owner:
        raise PermissionDenied("Only an Owner can load or remove trial data.")
    if not settings.ALLOW_DATA_RESET:
        raise PermissionDenied(
            "Trial data is switched off here. It is for staging and trial runs, not live books."
        )


def _pan(n: int, kind: str) -> str:
    """A made-up PAN of the right shape, different for every n (letters from n)."""
    letters = ""
    m = n
    for _ in range(3):
        letters += chr(65 + m % 26)
        m //= 26
    return f"{letters}{kind}T{n % 10000:04d}{chr(65 + (n // 10000) % 26)}"


def _gstin(state: str, pan: str) -> str:
    first = f"{state}{pan}1Z"
    return first + india.gstin_check_char(first)


def counts() -> dict[str, int]:
    """How many trial records there are now."""
    return {
        "customers": Party.objects.filter(customer_number__startswith="TCUST-").count(),
        "suppliers": Party.objects.filter(vendor_number__startswith="TVEND-").count(),
        "transporters": CourierAccount.objects.filter(name__startswith=PREFIX, notes=NOTE).count(),
        "people": SalesPerson.objects.filter(name__startswith=PREFIX, notes=NOTE).count(),
    }


def load(company: Company, user) -> dict[str, int]:
    """Make the trial records for `company`. Refused while any are there."""
    _allowed(user)
    if any(counts().values()):
        raise ValidationError(["Trial data is already loaded. Remove it first to load it again."])
    rng = random.Random(25112026)
    debtors = LedgerGroup.objects.get(company=company, name="Sundry Debtors")
    creditors = LedgerGroup.objects.get(company=company, name="Sundry Creditors")
    states = list(_CITIES)

    def party(n: int, side: str) -> tuple[Party, str, str]:
        state = rng.choice(states)
        # Suppliers number on after the customers, so no two names are the same.
        shown = n if side == "customer" else COUNTS["customers"] + n
        name = f"{PREFIX}{rng.choice(_FIRST)} {rng.choice(_TRADE)} {shown:05d}"
        registered = rng.random() < 0.6
        kind = "C" if side == "customer" else "F"
        pan = _pan(n + (0 if side == "customer" else 50000), kind) if registered else ""
        p = Party(
            name=name,
            gst_type=Party.REGULAR if registered else Party.UNREGISTERED,
            gstin=_gstin(state, pan) if registered else "",
            pan=pan,
            state_code=state,
            customer_number=f"TCUST-{n:05d}" if side == "customer" else "",
            vendor_number=f"TVEND-{n:05d}" if side == "supplier" else "",
        )
        return p, state, rng.choice(_CITIES[state])

    made = {}
    for side, how_many, group in (
        ("customer", COUNTS["customers"], debtors),
        ("supplier", COUNTS["suppliers"], creditors),
    ):
        rows = [party(n, side) for n in range(1, how_many + 1)]
        parties = Party.objects.bulk_create([p for p, _, _ in rows], batch_size=1000)
        PartyAddress.objects.bulk_create(
            [
                PartyAddress(
                    party=p,
                    label="Head office",
                    address=f"{rng.randint(1, 400)}, Main Road",
                    city=city,
                    state_code=state,
                    gstin=p.gstin,
                    is_billing=True,
                    is_shipping=True,
                )  # fmt: skip
                for p, (_, state, city) in zip(parties, rows, strict=True)
            ],
            batch_size=1000,
        )
        Ledger.objects.bulk_create(
            [
                Ledger(company=company, group=group, name=p.name, party=p, party_side=side)
                for p in parties
            ],
            batch_size=1000,
        )
        made[f"{side}s"] = len(parties)
    CourierAccount.objects.bulk_create(
        [
            CourierAccount(
                company=company,
                name=f"{PREFIX}{rng.choice(_FIRST)} {rng.choice(_CARRIER)} {n:05d}"[:60],
                state_code=(s := rng.choice(states)),
                city=rng.choice(_CITIES[s]),
                phone=f"9{rng.randint(100000000, 999999999)}",
                notes=NOTE,
            )
            for n in range(1, COUNTS["transporters"] + 1)
        ],
        batch_size=1000,
    )
    made["transporters"] = COUNTS["transporters"]
    SalesPerson.objects.bulk_create(
        [
            SalesPerson(
                name=f"{PREFIX}{rng.choice(_PEOPLE)} {rng.choice(_SURNAMES)} {n:05d}",
                is_salesman=n % 3 != 0,
                is_purchaser=n % 3 == 0,
                is_stores=n % 10 == 0,
                mobile=f"9{rng.randint(100000000, 999999999)}",
                notes=NOTE,
            )
            for n in range(1, COUNTS["people"] + 1)
        ],
        batch_size=1000,
    )
    made["people"] = COUNTS["people"]
    return made


def remove(user) -> dict[str, int]:
    """Delete every trial record. A trial record already on an entry stops it:
    the whole removal is undone and the reply says so."""
    _allowed(user)
    had = counts()
    parties = Party.objects.filter(customer_number__startswith="TCUST-") | Party.objects.filter(
        vendor_number__startswith="TVEND-"
    )
    parties = parties.filter(name__startswith=PREFIX)
    try:
        Ledger.objects.filter(party__in=parties).delete()
        parties.delete()
        CourierAccount.objects.filter(name__startswith=PREFIX, notes=NOTE).delete()
        SalesPerson.objects.filter(name__startswith=PREFIX, notes=NOTE).delete()
    except ProtectedError as e:
        used = sorted({str(o) for o in e.protected_objects})[:10]
        raise ValidationError(
            ["Some trial records are already used on entries, so nothing was removed: "] + used
        ) from None
    return had


class TrialDataView(APIView):
    """GET: whether trial data may be loaded here and how much there is.
    POST {action: "load", company} or {action: "remove"}."""

    permission_classes = [Signed]

    def get(self, request):
        if not request.user.is_owner:
            raise PermissionDenied("Only an Owner can load or remove trial data.")
        from django.conf import settings

        return Response(
            {"allowed": settings.ALLOW_DATA_RESET, "counts": counts(), "will_make": COUNTS}
        )

    @tenant_atomic()
    def post(self, request):
        action = request.data.get("action")
        if action == "remove":
            return Response({"removed": remove(request.user), "counts": counts()})
        if action != "load":
            raise ValidationError({"action": ["Choose load or remove."]})
        company = Company.objects.filter(pk=request.data.get("company") or 0).first()
        if company is None:
            raise ValidationError(
                {"company": ["Choose the company for the ledgers and transporters."]}
            )
        return Response({"made": load(company, request.user), "counts": counts()})
