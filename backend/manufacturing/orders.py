"""Manufacturing Orders (Entry > Production; Sidharth, 2026-11-23, preview 15d
in mockups/planning): what to make, how much, by when, with which BOM version.

Draft        the item, quantity, BOM version (the item's default to start
             with, any active version may be picked), dates, places and the
             Pack Details. The materials of the version are worked out for the
             quantity and are fixed; materials added on the order may be
             changed or removed.
Submit       gives the number (series "manufacturing_order"); the order is
             "Not Started". Added materials and the Pack Details stay open;
             what is made, how much and from which version do not.
In Process   once a Material Issue is made (next part); Completed once the
             Production Entries make the whole quantity; "Close" ends an order
             made short. Cancel only while nothing has been issued.

The order posts nothing. A draft or open order counts its materials still to
issue as Reserved and what it is still to make as Incoming in the Stock Check.
Who may do what: the production rights (production.view, create, submit, cancel).
"""

from __future__ import annotations

import calendar
import datetime
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import attachments, numbering
from core.api import Signed
from core.companies import visible_companies
from core.models import Item, ItemUnit, Party, SalesPerson, Unit, WarehouseLocation
from manufacturing.boms import CUSTOMER, factor, money, rate_of, source, source_text
from manufacturing.models import Bom, ManufacturingOrder, ManufacturingOrderLine
from posting.models import StockMove
from selling.models import SalesOrder
from selling.stock import on_hand, places
from stock.transfers import TRANSIT, _area, _branch
from tenancy.context import tenant_atomic

KIND = "manufacturing_order"  # the series and the attachments' record type
ZERO = Decimal("0")
HUNDRED = Decimal("100")
STEP = Decimal("0.000001")
MO = ManufacturingOrder


def may(user, action: str) -> bool:
    return user.can(f"production.{action}")


def _check(request, action: str) -> None:
    if not may(request.user, action):
        raise PermissionDenied("Your role may not do this with manufacturing orders.")


def _company(request, pk: int):
    company = visible_companies(request.user).filter(pk=pk).first()
    if company is None:
        raise NotFound("No such company.")
    if "production" not in company.modules:
        raise NotFound("This company does not use the Production module.")
    return company


def _plain(value) -> str:
    if value is None:
        return ""
    text = format(Decimal(value).quantize(STEP).normalize(), "f")
    return text


def _short(unit: Unit) -> str:
    return unit.short_name or unit.name


def add_period(day: datetime.date, value: int, unit: str) -> datetime.date:
    """A date `value` days or months on (a month end stays in range)."""
    if unit == Item.MONTHS:
        month = day.month - 1 + value
        year, month = day.year + month // 12, month % 12 + 1
        last = calendar.monthrange(year, month)[1]
        return datetime.date(year, month, min(day.day, last))
    return day + datetime.timedelta(days=value)


def expiry(pkd: datetime.date | None, value: int | None, unit: str) -> datetime.date | None:
    """Expiry (best before) date: the Pkd Date plus the Best Before period, the
    day before it ends (packed 24-11-2026, 18 months: 23-05-2028)."""
    if pkd is None or not value:
        return None
    return add_period(pkd, value, unit) - datetime.timedelta(days=1)


# The materials of a version, for a quantity --------------------------------------


def batches(bom: Bom, item: Item, qty: Decimal, unit_id: int) -> Decimal:
    """How many of the BOM's batches the quantity is."""
    mine = factor(item, unit_id) or Decimal(1)
    per = factor(bom.item, bom.makes_unit_id) or Decimal(1)
    return qty * mine / (bom.makes_qty * per)


def bom_lines(bom: Bom, item: Item, qty: Decimal, unit_id: int) -> list[dict]:
    """The BOM version's materials for `qty` of `unit_id`: per one of that unit,
    the loss, and what is required."""
    one = batches(bom, item, Decimal(1), unit_id)
    rows = []
    for ln in bom.lines.select_related("item", "unit"):
        per_unit = (ln.qty * one).quantize(STEP)
        rows.append(
            {
                "item": ln.item,
                "unit": ln.unit,
                "per_unit": per_unit,
                "loss_pct": ln.loss_pct,
                "required": required(per_unit, qty, ln.loss_pct),
                "from_bom": True,
            }
        )
    return rows


def required(per_unit: Decimal, qty: Decimal, loss: Decimal) -> Decimal:
    return (per_unit * qty * (1 + loss / HUNDRED)).quantize(STEP)


def versions(item: Item) -> list[Bom]:
    """The versions an order may use: active and not disabled, the default first."""
    return list(
        Bom.objects.filter(item=item, status=Bom.ACTIVE, is_active=True)
        .select_related("makes_unit", "customer")
        .order_by("-is_default", "version")
    )


# Free stock ------------------------------------------------------------------------


def reserved_lines(branch, item_ids, leave_out=None):
    """(item, unit, qty) still to issue on the branch's draft and open orders."""
    rows = ManufacturingOrderLine.objects.filter(
        order__branch=branch,
        order__status__in=[MO.DRAFT, *MO.OPEN],
        item_id__in=item_ids,
    )
    if leave_out is not None:
        rows = rows.exclude(order=leave_out)
    return [
        (i, u, max(r - s, ZERO))
        for i, u, r, s in rows.values_list("item", "unit", "required", "issued")
    ]


def incoming_lines(branch, item_ids):
    """(item, unit, qty) still to make on the branch's draft and open orders."""
    rows = MO.objects.filter(
        branch=branch, status__in=[MO.DRAFT, *MO.OPEN], item_id__in=item_ids
    ).values_list("item", "unit", "qty", "made_qty")
    return [(i, u, max(q - m, ZERO)) for i, u, q, m in rows]


def free_in_branch(branch, lines: list[dict], mo: MO | None, customer=None) -> dict[int, Decimal]:
    """What each material has free at the branch (its stock unit): on hand less
    everything reserved there except this order. A customer's goods count only
    that customer's stock."""
    from buying import planning

    ids = [r["item"].pk for r in lines]
    have = on_hand(ids, branch)
    held = planning.reserved(branch, ids)
    if mo is not None and mo.pk:
        own = planning._in_stock_units(
            [
                (i, u, max(r - s, ZERO))
                for i, u, r, s in mo.lines.values_list("item", "unit", "required", "issued")
            ],
            planning._factors(ids),
        )
        for k, v in own.items():
            held[k] = held.get(k, ZERO) - v
    theirs: dict[int, Decimal] = {}
    if customer is not None:
        rows = (
            StockMove.objects.filter(item__in=ids, owner=customer, location__in=places(branch))
            .values("item")
            .annotate(q=Sum("qty"))
        )
        theirs = {r["item"]: r["q"] or ZERO for r in rows}
    out = {}
    for r in lines:
        item = r["item"]
        if source(item)[0] == CUSTOMER:
            out[item.pk] = theirs.get(item.pk, ZERO) - held.get(item.pk, ZERO)
        else:
            out[item.pk] = have.get(item.pk, ZERO) - held.get(item.pk, ZERO)
    return out


# Reading ---------------------------------------------------------------------------


def _orders(company):
    return MO.objects.filter(company=company).select_related(
        "company", "branch", "item__stock_unit", "unit", "bom", "customer", "sales_order",
        "materials_from", "goods_to", "supervisor", "usp_per", "created_by", "submitted_by",
    )  # fmt: skip


def line_out(r: dict, free: dict, n: int) -> dict:
    item, unit = r["item"], r["unit"]
    code, sub = source(item)
    f = factor(item, unit.pk) or Decimal(1)
    have = free.get(item.pk)
    req = r["required"]
    return {
        "position": n,
        "item": item.pk,
        "item_name": item.name,
        "item_number": item.item_number,
        "unit": unit.pk,
        "unit_name": _short(unit),
        "per_unit": _plain(r["per_unit"]),
        "loss_pct": _plain(r["loss_pct"]),
        "required": _plain(req),
        "issued": _plain(r.get("issued", ZERO)),
        "from_bom": r["from_bom"],
        "source": code,
        "source_text": source_text(code, sub),
        "free": _plain(have / f) if have is not None else None,
        "short": have is not None and have < (req - r.get("issued", ZERO)) * f,
        "bom_note": r.get("bom_note", ""),
    }


def _cost(lines: list[dict]) -> tuple[Decimal, list[str]]:
    total, missing = ZERO, []
    for r in lines:
        _code, _sub, rate, _how, lacking = rate_of(r["item"], r["unit"].pk)
        if rate is None:
            missing.extend(x for x in lacking if x not in missing)
        else:
            total += money(r["required"] * rate)
    return total, missing


def _rows(mo: MO) -> list[dict]:
    return [
        {
            "item": ln.item,
            "unit": ln.unit,
            "per_unit": ln.per_unit,
            "loss_pct": ln.loss_pct,
            "required": ln.required,
            "issued": ln.issued,
            "from_bom": ln.from_bom,
        }
        for ln in mo.lines.select_related("item__stock_unit", "unit")
    ]


def materials_out(branch, bom, item, qty, unit_id, rows, mo=None, customer=None) -> dict:
    """The Materials and By-products boxes, and the cost estimate."""
    free = free_in_branch(branch, rows, mo, customer) if branch is not None else {}
    unit = Unit.objects.get(pk=unit_id)
    lines = [line_out(r, free, n) for n, r in enumerate(rows, 1)]
    scale = batches(bom, item, qty, unit_id)
    by = [
        {
            "item": b.item_id,
            "item_name": b.item.name,
            "qty": _plain(b.qty * scale),
            "unit_name": _short(b.unit),
            "kind_label": b.get_kind_display() + ("" if b.rate else ", no value"),
        }
        for b in bom.byproducts.select_related("item", "unit")
    ]
    total, missing = _cost(rows)
    stock_qty = qty * (factor(item, unit_id) or Decimal(1))
    return {
        "lines": lines,
        "byproducts": by,
        "cost": {
            "materials": str(total),
            "per_unit": str(money(total / qty)) if qty and not missing else None,
            "unit_name": _short(unit),
            "per_stock_unit": str(money(total / stock_qty)) if stock_qty and not missing else None,
            "stock_unit_name": _short(item.stock_unit),
            "missing": missing,
        },
    }


def order_out(mo: MO, full: bool = True) -> dict:
    data = {
        "id": mo.pk,
        "company": mo.company_id,
        "number": mo.number,
        "status": mo.status,
        "status_label": mo.get_status_display(),
        "branch": mo.branch_id,
        "branch_name": mo.branch.name,
        "order_date": mo.order_date,
        "item": mo.item_id,
        "item_name": mo.item.name,
        "item_number": mo.item.item_number,
        "qty": _plain(mo.qty),
        "unit": mo.unit_id,
        "unit_name": _short(mo.unit),
        "stock_qty": _plain(mo.qty * (factor(mo.item, mo.unit_id) or Decimal(1))),
        "stock_unit_name": _short(mo.item.stock_unit),
        "made_qty": _plain(mo.made_qty),
        "bom": mo.bom_id,
        "bom_number": mo.bom.number,
        "bom_version": mo.bom.version,
        "bom_name": mo.bom.name,
        "bom_default": mo.bom.is_default,
        "kind": mo.bom.kind,
        "kind_label": mo.bom.get_kind_display(),
        "customer": mo.customer_id,
        "customer_name": mo.customer.name if mo.customer_id else "",
        "start_date": mo.start_date,
        "due_date": mo.due_date,
        "sales_order": mo.sales_order_id,
        "sales_order_number": mo.sales_order.number if mo.sales_order_id else "",
        "materials_from": mo.materials_from_id,
        "materials_from_name": mo.materials_from.name if mo.materials_from_id else "",
        "goods_to": mo.goods_to_id,
        "goods_to_name": mo.goods_to.name if mo.goods_to_id else "",
        "supervisor": mo.supervisor_id,
        "supervisor_name": mo.supervisor.name if mo.supervisor_id else "",
        "notes": mo.notes,
        "mrp": str(mo.mrp) if mo.mrp is not None else None,
        "usp": str(mo.usp) if mo.usp is not None else None,
        "usp_per": mo.usp_per_id,
        "usp_per_name": _short(mo.usp_per) if mo.usp_per_id else "",
        "batch_no": mo.batch_no,
        "pkd_date": mo.pkd_date,
        "best_before_value": mo.best_before_value,
        "best_before_unit": mo.best_before_unit,
        "expiry_date": mo.expiry_date,
        "packing_notes": mo.packing_notes,
        "cancel_reason": mo.cancel_reason,
        "created_by_name": mo.created_by.display_name if mo.created_by else "",
        "created_at": mo.created_at,
        "submitted_at": mo.submitted_at,
        "submitted_by_name": mo.submitted_by.display_name if mo.submitted_by else "",
        "closed_at": mo.closed_at,
    }
    if full:
        rows = _rows(mo)
        bom_rows = {r["item"].pk: r for r in bom_lines(mo.bom, mo.item, mo.qty, mo.unit_id)}
        for r in rows:
            if not r["from_bom"]:
                r["bom_note"] = "Added (not in BOM)"
            elif (b := bom_rows.get(r["item"].pk)) is None or b["per_unit"] != r["per_unit"]:
                r["bom_note"] = "BOM changed since"
        data.update(
            materials_out(mo.branch, mo.bom, mo.item, mo.qty, mo.unit_id, rows, mo, mo.customer)
        )
    return data


def _fresh(mo: MO) -> dict:
    return order_out(_orders(mo.company).get(pk=mo.pk))


# Saving ------------------------------------------------------------------------------


class AddedSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    unit = serializers.IntegerField()
    per_unit = serializers.DecimalField(max_digits=18, decimal_places=6)
    loss_pct = serializers.DecimalField(max_digits=7, decimal_places=3, required=False, default=0)


class OrderSerializer(serializers.Serializer):
    branch = serializers.IntegerField()
    order_date = serializers.DateField()
    item = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6)
    unit = serializers.IntegerField()
    bom = serializers.IntegerField(required=False, allow_null=True)
    customer = serializers.IntegerField(required=False, allow_null=True)
    start_date = serializers.DateField()
    due_date = serializers.DateField()
    sales_order = serializers.IntegerField(required=False, allow_null=True)
    materials_from = serializers.IntegerField(required=False, allow_null=True)
    goods_to = serializers.IntegerField(required=False, allow_null=True)
    supervisor = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    mrp = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    usp = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    usp_per = serializers.IntegerField(required=False, allow_null=True)
    batch_no = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    pkd_date = serializers.DateField(required=False, allow_null=True)
    best_before_value = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    best_before_unit = serializers.ChoiceField(
        choices=Item.PERIODS, required=False, default=Item.DAYS
    )
    expiry_date = serializers.DateField(required=False, allow_null=True)
    packing_notes = serializers.CharField(required=False, allow_blank=True, default="")
    added = AddedSerializer(many=True, required=False, default=list)
    submit = serializers.BooleanField(required=False, default=False)


def _added(mo: MO, rows: list[dict], kind: str) -> list[dict]:
    """Check the materials added on the order."""
    errors, out = [], []
    issued = {
        ln.item_id: ln.issued
        for ln in (mo.lines.filter(from_bom=False) if mo.pk else [])
        if ln.issued
    }
    for k, row in enumerate(rows, start=1):
        item = Item.objects.filter(pk=row["item"], is_active=True, maintain_stock=True).first()
        if item is None:
            errors.append(f"Added material {k}: pick a stock item from the list.")
            continue
        if item.pk == mo.item_id:
            errors.append(f"Added material {k}: an order cannot use the item it makes.")
            continue
        if item.default_request_type == Item.CUSTOMER_PROVIDED and kind != Bom.JOB_WORK:
            errors.append(
                f"Added material {k}: {item.name} is a customer's own goods: only a job work "
                "order may use it."
            )
            continue
        unit = ItemUnit.objects.filter(item=item, unit=row["unit"]).select_related("unit").first()
        if unit is None:
            errors.append(f"Added material {k}: pick one of the units of {item.name}.")
            continue
        if row["per_unit"] <= 0:
            errors.append(f"Added material {k} ({item.name}): the quantity must be more than 0.")
            continue
        loss = row.get("loss_pct") or ZERO
        if loss < 0 or loss >= HUNDRED:
            errors.append(f"Added material {k} ({item.name}): Loss % must be from 0 to below 100.")
            continue
        need = required(row["per_unit"], mo.qty, loss)
        if need < issued.get(item.pk, ZERO):
            errors.append(
                f"Added material {k} ({item.name}): {_plain(issued[item.pk])} is already issued; "
                "the order cannot need less."
            )
            continue
        out.append(
            {
                "item": item,
                "unit": unit.unit,
                "per_unit": row["per_unit"],
                "loss_pct": loss,
                "required": need,
                "from_bom": False,
            }
        )
    gone = set(issued) - {r["item"].pk for r in out}
    for item_id in gone:
        name = Item.objects.get(pk=item_id).name
        errors.append(f"{name} is already issued, so it cannot be taken off the order.")
    if errors:
        raise ValidationError({"added": errors})
    return out


def _pick(model, value, field: str, message: str, **where):
    if not value:
        return None
    found = model.objects.filter(pk=value, **where).first()
    if found is None:
        raise ValidationError({field: [message]})
    return found


# What a submitted order keeps (Sidharth, 2026-11-23): all but the Start Date,
# Supervisor, Notes and the added materials.
LOCKED = {
    "order_date": "Order Date",
    "customer_id": "Customer",
    "due_date": "Due Date",
    "sales_order_id": "Sales Order",
    "materials_from_id": "Materials From",
    "goods_to_id": "Goods Go To",
    "mrp": "MRP",
    "usp": "USP",
    "usp_per_id": "USP Per",
    "batch_no": "Batch No",
    "pkd_date": "Pkd Date",
    "best_before_value": "Best Before",
    "best_before_unit": "Best Before",
    "expiry_date": "Expiry Date",
    "packing_notes": "Packing Notes",
}


def _save(mo: MO, data: dict) -> None:
    company = mo.company
    fixed = mo.pk is not None and mo.status != MO.DRAFT
    before = {f: getattr(mo, f) for f in LOCKED} if fixed else {}
    branch = _branch(company, data["branch"], "branch")
    item = Item.objects.filter(pk=data["item"], is_active=True, maintain_stock=True).first()
    if item is None:
        raise ValidationError({"item": ["Pick a stock item from the list."]})
    unit = ItemUnit.objects.filter(item=item, unit=data["unit"]).select_related("unit").first()
    if unit is None:
        raise ValidationError({"unit": [f"Pick one of the units of {item.name}."]})
    qty = data["qty"]
    if qty <= 0:
        raise ValidationError({"qty": ["The quantity must be more than 0."]})
    if unit.whole_numbers and qty != qty.to_integral_value():
        raise ValidationError({"qty": [f"{item.name} is counted in whole {_short(unit.unit)}."]})
    choices = versions(item)
    if not choices:
        raise ValidationError({"item": [f"{item.name} has no active BOM. Make one first."]})
    bom = choices[0]
    if data.get("bom"):
        bom = next((b for b in choices if b.pk == data["bom"]), None)
        if bom is None:
            raise ValidationError({"bom": [f"Pick an active BOM version of {item.name}."]})
    if fixed and (
        branch.pk != mo.branch_id
        or item.pk != mo.item_id
        or qty != mo.qty
        or unit.unit_id != mo.unit_id
        or bom.pk != mo.bom_id
    ):
        raise ValidationError(
            {
                "detail": "A submitted order keeps its branch, item, quantity and BOM version. "
                "Close it and make a new one to change them."
            }
        )
    customer = None
    if bom.kind == Bom.JOB_WORK:  # the version's own customer, else the one picked
        customer = _pick(
            Party, bom.customer_id or data.get("customer"), "customer",
            "Pick a customer from the list.", customer_number__gt="",
        )  # fmt: skip
        if customer is None:
            raise ValidationError({"customer": ["A job work order needs the customer."]})
    if data["due_date"] < data["start_date"]:
        raise ValidationError({"due_date": ["The Due Date cannot be before the Start Date."]})
    so = _pick(
        SalesOrder, data.get("sales_order"), "sales_order", "Pick a sales order of this company.",
        company=company,
    )  # fmt: skip
    mo.branch, mo.item, mo.qty, mo.unit, mo.bom, mo.customer = (
        branch, item, qty, unit.unit, bom, customer,
    )  # fmt: skip
    mo.order_date = data["order_date"]
    mo.start_date, mo.due_date, mo.sales_order = data["start_date"], data["due_date"], so
    mo.materials_from = _area(branch, data.get("materials_from"), "materials_from")
    mo.goods_to = _area(branch, data.get("goods_to"), "goods_to")
    mo.supervisor = _pick(
        SalesPerson, data.get("supervisor"), "supervisor", "Pick a person from the list."
    )
    mo.notes = data.get("notes", "").strip()
    mo.mrp, mo.usp = data.get("mrp"), data.get("usp")
    mo.usp_per = _pick(Unit, data.get("usp_per"), "usp_per", "Pick a unit from the list.")
    if mo.usp is None:
        mo.usp_per = None
    mo.batch_no = data.get("batch_no", "").strip()
    mo.pkd_date = data.get("pkd_date")
    mo.best_before_value = data.get("best_before_value")
    mo.best_before_unit = data.get("best_before_unit") or Item.DAYS
    mo.expiry_date = data.get("expiry_date") or expiry(
        mo.pkd_date, mo.best_before_value, mo.best_before_unit
    )
    if mo.pkd_date and mo.expiry_date and mo.expiry_date < mo.pkd_date:
        raise ValidationError({"expiry_date": ["The Expiry Date cannot be before the Pkd Date."]})
    mo.packing_notes = data.get("packing_notes", "").strip()
    if fixed and (changed := [f for f in LOCKED if getattr(mo, f) != before[f]]):
        names = ", ".join(dict.fromkeys(LOCKED[f] for f in changed))
        raise ValidationError(
            {
                "detail": f"A submitted order keeps its {names}. Only the Start Date, "
                "Supervisor, Notes and added materials can change."
            }
        )
    added = _added(mo, data.get("added") or [], bom.kind)
    if fixed:
        fixed_rows = [r for r in _rows(mo) if r["from_bom"]]
    else:
        fixed_rows = bom_lines(bom, item, qty, unit.unit_id)
        for r in fixed_rows:
            if r["item"].default_request_type == Item.CUSTOMER_PROVIDED and customer is None:
                raise ValidationError({"bom": ["This version uses a customer's goods."]})
    clash = {r["item"].pk for r in fixed_rows} & {r["item"].pk for r in added}
    if clash:
        names = ", ".join(Item.objects.get(pk=i).name for i in clash)
        raise ValidationError({"added": [f"{names} is already on the order from the BOM."]})
    issued = {ln.item_id: ln.issued for ln in mo.lines.all()} if mo.pk else {}
    mo.save()
    mo.lines.all().delete()
    ManufacturingOrderLine.objects.bulk_create(
        [
            ManufacturingOrderLine(
                order=mo,
                position=n,
                item=r["item"],
                unit=r["unit"],
                per_unit=r["per_unit"],
                loss_pct=r["loss_pct"],
                required=r["required"],
                issued=issued.get(r["item"].pk, ZERO),
                from_bom=r["from_bom"],
            )
            for n, r in enumerate([*fixed_rows, *added], start=1)
        ]
    )


def _submit(mo: MO, user) -> None:
    if not may(user, "submit"):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    attachments.require_file(mo, KIND)
    mo.number = numbering.next_document_number(mo.company, KIND, mo.order_date, mo.branch)
    mo.status = MO.NOT_STARTED
    mo.submitted_at = timezone.now()
    mo.submitted_by = user
    mo.save()


def _order(request, pk: int, lock: bool = False) -> MO:
    rows = MO.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    mo = rows.select_related("company", "branch").first()
    if mo is None or "production" not in mo.company.modules:
        raise NotFound("No such manufacturing order.")
    return mo


# Views -----------------------------------------------------------------------------------


class OrderListView(APIView):
    """GET ?view=draft|open|completed|closed|cancelled|all&q=text&branch=ID.
    POST: a new draft (with "submit": true, submitted at once)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        rows = _orders(company)
        view = request.query_params.get("view", "all")
        if view == "open":
            rows = rows.filter(status__in=MO.OPEN)
        elif view in dict(MO.STATUSES):
            rows = rows.filter(status=view)
        if branch := request.query_params.get("branch"):
            rows = rows.filter(branch=branch)
        if item := request.query_params.get("item"):
            rows = rows.filter(item=item)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(item__name__icontains=word)
                | Q(batch_no__icontains=word)
                | Q(notes__icontains=word)
            )
        return Response([order_out(mo, full=False) for mo in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        company = _company(request, pk)
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        mo = MO(company=company, created_by=request.user)
        _save(mo, data)
        if data.get("submit"):
            _submit(mo, request.user)
        return Response(_fresh(mo), status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    """GET one order; PATCH it (a draft fully; an open order only its added
    materials, Pack Details, dates, places and notes)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(_fresh(_order(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, "create")
        mo = _order(request, pk, lock=True)
        if mo.status not in (MO.DRAFT, *MO.OPEN):
            raise ValidationError(
                {"detail": f"A {mo.get_status_display().lower()} order cannot change."}
            )
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(mo, data)
        if data.get("submit") and mo.status == MO.DRAFT:
            _submit(mo, request.user)
        return Response(_fresh(mo))


class OrderSubmitView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        mo = _order(request, pk, lock=True)
        if mo.status != MO.DRAFT:
            raise ValidationError({"detail": "This order is not a draft."})
        _submit(mo, request.user)
        return Response(_fresh(mo))


class OrderCancelView(APIView):
    """POST {reason}: only while nothing has been issued or made."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "cancel")
        mo = _order(request, pk, lock=True)
        if mo.status not in (MO.DRAFT, *MO.OPEN):
            raise ValidationError({"detail": "Only a draft or an open order can be cancelled."})
        if mo.made_qty or mo.lines.filter(issued__gt=0).exists():
            raise ValidationError(
                {"detail": 'Materials are already issued: use "Close MO" instead.'}
            )
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        mo.status, mo.cancel_reason = MO.CANCELLED, reason[:200]
        mo.save()
        return Response(_fresh(mo))


class OrderCloseView(APIView):
    """POST: end an open order made short; the rest is no longer planned."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        mo = _order(request, pk, lock=True)
        if mo.status not in MO.OPEN:
            raise ValidationError({"detail": "Only a submitted order still open can be closed."})
        mo.status, mo.closed_at = MO.CLOSED, timezone.now()
        mo.save()
        return Response(_fresh(mo))


class OrderMaterialsView(APIView):
    """GET ?item=&bom=&qty=&unit=&branch=&customer=: the materials, by-products and
    cost a draft would have (the form shows them as the fields change)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        p = request.query_params
        item = Item.objects.filter(pk=p.get("item") or 0).select_related("stock_unit").first()
        if item is None:
            raise ValidationError({"item": ["Pick an item."]})
        choices = versions(item)
        bom = next(
            (b for b in choices if str(b.pk) == p.get("bom")), choices[0] if choices else None
        )
        if bom is None:
            return Response({"lines": [], "byproducts": [], "cost": None, "bom": None})
        unit_id = int(p.get("unit") or item.stock_unit_id)
        try:
            qty = Decimal(p.get("qty") or "0")
        except ArithmeticError:
            qty = ZERO
        branch = company.branches.filter(pk=p.get("branch") or 0, no_stock=False).first()
        customer = Party.objects.filter(pk=p.get("customer") or 0).first()
        rows = bom_lines(bom, item, qty, unit_id) if qty > 0 else []
        out = materials_out(branch, bom, item, qty or Decimal(1), unit_id, rows, None, customer)
        out["bom"] = bom.pk
        return Response(out)


class OrderFormView(APIView):
    """GET: what the form offers: stock branches and their areas, people, the
    items that have an active BOM (with their versions, units and Pack
    Details), stock items for added materials, customers, units, and the
    company's open sales orders."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        branches = list(company.branches.filter(no_stock=False).order_by("name"))
        areas = (
            WarehouseLocation.objects.filter(branch__company=company, kind=WarehouseLocation.AREA)
            .exclude(purpose=TRANSIT)
            .order_by("name")
        )
        boms = (
            Bom.objects.filter(status=Bom.ACTIVE, is_active=True)
            .select_related("makes_unit")
            .order_by("-is_default", "version")
        )
        by_item: dict[int, list[Bom]] = {}
        for b in boms:
            by_item.setdefault(b.item_id, []).append(b)
        stock_items = list(
            Item.objects.filter(is_active=True, maintain_stock=True)
            .select_related("stock_unit")
            .prefetch_related("units__unit")
            .order_by("name")
        )

        def units(i):
            return [
                {"unit": u.unit_id, "name": _short(u.unit), "whole_numbers": u.whole_numbers,
                 "factor": _plain(u.factor)}
                for u in i.units.all()
            ]  # fmt: skip

        return Response(
            {
                "branches": [
                    {
                        "id": b.pk,
                        "name": b.name,
                        "is_active": b.is_active,
                        "areas": [
                            {"id": a.pk, "name": a.name, "is_active": a.is_active}
                            for a in areas
                            if a.branch_id == b.pk
                        ],
                    }
                    for b in branches
                ],
                "people": [
                    {"id": p.pk, "name": p.name}
                    for p in SalesPerson.objects.filter(is_active=True).order_by("name")
                ],
                "makes": [
                    {
                        "id": i.pk,
                        "name": i.name,
                        "item_number": i.item_number,
                        "stock_unit": i.stock_unit_id,
                        "sales_unit": i.sales_unit_id,
                        "units": units(i),
                        "mrp": str(i.mrp) if i.mrp is not None else None,
                        "usp": str(i.usp) if i.usp is not None else None,
                        "usp_per": i.usp_per_id,
                        "batch_no": i.batch_no,
                        "best_before_value": i.best_before_value,
                        "best_before_unit": i.best_before_unit,
                        "versions": [
                            {
                                "id": b.pk,
                                "number": b.number,
                                "version": b.version,
                                "name": b.name,
                                "is_default": b.is_default,
                                "kind": b.kind,
                                "customer": b.customer_id,
                                "packing_notes": b.packing_notes,
                            }
                            for b in by_item[i.pk]
                        ],
                    }
                    for i in stock_items
                    if i.pk in by_item
                ],
                "materials": [
                    {
                        "id": i.pk,
                        "name": i.name,
                        "item_number": i.item_number,
                        "stock_unit": i.stock_unit_id,
                        "customer_goods": i.default_request_type == Item.CUSTOMER_PROVIDED,
                        "units": units(i),
                    }
                    for i in stock_items
                ],
                "customers": [
                    {"id": p.pk, "name": p.name}
                    for p in Party.objects.exclude(customer_number="").order_by("name")
                ],
                "units": [{"id": u.pk, "name": _short(u)} for u in Unit.objects.order_by("name")],
                "sales_orders": [
                    {"id": so.pk, "number": so.number, "customer_name": so.customer.name}
                    for so in SalesOrder.objects.filter(company=company, status__in=SalesOrder.OPEN)
                    .select_related("customer")
                    .order_by("-id")[:300]
                ],
            }
        )


class OrderPdfView(APIView):
    """GET (&download=1): the Manufacturing Order print (batch sheet): what to
    make, the Pack Details, the materials and the expected by-products."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from core import printout

        _check(request, "view")
        data = _fresh(_order(request, pk))

        def d(day):
            return day.strftime("%d-%m-%Y") if day else ""

        scope = " · ".join(
            x
            for x in [
                data["branch_name"],
                f"{data['item_name']}: {data['qty']} {data['unit_name']}",
                f"BOM {data['bom_number']} v{data['bom_version']}",
                data["customer_name"] and f"Job work for {data['customer_name']}",
                f"Start {d(data['start_date'])}, due {d(data['due_date'])}",
            ]
            if x
        )
        usp = ""
        if data["usp"]:
            usp = f"₹ {data['usp']}" + (
                f" per {data['usp_per_name']}" if data["usp_per_name"] else ""
            )
        best = ""
        if data["best_before_value"]:
            best = f"{data['best_before_value']} {data['best_before_unit'].title()}"
        pack = {
            "title": "Pack Details",
            "columns": ["MRP ₹", "USP", "Batch No", "Pkd Date", "Best Before", "Expiry Date"],
            "rows": [
                [
                    data["mrp"] or "", usp, data["batch_no"], d(data["pkd_date"]), best,
                    d(data["expiry_date"]),
                ]
            ],
        }  # fmt: skip
        mats = {
            "title": "Materials",
            "columns": [
                "#",
                "Item",
                f"Per {data['unit_name']}",
                "Loss %",
                "Required",
                "Unit",
                "Comes From",
                "Issued",
            ],  # fmt: skip
            "rows": [
                [
                    str(ln["position"]),
                    ln["item_name"] + ("" if ln["from_bom"] else " (added)"),
                    ln["per_unit"],
                    ln["loss_pct"],
                    ln["required"],
                    ln["unit_name"],
                    ln["source_text"],
                    ln["issued"],
                ]
                for ln in data["lines"]
            ],  # fmt: skip
        }
        sheets = [pack, mats]
        if data["byproducts"]:
            sheets.append(
                {
                    "title": "By-products and Scrap (expected)",
                    "columns": ["Item", "Expected", "Unit", "Kind"],
                    "rows": [
                        [b["item_name"], b["qty"], b["unit_name"], b["kind_label"]]
                        for b in data["byproducts"]
                    ],
                }
            )
        notes = "\n".join(
            x
            for x in [
                data["packing_notes"] and f"Packing Notes: {data['packing_notes']}",
                data["notes"] and f"Notes: {data['notes']}",
            ]
            if x
        )
        if notes:
            sheets.append({"title": "Notes", "columns": ["Notes"], "rows": [[notes]]})
        title = f"Manufacturing Order {data['number'] or 'Draft'}"
        response = printout.pdf_response(title, scope, sheets, data["number"] or KIND)
        if request.query_params.get("download") != "1":
            response["Content-Disposition"] = response["Content-Disposition"].replace(
                "attachment", "inline"
            )
        return response
