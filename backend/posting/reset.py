"""GL entries and stock moves count as entries for the Owner's "Reset data"
tool. The database refuses to delete posted rows unless the reset says so for
its own transaction (migration 0001)."""

from django.db import connections

from core.data_reset import register_entries
from posting.models import GLEntry, StockLot, StockLotUse, StockMove, StockRevaluation
from tenancy.context import require_tenant


def _of(model, company):
    rows = model.objects.all()
    return rows.filter(company=company) if company else rows


def _count(company) -> int:
    return _of(GLEntry, company).count() + _of(StockMove, company).count()


def _delete(company) -> None:
    with connections[require_tenant().db_alias].cursor() as cursor:
        cursor.execute("SET LOCAL myerp.purge_postings = 'on'")
    moves = _of(StockMove, company)
    StockLotUse.objects.filter(move__in=moves).delete()
    _of(StockRevaluation, company).delete()
    _of(StockLot, company).delete()
    moves.delete()
    _of(GLEntry, company).delete()
    with connections[require_tenant().db_alias].cursor() as cursor:
        cursor.execute("SET LOCAL myerp.purge_postings = 'off'")


register_entries("GL entries and stock moves", _count, _delete)
