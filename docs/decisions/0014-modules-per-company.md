# 0014. Modules are chosen per company

Date: 5 Nov 2026. Asked for by Sidharth.

## Decision

Each company has a list of the modules it uses (`Company.modules`, codes from `core/modules.py`). The tenant's Owner ticks them on the company page. A trading company leaves out Production; a service company can leave out Stock.

- Accounts is always on.
- Some modules need others: Production and Quality need Stock; Point of sale needs Sales and Stock. The check refuses a choice that breaks this.
- New and existing companies start with every module on, so nothing disappears until the Owner unticks it.
- Only an Owner can change the list; other roles see it.

## Later

- Menus, screens and APIs of a module that is off are hidden or refused for that company, as each module is built.
- Turning a module off once it has documents is refused (its data must stay reachable for reports and audit).
- SaaS: the tenant's plan caps which modules can be ticked and how many companies a tenant may have (platform admin console, Phase 10).
