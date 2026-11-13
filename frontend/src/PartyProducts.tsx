import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Combobox } from "./Combobox";
import { Section } from "./Brand";

export type PartyProduct = {
  item: number;
  item_number?: string;
  item_name?: string;
  item_active?: boolean;
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
}: {
  value: PartyProduct[];
  onChange: (rows: PartyProduct[]) => void;
  supplier: boolean;
  canEdit: boolean;
}) {
  const [items, setItems] = useState<ItemRow[]>([]);
  useEffect(() => {
    api<ItemRow[]>("v1/items/").then(setItems);
  }, []);
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
        {canEdit && (
          <label>
            Add Product
            <Combobox
              options={options}
              value=""
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
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={3} className="small">
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
      </Section>
    </>
  );
}
