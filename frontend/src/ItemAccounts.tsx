import { useEffect, useState } from "react";
import { api } from "./api";
import { Combobox } from "./Combobox";
import { useReturns } from "./Refresh";

/** An item's own "Expense Account" in each company (Sidharth, 2026-11-16, preview 82): where a
 * purchase bill without goods receipt books the item. Empty uses the item group's
 * COGS/Expense ledger. */
export type ItemAccount = { company: number; company_name: string; expense_ledger: number | null; expense_ledger_name: string; group_ledger_name: string };
type LedgerRow = { id: number; name: string; is_active: boolean; nature?: string; party?: unknown };

export function useItemAccounts(itemId: number | null) {
  const [rows, setRows] = useState<ItemAccount[] | null>(null);
  useEffect(() => {
    if (!itemId) return;
    api<ItemAccount[]>(`v1/items/${itemId}/accounts/`).then(setRows, () => setRows(null));
  }, [itemId]);
  return [rows, setRows] as const;
}

export const saveItemAccounts = (itemId: number, rows: ItemAccount[]) =>
  api(
    `v1/items/${itemId}/accounts/`,
    rows.map((r) => ({ company: r.company, expense_ledger: r.expense_ledger })),
    "PUT",
  );

export const accountsSummary = (rows: ItemAccount[] | null) => {
  const own = (rows ?? []).filter((r) => r.expense_ledger);
  return own.length ? [...new Set(own.map((r) => r.expense_ledger_name))].join(", ") : "From item group";
};

/** The table on the item form: one row per company, its expense ledgers to pick from. */
export function ItemAccountsEditor(props: { rows: ItemAccount[]; onChange: (rows: ItemAccount[]) => void }) {
  const [ledgers, setLedgers] = useState<Record<number, LedgerRow[]>>({});
  const companies = props.rows.map((r) => r.company).join(",");
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  useEffect(() => {
    for (const id of companies.split(",").filter(Boolean).map(Number)) {
      // Only expense ledgers that are not customers or suppliers, picked on the server (2026-11-26).
      api<LedgerRow[]>(`v1/companies/${id}/ledgers/?lean=1&nature=expense&party=0`).then((rows) =>
        setLedgers((all) => ({ ...all, [id]: rows })),
      );
    }
  }, [companies, visits]);
  const set = (company: number, value: string) =>
    props.onChange(
      props.rows.map((r) =>
        r.company === company
          ? { ...r, expense_ledger: value ? Number(value) : null, expense_ledger_name: (ledgers[company] ?? []).find((l) => String(l.id) === value)?.name ?? "" }
          : r,
      ),
    );
  return (
    <>
      <table className="grid">
        <thead>
          <tr>
            <th>Company</th>
            <th>Expense Account</th>
          </tr>
        </thead>
        <tbody>
          {props.rows.map((r) => (
            <tr key={r.company}>
              <td>{r.company_name}</td>
              <td>
                <Combobox
                  value={r.expense_ledger ? String(r.expense_ledger) : ""}
                  empty={r.group_ledger_name ? `From item group: ${r.group_ledger_name}` : "From item group (not set)"}
                  options={(ledgers[r.company] ?? [])
                    .filter((l) => l.is_active || l.id === r.expense_ledger)
                    .map((l) => ({ value: String(l.id), label: l.name }))}
                  onChange={(v) => set(r.company, v)}
                  ariaLabel={`Expense Account for ${r.company_name}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">
        The ledger a purchase bill without goods receipt books this item to. Only expense ledgers are offered. Left empty, the item group's COGS/Expense ledger
        is used. Items kept in stock go to stock as now.
      </p>
    </>
  );
}
