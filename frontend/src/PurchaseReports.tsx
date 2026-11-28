import { useCallback, useEffect, useMemo, useState } from "react";
import { api, download } from "./api";
import { PageHeader, Section } from "./Brand";
import { ColumnSearch } from "./ColumnSearch";
import { useColumns, type Column } from "./Columns";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu, type MenuItem, type PrintSheet } from "./Exchange";
import { useKept } from "./Keep";
import { Pager, type Paged } from "./Pager";
import { EntryLink, dmy, qty, rupees } from "./Reports";

/** Reports › Purchase (Sidharth, 2026-11-27, previews mockups/purchase-reports/1 and 4). */

type PendingOrder = {
  id: number;
  number: string;
  date: string;
  supplier: string;
  expected: string | null;
  late: number;
  purchaser: string;
  branch: string;
  lines: number;
  value: string;
  pending: string;
  status: string;
};
type Totals = { orders: number; lines: number; value: string; pending: string };
type Report<T> = Paged<T> & { company_name: string; branches: { id: number; name: string }[]; totals: Totals };

/** 1 April of this financial year. */
export function yearStart(): string {
  const d = new Date();
  const y = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1;
  return `${y}-04-01`;
}
const today = () => new Date().toISOString().slice(0, 10);

/** A column of a report: what the screen shows and, for Print, PDF and Excel, its text. */
export type ReportColumn<T> = Column<T> & { text: (row: T) => string };

/** The columns' search boxes, sent to the server once typing stops; a new search goes back to page 1. */
export function useServerSearch<T>(name: string, shown: ReportColumn<T>[], setPage: (p: number) => void) {
  const [searches, setSearches] = useKept<Record<string, string>>(`${name}.searches`, {});
  const [typed, setTyped] = useState<Record<string, string>>(searches);
  useEffect(() => {
    if (JSON.stringify(typed) === JSON.stringify(searches)) return;
    const wait = setTimeout(() => {
      setSearches(typed);
      setPage(1);
    }, 300);
    return () => clearTimeout(wait);
  }, [typed, searches]);
  const onSearch = useCallback(
    (values: string[]) => {
      const next: Record<string, string> = {};
      shown.forEach((c, i) => {
        if (c.search && values[i]?.trim()) next[c.search] = values[i].trim();
      });
      setTyped((was) => (JSON.stringify(was) === JSON.stringify(next) ? was : next));
    },
    [shown],
  );
  return { searches, onSearch };
}

/** "Export to Excel": the same sheets as Print and PDF, as an Excel file. */
export function excelItem(title: string, scope: string, load: () => Promise<PrintSheet["sheets"]>, onError: (e: unknown) => void): MenuItem {
  return {
    label: "Export to Excel",
    onClick: () => {
      const stem = `${title}-${today()}`.toLowerCase().replace(/[^a-z0-9]+/g, "-");
      load()
        .then((sheets) => download("v1/print/xlsx/", { title, scope, sheets }, `${stem}.xlsx`))
        .catch(onError);
    },
  };
}

/** Reports › Purchase › Pending Purchase Orders: submitted orders with goods still to come, one
 * row per order; 25 a page, searched and sorted on the server. */
export function PendingPurchaseOrdersPage({ companyId }: { companyId: number }) {
  const [from, setFrom] = useKept("PendingPOs.from", yearStart());
  const [to, setTo] = useKept("PendingPOs.to", today());
  const [branch, setBranch] = useKept("PendingPOs.branch", "");
  const [late, setLate] = useKept("PendingPOs.late", false);
  const [page, setPage] = useKept("PendingPOs.page", 1);
  const [data, setData] = useState<Report<PendingOrder> | null>(null);
  const [error, setError] = useState<unknown>("");

  const all: ReportColumn<PendingOrder>[] = useMemo(
    () => [
      {
        key: "number",
        label: "PO No",
        fixed: true,
        search: "number",
        cell: (r) => <EntryLink companyId={companyId} entry={{ type: "purchase_order", type_label: "Purchase Order", id: r.id, number: r.number, page: "purchase-orders" }} />,
        text: (r) => r.number,
      },
      { key: "date", label: "PO Date", standard: true, search: "date", cell: (r) => dmy(r.date), text: (r) => dmy(r.date) },
      { key: "supplier", label: "Supplier", standard: true, search: "supplier", cell: (r) => r.supplier, text: (r) => r.supplier },
      { key: "expected", label: "Expected Delivery", standard: true, search: "expected", cell: (r) => dmy(r.expected), text: (r) => dmy(r.expected) },
      {
        key: "late",
        label: "Days Late",
        standard: true,
        num: true,
        cell: (r) => (r.late ? <span className="late">{r.late}</span> : ""),
        text: (r) => (r.late ? String(r.late) : ""),
      },
      { key: "purchaser", label: "Purchaser", standard: true, search: "purchaser", cell: (r) => r.purchaser, text: (r) => r.purchaser },
      { key: "branch", label: "Branch", standard: true, search: "branch_name", cell: (r) => r.branch, text: (r) => r.branch },
      { key: "lines", label: "Lines Pending", standard: true, num: true, cell: (r) => r.lines, text: (r) => String(r.lines) },
      { key: "value", label: "Order Value ₹", standard: true, num: true, cell: (r) => rupees(r.value), text: (r) => rupees(r.value) },
      { key: "pending", label: "Pending Value ₹", standard: true, num: true, cell: (r) => rupees(r.pending), text: (r) => rupees(r.pending) },
      {
        key: "status",
        label: "Status",
        standard: true,
        search: "status",
        cell: (r) => <span className={`pill ${r.status === "Ordered" ? "on" : "warn"}`}>{r.status}</span>,
        text: (r) => r.status,
      },
    ],
    [companyId],
  );
  const columns = useColumns<PendingOrder>("pending-purchase-orders", all);
  const shown = columns.shown as ReportColumn<PendingOrder>[];
  const { searches, onSearch } = useServerSearch("PendingPOs", shown, setPage);

  const query = useCallback(
    (more: Record<string, string>) => {
      const q = new URLSearchParams(more);
      if (from) q.set("from", from);
      if (to) q.set("to", to);
      if (branch) q.set("branch", branch);
      if (late) q.set("late", "1");
      if (columns.sort) q.set("sort", columns.sort);
      Object.entries(searches).forEach(([k, v]) => v && q.set(k, v));
      return `v1/companies/${companyId}/pending-purchase-orders/?${q}`;
    },
    [companyId, from, to, branch, late, columns.sort, searches],
  );
  useEffect(() => {
    setError("");
    api<Report<PendingOrder>>(query({ page: String(page) })).then(setData, setError);
  }, [query, page]);

  const title = "Pending Purchase Orders";
  const branchName = data?.branches.find((b) => String(b.id) === branch)?.name;
  const scope = [data?.company_name, branchName, `PO dates ${dmy(from) || "start"} to ${dmy(to) || "today"}`, late ? "Late deliveries only" : ""]
    .filter(Boolean)
    .join(" · ");
  // Print, PDF and Excel take every row, not just this page.
  const load = useCallback(async (): Promise<PrintSheet["sheets"]> => {
    const d = await api<Report<PendingOrder>>(query({ all: "1" }));
    const rows = d.results.map((r) => shown.map((c) => c.text(r)));
    const t = d.totals;
    const totals: Record<string, string> = { number: "Total", lines: String(t.lines), value: rupees(t.value), pending: rupees(t.pending) };
    rows.push(shown.map((c) => totals[c.key] ?? ""));
    const text = shown.map((c, i) => (c.num ? -1 : i)).filter((i) => i >= 0);
    return [{ title, columns: shown.map((c) => c.label), rows, text, right: shown.map((c) => !!c.num) }];
  }, [query, shown]);
  const printing = usePrintMenu({ title, scope, load });
  const excel = excelItem(title, scope, load, setError);

  const totals = data?.totals;
  const totalCell = (key: string) =>
    key === "number" ? "Total" : key === "date" ? `${totals?.orders.toLocaleString("en-IN")} ${totals?.orders === 1 ? "order" : "orders"}` : key === "lines" ? totals?.lines : key === "value" ? rupees(totals?.value ?? "0") : key === "pending" ? rupees(totals?.pending ?? "0") : "";
  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={`${data?.company_name ?? ""}: submitted orders with goods still to come, one line per order. Closed lines are left out.`}
        actions={printing.menu([columns.item, ...printing.items, excel])}
      />
      {printing.panel}
      {columns.panel}
      <Section title="Show">
        <div className="row report-filters narrow">
          <label>
            PO Date From
            <input type="date" value={from} max="9999-12-31" onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
          </label>
          <label>
            To
            <input type="date" value={to} max="9999-12-31" onChange={(e) => { setTo(e.target.value); setPage(1); }} />
          </label>
          <label>
            Branch
            <Combobox
              ariaLabel="Branch"
              options={(data?.branches ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
              value={branch}
              empty="All branches"
              onChange={(v) => { setBranch(v); setPage(1); }}
            />
          </label>
          <label className="report-tick">
            <input type="checkbox" checked={late} onChange={(e) => { setLate(e.target.checked); setPage(1); }} /> Late Deliveries Only
          </label>
        </div>
      </Section>
      <ErrorNote error={error} />
      <table className="report pick" data-title={title}>
        <thead>
          <tr>
            {shown.map((c) => (
              <th key={c.key} className={c.num ? "num" : undefined} data-no-search={c.search ? undefined : ""}>
                {columns.heading(c)}
              </th>
            ))}
          </tr>
          <ColumnSearch key={shown.map((c) => c.key).join(",")} onSearch={onSearch} />
        </thead>
        <tbody>
          {data && data.results.length === 0 && (
            <tr>
              <td colSpan={shown.length} className="small">
                {Object.values(searches).some(Boolean) ? "Nothing matches the column searches." : "No orders are waiting for goods."}
              </td>
            </tr>
          )}
          {data?.results.map((r) => (
            <tr key={r.id}>
              {shown.map((c) => (
                <td key={c.key} className={c.num ? "num" : undefined}>
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
          {data && data.results.length > 0 && (
            <tr className="report-total">
              {shown.map((c) => (
                <td key={c.key} className={c.num ? "num" : undefined}>
                  {totalCell(c.key)}
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
      <Pager data={data} noun="orders" onPage={setPage} />
      <p className="small no-print">
        Click a PO number to open the order. Days Late counts from the Expected Delivery date to today. Pending Value is the quantity still to come at the order rate, before GST. The totals cover every page.
      </p>
    </section>
  );
}

type TrackerLine = {
  id: number;
  order: number;
  number: string;
  date: string;
  supplier: string;
  expected: string | null;
  late: boolean;
  item_code: string;
  item_name: string;
  unit: string;
  ordered: string;
  received: string;
  balance: string;
  grn: string;
  grn_id: number | null;
  billed: string;
  status: string;
  rate: string;
  pending: string;
  purchaser: string;
  branch: string;
  reason: string;
};

const LINES = [
  { value: "pending", label: "Pending only" },
  { value: "received", label: "Received" },
  { value: "all", label: "All" },
];
const STATUS_PILL: Record<string, string> = { Pending: "on", "Part received": "warn", Received: "", Closed: "" };

/** Reports › Purchase › Procurement Tracker: every order line with what was ordered, received and
 * billed, and what is still to come (Sidharth, 2026-11-27, preview mockups/purchase-reports/2). */
export function ProcurementTrackerPage({ companyId }: { companyId: number }) {
  const [from, setFrom] = useKept("Tracker.from", yearStart());
  const [to, setTo] = useKept("Tracker.to", today());
  const [branch, setBranch] = useKept("Tracker.branch", "");
  const [lines, setLines] = useKept("Tracker.lines", "pending");
  const [page, setPage] = useKept("Tracker.page", 1);
  const [data, setData] = useState<Report<TrackerLine> | null>(null);
  const [error, setError] = useState<unknown>("");

  const all: ReportColumn<TrackerLine>[] = useMemo(() => {
    const plain = (key: keyof TrackerLine, label: string, search?: string, standard = true): ReportColumn<TrackerLine> => ({
      key,
      label,
      standard,
      search,
      cell: (r) => String(r[key] ?? ""),
      text: (r) => String(r[key] ?? ""),
    });
    const number = (key: "ordered" | "received" | "balance" | "billed", label: string): ReportColumn<TrackerLine> => ({
      key,
      label,
      standard: true,
      num: true,
      cell: (r) => qty(r[key]),
      text: (r) => qty(r[key]),
    });
    return [
      { ...plain("supplier", "Supplier", "supplier"), fixed: true },
      {
        key: "number",
        label: "PO No",
        fixed: true,
        search: "number",
        cell: (r) => <EntryLink companyId={companyId} entry={{ type: "purchase_order", type_label: "Purchase Order", id: r.order, number: r.number, page: "purchase-orders" }} />,
        text: (r) => r.number,
      },
      { key: "date", label: "PO Date", standard: true, search: "date", cell: (r) => dmy(r.date), text: (r) => dmy(r.date) },
      {
        key: "expected",
        label: "Expected Delivery",
        standard: true,
        search: "expected",
        cell: (r) => (r.late ? <span className="late" title="Late: goods still to come">{dmy(r.expected)}</span> : dmy(r.expected)),
        text: (r) => dmy(r.expected),
      },
      plain("item_code", "Item Code", "item_code"),
      plain("item_name", "Item Name", "item_name"),
      plain("unit", "Unit", "unit"),
      number("ordered", "Qty Ordered"),
      number("received", "Qty Received"),
      number("balance", "Balance"),
      {
        key: "grn",
        label: "GRN No",
        standard: true,
        search: "grn",
        cell: (r) => (r.grn_id ? <EntryLink companyId={companyId} entry={{ type: "goods_receipt", type_label: "Goods Receipt", id: r.grn_id, number: r.grn, page: "goods-receipts" }} /> : ""),
        text: (r) => r.grn,
      },
      number("billed", "Qty Billed"),
      {
        key: "status",
        label: "Status",
        standard: true,
        search: "status",
        cell: (r) => <span className={`pill ${STATUS_PILL[r.status] ?? ""}`}>{r.status}</span>,
        text: (r) => r.status,
      },
      { key: "rate", label: "Rate ₹", num: true, cell: (r) => rupees(r.rate), text: (r) => rupees(r.rate) },
      { key: "pending", label: "Pending Value ₹", num: true, cell: (r) => rupees(r.pending), text: (r) => rupees(r.pending) },
      plain("purchaser", "Purchaser", "purchaser", false),
      plain("branch", "Branch", "branch_name", false),
      plain("reason", "Closed Reason", "reason", false),
    ];
  }, [companyId]);
  const columns = useColumns<TrackerLine>("procurement-tracker", all);
  const shown = columns.shown as ReportColumn<TrackerLine>[];
  const { searches, onSearch } = useServerSearch("Tracker", shown, setPage);

  const query = useCallback(
    (more: Record<string, string>) => {
      const q = new URLSearchParams(more);
      if (from) q.set("from", from);
      if (to) q.set("to", to);
      if (branch) q.set("branch", branch);
      q.set("lines", lines);
      if (columns.sort) q.set("sort", columns.sort);
      Object.entries(searches).forEach(([k, v]) => v && q.set(k, v));
      return `v1/companies/${companyId}/procurement-tracker/?${q}`;
    },
    [companyId, from, to, branch, lines, columns.sort, searches],
  );
  useEffect(() => {
    setError("");
    api<Report<TrackerLine>>(query({ page: String(page) })).then(setData, setError);
  }, [query, page]);

  const title = "Procurement Tracker";
  const branchName = data?.branches.find((b) => String(b.id) === branch)?.name;
  const linesName = LINES.find((l) => l.value === lines)?.label;
  const scope = [data?.company_name, branchName, `PO dates ${dmy(from) || "start"} to ${dmy(to) || "today"}`, `Lines: ${linesName}`].filter(Boolean).join(" · ");
  const load = useCallback(async (): Promise<PrintSheet["sheets"]> => {
    const d = await api<Report<TrackerLine>>(query({ all: "1" }));
    const rows = d.results.map((r) => shown.map((c) => c.text(r)));
    const text = shown.map((c, i) => (c.num ? -1 : i)).filter((i) => i >= 0);
    return [{ title, columns: shown.map((c) => c.label), rows, text, right: shown.map((c) => !!c.num) }];
  }, [query, shown]);
  const printing = usePrintMenu({ title, scope, load });
  const excel = excelItem(title, scope, load, setError);

  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={`${data?.company_name ?? ""}: every order line with what was ordered, received and billed, and what is still to come.`}
        actions={printing.menu([columns.item, ...printing.items, excel])}
      />
      {printing.panel}
      {columns.panel}
      <Section title="Show">
        <div className="row report-filters narrow">
          <label>
            PO Date From
            <input type="date" value={from} max="9999-12-31" onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
          </label>
          <label>
            To
            <input type="date" value={to} max="9999-12-31" onChange={(e) => { setTo(e.target.value); setPage(1); }} />
          </label>
          <label>
            Branch
            <Combobox
              ariaLabel="Branch"
              options={(data?.branches ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
              value={branch}
              empty="All branches"
              onChange={(v) => { setBranch(v); setPage(1); }}
            />
          </label>
          <label>
            Lines
            <Combobox ariaLabel="Lines" options={LINES} value={lines} onChange={(v) => { setLines(v || "pending"); setPage(1); }} />
          </label>
        </div>
      </Section>
      <ErrorNote error={error} />
      <table className="report pick tracker" data-title={title}>
        <thead>
          <tr>
            {shown.map((c) => (
              <th key={c.key} className={c.num ? "num" : undefined} data-no-search={c.search ? undefined : ""}>
                {columns.heading(c)}
              </th>
            ))}
          </tr>
          <ColumnSearch key={shown.map((c) => c.key).join(",")} onSearch={onSearch} />
        </thead>
        <tbody>
          {data && data.results.length === 0 && (
            <tr>
              <td colSpan={shown.length} className="small">
                {Object.values(searches).some(Boolean) ? "Nothing matches the column searches." : lines === "pending" ? "No order lines are waiting for goods." : "No order lines in these dates."}
              </td>
            </tr>
          )}
          {data?.results.map((r) => (
            <tr key={r.id}>
              {shown.map((c) => (
                <td key={c.key} className={c.num ? "num" : undefined}>
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <Pager data={data} noun="lines" onPage={setPage} />
      <p className="small no-print">
        "Lines" picks "Pending only" (goods still to come), "Received" (received in full or closed) or "All". A late Expected Delivery shows in red. Click a PO or GRN number to open it; GRN No is the latest receipt against the line. "Choose Columns…" in Actions adds Rate, Pending Value, Purchaser, Branch and Closed Reason.
      </p>
    </section>
  );
}
