# 0021. Customer and vendor numbers

Date: 9 Nov 2026. Asked by Sidharth: "For customers and vendors there should be a customer number and for vendor a vendor number".

## Decision

- `core.Party` gets `customer_number` and `vendor_number`, each unique across the group when filled. A party that a company holds under Sundry Debtors is a customer; under Sundry Creditors, a vendor. One party can be both (a customer of one company, a vendor of another), so it has both numbers.
- The number is given on Save the first time a ledger makes the party a customer or vendor, and never changes after. It is shown on the party form, in the "Existing customer or supplier" picker and the party summary, searched from the Ledgers list, and logged in the Activity.
- Numbers come from `core.NumberSeries` (`customer`, `vendor`), one row per kind for the whole group: prefix plus a zero-padded count (`CUST-00001`, `VEND-00001`), allocated under a row lock. A number typed by hand is upper-cased, must be unique, and is skipped by the counter. A blank value on Save keeps the number the party has.
- Migration 0017 numbers existing parties in order of creation.

## Later

The numbering master (prefix, width, restart rules for vouchers and documents) will make the prefix editable; until then the defaults above apply.
