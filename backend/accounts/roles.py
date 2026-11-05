"""Standard roles every tenant starts with. Tenants can change all of them
except Owner, and add their own."""

OWNER = "owner"


def _all(area: str) -> list[str]:
    return [f"{area}.{a}" for a in ("view", "create", "submit", "cancel")]


def _view(*areas: str) -> list[str]:
    return [f"{a}.view" for a in areas]


STANDARD_ROLES = [
    # (code, name, description, permissions). Owner's permissions are not
    # stored: an Owner can always do everything.
    (OWNER, "Owner", "Everything, including users, roles and approvals. Cannot be changed.", []),
    (
        "accountant",
        "Accountant",
        "Books, banks, GST and TDS; sees purchase and sales",
        ["masters.view", "masters.edit", *_all("accounts"), *_view("purchase", "sales", "stock")]
        + ["reports.view"],
    ),
    (
        "sales",
        "Sales",
        "Quotations, orders, dispatch and invoices",
        ["masters.view", *_all("sales")[:3], *_view("stock"), "reports.view"],
    ),
    (
        "purchase",
        "Purchase",
        "Requests, purchase orders and supplier bills",
        ["masters.view", *_all("purchase")[:3], *_view("stock"), "reports.view"],
    ),
    (
        "storekeeper",
        "Storekeeper",
        "Receipts, issues, transfers, counts and dispatch",
        ["masters.view", *_all("stock")[:3], *_view("purchase", "sales")],
    ),
    (
        "production",
        "Production supervisor",
        "Work orders, job cards and production entries",
        ["masters.view", *_all("production")[:3], *_view("stock", "quality")],
    ),
    (
        "quality",
        "Quality",
        "Checklists, inspections, batch release and CAPA",
        ["masters.view", *_all("quality")[:3], *_view("stock", "production", "purchase")],
    ),
    (
        "viewer",
        "Viewer",
        "Can see everything except payroll; changes nothing",
        [
            "masters.view",
            *_view("accounts", "stock", "purchase", "sales", "production", "quality"),
            "reports.view",
        ],
    ),
]


def create_missing_standard_roles(Role) -> None:
    """Adds any standard role the tenant does not have yet. Never overwrites
    a role the tenant has edited. `Role` is passed in so migrations can use
    their historical model."""
    for code, name, description, perms in STANDARD_ROLES:
        if not Role.objects.filter(code=code).exists():
            Role.objects.create(
                code=code,
                name=name,
                description=description,
                permissions=sorted(set(perms)),
                is_standard=True,
            )
