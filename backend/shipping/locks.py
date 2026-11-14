"""When a courier account counts as in use (core.locks)."""

from core import locks


def _account_uses(account) -> str:
    return locks._count(account.shipments.all(), "shipment")


def _preferred_by(side: str):
    return lambda account: locks._count(account.preferred_by.filter(party_side=side), side)


locks.register("courier_account", _account_uses)
locks.register("courier_account", _preferred_by("customer"))
locks.register("courier_account", _preferred_by("supplier"))
