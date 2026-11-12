"""Import, export and print (core/exchange.py) for the masters kept per
company on the company screens: Ledger groups, Branches, and Licences and
certificates. Each saves through the same function as its screen."""

from core import exchange
from core.api import (
    BranchSerializer,
    CertificateSerializer,
    LedgerGroupSerializer,
    save_branch,
    save_certificate,
    save_ledger_group,
)
from core.models import Branch, Certificate

exchange.register(
    exchange.Master(
        key="ledger-groups",
        label="Ledger groups",
        noun="ledger group",
        serializer=LedgerGroupSerializer,
        # Oldest first, so a group always comes after the group it sits under.
        queryset=lambda ctx: ctx.company.ledger_groups.select_related("parent").order_by("id"),
        save=lambda ctx, group, data: save_ledger_group(ctx.company, group, data),
        per_company=True,
        show=("nature", "schedule_iii", "is_standard"),
        labels={
            "parent": "Under group",
            "schedule_iii": "Schedule III head",
            "is_standard": "Standard",
        },
        hints={
            "parent": "The name of the group it sits under. List a new group after its parent.",
            "name": "Standard groups come with MyERP and cannot be renamed or moved; "
            "add your own under them",
        },
    )
)

exchange.register(
    exchange.Master(
        key="branches",
        label="Branches",
        noun="branch",
        serializer=BranchSerializer,
        queryset=lambda ctx: ctx.company.branches.order_by("-is_head_office", "name"),
        save=lambda ctx, branch, data: save_branch(branch or Branch(company=ctx.company), data),
        per_company=True,
        show=("is_head_office",),
        codecs={"state_code": exchange.STATE},
        labels={
            "state_code": "State",
            "gstin": "GSTIN",
            "is_head_office": "Head office",
            "default_billing": "Default billing",
            "default_ship_to": "Default ship to",
            "default_ship_from": "Default ship from",
        },
        hints={
            "gstin": "Leave empty when the branch uses the company's GSTIN",
            "default_billing": "One branch of the company has each default; "
            "tick it on another branch to move it",
        },
        report=("name", "state_code", "gstin", "city", "pincode", "phone", "is_active"),
    )
)

exchange.register(
    exchange.Master(
        key="certificates",
        label="Licences and certificates",
        noun="certificate",
        serializer=CertificateSerializer,
        queryset=lambda ctx: ctx.company.certificates.select_related("branch").order_by(
            "kind", "valid_until"
        ),
        save=lambda ctx, cert, data: save_certificate(
            cert or Certificate(company=ctx.company), data
        ),
        per_company=True,
        labels={"kind": "Certificate", "branch": "Branch"},
        hints={
            "branch": "Leave empty when it covers the whole company",
            "valid_until": "Leave empty when it never expires",
        },
    )
)
