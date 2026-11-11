"""When a courier account counts as in use (core.locks)."""

from core import locks


def _account_uses(account) -> str:
    return locks._count(account.shipments.all(), "shipment")


locks.register("courier_account", _account_uses)
