import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu } from "./Exchange";
import { openTab, SidePanel } from "./Master";
import { useOnReturn } from "./Refresh";

/** Entry › Planning › Stock Check (Sidharth, 2026-11-21, preview 2c): for one branch,
 * the items its Stock Planning says to buy that will fall below their safety stock,
 * and how much to order. "Create Purchase Orders" makes one draft per supplier. */

type Row = {
  item: number;
  item_name: string;
  item_number: string;
  item_group: number | null;
  item_group_name: string;
  stock_unit: string;
  in_stock: string;
  reserved: string;
  incoming: string;
  expected: string;
  safety: string;
  order_up_to: string | null;
  short: boolean;
  suggested: string;
  unit: number;
  unit_name: string;
  whole_numbers: boolean;
  supplier: number | null;
  preferred_supplier_name: string;
  supplier_missing: boolean;
  rate: string | null;
  lead_time_days: number | null;
  by: string;
};
type Daily = { on: boolean; hour: number; can_change: boolean };
type Run = { id: number; made_at: string; daily: boolean; made_by_name: string; short_count: number; order_count: number; missing: string[]; failed: string[] };
type Draft = { id: number; made_at: string; daily: boolean; made_by_name: string; supplier_name: string; item_count: number; expected_date: string | null; total: string };
type Result = {
  branch: number;
  checked_at: string;
  rows: Row[];
  suppliers: { id: number; name: string }[];
  /** The company's daily run (Sidharth, 2026-11-21, preview 4). */
  daily: Daily;
  runs: Run[];
  /** Drafts made by the daily run or "Create Purchase Orders", not yet submitted. */
  drafts: Draft[];
};
type Branch = { id: number; name: string; is_active: boolean; no_stock: boolean };
/** What the person changed on a line: ticked, quantity, supplier, and the supplier's rate. */
type Choice = { on: boolean; qty: string; supplier: string; rate: string | null };

const SHOW: [string, string][] = [
  ["short", "Below Safety Stock"],
  ["all", "All Planned Items"],
];
const indian = (v: string | null) =>
  v === null || v === "" ? "" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 6 });
const money = (v: string | null) =>
  v === null || v === "" ? "—" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB");
const HOURS = Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: `${String(h).padStart(2, "0")}:00` }));
const shortStamp = (iso: string) => {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit" })} ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
};
const isToday = (iso: string) => new Date(iso).toDateString() === new Date().toDateString();
const plural = (n: number, word: string) => `${n} ${n === 1 ? word : `${word}s`}`;
const stamp = (iso: string) => {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB")} at ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
};

export function StockCheckPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const mayOrder = session.permissions.includes("purchase.create");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [branch, setBranch] = useState("");
  const [show, setShow] = useState("short");
  const [group, setGroup] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [error, setError] = useState<unknown>("");
  const [made, setMade] = useState<{ id: number; supplier_name: string; lines: number }[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ branches: Branch[] }>(`v1/companies/${companyId}/`).then((c) => {
      const stock = c.branches.filter((b) => b.is_active && !b.no_stock);
      setBranches(stock);
      // The bell notice of the daily run opens its branch.
      const asked = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("branch") ?? "";
      const pick = stock.find((b) => String(b.id) === asked) ?? stock[0];
      setBranch((now) => now || (pick ? String(pick.id) : ""));
    });
  }, [companyId]);
  const run = useCallback(() => {
    if (!branch) return;
    setError("");
    api<Result>(`v1/companies/${companyId}/stock-check/?branch=${branch}&show=${show}`)
      .then((r) => {
        setResult(r);
        setChoices(
          Object.fromEntries(
            r.rows.map((row) => [
              row.item,
              { on: row.short && row.supplier !== null, qty: row.suggested, supplier: row.supplier ? String(row.supplier) : "", rate: row.rate },
            ]),
          ),
        );
      })
      .catch(setError);
  }, [companyId, branch, show]);
  useEffect(run, [run]);
  useOnReturn(run); // goods ordered in another tab count as soon as this tab is looked at again

  const rows = useMemo(() => (result?.rows ?? []).filter((r) => !group || String(r.item_group) === group), [result, group]);
  const groups = useMemo(() => {
    const seen = new Map<number, string>();
    for (const r of result?.rows ?? []) if (r.item_group !== null) seen.set(r.item_group, r.item_group_name);
    return [...seen].map(([value, label]) => ({ value: String(value), label })).sort((a, b) => a.label.localeCompare(b.label));
  }, [result]);
  const supplierName = (id: string) => result?.suppliers.find((s) => String(s.id) === id)?.name ?? "";
  // Lines grouped by the supplier now picked on them; lines with none come last.
  const bySupplier = useMemo(() => {
    const out = new Map<string, Row[]>();
    for (const r of rows) {
      const key = choices[r.item]?.supplier ?? "";
      out.set(key, [...(out.get(key) ?? []), r]);
    }
    return [...out].sort(([a], [b]) => (a === "" ? 1 : b === "" ? -1 : supplierName(a).localeCompare(supplierName(b))));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, choices, result]);
  const ticked = rows.filter((r) => choices[r.item]?.on && choices[r.item]?.supplier && Number(choices[r.item]?.qty) > 0);
  const draftCount = new Set(ticked.map((r) => choices[r.item].supplier)).size;

  const change = (row: Row, next: Partial<Choice>) => {
    const now = { ...choices[row.item], ...next };
    setChoices((c) => ({ ...c, [row.item]: now }));
    // A new supplier or quantity: ask that supplier's rate again.
    if ((next.supplier !== undefined || next.qty !== undefined) && now.supplier && Number(now.qty) > 0) {
      const today = new Date().toISOString().slice(0, 10);
      api<{ rate: string | null }>(
        `v1/companies/${companyId}/purchase-orders/rate/?supplier=${now.supplier}&item=${row.item}&unit=${row.unit}&qty=${now.qty}&date=${today}`,
      )
        .then((r) => setChoices((c) => ({ ...c, [row.item]: { ...c[row.item], rate: r.rate } })))
        .catch(() => undefined);
    }
  };
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const out = await api<{ id: number; supplier_name: string; lines: number }[]>(`v1/companies/${companyId}/stock-check/orders/`, {
        branch: Number(branch),
        lines: ticked.map((r) => ({ item: r.item, unit: r.unit, qty: choices[r.item].qty.trim(), supplier: Number(choices[r.item].supplier) })),
      });
      setMade(out);
      run();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const setDaily = async (next: Partial<Daily>) => {
    if (!result) return;
    setError("");
    try {
      const daily = await api<Daily>(`v1/companies/${companyId}/stock-check/daily/`, { ...result.daily, ...next }, "PUT");
      setResult((r) => (r ? { ...r, daily } : r));
    } catch (err) {
      setError(err);
    }
  };
  const poHref = (id: number) => `#/companies/${companyId}/purchase-orders?view=${id}`;
  const lastDaily = result?.runs.find((r) => r.daily && isToday(r.made_at) && r.order_count > 0);
  const drafts = result?.drafts ?? [];
  const runs = result?.runs ?? [];
  const branchName = branches.find((b) => String(b.id) === branch)?.name ?? "";
  const printing = usePrintMenu({ title: `Stock Check: ${branchName}`, scope: "" });
  const shortCount = (result?.rows ?? []).filter((r) => r.short).length;

  return (
    <section className="page">
      <PageHeader
        title="Stock Check"
        crumbs={[{ label: "Entry › Planning", href: `#/companies/${companyId}/stock-check` }]}
        sub={result ? `Checked ${stamp(result.checked_at)} · ${shortCount} ${shortCount === 1 ? "item" : "items"} below safety stock` : "Items to buy that will fall below their safety stock"}
        actions={printing.buttons}
      />
      {printing.panel}
      <div className="side-layout">
        <div className="side-main">
      <Section title="Check">
        <div className="row filters report-filters no-print">
          <label>
            Branch
            <Combobox value={branch} onChange={setBranch} ariaLabel="Branch" options={branches.map((b) => ({ value: String(b.id), label: b.name }))} />
          </label>
          <label>
            Show
            <Combobox value={show} onChange={setShow} ariaLabel="Show" options={SHOW.map(([value, label]) => ({ value, label }))} />
          </label>
          <label>
            Item Group
            <Combobox value={group} onChange={setGroup} ariaLabel="Item group" empty="All" options={groups} />
          </label>
          <button type="button" onClick={run} disabled={!branch}>
            Check Now
          </button>
        </div>
      </Section>
      <ErrorNote error={error} />
      {made.length > 0 && (
        <p className="ok-note no-print">
          Made {made.length} draft purchase {made.length === 1 ? "order" : "orders"}:{" "}
          {made.map((o, k) => (
            <span key={o.id}>
              {k > 0 && ", "}
              <a href={`#/companies/${companyId}/purchase-orders?view=${o.id}`} onClick={(e) => (e.preventDefault(), openTab(`#/companies/${companyId}/purchase-orders?view=${o.id}`))}>
                {o.supplier_name}
              </a>{" "}
              ({o.lines} {o.lines === 1 ? "item" : "items"})
            </span>
          ))}
          . Open each one, check it and Submit.
        </p>
      )}
      {lastDaily && made.length === 0 && (
        <p className="ok-note no-print">
          The daily run at {shortStamp(lastDaily.made_at).split(" ")[1]} made {plural(lastDaily.order_count, "draft purchase order")}. Check and Submit them
          below: they are not sent to the suppliers until submitted.
        </p>
      )}
      <Section title={`To Buy · ${rows.length} ${rows.length === 1 ? "item" : "items"}`}>
        {rows.length === 0 ? (
          <p className="small">{result ? "Nothing to buy: every planned item of this branch is at or above its safety stock." : "Pick a branch."}</p>
        ) : (
          <div className="table-scroll">
            <table className="grid by-group stock-check">
              <thead>
                <tr>
                  <th className="no-print" aria-label="Order" />
                  <th>Item</th>
                  <th className="num">In Stock</th>
                  <th className="num">Reserved</th>
                  <th className="num">Incoming</th>
                  <th className="num">Expected</th>
                  <th className="num">Safety</th>
                  <th className="num">Order Up To</th>
                  <th className="num">Suggested</th>
                  <th>Unit</th>
                  <th>Supplier</th>
                  <th className="num">Rate ₹</th>
                </tr>
              </thead>
              {bySupplier.map(([key, list]) => {
                const lead = Math.max(0, ...list.map((r) => r.lead_time_days ?? 0));
                const by = list.map((r) => r.by).sort().at(-1) ?? "";
                return (
                  <tbody key={key || "none"}>
                    <tr className="group-row">
                      <td colSpan={12} className={key ? undefined : "error"}>
                        {key
                          ? `${supplierName(key)} · Lead time ${lead} ${lead === 1 ? "day" : "days"} · by ${day(by)}`
                          : "No supplier: pick one on the line, or set the Preferred Supplier on the item"}
                      </td>
                    </tr>
                    {list.map((r) => {
                      const c = choices[r.item] ?? { on: false, qty: r.suggested, supplier: "", rate: null };
                      return (
                        <tr key={r.item}>
                          <td className="no-print">
                            <input
                              type="checkbox"
                              aria-label={`Order ${r.item_name}`}
                              checked={c.on}
                              disabled={!mayOrder || !c.supplier}
                              onChange={(e) => change(r, { on: e.target.checked })}
                            />
                          </td>
                          <td>
                            {r.item_name}
                            {r.supplier_missing && (
                              <div className="small error">{r.preferred_supplier_name} has no ledger in this company.</div>
                            )}
                          </td>
                          <td className="num">{indian(r.in_stock)}</td>
                          <td className="num">{indian(r.reserved)}</td>
                          <td className="num">{indian(r.incoming)}</td>
                          <td className={`num${r.short ? " error" : ""}`}>
                            <b>{indian(r.expected)}</b>
                          </td>
                          <td className="num">{indian(r.safety)}</td>
                          <td className="num">{r.order_up_to === null ? "—" : indian(r.order_up_to)}</td>
                          <td className="num">
                            <input
                              className="num"
                              inputMode="decimal"
                              aria-label={`Suggested ${r.item_name}`}
                              value={c.qty}
                              disabled={!mayOrder}
                              onChange={(e) => change(r, { qty: e.target.value })}
                            />
                          </td>
                          <td>{r.unit_name}</td>
                          <td>
                            <Combobox
                              value={c.supplier}
                              ariaLabel={`Supplier for ${r.item_name}`}
                              empty="Pick a supplier"
                              onChange={(v) => change(r, { supplier: v, on: Boolean(v) && (c.on || r.short) })}
                              options={(result?.suppliers ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
                            />
                          </td>
                          <td className="num">{money(c.rate)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                );
              })}
            </table>
          </div>
        )}
        {mayOrder && rows.length > 0 && (
          <p className="no-print">
            <button type="button" onClick={create} disabled={busy || ticked.length === 0}>
              Create Purchase Orders ({draftCount} {draftCount === 1 ? "draft" : "drafts"}, {ticked.length} {ticked.length === 1 ? "item" : "items"})
            </button>{" "}
            <span className="small">
              One draft order per supplier, rate from Supplier Prices, Expected Delivery = today + lead time. You check and Submit each one.
            </span>
          </p>
        )}
        <p className="small">
          "Reserved" is everything going out of the branch, submitted or still a draft: sales orders still to deliver (manufacturing and transfer orders will
          join when they are built). "Incoming" is everything coming in, drafts included: purchase orders still to receive. "Expected" = In Stock − Reserved +
          Incoming. "Suggested" = Order Up To − Expected, in the purchase unit, rounded up to the Minimum Order Qty. Quantities other than Suggested are in the
          item's default unit. "To Make" and "To Transfer" come with manufacturing and stock transfers.
        </p>
      </Section>
      {drafts.length > 0 && (
        <Section title="Draft Purchase Orders Made by Stock Check">
          <div className="table-scroll">
            <table className="grid">
              <thead>
                <tr>
                  <th>Made</th>
                  <th>By</th>
                  <th>Supplier</th>
                  <th className="num">Items</th>
                  <th>Expected Delivery</th>
                  <th className="num">Amount ₹</th>
                  <th className="no-print" aria-label="Open" />
                </tr>
              </thead>
              <tbody>
                {drafts.map((d) => (
                  <tr key={d.id}>
                    <td>{shortStamp(d.made_at)}</td>
                    <td>{d.daily ? "Daily run" : d.made_by_name}</td>
                    <td>{d.supplier_name}</td>
                    <td className="num">{d.item_count}</td>
                    <td>{d.expected_date ? day(d.expected_date) : ""}</td>
                    <td className="num">{money(d.total)}</td>
                    <td className="no-print">
                      <button type="button" className="link" onClick={() => openTab(poHref(d.id))}>
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
        </div>
        <div className="side-col no-print" aria-label="Daily run">
          {result && (
            <SidePanel title="Daily Run">
              <label className="daily-tick">
                <input type="checkbox" checked={result.daily.on} disabled={!result.daily.can_change} onChange={(e) => setDaily({ on: e.target.checked })} /> Run
                every morning and make draft purchase orders
              </label>
              <div className="daily-at">
                <span className="side-label">Run At</span>
                {result.daily.can_change ? (
                  <Combobox value={String(result.daily.hour)} ariaLabel="Run at" onChange={(v) => v && setDaily({ hour: Number(v) })} options={HOURS} />
                ) : (
                  <span>{HOURS[result.daily.hour]?.label}</span>
                )}
              </div>
              <p className="small">
                For every branch of this company with Stock Planning lines. The Purchase people get a bell notice.
                {!result.daily.can_change && " Only someone who may change masters can change this."}
              </p>
            </SidePanel>
          )}
          {runs.length > 0 && (
            <SidePanel title="Recent Runs">
              {runs.map((r) => (
                <div key={r.id} className="small">
                  {shortStamp(r.made_at)} · {r.daily ? "Daily" : r.made_by_name} ·{" "}
                  {r.short_count === 0 ? "nothing short" : `${r.short_count} short · ${plural(r.order_count, "PO")} made`}
                  {r.missing.length > 0 && <span className="error"> · no supplier: {r.missing.join(", ")}</span>}
                  {r.failed.length > 0 && <span className="error"> · {r.failed.join(" ")}</span>}
                </div>
              ))}
            </SidePanel>
          )}
        </div>
      </div>
    </section>
  );
}
