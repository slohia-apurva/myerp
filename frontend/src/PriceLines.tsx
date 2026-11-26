import { useEffect, useMemo, useState } from "react";
import { Combobox } from "./Combobox";
import { type Item } from "./Items";
import { unitLabel, useUnits, type Unit } from "./Units";
import { useReturns } from "./Refresh";
import { useItemSearch } from "./ItemSearch";
import { longDate, money } from "./Companies";

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

export type PartyOption = { id: number; name: string; customer_number: string; vendor_number: string };

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

/** Which items a party's own Item Prices may pick: those it may be sold (customer) or
 * bought from (supplier); with products listed on its "Products" tab, only those
 * plus items ticked "Offer to all" (Sidharth 2026-11-25). */
export type PartyItems = { side: "customer" | "supplier"; products: number[] };

export function useItemChoices(chosen: (number | null)[] = [], party?: PartyItems) {
  // Asked from the server as the person types (ItemSearch.ts), plus the items
  // already on the rows: the whole catalogue is 12,457 items on staging.
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  const url = party
    ? `v1/items/?side=${party.side}&products=${[...new Set(party.products)].sort((a, b) => a - b).join(",")}`
    : "v1/items/";
  return useItemSearch<Item>(url, chosen, visits);
}

/** Customers (or suppliers) for an item's Customer or Supplier Prices, asked from the server
 * as the person types, plus the parties already on the rows (10,000 parties on staging took
 * 8 s to load whole, and saved rows showed no name meanwhile: Sidharth 2026-11-26). */
export function usePartyChoices(side: "customer" | "supplier" | null, chosen: (number | null | undefined)[]) {
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  return useItemSearch<PartyOption>(side ? `v1/parties/?side=${side}` : null, chosen, visits);
}

/** The table of rates. `by` says what the first column picks: the item (price lists and a
 * customer's Item Prices) or the customer (an item's Customer Prices, where `item` is fixed). */
export function PriceTable(props: {
  rows: PriceRow[];
  onChange: (rows: PriceRow[]) => void;
  by: "item" | "customer" | "supplier";
  item?: Item | null;
  readOnly?: boolean;
  /** On a party's Item Prices: offer only the items that party may deal in. */
  party?: PartyItems;
  /** Saved rows show as one line each with "Edit"; a row opened or newly added shows its
   * boxes until "Done" (repeating sub-records, Sidharth 2026-11-16 and 2026-11-25). */
  asLines?: boolean;
  /** With asLines: changes when another record is loaded, folding every row. */
  resetKey?: unknown;
}) {
  if (props.asLines) return <PriceLines {...props} />;
  return <PriceGrid {...props} />;
}

function PriceGrid(props: Parameters<typeof PriceTable>[0]) {
  const { rows, onChange, by, readOnly } = props;
  const { items, onType } = useItemChoices(rows.map((r) => r.item), props.party);
  const { items: parties, onType: findParties } = usePartyChoices(by === "item" ? null : by, rows.map((r) => r.party));
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
              <th>{by === "item" ? "Item" : by === "supplier" ? "Supplier" : "Customer"}</th>
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
                      onType={onType}
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
                      placeholder={`Type to search ${by === "supplier" ? "suppliers" : "customers"}…`}
                      ariaLabel={by === "supplier" ? "Supplier" : "Customer"}
                      onType={findParties}
                      options={parties.map((x) => ({ value: String(x.id), label: x.name }))}
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

/** A party's own Item Prices as lines: "IT-003442 · Green Tea", then unit, from qty and
 * date under it, the rate at the right, and "Edit". Fits a phone. */
function PriceLines(props: Parameters<typeof PriceTable>[0]) {
  const { rows, onChange, readOnly, by } = props;
  const byParty = by !== "item";
  const { items, onType } = useItemChoices(byParty ? [] : rows.map((r) => r.item), props.party);
  const { items: parties, onType: findParties } = usePartyChoices(byParty ? by : null, rows.map((r) => r.party));
  const partyById = useMemo(() => new Map(parties.map((x) => [x.id, x])), [parties]);
  const { units } = useUnits();
  const unitById = useMemo(() => new Map(units.map((u) => [u.id, u])), [units]);
  const itemById = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);
  // Rows open for editing, by index; a new row opens, saved ones start folded.
  const [open, setOpen] = useState<Set<number>>(new Set());
  useEffect(() => setOpen(new Set()), [props.resetKey]);
  const set = (i: number, change: Partial<PriceRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const unitsOf = (itemId: number | null): Unit[] => {
    const item = (itemId && itemById.get(itemId)) || (props.item && props.item.id === itemId ? props.item : null);
    if (!item) return [];
    return item.units.map((u) => unitById.get(u.unit)).filter((u): u is Unit => !!u);
  };
  const partyText = (r: PriceRow) => (r.party ? (partyById.get(r.party)?.name ?? r.party_name ?? "") : "");
  const itemText = (r: PriceRow) => {
    if (byParty) return partyText(r);
    const it = r.item ? itemById.get(r.item) : null;
    return it ? `${it.item_number} · ${it.name}` : (r.item_name ?? "");
  };
  const unitText = (r: PriceRow) => {
    const u = r.unit ? unitById.get(r.unit) : null;
    return u ? u.short_name || u.name : "";
  };
  const remove = (i: number) => {
    onChange(rows.filter((_, j) => j !== i));
    setOpen((o) => new Set([...o].filter((j) => j !== i).map((j) => (j > i ? j - 1 : j))));
  };
  const fold = (i: number, button: HTMLElement) => {
    const empty = button.closest(".price-open")?.querySelector<HTMLInputElement>(":invalid");
    if (empty) return empty.reportValidity();
    const r = rows[i];
    if (!r.item || !r.unit || (byParty && !r.party)) return;
    setOpen((o) => {
      const n = new Set(o);
      n.delete(i);
      return n;
    });
  };
  return (
    <>
      {rows.length === 0 && <p className="small">No prices yet.</p>}
      {rows.length > 0 && (
        <table className="row-list price-lines">
          <thead>
            <tr>
              <th>{by === "item" ? "Item" : by === "supplier" ? "Supplier" : "Customer"}</th>
              <th className="num">Rate</th>
              {!readOnly && <th />}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) =>
              !open.has(i) || readOnly ? (
                <tr key={i}>
                  <td>
                    {itemText(r)}
                    <div className="small">
                      {[unitText(r), `From Qty ${r.min_qty || "1"}`, r.from_date ? `From ${longDate(r.from_date)}` : ""]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                  </td>
                  <td className="num">{r.rate ? money(r.rate) : ""}</td>
                  {!readOnly && (
                    <td className="row-edit">
                      <button type="button" className="link" onClick={() => setOpen((o) => new Set(o).add(i))}>
                        Edit
                      </button>
                    </td>
                  )}
                </tr>
              ) : (
                <tr key={i}>
                  <td colSpan={3} className="row-open">
                    <div className="address-card price-open">
                      <div className="row">
                        {byParty ? (
                          <label className="wide">
                            {by === "supplier" ? "Supplier" : "Customer"}
                            <Combobox
                              value={r.party ? String(r.party) : ""}
                              onType={findParties}
                              placeholder={`Type to search ${by === "supplier" ? "suppliers" : "customers"}…`}
                              ariaLabel={by === "supplier" ? "Supplier" : "Customer"}
                              options={parties.map((x) => ({ value: String(x.id), label: x.name }))}
                              onChange={(v) => set(i, { party: Number(v) || null })}
                            />
                          </label>
                        ) : (
                          <label className="wide">
                            Item
                            <Combobox
                              value={r.item ? String(r.item) : ""}
                              onType={onType}
                              placeholder="Type to search items…"
                              ariaLabel="Item"
                              options={items
                                .filter((x) => x.is_active || x.id === r.item)
                                .map((x) => ({ value: String(x.id), label: `${x.item_number} · ${x.name}` }))}
                              onChange={(v) => {
                                const id = Number(v) || null;
                                const it = id ? itemById.get(id) : null;
                                set(i, { item: id, unit: it ? it.stock_unit : null });
                              }}
                            />
                          </label>
                        )}
                        <label>
                          Unit
                          <Combobox
                            value={r.unit ? String(r.unit) : ""}
                            ariaLabel="Unit"
                            options={unitsOf(r.item).map((u) => ({ value: String(u.id), label: unitLabel(u) }))}
                            onChange={(v) => set(i, { unit: Number(v) || null })}
                          />
                        </label>
                      </div>
                      <div className="row">
                        <label>
                          From Qty
                          <input className="num" inputMode="decimal" value={r.min_qty} onChange={(e) => set(i, { min_qty: e.target.value })} />
                        </label>
                        <label>
                          Rate
                          <input className="num" inputMode="decimal" required value={r.rate} onChange={(e) => set(i, { rate: e.target.value })} />
                        </label>
                        <label>
                          From Date
                          <input type="date" required value={r.from_date} onChange={(e) => set(i, { from_date: e.target.value })} />
                        </label>
                      </div>
                      <div className="address-flags">
                        <button type="button" className="link danger" onClick={() => remove(i)}>
                          Remove
                        </button>
                        <button type="button" onClick={(e) => fold(i, e.currentTarget)}>
                          Done
                        </button>
                      </div>
                    </div>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      )}
      {!readOnly && (
        <div>
          <button
            type="button"
            className="link"
            onClick={() => {
              setOpen((o) => new Set(o).add(rows.length));
              onChange([...rows, blankRow(props.item?.id ?? null, props.item?.stock_unit ?? null)]);
            }}
          >
            Add price
          </button>
        </div>
      )}
    </>
  );
}
