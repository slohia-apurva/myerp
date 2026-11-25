import { useMemo } from "react";
import { Combobox } from "./Combobox";
import { Section } from "./Brand";
import { usePrintMenu } from "./Exchange";
import { useReturns } from "./Refresh";
import { useItemSearch } from "./ItemSearch";

export type PartyProduct = {
  item: number;
  item_number?: string;
  item_name?: string;
  item_active?: boolean;
  /** What this party calls the item; kept on the item and shown here read only. */
  their_name?: string;
  their_code?: string;
};

type ItemRow = { id: number; item_number: string; name: string; is_active: boolean };

/** The "Products" tab of a customer or supplier: the items that may be sold
 * to the customer, or bought from the supplier. An empty list means any item;
 * a list means only these (plus items ticked "Offer to all"). No prices here. */
export function PartyProducts({
  value,
  onChange,
  supplier,
  canEdit,
  partyName,
}: {
  value: PartyProduct[];
  onChange: (rows: PartyProduct[]) => void;
  supplier: boolean;
  canEdit: boolean;
  partyName?: string;
}) {
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  // Asked from the server as the person types (ItemSearch.ts), plus the items
  // already listed: the whole catalogue is 12,457 items on staging.
  const { items, onType } = useItemSearch<ItemRow>(
    "v1/items/",
    value.map((r) => r.item),
    visits,
  );
  const byId = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);
  const listed = new Set(value.map((r) => r.item));
  const options = items
    .filter((i) => i.is_active && !listed.has(i.id))
    .map((i) => ({ value: String(i.id), label: `${i.item_number} · ${i.name}` }));
  const verb = supplier ? "bought from this supplier" : "sold to this customer";
  const rows = value.map((r) => {
    const live = byId.get(r.item);
    return {
      ...r,
      number: live?.item_number ?? r.item_number ?? "",
      name: live?.name ?? r.item_name ?? "",
      active: live ? live.is_active : (r.item_active ?? true),
    };
  });
  // The table sits inside the party's form, so the print sheet is given directly:
  // item number, item name and what this party calls it, for a customer-wise or supplier-wise list.
  const printing = usePrintMenu({
    title: `Items of ${partyName || (supplier ? "supplier" : "customer")}`,
    scope: supplier ? "Supplier's item list" : "Customer's item list",
    read: () => [
      {
        title: "Products",
        columns: ["Item No", "Item Name", "Their Item Name", "Their Item Code"],
        rows: rows.map((r) => [r.number, r.name, r.their_name ?? "", r.their_code ?? ""]),
      },
    ],
  });
  return (
    <>
      <Section>
        {value.length === 0 ? (
          <>
            <strong>No products listed.</strong> Any item can be {verb}.
            <br />
            Add products below to limit this {supplier ? "supplier" : "customer"} to those items only.
          </>
        ) : (
          <>
            <strong>Only the products listed here</strong> can be {verb}. Other items will not be offered on
            quotations, orders or bills for this {supplier ? "supplier" : "customer"}.
            <br />
            Remove every row to allow any item again.
          </>
        )}
      </Section>
      <Section title={`Products (${value.length} listed)`}>
        <div className="page-head">
          <span />
          {printing.buttons}
        </div>
        {printing.panel}
        {canEdit && (
          <label>
            Add Product
            <Combobox
              options={options}
              value=""
              onType={onType}
              placeholder="Type to search items…"
              ariaLabel="Add product"
              onChange={(v) => {
                const id = Number(v);
                if (id) onChange([...value, { item: id }]);
              }}
            />
          </label>
        )}
        <table>
          <thead>
            <tr>
              <th>Item No</th>
              <th>Item Name</th>
              <th>Their Item Name</th>
              <th>Their Item Code</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="small">
                  Nothing added. Any item is allowed.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.item} className={r.active ? "" : "inactive"}>
                <td>{r.number}</td>
                <td>
                  {r.name} {!r.active && <span className="pill">Disabled: stays off</span>}
                </td>
                <td>{r.their_name}</td>
                <td>{r.their_code}</td>
                <td>
                  {canEdit && (
                    <button
                      type="button"
                      className="link danger"
                      onClick={() => onChange(value.filter((x) => x.item !== r.item))}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small">
          Their item name and code are changed on the item, under "Customer And Supplier Names".{" "}
          <a href="#/items" target="_blank" rel="noreferrer">
            Open the items
          </a>{" "}
          (new tab).
        </p>
      </Section>
    </>
  );
}
