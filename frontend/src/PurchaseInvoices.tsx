import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { Attachments, keptDraft } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { longDate, money } from "./Companies";
import { announceSaved, closeThisTab, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { RateLinesTable, type RateLine } from "./RateLines";
import { SupplementaryFormTab, type SupplementaryBill } from "./SupplementaryBills";
import { TdsBox, type TdsInfo } from "./Tds";
import { BillTypePicker, DirectFormTab, type DirectBill, type DirectLine } from "./DirectBills";
import { useReturns } from "./Refresh";

/** Entry > Purchase > Purchase Invoice (Sidharth, 2026-11-15, preview 67): the supplier's
 * bill, entered against goods receipts. Submit clears "Goods Received but Bills not
 * Received", books input GST, puts a rate difference into the stock still on hand (else
 * "Purchase Price Difference") and credits the supplier with due dates from the credit term.
 * Served by buying/invoices.py. */

type Line = {
  id?: number;
  receipt_line: number;
  receipt: number;
  receipt_number: string;
  order_number: string;
  item: number;
  item_name: string;
  hsn: string;
  unit: number;
  unit_name: string;
  unbilled_qty: string;
  qty: string;
  receipt_rate: string;
  rate: string;
  gst_rate: string;
  taxable?: string;
  cgst?: string;
  sgst?: string;
  igst?: string;
  amount?: string;
  receipt_value?: string;
  stock_difference?: string;
  price_difference?: string;
};
type Charge = { item: number; item_name: string; sac: string; amount: string; gst_rate: string; in_stock_cost: boolean; cgst?: string; sgst?: string; igst?: string };
export type Entry = { ledger: string; why: string; debit: string; credit: string };
type Invoice = {
  id: number;
  company: number;
  kind: string;
  kind_label: string;
  original: number | null;
  original_number: string;
  original_bill_no: string;
  original_bill_date: string | null;
  rate_lines?: RateLine[];
  expense_lines?: DirectLine[];
  later?: { id: number; number: string; kind: string; total: string }[];
  number: string;
  status: string;
  status_label: string;
  supplier: number;
  supplier_name: string;
  supplier_gstin: string;
  branch: number;
  branch_name: string;
  bill_no: string;
  bill_date: string | null;
  posting_date: string | null;
  credit_term: number | null;
  credit_term_name: string;
  credit_term_summary: string;
  bill_total: string | null;
  interstate: boolean;
  taxable_total: string;
  cgst_total: string;
  sgst_total: string;
  igst_total: string;
  round_off: string;
  total: string;
  notes: string;
  cancel_reason: string;
  receipts: { id: number; number: string }[];
  first_due: string | null;
  created_by_name: string;
  submitted_at: string | null;
  submitted_by_name: string;
  lines?: Line[];
  charges?: Charge[];
  dues?: { due_date: string; amount: string }[];
  orders?: string[];
  entries?: Entry[];
  tds_total?: string;
  tds?: TdsInfo;
};
type DraftFrom = {
  supplier: number;
  supplier_name: string;
  branch: number;
  branch_name: string;
  credit_term: number | null;
  interstate: boolean;
  lines: Line[];
  charges: Charge[];
};
type Setup = {
  suppliers: { id: number; name: string; credit_term: number | null }[];
  branches: { id: number; name: string }[];
  charge_items: { id: number; name: string; sac: string; add_to_stock: string; gst_rate: string | null }[];
};
type Unbilled = { receipt: number; receipt_number: string; receipt_date: string; supplier_name: string; branch_name: string; orders: string; lines: number; value: string };

const base = (companyId: number) => `#/companies/${companyId}/purchase-invoices`;
const showDate = (iso: string | null) => (iso ? longDate(iso) : "");
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const num = (v: string | undefined) => Number(v) || 0;
const r2 = (n: number) => Math.round(n * 100) / 100;
const pillClass = (status: string) => (status === "submitted" ? "pill on" : "pill");
const today = () => new Date().toISOString().slice(0, 10);
/** "Print ▾": the invoice as this page prints, and a PDF through the browser's own "Save as PDF". */
const printItems = [
  { label: "Purchase Invoice", onClick: () => window.print() },
  { label: "Download PDF", onClick: () => window.print() },
];

function useSetup(companyId: number) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [terms, setTerms] = useState<{ id: number; name: string }[]>([]);
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  useEffect(() => {
    api<Setup>(`v1/companies/${companyId}/purchase-orders/setup/`).then(setSetup, () => setSetup(null));
    api<{ id: number; name: string }[]>("v1/credit-terms/").then(setTerms, () => setTerms([]));
  }, [companyId, visits]);
  return { setup, terms };
}

export function PurchaseInvoicesPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const can = (p: string) => session.permissions.includes(`purchase.${p}`);
  const form = hashParam("form");
  const view = Number(hashParam("view"));
  if (form && can("create")) return <InvoiceFormTab companyId={companyId} form={form} canSubmit={can("submit")} />;
  if (view > 0) return <InvoiceView companyId={companyId} id={view} can={can} />;
  return <InvoiceList companyId={companyId} canCreate={can("create")} />;
}

// The list ----------------------------------------------------------------------

const VIEWS = [
  { value: "submitted", label: "Submitted" },
  { value: "draft", label: "Drafts" },
  { value: "cancelled", label: "Cancelled" },
  { value: "all", label: "All" },
  { value: "unbilled", label: "Goods received, not billed" },
];
const COLUMNS: [key: string, label: string, text: (r: Invoice) => string, num?: boolean][] = [
  ["number", "PI No", (r) => r.number || "Draft"],
  ["date", "Posting Date", (r) => `${shortDate(r.posting_date)} ${showDate(r.posting_date)}`],
  ["supplier", "Supplier", (r) => r.supplier_name],
  ["bill", "Supplier Invoice No", (r) => r.bill_no],
  ["bill_date", "Bill Date", (r) => shortDate(r.bill_date)],
  ["receipts", "Goods Receipts", (r) => (r.kind === "supplementary" ? `Supplementary against ${r.original_number}` : r.kind === "direct" ? "No GRN" : r.receipts.map((x) => x.number).join(" "))],
  ["total", "Amount ₹", (r) => `${r.total} ${money(r.total)}`, true],
  ["due", "First Due", (r) => shortDate(r.first_due)],
  ["status", "Status", (r) => r.status_label],
];

function InvoiceList({ companyId, canCreate }: { companyId: number; canCreate: boolean }) {
  const [view, setView] = useState("submitted");
  const [rows, setRows] = useState<Invoice[]>([]);
  const [unbilled, setUnbilled] = useState<Unbilled[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<unknown>("");
  const reload = useCallback(() => {
    if (view === "unbilled") api<Unbilled[]>(`v1/companies/${companyId}/purchase-invoices/unbilled/`).then(setUnbilled, setError);
    else api<Invoice[]>(`v1/companies/${companyId}/purchase-invoices/?view=${view}`).then(setRows, setError);
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("purchase_invoice_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      rows.filter((r) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          const value = text(r).toLowerCase();
          return words.every((w) => value.includes(w));
        }),
      ),
    [rows, search],
  );
  const selected = view === "unbilled" ? null : (rows.find((r) => r.id === selectedId) ?? null);
  const printing = usePrintMenu({ title: `Purchase invoices: ${VIEWS.find((v) => v.value === view)?.label ?? ""}`, scope: "" });
  const total = shown.reduce((sum, r) => sum + Number(r.total), 0);
  return (
    <section className="page">
      <PageHeader
        title="Purchase Invoice"
        crumbs={[{ label: "Entry › Purchase", href: base(companyId) }]}
        sub={view === "unbilled" ? `${unbilled.length} receipts waiting for a bill` : `${shown.length} ${shown.length === 1 ? "invoice" : "invoices"}`}
        actions={
          <>
            {canCreate && (
              <button
                type="button"
                className="secondary"
                disabled={selected?.status !== "draft"}
                title={selected ? (selected.status === "draft" ? "" : "Only a draft can be changed") : "Click a draft invoice first"}
                onClick={() => selected && openTab(`${base(companyId)}?form=${selected.id}`)}
              >
                Edit
              </button>
            )}
            {canCreate && <button onClick={() => openTab(`${base(companyId)}?form=new`)}>New purchase invoice</button>}
            {printing.buttons}
          </>
        }
      />
      <ErrorNote error={error} />
      {printing.panel}
      <div className={selected ? "side-layout" : "full-list"}>
        <div className="side-main">
          <div className="row filters no-print">
            <span className="po-view">
              <Combobox value={view} onChange={setView} ariaLabel="Show" options={VIEWS} />
            </span>
            {view !== "unbilled" && Object.values(search).some(Boolean) && (
              <button type="button" className="link" onClick={() => setSearch({})}>
                Clear searches
              </button>
            )}
          </div>
          {view === "unbilled" ? (
            <table className="pick po-list">
              <thead>
                <tr>
                  <th>GRN No</th>
                  <th>Date</th>
                  <th>Supplier</th>
                  <th>Warehouse</th>
                  <th>Purchase Orders</th>
                  <th className="num">Lines</th>
                  <th className="num">Value to Bill ₹</th>
                  <th className="no-print" />
                </tr>
              </thead>
              <tbody>
                {unbilled.length === 0 && (
                  <tr>
                    <td colSpan={8} className="small">
                      Every goods receipt has been billed.
                    </td>
                  </tr>
                )}
                {unbilled.map((u) => (
                  <tr key={u.receipt}>
                    <td>
                      <b>{u.receipt_number}</b>
                    </td>
                    <td className="nowrap">{shortDate(u.receipt_date)}</td>
                    <td>{u.supplier_name}</td>
                    <td>{u.branch_name}</td>
                    <td>{u.orders}</td>
                    <td className="num">{u.lines}</td>
                    <td className="num">{money(u.value)}</td>
                    <td className="num no-print">
                      {canCreate && (
                        <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?form=new&receipt=${u.receipt}`)}>
                          Make Invoice
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="pick po-list">
              <thead>
                <tr>
                  {COLUMNS.map(([key, label, , isNum]) => (
                    <th key={key} className={isNum ? "num" : undefined}>
                      {label}
                    </th>
                  ))}
                </tr>
                <tr className="col-search no-print">
                  {COLUMNS.map(([key, label]) => (
                    <th key={key}>
                      <input
                        type="search"
                        aria-label={`Search ${label}`}
                        placeholder="Search"
                        value={search[key] ?? ""}
                        onChange={(e) => setSearch({ ...search, [key]: e.target.value })}
                      />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.length === 0 && (
                  <tr>
                    <td colSpan={COLUMNS.length} className="small">
                      No purchase invoices match.
                    </td>
                  </tr>
                )}
                {shown.map((r) => {
                  const overdue = r.status === "submitted" && r.first_due && r.first_due < today();
                  return (
                    <tr
                      key={r.id}
                      tabIndex={0}
                      className={selected?.id === r.id ? "selected" : ""}
                      onClick={() => setSelectedId(selected?.id === r.id ? null : r.id)}
                      onDoubleClick={() => openTab(`${base(companyId)}?view=${r.id}`)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") openTab(`${base(companyId)}?view=${r.id}`);
                      }}
                    >
                      <td>{r.number ? <b>{r.number}</b> : <span className="small">Draft</span>}</td>
                      <td className="nowrap">{shortDate(r.posting_date)}</td>
                      <td>{r.supplier_name}</td>
                      <td>{r.bill_no}</td>
                      <td className="nowrap">{shortDate(r.bill_date)}</td>
                      <td>
                        {r.kind === "supplementary" ? (
                          <>
                            <span className="tag">Supplementary</span> <span className="small">against {r.original_number}</span>
                          </>
                        ) : r.kind === "direct" ? (
                          <span className="tag">No GRN</span>
                        ) : (
                          r.receipts.map((x) => x.number).join(", ")
                        )}
                      </td>
                      <td className="num">{money(r.total)}</td>
                      <td className="nowrap">{overdue ? <span className="pill bad">{shortDate(r.first_due)}</span> : shortDate(r.first_due)}</td>
                      <td>
                        <span className={pillClass(r.status)}>{r.status_label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              {shown.length > 1 && (
                <tfoot>
                  <tr>
                    <td colSpan={6}>Total</td>
                    <td className="num">{money(total)}</td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              )}
            </table>
          )}
          {view !== "unbilled" && shown.length > 0 && (
            <p className="small no-print">Click an invoice to see it at the right (click it again to close the panel); double-click or press Enter to open it in a new tab.</p>
          )}
        </div>
        {selected && (
          <div className="side-col" aria-label="Invoice details">
            <SidePanel title={selected.number || "Draft invoice"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Supplier", selected.supplier_name],
                  ["Supplier Invoice No", selected.bill_no],
                  ["Bill Date", showDate(selected.bill_date)],
                  ["Posting Date", showDate(selected.posting_date)],
                  ["Goods Receipts", selected.receipts.map((x) => x.number).join(", ")],
                  ["Total", `₹${money(selected.total)}`],
                  ["First Due", showDate(selected.first_due)],
                  ["Made By", selected.created_by_name],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => openTab(`${base(companyId)}?view=${selected.id}`)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?view=${selected.id}`)}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="purchase_invoice" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// The form ------------------------------------------------------------------------

function InvoiceFormTab({ companyId, form, canSubmit }: { companyId: number; form: string; canSubmit: boolean }) {
  const [inv, setInv] = useState<Invoice | null>(null);
  const [from, setFrom] = useState<DraftFrom | null>(null);
  const [error, setError] = useState<unknown>("");
  const receipt = hashParam("receipt");
  const order = hashParam("order");
  const original = Number(hashParam("supplementary"));
  const direct = hashParam("type") === "direct";
  useEffect(() => {
    if (form === "new" && (original || direct)) return;
    if (form !== "new") {
      api<Invoice>(`v1/purchase-invoices/${Number(form)}/`).then(setInv, setError);
      return;
    }
    const q = receipt ? `receipt=${receipt}` : order ? `order=${order}` : "";
    if (q) api<DraftFrom>(`v1/companies/${companyId}/purchase-invoices/draft-from/?${q}`).then(setFrom, setError);
  }, [companyId, form, receipt, order, original, direct]);
  if (form === "new" && original) return <SupplementaryFormTab companyId={companyId} original={original} canSubmit={canSubmit} />;
  if (form === "new" && direct) return <DirectFormTab key="new-direct" companyId={companyId} canSubmit={canSubmit} />;
  const title = form === "new" ? "New Purchase Invoice" : "Edit Purchase Invoice";
  const shell = (note?: unknown) => (
    <section className="page">
      <PageHeader title={title} crumbs={[{ label: "Entry › Purchase › Purchase Invoice", href: base(companyId) }]} />
      <ErrorNote error={note} />
    </section>
  );
  if (error) return shell(error);
  if (form !== "new" && !inv) return shell();
  if ((receipt || order) && !from) return shell();
  if (inv && inv.status !== "draft") return shell("A submitted invoice cannot be changed. Cancel it and make a new one.");
  if (inv?.kind === "direct") return <DirectFormTab companyId={companyId} bill={inv as unknown as DirectBill} canSubmit={canSubmit} />;
  if (inv?.kind === "supplementary") return <SupplementaryFormTab companyId={companyId} bill={inv as unknown as SupplementaryBill} canSubmit={canSubmit} />;
  return <InvoiceForm companyId={companyId} title={title} invoice={inv} from={from} canSubmit={canSubmit} />;
}

type ChargeDraft = { key: number; item: string; amount: string; gst_rate: string; in_stock_cost: boolean };
let nextKey = 1;

function InvoiceForm(props: { companyId: number; title: string; invoice: Invoice | null; from: DraftFrom | null; canSubmit: boolean }) {
  const { companyId, invoice: inv, from } = props;
  const { setup, terms } = useSetup(companyId);
  const [supplier, setSupplier] = useState(String(inv?.supplier ?? from?.supplier ?? ""));
  const [branch, setBranch] = useState(String(inv?.branch ?? from?.branch ?? ""));
  const [billNo, setBillNo] = useState(inv?.bill_no ?? "");
  const [billDate, setBillDate] = useState(inv?.bill_date ?? "");
  const [postingDate, setPostingDate] = useState(inv?.posting_date ?? "");
  const [term, setTerm] = useState(String(inv?.credit_term ?? from?.credit_term ?? ""));
  const [billTotal, setBillTotal] = useState(inv?.bill_total ?? "");
  const [notes, setNotes] = useState(inv?.notes ?? "");
  const [interstate, setInterstate] = useState(inv?.interstate ?? from?.interstate ?? false);
  const [lines, setLines] = useState<Line[]>(inv?.lines ?? from?.lines ?? []);
  const [charges, setCharges] = useState<ChargeDraft[]>(() =>
    (inv?.charges ?? from?.charges ?? []).map((c) => ({ key: nextKey++, item: String(c.item), amount: c.amount, gst_rate: c.gst_rate, in_stock_cost: c.in_stock_cost })),
  );
  const [saved, setSaved] = useState<Invoice | null>(inv);
  const [draftId, setDraftId] = useState<number | null>(inv?.id ?? null);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState("");

  // Posting Date follows the bill date until it is changed (Sidharth, 2026-11-15).
  const [postingTouched, setPostingTouched] = useState(!!inv?.posting_date && inv.posting_date !== inv.bill_date);
  const changeBillDate = (v: string) => {
    setBillDate(v);
    if (!postingTouched) setPostingDate(v);
  };
  const getItems = async () => {
    setError("");
    try {
      const got = await api<DraftFrom>(`v1/companies/${companyId}/purchase-invoices/draft-from/?supplier=${supplier}${branch ? `&branch=${branch}` : ""}`);
      const have = new Set(lines.map((l) => l.receipt_line));
      setLines([...lines, ...got.lines.filter((l) => !have.has(l.receipt_line))]);
      if (!branch) setBranch(String(got.branch));
      if (!term && got.credit_term) setTerm(String(got.credit_term));
      setInterstate(got.interstate);
      if (!charges.length) setCharges(got.charges.map((c) => ({ key: nextKey++, item: String(c.item), amount: c.amount, gst_rate: c.gst_rate, in_stock_cost: c.in_stock_cost })));
    } catch (err) {
      setError(err);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };
  const pickSupplier = (v: string) => {
    setSupplier(v);
    setLines([]);
    setCharges([]);
    const s = setup?.suppliers.find((x) => String(x.id) === v);
    if (s?.credit_term) setTerm(String(s.credit_term));
  };
  const changeLine = (i: number, patch: Partial<Line>) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, ...patch } : l)));
  const changeCharge = (key: number, patch: Partial<ChargeDraft>) => setCharges((cs) => cs.map((c) => (c.key === key ? { ...c, ...patch } : c)));

  // Totals as the server works them out: GST per line, the total to the rupee.
  const tax = (taxable: number, rate: number) => {
    const t = r2((taxable * rate) / 100);
    return interstate ? { c: 0, s: 0, i: t } : { c: r2(t / 2), s: r2(t - r2(t / 2)), i: 0 };
  };
  const calc = lines.map((l) => {
    const taxable = r2(num(l.qty) * num(l.rate));
    const t = tax(taxable, num(l.gst_rate));
    return { taxable, ...t, amount: r2(taxable + t.c + t.s + t.i) };
  });
  const ccalc = charges.map((c) => {
    const t = tax(num(c.amount), num(c.gst_rate));
    return { taxable: num(c.amount), ...t };
  });
  const all = [...calc, ...ccalc];
  const taxable = r2(all.reduce((s, x) => s + x.taxable, 0));
  const cgst = r2(all.reduce((s, x) => s + x.c, 0));
  const sgst = r2(all.reduce((s, x) => s + x.s, 0));
  const igst = r2(all.reduce((s, x) => s + x.i, 0));
  const exact = r2(taxable + cgst + sgst + igst);
  const ours = billTotal && Math.abs(num(billTotal) - exact) < 1 ? num(billTotal) : Math.round(exact);
  const matches = billTotal !== "" && Math.abs(num(billTotal) - ours) < 0.005;

  const sup = setup?.suppliers.find((s) => String(s.id) === supplier);
  const chargeItems = setup?.charge_items ?? [];
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      supplier: Number(supplier) || 0,
      branch: Number(branch) || 0,
      bill_no: billNo,
      bill_date: billDate || null,
      posting_date: postingDate || billDate || null,
      credit_term: term ? Number(term) : null,
      bill_total: billTotal === "" ? null : billTotal,
      notes,
      lines: lines.map((l) => ({ receipt_line: l.receipt_line, qty: l.qty || "0", rate: l.rate || "0", gst_rate: l.gst_rate || "0" })),
      charges: charges.filter((c) => c.item).map((c) => ({ item: Number(c.item), amount: c.amount || "0", gst_rate: c.gst_rate || "0", in_stock_cost: c.in_stock_cost })),
      submit,
    };
    try {
      const done = draftId
        ? await api<Invoice>(`v1/purchase-invoices/${draftId}/`, body, "PATCH")
        : await api<Invoice>(`v1/companies/${companyId}/purchase-invoices/`, body);
      announceSaved("purchase_invoice_saved", { id: done.id, name: done.number || "Draft" });
      if (submit) {
        window.location.hash = `${base(companyId)}?view=${done.id}`;
        return;
      }
      if (!draftId) {
        setDraftId(done.id);
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${done.id}`);
      }
      setSaved(done);
      setSavedAt(new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }));
    } catch (err) {
      const kept = keptDraft(err);
      if (kept && !draftId) {
        setDraftId(kept);
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${kept}`);
      }
      setError(err);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    setBusy(false);
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    save(false);
  };

  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId && !inv ? "Edit Purchase Invoice" : props.title}
        sub={savedAt ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.` : undefined}
        crumbs={[{ label: "Entry › Purchase › Purchase Invoice", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <button type="button" className="link" disabled title="Comes in a later piece of work">
              Scan e-invoice QR
            </button>
            <ActionsMenu label="Print" items={printItems} />
            <button type="submit" form="pinv-form" className={props.canSubmit ? "secondary" : undefined} disabled={busy}>
              Save
            </button>
            {props.canSubmit && (
              <button type="button" disabled={busy} onClick={() => save(true)}>
                Submit
              </button>
            )}
          </>
        }
      />
      <form id="pinv-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{sup?.name ?? from?.supplier_name ?? inv?.supplier_name ?? "Pick a supplier"}</p>
            <p className="item-sub">
              <b>{inv?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              {[...new Set(lines.map((l) => l.receipt_number))].map((n) => (
                <span key={n} className="tag">
                  {n}
                </span>
              ))}
            </p>
          </div>
          <ErrorNote error={error} />
          <Fold title="Supplier's Bill" open>
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <BillTypePicker companyId={companyId} direct={false} locked={!!draftId || !!from} />
              <label>
                <span className="req">Supplier</span>
                <Combobox
                  required
                  value={supplier}
                  onChange={pickSupplier}
                  options={[...(setup?.suppliers ?? []), ...(inv && !setup?.suppliers.some((s) => s.id === inv.supplier) ? [{ id: inv.supplier, name: inv.supplier_name }] : [])].map((s) => ({
                    value: String(s.id),
                    label: s.name,
                  }))}
                />
              </label>
              <label>
                <span className="req">Supplier Invoice No</span>
                <input value={billNo} maxLength={40} onChange={(e) => setBillNo(e.target.value)} />
              </label>
              <label>
                <span className="req">Supplier Invoice Date</span>
                <input type="date" value={billDate} onChange={(e) => changeBillDate(e.target.value)} />
              </label>
              <label>
                <span className="req">Posting Date</span>
                <input
                  type="date"
                  value={postingDate}
                  onChange={(e) => {
                    setPostingDate(e.target.value);
                    setPostingTouched(true);
                  }}
                />
                <span className="small">The month the entries and GST credit go into; starts as the bill date</span>
              </label>
              <label>
                <span className="req">Branch</span>
                <Combobox required value={branch} onChange={setBranch} options={(setup?.branches ?? []).map((b) => ({ value: String(b.id), label: b.name }))} />
              </label>
              <label>
                Credit Term
                <Combobox value={term} onChange={setTerm} empty="Due on the bill date" options={terms.map((t) => ({ value: String(t.id), label: t.name }))} />
                <span className="small">Due dates count from the supplier's invoice date</span>
              </label>
              <label>
                <span className="req">Supplier's Bill Total ₹</span>
                <input inputMode="decimal" value={billTotal} onChange={(e) => setBillTotal(e.target.value)} placeholder="The grand total printed on the bill" />
                {billTotal !== "" && (
                  <span className={matches ? "small ok-note" : "small bad-note"}>
                    {matches ? "✓ Matches our total" : `Our total is ₹${money(String(ours))}; difference ₹${money(String(r2(num(billTotal) - ours)))}`}
                  </span>
                )}
              </label>
            </div>
            {supplier && (
              <p>
                <button type="button" className="secondary" onClick={getItems}>
                  Get items
                </button>{" "}
                <span className="small">Brings what this supplier's goods receipts still have to be billed.</span>
              </p>
            )}
          </Fold>
          <Fold title="Items" open summary={lines.length ? `${lines.length} ${lines.length === 1 ? "line" : "lines"}` : ""}>
            {lines.length === 0 ? (
              <p className="small">Pick the supplier and click "Get items", or open this from a Goods Receipt's "Create ▾".</p>
            ) : (
              <div className="table-scroll">
                <table className="grid po-lines">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item</th>
                      <th>Receipt</th>
                      <th className="num">To Bill</th>
                      <th className="num">Bill Qty</th>
                      <th>Unit</th>
                      <th className="num">Receipt Rate</th>
                      <th className="num">Bill Rate</th>
                      <th className="num">Taxable ₹</th>
                      <th className="num">GST %</th>
                      <th className="num">GST ₹</th>
                      <th className="num">Amount ₹</th>
                      <th className="no-print" />
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((l, i) => {
                      const differs = num(l.rate) !== num(l.receipt_rate);
                      return (
                        <tr key={l.receipt_line} className={differs ? "differs" : undefined}>
                          <td>{i + 1}</td>
                          <td className="po-item">
                            <b>{l.item_name}</b>
                            <span className="small">
                              HSN {l.hsn}
                              {differs && ` · bill rate differs by ₹${money(String(r2(num(l.rate) - num(l.receipt_rate))))} per ${l.unit_name}`}
                            </span>
                          </td>
                          <td className="nowrap">{l.receipt_number}</td>
                          <td className="num">{Number(l.unbilled_qty)}</td>
                          <td className="num">
                            <input className="num-in" inputMode="decimal" value={l.qty} onChange={(e) => changeLine(i, { qty: e.target.value })} aria-label="Bill quantity" />
                          </td>
                          <td>{l.unit_name}</td>
                          <td className="num">{money(l.receipt_rate)}</td>
                          <td className="num">
                            <input className="num-in" inputMode="decimal" value={l.rate} onChange={(e) => changeLine(i, { rate: e.target.value })} aria-label="Bill rate" />
                          </td>
                          <td className="num">{money(String(calc[i].taxable))}</td>
                          <td className="num">
                            <input className="num-in small-in" inputMode="decimal" value={l.gst_rate} onChange={(e) => changeLine(i, { gst_rate: e.target.value })} aria-label="GST %" />
                          </td>
                          <td className="num">{money(String(r2(calc[i].c + calc[i].s + calc[i].i)))}</td>
                          <td className="num">{money(String(calc[i].amount))}</td>
                          <td className="no-print">
                            <button type="button" className="link danger" onClick={() => setLines(lines.filter((_, n) => n !== i))}>
                              Remove
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Fold>
          <Fold title="Charges on the Bill" open summary={charges.length ? `${charges.length}` : "None"}>
            {charges.length > 0 && (
              <table className="grid">
                <thead>
                  <tr>
                    <th>Charge</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th>Already in Stock Cost</th>
                    <th className="no-print" />
                  </tr>
                </thead>
                <tbody>
                  {charges.map((c) => (
                    <tr key={c.key}>
                      <td>
                        <Combobox
                          value={c.item}
                          onChange={(v) => {
                            const it = chargeItems.find((x) => String(x.id) === v);
                            changeCharge(c.key, { item: v, gst_rate: it?.gst_rate ?? c.gst_rate, in_stock_cost: it ? it.add_to_stock !== "no" : c.in_stock_cost });
                          }}
                          options={chargeItems.map((x) => ({ value: String(x.id), label: x.name }))}
                          ariaLabel="Charge"
                        />
                      </td>
                      <td className="num">
                        <input className="num-in" inputMode="decimal" value={c.amount} onChange={(e) => changeCharge(c.key, { amount: e.target.value })} aria-label="Charge amount" />
                      </td>
                      <td className="num">
                        <input className="num-in small-in" inputMode="decimal" value={c.gst_rate} onChange={(e) => changeCharge(c.key, { gst_rate: e.target.value })} aria-label="Charge GST %" />
                      </td>
                      <td>
                        <label className="tick">
                          <input type="checkbox" checked={c.in_stock_cost} onChange={(e) => changeCharge(c.key, { in_stock_cost: e.target.checked })} />
                          <span className="small">{c.in_stock_cost ? "Added to the goods by the receipt" : "Booked to the charge's expense"}</span>
                        </label>
                      </td>
                      <td className="no-print">
                        <button type="button" className="link danger" onClick={() => setCharges(charges.filter((x) => x.key !== c.key))}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button type="button" className="link" onClick={() => setCharges([...charges, { key: nextKey++, item: "", amount: "", gst_rate: "", in_stock_cost: false }])}>
              Add charge
            </button>
          </Fold>
          <Fold title="Totals" open summary={`₹${money(String(ours))}`}>
            <Totals taxable={taxable} cgst={cgst} sgst={sgst} igst={igst} roundOff={r2(ours - exact)} total={ours} />
          </Fold>
          {saved && <TdsBox<Invoice> billId={saved.id} tds={saved.tds} total={saved.total} draft onChanged={setSaved} />}
          {saved && <EntriesBox entries={saved.entries ?? []} dues={saved.dues ?? []} draft />}
          <Fold title="Notes" open={!!notes}>
            <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Notes" />
          </Fold>
          <Attachments type="purchase_invoice" id={draftId} />
        </div>
      </form>
    </section>
  );
}

export function Totals(t: { taxable: number | string; cgst: number | string; sgst: number | string; igst: number | string; roundOff: number | string; total: number | string }) {
  const rows: [string, number | string][] = [
    ["Taxable", t.taxable],
    ["CGST", t.cgst],
    ["SGST", t.sgst],
    ["IGST", t.igst],
    ["Round Off", t.roundOff],
  ];
  return (
    <table className="grid totals-box">
      <tbody>
        {rows
          .filter(([k, v]) => Number(v) || k === "Taxable")
          .map(([k, v]) => (
            <tr key={k}>
              <td>{k}</td>
              <td className="num">{money(String(v))}</td>
            </tr>
          ))}
        <tr>
          <td>
            <b>Total</b>
          </td>
          <td className="num">
            <b>{money(String(t.total))}</b>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

/** "Entries on Submit" and "Due Dates": what a draft would post (as last saved), or what was posted. */
export function EntriesBox({ entries, dues, draft, children }: { entries: Entry[]; dues: { due_date: string; amount: string }[]; draft?: boolean; children?: ReactNode }) {
  const dr = entries.reduce((s, e) => s + num(e.debit), 0);
  const cr = entries.reduce((s, e) => s + num(e.credit), 0);
  return (
    <>
      <Fold title={draft ? "Entries on Submit" : "Entries"} open>
        {draft && <p className="small">As last saved; click "Save" to see them again after a change.</p>}
        {entries.length === 0 ? (
          <p className="small">Nothing to post yet.</p>
        ) : entries.length === 1 && !entries[0].ledger ? (
          <p className="use-note">{entries[0].why}</p>
        ) : (
          <table className="grid">
            <thead>
              <tr>
                <th>Ledger</th>
                <th>Why</th>
                <th className="num">Debit ₹</th>
                <th className="num">Credit ₹</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i}>
                  <td>{e.ledger}</td>
                  <td className="small">{e.why}</td>
                  <td className="num">{num(e.debit) ? money(e.debit) : ""}</td>
                  <td className="num">{num(e.credit) ? money(e.credit) : ""}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={2}>Total</td>
                <td className="num">{money(String(r2(dr)))}</td>
                <td className="num">{money(String(r2(cr)))}</td>
              </tr>
            </tfoot>
          </table>
        )}
        {children}
      </Fold>
      {dues.length > 0 && (
        <Fold title="Due Dates" open>
          <table className="grid totals-box">
            <thead>
              <tr>
                <th>Due On</th>
                <th className="num">Amount ₹</th>
              </tr>
            </thead>
            <tbody>
              {dues.map((d) => (
                <tr key={d.due_date + d.amount}>
                  <td>{shortDate(d.due_date)}</td>
                  <td className="num">{money(d.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Fold>
      )}
    </>
  );
}

// The view ------------------------------------------------------------------------

function InvoiceView({ companyId, id, can }: { companyId: number; id: number; can: (p: string) => boolean }) {
  const [inv, setInv] = useState<Invoice | null>(null);
  const [error, setError] = useState<unknown>("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const reload = useCallback(() => {
    api<Invoice>(`v1/purchase-invoices/${id}/`).then(setInv, setError);
  }, [id]);
  useEffect(reload, [reload]);
  useCreated("purchase_invoice_saved", (c) => {
    if (c.id === id) reload();
  });
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const cancel = async () => {
    setError("");
    try {
      const done = await api<Invoice>(`v1/purchase-invoices/${id}/cancel/`, { reason });
      setInv(done);
      setCancelling(false);
      announceSaved("purchase_invoice_saved", { id, name: done.number || "Draft" });
    } catch (err) {
      setError(err);
    }
  };
  if (!inv)
    return (
      <section className="page">
        <PageHeader title="Purchase Invoice" crumbs={[{ label: "Entry › Purchase › Purchase Invoice", href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const draft = inv.status === "draft";
  const supp = inv.kind === "supplementary";
  const direct = inv.kind === "direct";
  const name = supp ? "Supplementary Bill" : "Purchase Invoice";
  return (
    <section className="page">
      <PageHeader
        title={inv.number ? `${name} ${inv.number}` : `${name} (draft)`}
        sub={
          inv.number && inv.submitted_at
            ? `Submitted as ${inv.number} on ${showDate(inv.submitted_at.slice(0, 10))} at ${new Date(inv.submitted_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`
            : undefined
        }
        crumbs={[{ label: "Entry › Purchase › Purchase Invoice", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {draft && can("create") && (
              <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?form=${inv.id}`)}>
                Edit
              </button>
            )}
            {can("cancel") && inv.status !== "cancelled" && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel invoice
              </button>
            )}
            <ActionsMenu label="Print" items={printItems} />
            {draft && can("create") && (
              <button type="button" onClick={() => openTab(`${base(companyId)}?form=${inv.id}`)}>
                Open to Submit
              </button>
            )}
            {inv.status === "submitted" && !supp && !direct && (
              <ActionsMenu
                label="Create"
                main
                items={[
                  {
                    label: "Debit Note (goods sent back)",
                    onClick: () => openTab(`#/companies/${companyId}/debit-notes?form=new&invoice=${inv.id}`),
                  },
                  {
                    label: "Debit Note (rate charged higher)",
                    onClick: () => openTab(`#/companies/${companyId}/debit-notes?form=new&invoice=${inv.id}&reason=rate`),
                  },
                  {
                    label: "Supplementary Bill (rate charged lower)",
                    onClick: () => openTab(`${base(companyId)}?form=new&supplementary=${inv.id}`),
                  },
                ]}
              />
            )}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{inv.supplier_name}</p>
            <p className="item-sub">
              <b>{inv.number || "Number given on Submit"}</b>
              <span className={pillClass(inv.status)}>{inv.status_label}</span>
              <span className="tag">Bill {inv.bill_no}</span>
              {supp && <span className="tag">Supplementary · against Bill {inv.original_bill_no}</span>}
              {direct && <span className="tag">Without goods receipt</span>}
              {inv.receipts.map((r) => (
                <span key={r.id} className="tag">
                  {r.number}
                </span>
              ))}
            </p>
          </div>
          {inv.status === "cancelled" && <p className="use-note">Cancelled: {inv.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this invoice cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Entered with the wrong rate" />
              </label>
              <p className="small">The entries are reversed and the receipts show the goods as not billed again.</p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep the invoice
                </button>
                <button type="button" className="link danger" onClick={cancel}>
                  Cancel invoice
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="Supplier's Bill" open>
            <dl className="kv">
              {(
                [
                  ["Supplier", inv.supplier_name + (inv.supplier_gstin ? ` · ${inv.supplier_gstin}` : "")],
                  ["Supplier Invoice No", inv.bill_no],
                  ["Supplier Invoice Date", showDate(inv.bill_date)],
                  ["Posting Date", showDate(inv.posting_date)],
                  ["Branch", inv.branch_name],
                  ["Credit Term", inv.credit_term_name ? `${inv.credit_term_name} (${inv.credit_term_summary})` : ""],
                  ["Against Invoice", supp ? `${inv.original_number} · Bill ${inv.original_bill_no}` : ""],
                  ["Purchase Orders", (inv.orders ?? []).join(", ")],
                  ["Later Changes", (inv.later ?? []).map((x) => `${x.kind === "debit_note" ? "Debit Note" : "Supplementary Bill"} ${x.number} (₹${money(x.total)})`).join(", ")],
                  ["Supplier's Bill Total", inv.bill_total ? `₹${money(inv.bill_total)}` : ""],
                ] as [string, string][]
              )
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
            </dl>
          </Fold>
          {supp ? (
            <Fold title="Items" open>
              <RateLinesTable lines={inv.rate_lines ?? []} way="up" interstate={inv.interstate} />
            </Fold>
          ) : direct ? (
            <Fold title="Items and Services" open>
              <div className="table-scroll">
                <table className="grid po-lines">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item or Ledger</th>
                      <th>Description</th>
                      <th>HSN / SAC</th>
                      <th className="num">Qty</th>
                      <th>Unit</th>
                      <th className="num">Rate</th>
                      <th className="num">Taxable ₹</th>
                      <th className="num">GST %</th>
                      <th className="num">GST ₹</th>
                      <th>Booked To</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(inv.expense_lines ?? []).map((l, i) => (
                      <tr key={l.id ?? i}>
                        <td>{i + 1}</td>
                        <td className="po-item">
                          <b>{l.name}</b>
                          <span className="small">{l.what}</span>
                        </td>
                        <td>{l.description}</td>
                        <td>{l.hsn}</td>
                        <td className="num">{Number(l.qty)}</td>
                        <td>{l.unit_name}</td>
                        <td className="num">{money(l.rate)}</td>
                        <td className="num">{money(l.taxable)}</td>
                        <td className="num">{Number(l.gst_rate)}</td>
                        <td className="num">{money(String(r2(num(l.cgst) + num(l.sgst) + num(l.igst))))}</td>
                        <td>{l.booked_to_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Fold>
          ) : (
            <Fold title="Items" open>
              <div className="table-scroll">
                <table className="grid po-lines">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item</th>
                      <th>Receipt</th>
                      <th className="num">Qty</th>
                      <th>Unit</th>
                      <th className="num">Receipt Rate</th>
                      <th className="num">Bill Rate</th>
                      <th className="num">Taxable ₹</th>
                      <th className="num">GST %</th>
                      <th className="num">GST ₹</th>
                      <th className="num">Amount ₹</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(inv.lines ?? []).map((l, i) => {
                      const differs = num(l.rate) !== num(l.receipt_rate);
                      return (
                        <tr key={l.receipt_line} className={differs ? "differs" : undefined}>
                          <td>{i + 1}</td>
                          <td className="po-item">
                            <b>{l.item_name}</b>
                            <span className="small">
                              HSN {l.hsn}
                              {inv.status === "submitted" && (num(l.stock_difference) || num(l.price_difference))
                                ? ` · rate difference: ${[
                                    num(l.stock_difference) ? `₹${money(l.stock_difference ?? "0")} to stock on hand` : "",
                                    num(l.price_difference) ? `₹${money(l.price_difference ?? "0")} to Purchase Price Difference` : "",
                                  ]
                                    .filter(Boolean)
                                    .join(", ")}`
                                : ""}
                            </span>
                          </td>
                          <td className="nowrap">{l.receipt_number}</td>
                          <td className="num">{Number(l.qty)}</td>
                          <td>{l.unit_name}</td>
                          <td className="num">{money(l.receipt_rate)}</td>
                          <td className="num">{money(l.rate)}</td>
                          <td className="num">{money(l.taxable ?? "0")}</td>
                          <td className="num">{Number(l.gst_rate)}</td>
                          <td className="num">{money(String(r2(num(l.cgst) + num(l.sgst) + num(l.igst))))}</td>
                          <td className="num">{money(l.amount ?? "0")}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Fold>
          )}
          {!!inv.charges?.length && (
            <Fold title="Charges on the Bill" open>
              <table className="grid">
                <thead>
                  <tr>
                    <th>Charge</th>
                    <th>SAC</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th className="num">GST ₹</th>
                    <th>Booked</th>
                  </tr>
                </thead>
                <tbody>
                  {inv.charges.map((c, i) => (
                    <tr key={i}>
                      <td>{c.item_name}</td>
                      <td>{c.sac}</td>
                      <td className="num">{money(c.amount)}</td>
                      <td className="num">{Number(c.gst_rate)}</td>
                      <td className="num">{money(String(r2(num(c.cgst) + num(c.sgst) + num(c.igst))))}</td>
                      <td className="small">{c.in_stock_cost ? "Already in stock cost by the receipt" : "To the charge's expense"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Fold>
          )}
          <Fold title="Totals" open summary={`₹${money(inv.total)}`}>
            <Totals taxable={inv.taxable_total} cgst={inv.cgst_total} sgst={inv.sgst_total} igst={inv.igst_total} roundOff={inv.round_off} total={inv.total} />
          </Fold>
          <TdsBox<Invoice> billId={inv.id} tds={inv.tds} total={inv.total} draft={draft && can("create")} onChanged={setInv} />
          <EntriesBox entries={inv.entries ?? []} dues={inv.dues ?? []} draft={draft} />
          {inv.notes && (
            <Fold title="Notes" open>
              <p className="pre">{inv.notes}</p>
            </Fold>
          )}
          <Attachments type="purchase_invoice" id={inv.id} onChange={() => setFiles((n) => n + 1)} />
        </div>
        <div className="doc-foot">
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="purchase_invoice" id={inv.id} stamp={JSON.stringify(inv) + files} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}
