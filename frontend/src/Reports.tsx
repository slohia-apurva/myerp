import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Chevron, PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu } from "./Exchange";
import { openTab } from "./Master";

/** Reports, read straight from the two ledgers (Sidharth, 2026-11-18, preview
 * mockups/reports/1-reports-preview.png). Stock: the Stock Summary (item ›
 * batch › bin, quantity and value) and the Stock Ledger of one item. */

type Branch = { id: number; name: string };
type ItemRow = { id: number; name: string; item_number: string; maintain_stock?: boolean };

type Bin = { location: number; place: string; qty: string; value: string };
type BatchRow = { batch: number | null; number: string; expiry_date: string | null; status: string; qty: string; value: string; bins: Bin[] };
type SummaryItem = { item: number; item_number: string; item_name: string; unit: string; batch_tracked: boolean; qty: string; value: string; rate: string; batches: BatchRow[] };
type Summary = { company_name: string; as_on: string; items: SummaryItem[]; total_value: string };

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

const LEVELS = [
  { value: "1", label: "Items" },
  { value: "2", label: "Items › Batches" },
  { value: "3", label: "Items › Batches › Bins" },
];

/** Reports › Stock Summary: what is on hand on a day, by item, batch and bin. */
export function StockSummaryPage({ companyId }: { companyId: number }) {
  const branches = useBranches(companyId);
  const items = useItems();
  const [asOn, setAsOn] = useState(today());
  const [branch, setBranch] = useState("");
  const [item, setItem] = useState("");
  const [levels, setLevels] = useState("3");
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<unknown>("");
  // Items and batches folded by hand, on top of the "Show" level.
  const [folded, setFolded] = useState<Set<string>>(new Set());
  useEffect(() => {
    const params = new URLSearchParams({ as_on: asOn });
    if (branch) params.set("branch", branch);
    if (item) params.set("item", item);
    setError("");
    api<Summary>(`v1/companies/${companyId}/stock-summary/?${params}`).then(setData, setError);
  }, [companyId, asOn, branch, item]);
  const branchName = branches.find((b) => String(b.id) === branch)?.name;
  const printing = usePrintMenu({
    title: "Stock Summary",
    scope: [data?.company_name, `As on ${dmy(asOn)}`, branchName].filter(Boolean).join(" · "),
  });
  const toggle = (key: string) =>
    setFolded((f) => {
      const next = new Set(f);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const openLedger = (id: number) => {
    const params = new URLSearchParams({ item: String(id), to: asOn });
    if (branch) params.set("branch", branch);
    openTab(`#/companies/${companyId}/stock-ledger?${params}`);
  };
  const depth = Number(levels);

  return (
    <section className="page">
      <PageHeader
        title="Stock Summary"
        sub={`${data?.company_name ?? ""}: what is in stock on a day, by item, batch and bin.`}
        actions={printing.buttons}
      />
      {printing.panel}
      <Section title="Show">
        <div className="row report-filters">
          <label>
            As On
            <input type="date" value={asOn} max="9999-12-31" onChange={(e) => setAsOn(e.target.value || today())} />
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
            Item
            <Combobox
              options={items.map((i) => ({ value: String(i.id), label: i.name, hint: i.item_number }))}
              value={item}
              onChange={setItem}
              empty="All"
              ariaLabel="Item"
            />
          </label>
          <label>
            Show
            <Combobox
              options={LEVELS}
              value={levels}
              onChange={(v) => {
                setLevels(v || "3");
                setFolded(new Set());
              }}
              ariaLabel="Show"
            />
          </label>
        </div>
      </Section>
      <ErrorNote error={error} />
      {data && data.items.length === 0 ? (
        <p className="small">Nothing in stock on {dmy(data.as_on)}.</p>
      ) : (
        data && (
          <table className="report" data-title="Stock Summary">
            <thead>
              <tr>
                <th>Item / Batch / Bin</th>
                <th>Unit</th>
                <th className="num">Quantity</th>
                <th className="num">Rate ₹</th>
                <th className="num">Value ₹</th>
              </tr>
            </thead>
            <tbody>
              {data.items.flatMap((it) => {
                const itemKey = `i${it.item}`;
                const itemOpen = depth > 1 && !folded.has(itemKey);
                const rows = [
                  <tr key={itemKey} className="report-l1">
                    <td>
                      {depth > 1 && (
                        <button
                          className="fold no-print"
                          aria-expanded={itemOpen}
                          aria-label={`${itemOpen ? "Hide" : "Show"} batches of ${it.item_name}`}
                          onClick={() => toggle(itemKey)}
                        >
                          <Chevron open={itemOpen} />
                        </button>
                      )}{" "}
                      <a
                        href={`#/companies/${companyId}/stock-ledger?item=${it.item}`}
                        title="Open the Stock Ledger of this item"
                        onClick={(e) => {
                          e.preventDefault();
                          openLedger(it.item);
                        }}
                      >
                        {it.item_number} {it.item_name}
                      </a>
                    </td>
                    <td>{it.unit}</td>
                    <td className="num">{qty(it.qty)}</td>
                    <td className="num">{it.rate ? rupees(it.rate) : ""}</td>
                    <td className="num">{rupees(it.value)}</td>
                  </tr>,
                ];
                if (!itemOpen) return rows;
                for (const b of it.batches) {
                  const batchKey = `${itemKey}b${b.batch ?? 0}`;
                  const batchOpen = depth > 2 && !folded.has(batchKey);
                  const label = b.number
                    ? `Batch ${b.number}${b.expiry_date ? `, expiry ${dmy(b.expiry_date)}` : ""}${b.status ? `, ${b.status}` : ""}`
                    : "No batch";
                  rows.push(
                    <tr key={batchKey} className="report-l2">
                      <td>
                        {depth > 2 && (
                          <button
                            className="fold no-print"
                            aria-expanded={batchOpen}
                            aria-label={`${batchOpen ? "Hide" : "Show"} bins of ${label}`}
                            onClick={() => toggle(batchKey)}
                          >
                            <Chevron open={batchOpen} />
                          </button>
                        )}{" "}
                        {label}
                      </td>
                      <td>{it.unit}</td>
                      <td className="num">{qty(b.qty)}</td>
                      <td />
                      <td className="num">{rupees(b.value)}</td>
                    </tr>,
                  );
                  if (batchOpen)
                    for (const bin of b.bins)
                      rows.push(
                        <tr key={`${batchKey}l${bin.location}`} className="report-l3">
                          <td>{bin.place}</td>
                          <td>{it.unit}</td>
                          <td className="num">{qty(bin.qty)}</td>
                          <td />
                          <td className="num">{rupees(bin.value)}</td>
                        </tr>,
                      );
                }
                return rows;
              })}
              <tr className="report-total">
                <td>Total</td>
                <td />
                <td />
                <td />
                <td className="num">{rupees(data.total_value)}</td>
              </tr>
            </tbody>
          </table>
        )
      )}
      {data && data.items.length > 0 && <p className="small no-print">Click an item to open its Stock Ledger.</p>}
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
