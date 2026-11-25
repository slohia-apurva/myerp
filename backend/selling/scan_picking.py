"""Scan Picking (Entry > Sales > Scan Picking; Sidharth, 2026-11-25, preview
mockups/scan-picking): the picker scans the pick list's barcode, then each
package label (PK-000241), the unit barcode of loose goods, or a bin's LOC
label, and the system says at once whether it is right.

- A package on the list ticks its row. A package of the same item and batch
  that is free (not on another list) is offered in place of a listed one
  that is not ticked yet ("Use PK-… instead"), which changes the list.
- A unit barcode (an item's carton or packet barcode) counts that many stock
  units against the item's rows that have no package.
- Any row can be ticked by hand, with the quantity, as the last resort.
- Anything else is a wrong scan: kept for the count, nothing ticked.

Every scan is saved at once, so a refresh or a second picker carries on. Only
an open list can be scanned; Submit is the pick list's own (it warns on the
screen when rows are not checked, decided 2026-11-25). Nothing here posts.
"""

import re
from decimal import Decimal

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import Signed
from core.models import ItemUnit, Package, WarehouseLocation
from selling import picking
from selling.api import _company
from selling.models import PickList, PickListLine, PickScan
from selling.pick_lists import _check, _check_rows, _pick
from tenancy.context import tenant_atomic

ZERO = Decimal("0")
PK = re.compile(r"^PK-?(\d{1,9})$")
LOC = re.compile(r"^LOC-?(\d{1,9})$")


def _rows(p: PickList) -> list[PickListLine]:
    return list(
        p.lines.select_related(
            "item__stock_unit", "location", "batch", "package", "order_line"
        ).order_by("location__name", "position", "id")
    )


def _key(x) -> tuple:
    return (x.order_line_id, x.location_id, x.batch_id)


def check(p: PickList, rows: list[PickListLine] | None = None) -> dict:
    """Per row: whether the goods in hand were checked, how much and how; and
    the counts the screens show."""
    rows = _rows(p) if rows is None else rows
    scans = list(p.scans.select_related("by", "item_unit__unit"))
    by_package: dict[int, PickScan] = {}
    loose: dict[tuple, list[PickScan]] = {}
    for s in scans:
        if s.kind == PickScan.WRONG:
            continue
        if s.package_id:
            by_package.setdefault(s.package_id, s)
        else:
            loose.setdefault(_key(s), []).append(s)
    left = {k: sum((s.qty for s in v), ZERO) for k, v in loose.items()}
    out = {}
    for r in rows:
        unit = r.item.stock_unit.short_name or r.item.stock_unit.name
        if r.package_id:
            s = by_package.get(r.package_id)
            got = r.qty if s else ZERO
            if s is None:
                how = ""
            elif s.kind == PickScan.HAND:
                how = f"By hand · {s.by.display_name}"
            elif s.swapped_for:
                how = f"Swapped for {s.swapped_for}"
            else:
                how = "Scanned"
            when = s.at if s else None
        else:
            k = _key(r)
            got = min(left.get(k, ZERO), r.qty)
            left[k] = left.get(k, ZERO) - got
            mine = loose.get(k, [])
            parts = []
            units: dict[str, int] = {}
            for s in mine:
                if s.kind == PickScan.UNIT and s.item_unit:
                    name = s.item_unit.unit.short_name or s.item_unit.unit.name
                    units[name] = units.get(name, 0) + 1
            parts += [f"{n} {u} by item barcode" for u, n in units.items()]
            hands = {s.by.display_name for s in mine if s.kind == PickScan.HAND}
            parts += [f"By hand · {n}" for n in sorted(hands)]
            how = ", ".join(parts) if got > 0 else ""
            when = mine[-1].at if mine and got > 0 else None
        out[r.pk] = {
            "done": got >= r.qty,
            "got": picking.plain(got),
            "how": how,
            "at": when,
            "unit": unit,
        }
    kinds = {k: sum(1 for s in scans if s.kind == k) for k, _ in PickScan.KINDS}
    return {
        "rows": out,
        "done": sum(1 for v in out.values() if v["done"]),
        "total": len(out),
        "scanned": kinds[PickScan.PACKAGE],
        "by_barcode": kinds[PickScan.UNIT],
        "by_hand": kinds[PickScan.HAND],
        "wrong": kinds[PickScan.WRONG],
        "started": bool(scans),
    }


def screen(p: PickList) -> dict:
    """What the scan screen shows: the list's head, its rows bin by bin with
    their check, and the counts."""
    rows = _rows(p)
    c = check(p, rows)
    return {
        "id": p.pk,
        "number": p.number,
        "status": p.status,
        "status_label": p.get_status_display(),
        "customer_name": p.order.customer.name,
        "order_number": p.order.number,
        "despatch_from": p.branch.name + (f" › {p.area.name}" if p.area_id else ""),
        **{k: v for k, v in c.items() if k != "rows"},
        "rows": [
            {
                "id": r.pk,
                "position": r.position,
                "item": r.item_id,
                "item_name": r.item.name,
                "item_number": r.item.item_number,
                "location": r.location_id,
                "location_name": r.location.name,
                "batch_number": r.batch.number if r.batch else "",
                "package_number": r.package.number if r.package else "",
                "package_left": picking.plain(r.package.left_qty) if r.package else "",
                "qty": picking.plain(r.qty),
                **c["rows"][r.pk],
            }
            for r in rows
        ],
    }


def _open(p: PickList) -> None:
    if p.status != PickList.OPEN:
        raise ValidationError(
            {"detail": f"{p.number} is {p.get_status_display()}: only an open list is picked."}
        )


def _reply(p: PickList, result: str, message: str, **more) -> Response:
    return Response({"result": result, "message": message, **more, "list": screen(p)})


def _wrong(p: PickList, user, code: str, message: str, **more) -> Response:
    PickScan.objects.create(
        pick_list=p, kind=PickScan.WRONG, code=code[:60], message=message[:300], by=user
    )
    return _reply(p, "wrong", message, **more)


def _free(p: PickList, pk: Package) -> Decimal:
    """What may still be taken from a package not on this list: nothing if
    another list holds it, or it is outside the list's Despatch From."""
    for s in picking.spots(pk.item, p.branch, p.area, p):
        if s.package and s.package.pk == pk.pk:
            return s.free
    return ZERO


def _package(p: PickList, user, code: str, number: str) -> Response:
    pk = (
        Package.objects.filter(company=p.company, number=number)
        .select_related("item", "batch", "location")
        .first()
    )
    if pk is None:
        return _wrong(p, user, code, f"No package {number} in this company.")
    rows = _rows(p)
    c = check(p, rows)
    mine = next((r for r in rows if r.package_id == pk.pk), None)
    if mine is not None:
        if c["rows"][mine.pk]["done"]:
            return _reply(p, "warn", f"{number} was already checked (line {mine.position}).")
        PickScan.objects.create(
            pick_list=p, kind=PickScan.PACKAGE, code=code[:60], order_line=mine.order_line,
            location=mine.location, batch=mine.batch, package=pk, qty=mine.qty, by=user,
        )  # fmt: skip
        unit = c["rows"][mine.pk]["unit"]
        what = f"{number} · {pk.item.name}" + (f" · Batch {pk.batch.number}" if pk.batch else "")
        return _reply(p, "ok", f"{what} · {picking.plain(mine.qty)} {unit}", row=mine.pk)
    same_item = [r for r in rows if r.item_id == pk.item_id]
    what = pk.item.name + (f", batch {pk.batch.number}" if pk.batch else "")
    if not same_item:
        return _wrong(
            p, user, code, f"{number} is {what}, which is not on this pick list. Put it back."
        )
    if pk.status in (Package.USED_UP, Package.CANCELLED):
        return _wrong(p, user, code, f"{number} is {pk.get_status_display().lower()}. Put it back.")
    waiting = [r for r in same_item if not c["rows"][r.pk]["done"]]
    if not waiting:
        return _wrong(
            p, user, code, f"All of {pk.item.name} is already checked. Put {number} back."
        )
    match = [r for r in waiting if r.batch_id == pk.batch_id]
    if not match:
        wanted = ", ".join(sorted({r.batch.number if r.batch else "no batch" for r in waiting}))
        return _wrong(
            p, user, code, f"{number} is {what}, but the list wants batch {wanted}. Put it back."
        )
    free = _free(p, pk)
    row = next((r for r in match if r.qty <= free), None)
    if row is None:
        why = "is on another pick list" if free <= 0 else f"has only {picking.plain(free)} free"
        return _wrong(p, user, code, f"{number} {why}. Put it back.")
    listed = (
        row.package.number if row.package else f"{picking.plain(row.qty)} from {row.location.name}"
    )
    return _reply(
        p,
        "offer",
        f"{number} is {what}, {picking.plain(pk.left_qty)} "
        f"{c['rows'][row.pk]['unit']}, but the list says {listed}.",
        offer={"row": row.pk, "package": pk.pk, "package_number": number, "instead_of": listed},
    )


def _unit(p: PickList, user, code: str, iu: ItemUnit) -> Response:
    rows = _rows(p)
    c = check(p, rows)
    name = iu.unit.short_name or iu.unit.name
    same = [r for r in rows if r.item_id == iu.item_id]
    if not same:
        return _wrong(
            p, user, code, f"That barcode is {iu.item.name} ({name}), not on this pick list."
        )
    loose = [r for r in same if not r.package_id]
    if not loose:
        return _wrong(
            p, user, code, f"{iu.item.name} is picked by package here: scan the PK label instead."
        )
    room = [(r, r.qty - Decimal(c["rows"][r.pk]["got"])) for r in loose]
    left = sum((x for _, x in room), ZERO)
    unit = c["rows"][loose[0].pk]["unit"]
    if left <= 0:
        return _reply(p, "warn", f"All of {iu.item.name} is already checked. Put it back.")
    if iu.factor > left:
        return _wrong(
            p, user, code,
            f"One {name} of {iu.item.name} is {picking.plain(iu.factor)} {unit}; "
            f"only {picking.plain(left)} {unit} is left to pick.",
        )  # fmt: skip
    need = iu.factor
    for r, space in room:
        if need <= 0 or space <= 0:
            continue
        take = min(space, need)
        PickScan.objects.create(
            pick_list=p, kind=PickScan.UNIT, code=code[:60], order_line=r.order_line,
            location=r.location, batch=r.batch, item_unit=iu, qty=take, by=user,
        )  # fmt: skip
        need -= take
    extra = f" ({picking.plain(iu.factor)} {unit})" if iu.factor != 1 else ""
    return _reply(
        p,
        "ok",
        f"+1 {name}{extra} · {iu.item.name} · {picking.plain(left - iu.factor)} {unit} to go",
    )


class FindView(APIView):
    """GET ?code=PL number: the open (or other) pick list of that number."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        code = str(request.query_params.get("code", "")).strip()
        p = PickList.objects.filter(company=company, number__iexact=code).first()
        if p is None:
            raise NotFound(f"No pick list {code}." if code else "Scan a pick list.")
        return Response({"id": p.pk, "number": p.number, "status": p.status})


class ScanView(APIView):
    """GET: the scan screen of a list. POST {code}: one scan. DELETE: start
    again (an open list's checks are cleared)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(screen(_pick(request, pk)))

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        p = _pick(request, pk, lock=True)
        _open(p)
        code = str(request.data.get("code", "")).strip()
        if not code:
            raise ValidationError({"code": ["Scan or type a code."]})
        upper = code.upper().replace(" ", "")
        if m := PK.match(upper):
            return _package(p, request.user, code, f"PK-{int(m.group(1)):06d}")
        if m := LOC.match(upper):
            place = WarehouseLocation.objects.filter(
                pk=int(m.group(1)), branch__company=p.company
            ).first()
            here = [r for r in _rows(p) if place and r.location_id == place.pk]
            if not here:
                name = place.name if place else code
                return _reply(p, "warn", f"Nothing on this list is picked from {name}.")
            return _reply(p, "bin", f"Bin {place.name}: {len(here)} to pick here.", bin=place.pk)
        if PickList.objects.filter(company=p.company, number__iexact=code).exists():
            if p.number.lower() == code.lower():
                return _reply(p, "warn", f"This is {p.number}, the list you are on.")
            return _reply(p, "warn", f"{code} is another pick list. Close this one to change.")
        iu = (
            ItemUnit.objects.filter(barcode=code, item__is_active=True)
            .select_related("item", "unit")
            .first()
        )
        if iu is not None:
            return _unit(p, request.user, code, iu)
        return _wrong(p, request.user, code, f"{code} is not a package, bin or item barcode.")

    @tenant_atomic()
    def delete(self, request, pk: int):
        _check(request, "create")
        p = _pick(request, pk, lock=True)
        _open(p)
        p.scans.all().delete()
        return Response(screen(p))


class SwapView(APIView):
    """POST {row, package}: take this package in place of the row's own, from
    the "Use PK-… instead" offer. Same item and batch, and free."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        p = _pick(request, pk, lock=True)
        _open(p)
        rows = _rows(p)
        row = next((r for r in rows if r.pk == request.data.get("row")), None)
        bag = Package.objects.filter(company=p.company, pk=request.data.get("package") or 0).first()
        if row is None or bag is None:
            raise ValidationError({"detail": "Scan the package again."})
        if bag.item_id != row.item_id or bag.batch_id != row.batch_id:
            raise ValidationError({"detail": f"{bag.number} is not the same item and batch."})
        if check(p, rows)["rows"][row.pk]["done"]:
            raise ValidationError({"detail": "That line is already checked."})
        if _free(p, bag) < row.qty:
            raise ValidationError({"detail": f"{bag.number} is on another pick list or too small."})
        old = row.package.number if row.package else ""
        row.package, row.location = bag, bag.location
        _check_rows(p, rows)
        row.save(update_fields=["package", "location"])
        PickScan.objects.create(
            pick_list=p, kind=PickScan.PACKAGE, code=bag.number, order_line=row.order_line,
            location=bag.location, batch=row.batch, package=bag, qty=row.qty,
            swapped_for=old or "no package", by=request.user,
        )  # fmt: skip
        return _reply(
            p, "ok", f"{bag.number} taken in place of {old or 'the listed stock'}.", row=row.pk
        )


class HandView(APIView):
    """POST {row, qty}: a row ticked by hand (loose goods with no label), the
    quantity in the stock unit; a packaged row is ticked whole."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        p = _pick(request, pk, lock=True)
        _open(p)
        rows = _rows(p)
        row = next((r for r in rows if r.pk == request.data.get("row")), None)
        if row is None:
            raise ValidationError({"detail": "No such line on this list."})
        c = check(p, rows)["rows"][row.pk]
        if c["done"]:
            raise ValidationError({"detail": "That line is already checked."})
        if row.package_id:
            qty = row.qty
        else:
            try:
                qty = Decimal(str(request.data.get("qty", "")).strip())
            except ArithmeticError:
                qty = ZERO
            space = row.qty - Decimal(c["got"])
            if qty <= 0 or qty > space:
                most = f"{picking.plain(space)} {c['unit']}"
                raise ValidationError({"qty": [f"Give a quantity above 0, at most {most}."]})
        PickScan.objects.create(
            pick_list=p, kind=PickScan.HAND, order_line=row.order_line, location=row.location,
            batch=row.batch, package=row.package, qty=qty, by=request.user,
        )  # fmt: skip
        return _reply(
            p,
            "ok",
            f"Line {row.position} ticked by hand: {picking.plain(qty)} {c['unit']}.",
            row=row.pk,
        )
