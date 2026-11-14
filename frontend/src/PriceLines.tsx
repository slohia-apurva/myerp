import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Combobox } from "./Combobox";
import { type Item } from "./Items";
import { unitLabel, useUnits, type Unit } from "./Units";

/** One rate: an item (or, on an item's own page, a customer) in one unit, from a
 * quantity, from a date. Shared by price lists, a customer's Item Prices and an
 * item's Customer Prices (Sidharth, 2026-11-14). */
export type PriceRow = {
  item: number | null;
  party?: number | null;
  unit: number | null;
  min_qty: string;
  rate: string;
  from_date: string;
  item_name?: string;
  party_name?: string;
  unit_label?: string;
};

export type PartyOption = { id: number; name: string; customer_number: string };

const today = () => new Date().toISOString().slice(0, 10);

export const blankRow = (item: number | null, unit: number | null, party: number | null = null): PriceRow => ({
  item,
  party,
  unit,
  min_qty: "1",
  rate: "",
  from_date: today(),
});

/** A saved line as the form holds it (quantities without trailing zeros). */
export const rowFromServer = (r: PriceRow & { min_qty: string; rate: string }): PriceRow => ({
  item: r.item,
  party: r.party,
  unit: r.unit,
  min_qty: String(Number(r.min_qty)),
  rate: String(Number(r.rate)),
  from_date: r.from_date,
  item_name: r.item_name,
  party_name: r.party_name,
});

/** The rows as the server wants them (blank rows left out). */
export const priceBody = (rows: PriceRow[]) =>
  rows
    .filter((r) => r.rate.trim() !== "" || r.item || r.party)
    .map((r) => ({
      item: r.item,
      ...(r.party !== undefined ? { party: r.party } : {}),
      unit: r.unit,
      min_qty: r.min_qty.trim() || "1",
      rate: r.rate.trim(),
      from_date: r.from_date,
    }));

export function useItemChoices() {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => {
    api<Item[]>("v1/items/").then(setItems);
  }, []);
  return items;
}

export function useCustomerChoices() {
  const [parties, setParties] = useState<PartyOption[]>([]);
  useEffect(() => {
    api<PartyOption[]>("v1/parties/").then(setParties, () => setParties([]));
  }, []);
  return parties;
}

/** The table of rates. `by` says what the first column picks: the item (price lists and a
 * customer's Item Prices) or the customer (an item's Customer Prices, where `item` is fixed). */
export function PriceTable(props: {
  rows: PriceRow[];
  onChange: (rows: PriceRow[]) => void;
  by: "item" | "customer";
  item?: Item | null;
  readOnly?: boolean;
}) {
  const { rows, onChange, by, readOnly } = props;
  const items = useItemChoices();
  const parties = useCustomerChoices();
  const { units } = useUnits();
  const unitById = useMemo(() => new Map(units.map((u) => [u.id, u])), [units]);
  const itemById = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);
  const unitsOf = (itemId: number | null): Unit[] => {
    const item = (itemId && itemById.get(itemId)) || (props.item && props.item.id === itemId ? props.item : null);
    if (!item) return [];
    return item.units.map((u) => unitById.get(u.unit)).filter((u): u is Unit => !!u);
  };
  const set = (i: number, change: Partial<PriceRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const firstUnit = (itemId: number | null) => {
    const item = itemId ? itemById.get(itemId) : null;
    return item ? item.stock_unit : null;
  };
  return (
    <>
      <div className="wrap">
        <table className="grid">
          <thead>
            <tr>
              <th>{by === "item" ? "Item" : "Customer"}</th>
              <th>Unit</th>
              <th className="num">From Qty</th>
              <th className="num">Rate</th>
              <th>From Date</th>
              {!readOnly && <th />}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="small">
                  No prices yet.
                </td>
              </tr>
            )}
            {rows.map((r, i) => (
              <tr key={i}>
                <td>
                  {by === "item" ? (
                    <Combobox
                      value={r.item ? String(r.item) : ""}
                      placeholder="Type to search items…"
                      ariaLabel="Item"
                      options={items
                        .filter((x) => x.is_active || x.id === r.item)
                        .map((x) => ({ value: String(x.id), label: `${x.item_number} · ${x.name}` }))}
                      onChange={(v) => {
                        const id = Number(v) || null;
                        set(i, { item: id, unit: firstUnit(id) });
                      }}
                    />
                  ) : (
                    <Combobox
                      value={r.party ? String(r.party) : ""}
                      placeholder="Type to search customers…"
                      ariaLabel="Customer"
                      options={parties.filter((x) => x.customer_number).map((x) => ({ value: String(x.id), label: x.name }))}
                      onChange={(v) => set(i, { party: Number(v) || null })}
                    />
                  )}
                </td>
                <td>
                  <Combobox
                    value={r.unit ? String(r.unit) : ""}
                    ariaLabel="Unit"
                    options={unitsOf(r.item).map((u) => ({ value: String(u.id), label: unitLabel(u) }))}
                    onChange={(v) => set(i, { unit: Number(v) || null })}
                  />
                </td>
                <td>
                  <input
                    className="num"
                    inputMode="decimal"
                    aria-label="From quantity"
                    disabled={readOnly}
                    value={r.min_qty}
                    onChange={(e) => set(i, { min_qty: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    className="num"
                    inputMode="decimal"
                    aria-label="Rate"
                    required
                    disabled={readOnly}
                    value={r.rate}
                    onChange={(e) => set(i, { rate: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="date"
                    aria-label="From date"
                    required
                    disabled={readOnly}
                    value={r.from_date}
                    onChange={(e) => set(i, { from_date: e.target.value })}
                  />
                </td>
                {!readOnly && (
                  <td>
                    <button type="button" className="link danger" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                      Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!readOnly && (
        <div>
          <button
            type="button"
            className="link"
            onClick={() => onChange([...rows, blankRow(props.item?.id ?? null, props.item?.stock_unit ?? null)])}
          >
            Add price
          </button>
        </div>
      )}
    </>
  );
}
