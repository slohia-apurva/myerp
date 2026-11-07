# 0016. Audit log of master changes

Date: 7 Nov 2026. Chosen by Sidharth as the next masters piece.

## Decision

Every add, change and delete of a master is written to `audit.AuditEntry` in the tenant's database: who, when, which record, and each changed field's old and new value as the screen shows it (state names, group names, "Yes"/"No").

- Model signals do the recording (`audit/recorder.py`), so new screens are covered without extra code. Tracked now: company, branch, licence/certificate, ledger group, ledger, user, role. A new master is added to `TRACKED`.
- One request = one entry per record. A save that changes the record twice, or changes things beside it (a ledger's opening bills, a user's roles and companies), is merged into one entry compared with the record before the request. Saves that change nothing write nothing; failed saves roll back with their entry.
- `QuerySet.update()` and `bulk_create()` skip signals, so code must save tracked masters one by one (the branch default move does).
- What MyERP creates for a new company (head office, standard groups, Cash ledger) is not logged; the company's own entry is.
- Entries cannot be edited or deleted through the model; there is no API to do so.
- Company masters' log needs `masters.view` and access to that company; the users and roles log needs `users.manage`.

## Later

- Vouchers do not use this: posted entries are immutable and keep their own cancel/amend trail (rule 2).
- A database-level guard (trigger) against UPDATE/DELETE on the table, if the log must stand up to someone with direct database access.
- Reports on the log (by user, by date range) when the report framework exists.
