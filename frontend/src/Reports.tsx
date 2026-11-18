import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { PageHeader, Section } from "./Brand";
import { ColumnSearch } from "./ColumnSearch";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu } from "./Exchange";
import { openTab } from "./Master";

/** Reports, read straight from the two ledgers (Sidharth, 2026-11-18, preview
 * mockups/reports/1-reports-preview.png). Stock: the Stock Summary (item ›
 * batch › bin, quantity and value) and the Stock Ledger of one item. */

type Branch = { id: number; name: string };
type ItemRow = { id: number; name: string; item_number: string; maintain_stock?: boolean };

type SummaryLine = { item: number; item_number: string; item_name: string; batch: string; warehouse: string; bin: string; unit: string; qty: string; rate: string; value: string };
type Summary = { company_name: string; as_on: string; lines: SummaryLine[]; total_value: string };

type Entry = { type: string; type_label: string; id: number; number: string; page: string };
type LedgerRow = {
  date: string;
  entry: Entry;
  cancel: boolean;
  revaluation?: boolean;
  batch: string;
  place: string;
  qty_in: string;
  qty_out: string;
  value: string;
  balance_qty: string;
  balance_value: string;
};
type StockLedger = {
  company_name: string;
  item: number;
  item_number: string;
  item_name: string;
  unit: string;
  from: string | null;
  to: string;
  opening_qty: string;
  opening_value: string;
  rows: LedgerRow[];
  closing_qty: string;
  closing_value: string;
  batches: { id: number; number: string }[];
  places: { id: number; name: string }[];
};

const today = () => new Date().toISOString().slice(0, 10);
/** 1 April of the financial year the day falls in. */
const yearStart = (iso: string) => {
  const [y, m] = iso.split("-").map(Number);
  return `${m >= 4 ? y : y - 1}-04-01`;
};
export const dmy = (iso: string | null) => (iso ? iso.split("-").reverse().join("-") : "");
export const rupees = (v: string) =>
  Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const qty = (v: string) =>
  v === "" ? "" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 3, maximumFractionDigits: 6 });

/** The query of the address after "?", e.g. ?item=3. */
function hashParam(key: string): string {
  const query = window.location.hash.split("?")[1] ?? "";
  return new URLSearchParams(query).get(key) ?? "";
}

function useBranches(companyId: number) {
  const [branches, setBranches] = useState<Branch[]>([]);
  useEffect(() => {
    api<{ branches: Branch[] }>(`v1/companies/${companyId}/`).then((d) => setBranches(d.branches ?? []));
  }, [companyId]);
  return branches;
}

function useItems() {
  const [items, setItems] = useState<ItemRow[]>([]);
  useEffect(() => {
    api<ItemRow[]>("v1/items/").then((rows) => setItems(rows.filter((i) => i.maintain_stock !== false)));
  }, []);
  return items;
}

/** Opens the entry a report row came from, in a new tab. */
export function EntryLink({ companyId, entry }: { companyId: number; entry: Entry }) {
  if (!entry.page) return <>{entry.number}</>;
  const href = `#/companies/${companyId}/${entry.page}?view=${entry.id}`;
  return (
    <a
      href={href}
      title={`Open ${entry.type_label} ${entry.number}`}
      onClick={(e) => {
        e.preventDefault();
        openTab(href);
      }}
    >
      {entry.number}
    </a>
  );
}

/** Does every word typed in a column's box appear in the cell (capitals ignored)? */
const matches = (text: string, typed: string) =>
  typed
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((w) => text.toLowerCase().includes(w));

/** Reports › Stock Summary: what is on hand on a day, one line per item, batch and bin, every
 * field its own column with a search box under its heading (Sidharth, 2026-11-18, preview
 * mockups/reports/3-stock-summary-flat-preview.png). The totals add up the lines shown. */
export function StockSummaryPage({ companyId }: { companyId: number }) {
  const [asOn, setAsOn] = useState(today());
  // From the Items screen: one item only, until "Show all items".
  const [item, setItem] = useState(hashParam("item"));
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<unknown>("");
  const [search, setSearch] = useState<string[]>([]);
  useEffect(() => {
    const params = new URLSearchParams({ as_on: asOn });
    if (item) params.set("item", item);
    setError("");
    api<Summary>(`v1/companies/${companyId}/stock-summary/?${params}`).then(setData, setError);
  }, [companyId, asOn, item]);
  const cells = (r: SummaryLine) => [r.item_number, r.item_name, r.batch, r.warehouse, r.bin, r.unit, qty(r.qty), r.rate ? rupees(r.rate) : "", rupees(r.value)];
  const shown = useMemo(
    () => (data?.lines ?? []).filter((r) => cells(r).every((text, i) => !search[i]?.trim() || matches(text, search[i]))),
    [data, search],
  );
  const units = new Set(shown.map((r) => r.unit));
  const totalQty = shown.reduce((t, r) => t + Number(r.qty), 0);
  const totalValue = shown.reduce((t, r) => t + Number(r.value), 0);
  const typed = search.filter((v) => v.trim()).length > 0;
  const printing = usePrintMenu({
    title: "Stock Summary",
    scope: [data?.company_name, `As on ${dmy(asOn)}`].filter(Boolean).join(" · "),
  });

  return (
    <section className="page">
      <PageHeader
        title="Stock Summary"
        sub={`${data?.company_name ?? ""}: what is in stock on a day, one line per item, batch and bin.`}
        actions={printing.buttons}
      />
      {printing.panel}
      <Section title="Show">
        <div className="row report-filters">
          <label>
            As On
            <input type="date" value={asOn} max="9999-12-31" onChange={(e) => setAsOn(e.target.value || today())} />
          </label>
        </div>
        {item && (
          <p className="small">
            One item only.{" "}
            <button type="button" className="link" onClick={() => setItem("")}>
              Show all items
            </button>
          </p>
        )}
      </Section>
      <ErrorNote error={error} />
      {data && (
        <table className="report" data-title="Stock Summary">
          <thead>
            <tr>
              <th>Item No</th>
              <th>Item Name</th>
              <th>Batch</th>
              <th>Warehouse</th>
              <th>Bin</th>
              <th>Unit</th>
              <th className="num">Quantity</th>
              <th className="num">Rate ₹</th>
              <th className="num">Value ₹</th>
            </tr>
            <ColumnSearch onSearch={setSearch} />
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr>
                <td colSpan={9} className="small">
                  {typed ? "Nothing matches the column searches." : `Nothing in stock on ${dmy(data.as_on)}.`}
                </td>
              </tr>
            )}
            {shown.map((r, n) => (
              <tr key={n}>
                <td>
                  <a
                    href={`#/companies/${companyId}/stock-ledger?item=${r.item}`}
                    title="Open the Stock Ledger of this item"
                    onClick={(e) => {
                      e.preventDefault();
                      openTab(`#/companies/${companyId}/stock-ledger?${new URLSearchParams({ item: String(r.item), to: asOn })}`);
                    }}
                  >
                    {r.item_number}
                  </a>
                </td>
                <td>{r.item_name}</td>
                <td>{r.batch}</td>
                <td>{r.warehouse}</td>
                <td>{r.bin}</td>
                <td>{r.unit}</td>
                <td className="num">{qty(r.qty)}</td>
                <td className="num">{r.rate ? rupees(r.rate) : ""}</td>
                <td className="num">{rupees(r.value)}</td>
              </tr>
            ))}
            {shown.length > 0 && (
              <tr className="report-total">
                <td>Total</td>
                <td />
                <td />
                <td />
                <td />
                <td>{units.size === 1 ? [...units][0] : ""}</td>
                <td className="num">{units.size === 1 ? qty(String(totalQty)) : ""}</td>
                <td />
                <td className="num">{rupees(String(totalValue))}</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {data && data.lines.length > 0 && (
        <p className="small no-print">
          Click an item number to open its Stock Ledger. The totals add up the lines shown; the quantity total shows when they are all in one unit.
        </p>
      )}
    </section>
  );
}

/** Reports › Stock Ledger: every move of one item in a period, with the balance after each. */
export function StockLedgerPage({ companyId }: { companyId: number }) {
  const branches = useBranches(companyId);
  const items = useItems();
  const [item, setItem] = useState(hashParam("item"));
  const [to, setTo] = useState(hashParam("to") || today());
  const [from, setFrom] = useState(hashParam("from") || yearStart(hashParam("to") || today()));
  const [branch, setBranch] = useState(hashParam("branch"));
  const [batch, setBatch] = useState("");
  const [place, setPlace] = useState("");
  const [data, setData] = useState<StockLedger | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    if (!item) {
      setData(null);
      return;
    }
    const params = new URLSearchParams({ item, from, to });
    if (branch) params.set("branch", branch);
    if (batch) params.set("batch", batch);
    if (place) params.set("location", place);
    setError("");
    api<StockLedger>(`v1/companies/${companyId}/stock-ledger/?${params}`).then(setData, setError);
  }, [companyId, item, from, to, branch, batch, place]);
  const title = data ? `Stock Ledger: ${data.item_name}` : "Stock Ledger";
  const scope = useMemo(
    () =>
      [
        data?.company_name,
        `${dmy(from)} to ${dmy(to)}`,
        branches.find((b) => String(b.id) === branch)?.name,
        data?.batches.find((b) => String(b.id) === batch)?.number && `Batch ${data?.batches.find((b) => String(b.id) === batch)?.number}`,
        data?.places.find((p) => String(p.id) === place)?.name,
      ]
        .filter(Boolean)
        .join(" · "),
    [data, from, to, branch, batch, place, branches],
  );
  const printing = usePrintMenu({ title, scope });

  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={data ? `${data.item_number} · stock in ${data.unit}: every move in and out, with the balance after each.` : "Pick an item to see every move in and out."}
        actions={printing.buttons}
      />
      {printing.panel}
      <Section title="Show">
        <div className="row report-filters">
          <label>
            Item
            <Combobox
              options={items.map((i) => ({ value: String(i.id), label: i.name, hint: i.item_number }))}
              value={item}
              onChange={(v) => {
                setItem(v);
                setBatch("");
                setPlace("");
              }}
              placeholder="Pick an item"
              ariaLabel="Item"
            />
          </label>
          <label>
            From
            <input type="date" value={from} max="9999-12-31" onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label>
            To
            <input type="date" value={to} max="9999-12-31" onChange={(e) => setTo(e.target.value || today())} />
          </label>
          <label>
            Warehouse
            <Combobox
              options={branches.map((b) => ({ value: String(b.id), label: b.name }))}
              value={branch}
              onChange={setBranch}
              empty="All"
              ariaLabel="Warehouse"
            />
          </label>
          <label>
            Batch
            <Combobox
              options={(data?.batches ?? []).map((b) => ({ value: String(b.id), label: b.number }))}
              value={batch}
              onChange={setBatch}
              empty="All"
              ariaLabel="Batch"
            />
          </label>
          <label>
            Bin
            <Combobox
              options={(data?.places ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
              value={place}
              onChange={setPlace}
              empty="All"
              ariaLabel="Bin"
            />
          </label>
        </div>
      </Section>
      <ErrorNote error={error} />
      {data && (
        <table className="report" data-title={title}>
          <thead>
            <tr>
              <th>Date</th>
              <th>Entry</th>
              <th>Batch</th>
              <th>Bin</th>
              <th className="num">In</th>
              <th className="num">Out</th>
              <th className="num">Balance</th>
              <th className="num">Value ₹</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{dmy(data.from)}</td>
              <td>
                <i>Opening</i>
              </td>
              <td />
              <td />
              <td />
              <td />
              <td className="num">{qty(data.opening_qty)}</td>
              <td className="num">{rupees(data.opening_value)}</td>
            </tr>
            {data.rows.map((r, n) => (
              <tr key={n} className={r.cancel ? "inactive" : ""}>
                <td>{dmy(r.date)}</td>
                <td>
                  <EntryLink companyId={companyId} entry={r.entry} />
                  <span className="small">
                    {" "}
                    {r.entry.type_label}
                    {r.cancel ? " (cancelled)" : r.revaluation ? " (rate change)" : ""}
                  </span>
                </td>
                <td>{r.batch}</td>
                <td>{r.place}</td>
                <td className="num">{qty(r.qty_in)}</td>
                <td className="num">{qty(r.qty_out)}</td>
                <td className="num">{qty(r.balance_qty)}</td>
                <td className="num">{rupees(r.balance_value)}</td>
              </tr>
            ))}
            <tr className="report-total">
              <td>{dmy(data.to)}</td>
              <td>Closing</td>
              <td />
              <td />
              <td />
              <td />
              <td className="num">{qty(data.closing_qty)}</td>
              <td className="num">{rupees(data.closing_value)}</td>
            </tr>
          </tbody>
        </table>
      )}
      {data && data.rows.length === 0 && <p className="small">No moves in this period.</p>}
    </section>
  );
}

// Stock on the Items master (Sidharth, 2026-11-18, preview mockups/reports/2-items-stock-preview.png)

type ItemStock = {
  item: number;
  unit: string;
  qty: string;
  value: string;
  branches: { branch: number; name: string; qty: string; value: string }[];
  batches: { number: string; expiry_date: string | null; qty: string }[];
  last_received: (Entry & { date: string }) | null;
};

/** Each item's quantity in stock in the company: item id → quantity. */
export function useItemStock(companyId: number | undefined) {
  const [stock, setStock] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!companyId) return;
    api<{ items: Record<string, string> }>(`v1/companies/${companyId}/item-stock/`).then(
      (d) => setStock(d.items),
      () => setStock({}),
    );
  }, [companyId]);
  return stock;
}

/** Opens the Stock Summary of one item, down to its batches and bins, in a new tab. */
export function openItemStock(companyId: number, itemId: number) {
  openTab(`#/companies/${companyId}/stock-summary?item=${itemId}`);
}

/** The "Stock" box beside an item: quantity and value per warehouse, batches, last receipt. */
export function ItemStockBox({ companyId, itemId }: { companyId: number; itemId: number }) {
  const [s, setS] = useState<ItemStock | null>(null);
  useEffect(() => {
    setS(null);
    api<ItemStock>(`v1/companies/${companyId}/item-stock/?item=${itemId}`).then(setS, () => setS(null));
  }, [companyId, itemId]);
  if (!s) return null;
  return (
    <section className="side-panel">
      <h3>
        Stock<em>as on today</em>
      </h3>
      <div className="side-body">
        {s.branches.length === 0 ? (
          <p className="small">Nothing in stock in this company.</p>
        ) : (
          <table className="report side-table no-print">
            <thead>
              <tr>
                <th>Warehouse</th>
                <th className="num">Qty ({s.unit})</th>
                <th className="num">Value ₹</th>
              </tr>
            </thead>
            <tbody>
              {s.branches.map((b) => (
                <tr key={b.branch}>
                  <td>{b.name}</td>
                  <td className="num">{qty(b.qty)}</td>
                  <td className="num">{rupees(b.value)}</td>
                </tr>
              ))}
              {s.branches.length > 1 && (
                <tr className="report-total">
                  <td>Total</td>
                  <td className="num">{qty(s.qty)}</td>
                  <td className="num">{rupees(s.value)}</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        {s.batches.length > 0 && (
          <div className="side-row">
            <span>Batches</span>
            <span>
              {s.batches
                .map((b) => `${b.number}${b.expiry_date ? `, expiry ${dmy(b.expiry_date)}` : ""} (${qty(b.qty)})`)
                .join("; ")}
            </span>
          </div>
        )}
        {s.last_received && (
          <div className="side-row">
            <span>Last received</span>
            <span>
              {dmy(s.last_received.date)}, <EntryLink companyId={companyId} entry={s.last_received} />
            </span>
          </div>
        )}
        <div className="side-buttons">
          <button type="button" className="link" onClick={() => openItemStock(companyId, itemId)}>
            Bins and batches
          </button>
          <button
            type="button"
            className="link"
            onClick={() => openTab(`#/companies/${companyId}/stock-ledger?item=${itemId}`)}
          >
            Stock Ledger
          </button>
        </div>
      </div>
    </section>
  );
}
