"""When an insurance policy counts as in use (core.locks): once an order names it."""

from core import locks


def _orders(policy) -> str:
    from buying.models import PurchaseOrder

    return locks._count(PurchaseOrder.objects.filter(insurance_policy=policy), "purchase order")


locks.register("insurance_policy", _orders)
