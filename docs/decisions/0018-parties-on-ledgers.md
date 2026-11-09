# 0018. Customers and suppliers are ledgers with party details

Date: 9 Nov 2026. Chosen by Sidharth as the next masters piece.

## Decision

A customer or supplier is a ledger under Sundry Debtors or Sundry Creditors (or a group under them), as in Tally. What a ledger alone does not hold is kept in `core.Party`, one per such ledger, edited on the same ledger form and saved with it:

- GST type (regular, composition, unregistered business, consumer, SEZ, overseas), GSTIN, PAN, state (place of supply) or country for overseas parties.
- Credit limit (0 = none) and credit terms (decision 0019); the salesman (a MyERP user) who looks after the customer.
- Any number of addresses (`core.PartyAddress`), each with its own state and, for parties registered in several states, its own GSTIN under the same PAN. One default billing and one default shipping address.
- Any number of contacts (`core.PartyContact`): name, designation, phone, email, with one ticked as the main contact (Sidharth, 9 Nov 2026).

On the form, the party details are split into tabs: "GST and credit", "Addresses", "Contacts" and "Opening balance" (the bill-by-bill opening balances, which other ledgers show as their own section).

Checks: a registered type needs a GSTIN; the GSTIN fixes the PAN and state and must agree with them; unregistered types cannot carry a GSTIN; overseas parties have a country other than India and no state. A party ledger saved without details starts as an unregistered business in the company's state.

Party changes appear in the ledger's own Activity entries (decision 0016).

## Later

- TDS section on suppliers once TDS sections exist as dated master data.
- Price list and approved items per customer, for the salesman app.
- GSTIN lookup from the GST database through a GSP fills these fields.
- Credit limit enforcement on sales orders (rule 15, approvals).
