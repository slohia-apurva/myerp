"""What a role can be allowed to do.

The list of permissions is code (each module adds its own); which role gets
which permission is data in the tenant's database, edited on the Roles screen.
"""

from dataclasses import dataclass

from rest_framework.permissions import BasePermission


@dataclass(frozen=True)
class Area:
    code: str
    label: str
    actions: tuple[tuple[str, str], ...]


DOCUMENT_ACTIONS = (
    ("view", "View"),
    ("create", "Create and edit drafts"),
    ("submit", "Submit"),
    ("cancel", "Cancel and amend"),
)

AREAS = (
    Area("users", "Users and roles", (("manage", "Add, edit and deactivate users"),)),
    Area("masters", "Masters", (("view", "View"), ("edit", "Create and edit"))),
    Area("accounts", "Accounts", DOCUMENT_ACTIONS),
    Area("stock", "Stock", DOCUMENT_ACTIONS),
    Area("purchase", "Purchase", DOCUMENT_ACTIONS),
    Area("sales", "Sales", DOCUMENT_ACTIONS),
    Area("production", "Production", DOCUMENT_ACTIONS),
    Area("quality", "Quality and food safety", DOCUMENT_ACTIONS),
    Area("payroll", "Payroll and staff", (("view", "View"), ("manage", "Run payroll"))),
    Area("reports", "Reports and dashboards", (("view", "View"),)),
    Area("approvals", "Approvals", (("approve", "Approve documents sent for approval"),)),
)

ALL = frozenset(f"{a.code}.{action}" for a in AREAS for action, _ in a.actions)


def catalogue() -> list[dict]:
    return [
        {
            "code": a.code,
            "label": a.label,
            "permissions": [
                {"code": f"{a.code}.{action}", "label": label} for action, label in a.actions
            ],
        }
        for a in AREAS
    ]


def clean(codes) -> list[str]:
    """Known permission codes only, sorted and without repeats."""
    unknown = set(codes) - ALL
    if unknown:
        raise ValueError(f"Unknown permissions: {', '.join(sorted(unknown))}")
    return sorted(set(codes))


def requires(code: str) -> type[BasePermission]:
    """DRF permission class: the signed-in user's roles must grant `code`."""
    assert code in ALL, code

    class Requires(BasePermission):
        message = "Your role does not allow this."

        def has_permission(self, request, view):
            user = request.user
            return bool(user and user.is_authenticated and user.can(code))

    Requires.__name__ = f"Requires_{code.replace('.', '_')}"
    return Requires
