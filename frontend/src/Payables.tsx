import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { PageHeader, Section } from "./Brand";
import { ColumnSearch } from "./ColumnSearch";
import { useColumns } from "./Columns";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu, type MenuItem, type PrintSheet } from "./Exchange";
import { useKept } from "./Keep";
import { Fold, openTab, SidePanel, SideRows } from "./Master";
import { Pager, type Paged } from "./Pager";
import { excelItem, useServerSearch, type ReportColumn } from "./PurchaseReports";
import { dmy, rupees } from "./Reports";
import { People } from "./SupplierMail";

/** Reports › Purchase › Accounts Payable (Sidharth, 2026-11-28, previews mockups/accounts-payable/1
 * to 4): what the company owes each supplier, bill by bill, aged by days past the due date. */

type Choice = { id: number; name: string };
type SupplierRow = {
  id: number;
  supplier: string;
  code: string;
  term: string;
  purchaser: string;
  bills: number;
  b: string[];
  due: string;
  overdue: string;
  oldest: number;
};
type BillRow = {
  id: string;
  invoice: number | null;
  supplier_id: number;
  supplier: string;
  code: string;
  term: string;
  bill_no: string;
  our_no: string;
  bill_date: string;
  due_date: string;
  amount: string;
  tds: string;
  tds_note: string;
  dn: string;
  dn_note: string;
  paid: string;
  paid_note: string;
  balance: string;
  late: number;
  age: string;
  age_index: number;
  buckets: string[];
};
type Group = { bills: number; amount: string; tds: string; dn: string; paid: string; balance: string };
type Report<T> = Paged<T> & {
  company_name: string;
  as_on: string;
  labels: string[];
  branches: Choice[];
  purchasers: Choice[];
  totals: Record<string, string | number | string[]>;
  groups?: Record<string, Group>;
};

const today = () => new Date().toISOString().slice(0, 10);
const VIEWS = [
  { value: "suppliers", label: "Suppliers" },
  { value: "bills", label: "Bills" },
];
const AGE_BY = [
  { value: "due", label: "Due Date" },
  { value: "bill", label: "Bill Date" },
];
/** A rupee figure, empty for nothing. */
const amount = (v: string) => (Number(v) ? rupees(v) : "");
const days = (n: number) => (n > 60 ? <span className="late">{n}</span> : n || "");
const bucketName = (labels: string[], i: number, byBill: boolean) => (i === 0 && !byBill ? labels[0] : `${labels[i]} days`);

export function PayablesPage({ companyId, canMail }: { companyId: number; canMail: boolean }) {
  const [asOn, setAsOn] = useKept("Payables.asOn", today());
  const [view, setView] = useKept("Payables.view", "suppliers");
  const [ageBy, setAgeBy] = useKept("Payables.ageBy", "due");
  const [branch, setBranch] = useKept("Payables.branch", "");
  const [purchaser, setPurchaser] = useKept("Payables.purchaser", "");
  const [overdue, setOverdue] = useKept("Payables.overdue", false);
  // "Show Bills" from a supplier: the Bills view for that supplier alone.
  const [onlySupplier, setOnlySupplier] = useKept<{ id: number; name: string } | null>("Payables.onlySupplier", null);
  const [page, setPage] = useKept("Payables.page", 1);
  const [picked, setPicked] = useKept<number | null>("Payables.picked", null);
  // Bills ticked to pay (Sidharth, 2026-11-28): id -> balance, kept across pages.
  const [ticked, setTicked] = useKept<Record<string, string>>("Payables.ticked", {});
  const [data, setData] = useState<Report<SupplierRow | BillRow> | null>(null);
  const [error, setError] = useState<unknown>("");
  const bills = view === "bills";
  const byBill = ageBy === "bill";
  const labels = data?.labels ?? (byBill ? ["0-30", "31-60", "61-90", "91-180", "Over 180"] : ["Not Due", "1-30", "31-60", "61-90", "Over 90"]);

  const supplierColumns: ReportColumn<SupplierRow>[] = useMemo(
    () => [
      {
        key: "supplier",
        label: "Supplier",
        fixed: true,
        search: "supplier",
        cell: (r) => (
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setPicked(r.id);
            }}
          >
            {r.supplier}
          </a>
        ),
        text: (r) => r.supplier,
      },
      { key: "code", label: "Code", standard: true, search: "code", cell: (r) => r.code, text: (r) => r.code },
      { key: "term", label: "Credit Term", standard: true, search: "term", cell: (r) => r.term, text: (r) => r.term },
      { key: "purchaser", label: "Purchaser", search: "purchaser", cell: (r) => r.purchaser, text: (r) => r.purchaser },
      { key: "bills", label: "Bills", standard: true, num: true, cell: (r) => r.bills, text: (r) => String(r.bills) },
      ...labels.map(
        (lab, i): ReportColumn<SupplierRow> => ({
          key: `b${i}`,
          label: `${lab} ₹`,
          standard: true,
          num: true,
          cell: (r) => (i >= 3 && !byBill && Number(r.b[i]) ? <span className="late">{rupees(r.b[i])}</span> : amount(r.b[i])),
          text: (r) => amount(r.b[i]),
        }),
      ),
      { key: "due", label: "Total Due ₹", standard: true, num: true, cell: (r) => <b>{rupees(r.due)}</b>, text: (r) => rupees(r.due) },
      {
        key: "oldest",
        label: "Oldest Overdue",
        standard: true,
        num: true,
        cell: (r) => (r.oldest > 60 ? <span className="late">{r.oldest} days</span> : r.oldest ? `${r.oldest} days` : ""),
        text: (r) => (r.oldest ? `${r.oldest} days` : ""),
      },
    ],
    [labels.join(","), byBill],
  );
  const billColumns: ReportColumn<BillRow>[] = useMemo(() => {
    const withNote = (key: "tds" | "dn" | "paid", label: string): ReportColumn<BillRow> => ({
      key,
      label,
      standard: true,
      num: true,
      cell: (r) => (
        <>
          {amount(r[key])}
          {r[`${key}_note`] && <div className="small-inline">{r[`${key}_note`]}</div>}
        </>
      ),
      text: (r) => amount(r[key]),
    });
    return [
      { key: "supplier", label: "Supplier", fixed: true, search: "supplier", cell: () => "", text: (r) => r.supplier },
      {
        key: "bill_no",
        label: "Bill No",
        fixed: true,
        search: "bill_no",
        cell: (r) =>
          r.invoice ? (
            <a
              href={`#/companies/${companyId}/purchase-invoices?view=${r.invoice}`}
              onClick={(e) => {
                e.preventDefault();
                openTab(`#/companies/${companyId}/purchase-invoices?view=${r.invoice}`);
              }}
            >
              {r.bill_no}
            </a>
          ) : (
            r.bill_no
          ),
        text: (r) => r.bill_no,
      },
      { key: "our_no", label: "Our Entry", standard: true, search: "our_no", cell: (r) => (r.our_no === "Opening" ? "Opening bill" : r.our_no), text: (r) => r.our_no },
      { key: "bill_date", label: "Bill Date", standard: true, nowrap: true, search: "bill_date", cell: (r) => dmy(r.bill_date), text: (r) => dmy(r.bill_date) },
      { key: "due_date", label: "Due Date", standard: true, nowrap: true, search: "due_date", cell: (r) => dmy(r.due_date), text: (r) => dmy(r.due_date) },
      { key: "amount", label: "Bill Amount ₹", standard: true, num: true, cell: (r) => rupees(r.amount), text: (r) => rupees(r.amount) },
      withNote("tds", "TDS ₹"),
      withNote("dn", "Debit Notes ₹"),
      withNote("paid", "Paid ₹"),
      { key: "balance", label: "Balance ₹", standard: true, num: true, cell: (r) => <b>{rupees(r.balance)}</b>, text: (r) => rupees(r.balance) },
      { key: "late", label: "Days Overdue", standard: true, num: true, cell: (r) => days(r.late), text: (r) => (r.late ? String(r.late) : "") },
      {
        key: "age",
        label: "Age",
        standard: true,
        search: "age",
        cell: (r) => <span className={`pill ${r.age_index === 0 ? "on" : r.age_index >= 3 && !byBill ? "bad" : "warn"}`}>{r.age}</span>,
        text: (r) => r.age,
      },
    ];
  }, [companyId, byBill]);
  const supplierCols = useColumns<SupplierRow>("accounts-payable-suppliers", supplierColumns);
  const billCols = useColumns<BillRow>("accounts-payable-bills", billColumns);
  const columns = bills ? billCols : supplierCols;
  const shown = columns.shown as ReportColumn<SupplierRow | BillRow>[];
  const { searches, onSearch } = useServerSearch(bills ? "Payables.bills" : "Payables.suppliers", shown, setPage);
  // The Bills view has a tick column first, with no search box: its boxes start one later.
  const onBoxes = useCallback((values: string[]) => onSearch(bills ? values.slice(1) : values), [onSearch, bills]);

  const filters = useMemo(() => {
    const q = new URLSearchParams();
    if (asOn) q.set("as_on", asOn);
    q.set("age_by", ageBy);
    if (branch) q.set("branch", branch);
    if (purchaser) q.set("purchaser", purchaser);
    if (overdue) q.set("overdue", "1");
    return q;
  }, [asOn, ageBy, branch, purchaser, overdue]);
  const query = useCallback(
    (more: Record<string, string>) => {
      const q = new URLSearchParams(filters);
      q.set("view", view);
      if (bills && onlySupplier) q.set("ledger", String(onlySupplier.id));
      if (columns.sort) q.set("sort", columns.sort);
      Object.entries(searches).forEach(([k, v]) => v && q.set(k, v));
      Object.entries(more).forEach(([k, v]) => q.set(k, v));
      return `v1/companies/${companyId}/accounts-payable/?${q}`;
    },
    [companyId, filters, view, bills, onlySupplier, columns.sort, searches],
  );
  useEffect(() => {
    setError("");
    setData(null);
    api<Report<SupplierRow | BillRow>>(query({ page: String(page) })).then(setData, setError);
  }, [query, page]);

  const title = "Accounts Payable";
  const branchName = data?.branches.find((b) => String(b.id) === branch)?.name;
  const purchaserName = data?.purchasers.find((p) => String(p.id) === purchaser)?.name;
  const scope = [
    data?.company_name,
    branchName ?? "All branches",
    purchaserName && `Purchaser ${purchaserName}`,
    bills && onlySupplier ? onlySupplier.name : "",
    `As on ${dmy(asOn)}`,
    byBill ? "Aged by Bill Date" : "Aged by Due Date",
    overdue ? "Overdue only" : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const load = useCallback(async (): Promise<PrintSheet["sheets"]> => {
    const d = await api<Report<SupplierRow | BillRow>>(query({ all: "1" }));
    const rows = d.results.map((r) => shown.map((c) => c.text(r)));
    const t = d.totals;
    const totals: Record<string, string> = bills
      ? { supplier: "Total", amount: rupees(String(t.amount)), tds: amount(String(t.tds)), dn: amount(String(t.dn)), paid: amount(String(t.paid)), balance: rupees(String(t.balance)) }
      : {
          supplier: "Total",
          bills: String(t.bills),
          due: rupees(String(t.due)),
          ...Object.fromEntries((t.b as string[]).map((v, i) => [`b${i}`, rupees(v)])),
        };
    rows.push(shown.map((c) => totals[c.key] ?? ""));
    const text = shown.map((c, i) => (c.num ? -1 : i)).filter((i) => i >= 0);
    return [{ title, columns: shown.map((c) => c.label), rows, text, right: shown.map((c) => !!c.num) }];
  }, [query, shown, bills]);
  const printing = usePrintMenu({ title, scope, load });
  const excel = excelItem(title, scope, load, setError);
  const pdfUrl = (layout: string) => `/api/v1/companies/${companyId}/accounts-payable/pdf/?${filters}&layout=${layout}`;
  const managementItems: MenuItem[] = [
    { label: "Print Summary with Ageing", onClick: () => openTab(pdfUrl("summary")) },
    { label: "Print Summary with Bills", onClick: () => openTab(pdfUrl("bills")) },
  ];
  const statementUrl = (id: number, download = false) =>
    `/api/v1/companies/${companyId}/accounts-payable/suppliers/${id}/pdf/?as_on=${asOn}&age_by=${ageBy}${download ? "&download=1" : ""}`;

  const t = data?.totals;
  const supplierRows = !bills ? ((data?.results ?? []) as SupplierRow[]) : [];
  const billRows = bills ? ((data?.results ?? []) as BillRow[]) : [];
  const selected = supplierRows.find((r) => r.id === picked) ?? null;
  const grouped = bills && (!columns.sort || columns.sort === "supplier");
  const tickedIds = Object.keys(ticked);
  const tickedTotal = Object.values(ticked).reduce((s, v) => s + Number(v), 0);
  const tick = (r: BillRow, on: boolean) =>
    setTicked((was) => {
      const next = { ...was };
      if (on) next[r.id] = r.balance;
      else delete next[r.id];
      return next;
    });
  const pageTicked = billRows.length > 0 && billRows.filter((r) => Number(r.balance) > 0).every((r) => ticked[r.id]);
  const change = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  const totalCell = (key: string) => {
    if (!t) return "";
    if (key === "supplier") return "Total";
    if (bills) {
      if (key === "bill_no") return `${Number(t.bills).toLocaleString("en-IN")} bills · ${t.suppliers} suppliers`;
      if (["amount", "balance"].includes(key)) return rupees(String(t[key]));
      if (["tds", "dn", "paid"].includes(key)) return amount(String(t[key]));
      return "";
    }
    if (key === "code") return `${t.suppliers} ${t.suppliers === 1 ? "supplier" : "suppliers"}`;
    if (key === "bills") return String(t.bills);
    if (key === "due") return rupees(String(t.due));
    if (/^b\d$/.test(key)) return rupees((t.b as string[])[Number(key[1])]);
    return "";
  };

  const groupRow = (r: BillRow) => {
    const g = data?.groups?.[String(r.supplier_id)];
    return (
      <tr key={`g-${r.supplier_id}`} className="report-group">
        <td />
        {shown.map((c, i) =>
          i === 0 ? (
            <td key={c.key}>{[r.supplier, r.code, r.term].filter(Boolean).join(" · ")}</td>
          ) : (
            <td key={c.key} className={c.num ? "num" : undefined}>
              {g && ["amount", "balance"].includes(c.key) ? rupees(g[c.key as "amount"]) : g && ["tds", "dn", "paid"].includes(c.key) ? amount(g[c.key as "tds"]) : ""}
            </td>
          ),
        )}
      </tr>
    );
  };

  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={`${data?.company_name ?? ""}: ${bills ? "every open supplier bill on the As On date, grouped by supplier." : "what we owe each supplier on the As On date, aged by days past the due date."}`}
        actions={printing.menu([columns.item, ...printing.items, excel, ...managementItems])}
      />
      {printing.panel}
      {columns.panel}
      <Section title="Show">
        <div className="row report-filters narrow">
          <label>
            As On
            <input type="date" value={asOn} max="9999-12-31" onChange={(e) => change(setAsOn)(e.target.value)} />
          </label>
          <label>
            View
            <Combobox ariaLabel="View" options={VIEWS} value={view} onChange={(v) => { setView(v || "suppliers"); setPage(1); }} />
          </label>
          <label>
            Age By
            <Combobox ariaLabel="Age By" options={AGE_BY} value={ageBy} onChange={(v) => change(setAgeBy)(v || "due")} />
          </label>
          <label>
            Branch
            <Combobox
              ariaLabel="Branch"
              options={(data?.branches ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
              value={branch}
              empty="All branches"
              onChange={change(setBranch)}
            />
          </label>
          <label>
            Purchaser
            <Combobox
              ariaLabel="Purchaser"
              options={(data?.purchasers ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
              value={purchaser}
              empty="All"
              onChange={change(setPurchaser)}
            />
          </label>
          <label className="report-tick">
            <input type="checkbox" checked={overdue} onChange={(e) => change(setOverdue)(e.target.checked)} /> Overdue Only
          </label>
        </div>
      </Section>
      <ErrorNote error={error} />
      {bills && onlySupplier && (
        <p className="use-note no-print">
          Showing the bills of <b>{onlySupplier.name}</b> only.{" "}
          <button type="button" className="link" onClick={() => { setOnlySupplier(null); setPage(1); }}>
            Show All Suppliers
          </button>
        </p>
      )}
      {bills && tickedIds.length > 0 && (
        <div className="pay-bar no-print">
          <span>
            <b>{tickedIds.length}</b> {tickedIds.length === 1 ? "bill" : "bills"} ticked · To Pay <b>₹{rupees(tickedTotal.toFixed(2))}</b>
          </span>
          <button type="button" className="link" onClick={() => setTicked({})}>
            Clear Ticks
          </button>
          <button type="button" disabled title="Comes with the Payment entry">
            Make Payment
          </button>
        </div>
      )}
      <div className={selected ? "side-layout" : "full-list"}>
        <div className="side-main">
          <table className="report pick" data-title={title}>
            <thead>
              <tr>
                {bills && (
                  <th className="no-print tick-col" data-no-search="">
                    <input
                      type="checkbox"
                      aria-label="Tick every bill on this page"
                      checked={pageTicked}
                      onChange={(e) => billRows.filter((r) => Number(r.balance) > 0).forEach((r) => tick(r, e.target.checked))}
                    />
                  </th>
                )}
                {shown.map((c) => (
                  <th key={c.key} className={c.num ? "num" : undefined} data-no-search={c.search ? undefined : ""}>
                    {columns.heading(c as never)}
                  </th>
                ))}
              </tr>
              <ColumnSearch key={`${view}:${shown.map((c) => c.key).join(",")}`} onSearch={onBoxes} />
            </thead>
            <tbody>
              {data && data.results.length === 0 && (
                <tr>
                  <td colSpan={shown.length + (bills ? 1 : 0)} className="small">
                    {Object.values(searches).some(Boolean) ? "Nothing matches the column searches." : "No supplier bills are open on this date."}
                  </td>
                </tr>
              )}
              {supplierRows.map((r) => (
                <tr key={r.id} tabIndex={0} className={picked === r.id ? "selected" : ""} onClick={() => setPicked(picked === r.id ? null : r.id)}>
                  {shown.map((c) => (
                    <td key={c.key} className={c.num ? "num" : undefined}>
                      {c.cell(r as never)}
                    </td>
                  ))}
                </tr>
              ))}
              {billRows.map((r, n) => (
                <FragmentRows key={r.id}>
                  {grouped && (n === 0 || billRows[n - 1].supplier_id !== r.supplier_id) && groupRow(r)}
                  <tr className={ticked[r.id] ? "selected" : ""}>
                    <td className="no-print tick-col">
                      {Number(r.balance) > 0 && <input type="checkbox" aria-label={`Tick bill ${r.bill_no}`} checked={!!ticked[r.id]} onChange={(e) => tick(r, e.target.checked)} />}
                    </td>
                    {shown.map((c) => (
                      <td key={c.key} className={c.num ? "num" : c.nowrap ? "nowrap" : undefined}>
                        {c.key === "supplier" && !grouped ? r.supplier : c.cell(r as never)}
                      </td>
                    ))}
                  </tr>
                </FragmentRows>
              ))}
              {data && data.results.length > 0 && (
                <tr className="report-total">
                  {bills && <td className="no-print" />}
                  {shown.map((c) => (
                    <td key={c.key} className={c.num ? "num" : undefined}>
                      {totalCell(c.key)}
                    </td>
                  ))}
                </tr>
              )}
            </tbody>
          </table>
          <Pager data={data} noun={bills ? "bills" : "suppliers"} onPage={setPage} />
          <p className="small no-print">
            {bills
              ? 'Tick bills to see what they come to; "Make Payment" will use the ticks once the Payment entry is built. The grey line under an amount names what made it: the TDS section (and any TDS Adjustment), the debit note numbers, the payments. Click a bill number to open the purchase invoice.'
              : 'Click a supplier to see its ageing at the right. Due dates come from each bill\'s credit term. Balance is the bill amount less TDS, debit notes and payments set against it; bills brought from the old books are included. The totals cover every page.'}
          </p>
        </div>
        {selected && (
          <SupplierPanel
            companyId={companyId}
            row={selected}
            labels={labels}
            byBill={byBill}
            filters={filters}
            canMail={canMail}
            statementUrl={statementUrl}
            onBills={() => {
              setOnlySupplier({ id: selected.id, name: selected.supplier });
              setView("bills");
              setPage(1);
            }}
          />
        )}
      </div>
    </section>
  );
}

/** Several rows under one key (a supplier's heading and its first bill). */
function FragmentRows({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

function SupplierPanel(props: {
  companyId: number;
  row: SupplierRow;
  labels: string[];
  byBill: boolean;
  filters: URLSearchParams;
  canMail: boolean;
  statementUrl: (id: number, download?: boolean) => string;
  onBills: () => void;
}) {
  const { companyId, row, labels, byBill, filters } = props;
  const [late, setLate] = useState<BillRow[]>([]);
  const [mailing, setMailing] = useState(false);
  const [sent, setSent] = useState("");
  useEffect(() => {
    setLate([]);
    setMailing(false);
    setSent("");
    const q = new URLSearchParams(filters);
    q.set("view", "bills");
    q.set("ledger", String(row.id));
    q.set("overdue", "1");
    q.set("all", "1");
    q.set("sort", "-late");
    api<Report<BillRow>>(`v1/companies/${companyId}/accounts-payable/?${q}`).then((d) => setLate(d.results), (e) => console.error("overdue bills", e));
  }, [companyId, row.id, filters]);
  return (
    <div className="side-col" aria-label="Supplier details">
      <SidePanel title={row.supplier} tag={row.code}>
        <SideRows
          rows={[
            ["Credit Term", row.term],
            ["Purchaser", row.purchaser],
            ...labels.map((_, i): [string, string] => [bucketName(labels, i, byBill), `₹${rupees(row.b[i])}`]),
            ["Total Due", `₹${rupees(row.due)}`],
          ]}
        />
        {late.length > 0 && (
          <table className="side-lines">
            <thead>
              <tr>
                <th>Overdue Bill</th>
                <th className="num">Days</th>
                <th className="num">Balance ₹</th>
              </tr>
            </thead>
            <tbody>
              {late.map((b) => (
                <tr key={b.id}>
                  <td>{b.bill_no}</td>
                  <td className="num">{b.late}</td>
                  <td className="num">{rupees(b.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="side-buttons wrap">
          <button type="button" onClick={props.onBills}>
            Show Bills
          </button>
          <button type="button" className="link" onClick={() => openTab(`#/companies/${companyId}/ledger-statement?ledger=${row.id}`)}>
            Open Ledger Statement
          </button>
          <button type="button" className="link" onClick={() => openTab(props.statementUrl(row.id))}>
            Print Outstanding Statement
          </button>
          {props.canMail && (
            <button type="button" className="link" onClick={() => setMailing(true)}>
              Email Outstanding Statement
            </button>
          )}
        </div>
        {sent && <p className="use-note">Sent to {sent}.</p>}
      </SidePanel>
      {mailing && (
        <StatementMail
          companyId={companyId}
          ledger={row.id}
          query={`as_on=${filters.get("as_on") ?? ""}&age_by=${filters.get("age_by") ?? "due"}`}
          pdf={props.statementUrl(row.id)}
          onClose={() => setMailing(false)}
          onSent={(to) => {
            setMailing(false);
            setSent(to.join(", "));
          }}
        />
      )}
    </div>
  );
}

type Person = { name: string; email: string; of?: string };
type MailDraft = {
  supplier_name: string;
  mail_ready: boolean;
  from: string;
  to: Person[];
  to_options: Person[];
  cc: Person[];
  cc_options: Person[];
  subject: string;
  message: string;
  signature: string;
  attachment: string;
};

/** "Email Outstanding Statement": the Outstanding Bills PDF to the supplier, from the company's mailbox. */
function StatementMail(props: { companyId: number; ledger: number; query: string; pdf: string; onClose: () => void; onSent: (to: string[]) => void }) {
  const link = `v1/companies/${props.companyId}/accounts-payable/suppliers/${props.ledger}/mail/`;
  const [draft, setDraft] = useState<MailDraft | null>(null);
  const [to, setTo] = useState<Person[]>([]);
  const [cc, setCc] = useState<Person[]>([]);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<MailDraft>(`${link}?${props.query}`).then((d) => {
      setDraft(d);
      setTo(d.to);
      setCc(d.cc);
      setSubject(d.subject);
      setMessage(d.message);
    }, setError);
  }, [link, props.query]);
  if (!draft)
    return (
      <Fold title="Email Outstanding Statement" open>
        <ErrorNote error={error} />
      </Fold>
    );
  const send = async () => {
    setBusy(true);
    setError("");
    try {
      const q = new URLSearchParams(props.query);
      const done = await api<{ sent_to: string[] }>(link, {
        to: to.map((p) => p.email),
        cc: cc.map((p) => p.email),
        subject,
        message,
        as_on: q.get("as_on") ?? "",
        age_by: q.get("age_by") ?? "due",
      });
      props.onSent(done.sent_to);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const greeting = draft.to_options.find((o) => o.email === to[0]?.email)?.name || "Sir/Madam";
  return (
    <Fold title="Email Outstanding Statement" open summary={draft.mail_ready ? `From ${draft.from}` : "Mail account not set up"}>
      {!draft.mail_ready && <p className="use-note">The company's mail account is not set up yet. An Owner sets it under Admin › Company › Edit › "Mail Account".</p>}
      {draft.to_options.length === 0 && <p className="use-note">{draft.supplier_name} has no contact with an email address. Add one on the party's "Contacts", or type an address below.</p>}
      <People label="To" value={to} options={draft.to_options} onChange={setTo} />
      <People label="CC" value={cc} options={draft.cc_options} onChange={setCc} />
      <label className="field">
        <span className="fact-label">Subject</span>
        <input value={subject} onChange={(e) => setSubject(e.target.value)} />
      </label>
      <div className="field">
        <span className="fact-label">Attached</span>
        <a href={props.pdf} target="myerp-print" rel="noreferrer">
          {draft.attachment}
        </a>
      </div>
      <div className="mail-preview">
        <p>Dear {greeting},</p>
        <textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} aria-label="Message" />
        <p className="pre">Regards,{"\n" + draft.signature}</p>
      </div>
      <ErrorNote error={error} />
      <div className="buttons">
        <button type="button" className="link" onClick={props.onClose}>
          Cancel
        </button>
        <button type="button" disabled={busy || !draft.mail_ready || !to.length} onClick={send}>
          {busy ? "Sending…" : "Send"}
        </button>
      </div>
    </Fold>
  );
}
