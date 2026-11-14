"""The default store of a branch that holds stock. Every branch holds stock unless it is
ticked "No stock", and goods need a place even in a simple office with no racks or bins,
so a stock-holding branch always has one storage area marked as its default (Sidharth,
2026-11-14). Stock entries use it when no other rack, bin or area is chosen; receipts go
to the branch's Receiving area first, if it has one."""

from core.models import Branch, WarehouseLocation


def sync_default_store(branch: Branch) -> None:
    """Make sure a stock-holding branch has its active default store, and that a branch
    ticked "No stock" has none in use. Safe to call after every save of a branch."""
    L = WarehouseLocation
    store = L.objects.filter(branch=branch, is_default=True).first()
    if branch.no_stock:
        if store is not None and store.is_active:
            store.is_active = False
            store.save(update_fields=["is_active"])
        return
    if store is not None:
        if not store.is_active:
            store.is_active = True
            store.save(update_fields=["is_active"])
        return
    name = f"{branch.name} Store"[:60]
    if L.objects.filter(
        branch=branch, kind=L.AREA, parent__isnull=True, name__iexact=name
    ).exists():
        name = f"{name[:50]} (default)"
    L.objects.create(branch=branch, kind=L.AREA, name=name, purpose="storage", is_default=True)
