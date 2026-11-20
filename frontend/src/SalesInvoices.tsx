import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { DocSide } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { money } from "./Companies";
import { announceSaved, closeThisTab, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { LedgerPosting, MissingLedgersPopup, missingLedgersOf, type MissingLedgers } from "./LedgerPosting";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { TotalsPanel } from "./PurchaseOrders";

/** Entry > Sales > Sales Invoice: the tax invoice for a submitted delivery note (Sidharth,
 * 2026-11-20, previews 14a/14b in mockups/sales). Quantities are what the note sent; rates start at
 * the order's and may change until Submit. Submit books the sale and moves the note's cost to Cost
 * of Goods Sold. The e-invoice and e-way bill numbers are typed in from the portal for now. */

type Line = {
  id: number;
  position: number;
  item: number;
  item_name: string;
  hsn: string;
  unit_name: string;
  qty: string;
  rate: string;
  order_rate: string;
  rate_source: string;
  taxable: string;
  gst_rate: string;
  amount: string;
  cost: string;
};
type Charge = {
  id: number;
  item: number;
  item_name: string;
  sac: string;
  basis: string;
  basis_label: string;
  rate: string;
  amount: string;
  gst_rate: string;
  cgst: string;
  sgst: string;
  igst: string;
};
type Place = { label?: string; address?: string; city?: string; pincode?: string; state?: string };
type Invoice = {
  id: number;
  company: number;
  number: string;
  status: string;
  status_label: string;
  customer_name: string;
  customer_gstin: string;
  delivery_note: number;
  delivery_note_number: string;
  order: number;
  order_number: string;
  customer_po_no: string;
  customer_po_date: string | null;
  salesman_name: string;
  invoice_date: string;
  bill_from_name: string;
  bill_from_gstin: string;
  bill_address: Place;
  ship_address: Place;
  place_of_supply_name: string;
  credit_term: number | null;
  credit_term_name: string;
  credit_term_summary: string;
  dues: { due_date: string; amount: string }[];
  first_due: string | null;
  transporter: number | null;
  transporter_name: string;
  mode: string;
  mode_label: string;
  vehicle_no: string;
  distance_km: number | null;
  lr_no: string;
  lr_date: string | null;
  packages: number | null;
  gross_weight: string;
  notes: string;
  interstate: boolean;
  taxable_total: string;
  cgst_total: string;
  sgst_total: string;
  igst_total: string;
  round_off: string;
  total: string;
  cost_total: string;
  irn: string;
  ack_no: string;
  ack_date: string | null;
  has_signed_qr: boolean;
  eway_bill_no: string;
  eway_bill_date: string | null;
  eway_valid_until: string | null;
  needs_einvoice: boolean;
  cancel_reason: string;
  created_at: string;
  created_by_name: string;
  submitted_at: string | null;
  submitted_by_name: string;
  lines?: Line[];
  charges?: Charge[];
};
type Setup = {
  credit_terms: { id: number; name: string; is_active: boolean }[];
  transporters: { id: number; name: string; is_active: boolean }[];
  charge_items: { id: number; name: string; sac: string; gst_rate: string | null }[];
  gst_rates: string[];
};

const VIEWS: [string, string][] = [
  ["all", "All"],
  ["draft", "Draft"],
  ["submitted", "Submitted"],
  ["cancelled", "Cancelled"],
];
const MODES: [string, string][] = [
  ["road", "Road"],
  ["rail", "Rail"],
  ["air", "Air"],
  ["ship", "Ship"],
];
const BASES: [string, string][] = [
  ["fixed", "Fixed"],
  ["percent", "% of items"],
  ["per_unit", "Per unit"],
];
export const invoiceBase = (companyId: number) => `#/companies/${companyId}/sales-invoices`;
const CRUMB = "Entry › Sales › Sales Invoice";
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const time = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
const at = (iso: string) => `${shortDate(iso)} at ${time(iso)}`;
const when = (iso: string | null) => (iso ? at(iso) : "");
const pillClass = (s: string) => (s === "submitted" ? "pill on" : s === "draft" ? "pill warn" : "pill");
const round2 = (n: number) => Math.round(n * 100) / 100;
const can = (session: SignedIn, action: string) => session.permissions.includes(`sales.${action}`);
const pdf = (id: number, layout: string, download = false) =>
  openTab(`/api/v1/sales-invoices/${id}/pdf/?layout=${layout}${download ? "&download=1" : ""}`);
const printItems = (id: number) => [
  { label: "Tax Invoice (Original for Recipient)", onClick: () => pdf(id, "invoice") },
  { label: "Tax Invoice (3 copies: Original, Duplicate, Triplicate)", onClick: () => pdf(id, "copies") },
  { label: "e-Way Bill", onClick: () => pdf(id, "eway") },
  { label: "Download PDF", onClick: () => pdf(id, "invoice", true) },
];
/** "Create ▾" on a submitted invoice: the documents that follow from it, built one by one. */
const NEXT = [
  { label: "Receipt (later)", disabled: true },
  { label: "Sales Return / Credit Note (next)", disabled: true },
];
const placeText = (p: Place | null | undefined) => [p?.label, p?.address?.split("\n")[0], p?.city, p?.pincode].filter(Boolean).join(", ");
/** "2026-11-20T21:12:00+05:30" -> "2026-11-20T21:12" for a datetime-local box. */
const localInput = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/** "Create ▾ › Sales Invoice" on a submitted delivery note: the note's draft invoice (made if new),
 * opened in a new tab. */
export async function makeSalesInvoice(companyId: number, noteId: number): Promise<void> {
  const inv = await api<Invoice>(`v1/delivery-notes/${noteId}/invoice/`, {});
  openTab(`${invoiceBase(companyId)}?view=${inv.id}`);
}

export function SalesInvoicesPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const view = Number(hashParam("view"));
  if (view > 0) return <InvoiceView companyId={companyId} id={view} session={session} />;
  return <InvoiceList companyId={companyId} />;
}

const COLUMNS: [key: string, label: string, text: (i: Invoice) => string, num?: boolean][] = [
  ["number", "Invoice No", (i) => i.number || "Draft"],
  ["date", "Date", (i) => shortDate(i.invoice_date)],
  ["customer", "Customer", (i) => i.customer_name],
  ["note", "Delivery Note", (i) => i.delivery_note_number],
  ["due", "Due", (i) => shortDate(i.first_due)],
  ["einvoice", "e-Invoice", (i) => (i.irn ? "Made" : i.status === "submitted" && i.needs_einvoice ? "Pending" : "")],
  ["total", "Total ₹", (i) => money(i.total), true],
  ["status", "Status", (i) => i.status_label],
];

function InvoiceList({ companyId }: { companyId: number }) {
  const [view, setView] = useState("all");
  const [rows, setRows] = useState<Invoice[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Invoice[]>(`v1/companies/${companyId}/sales-invoices/?view=${view}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("sales_invoice_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      rows.filter((i) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          return words.every((w) => text(i).toLowerCase().includes(w));
        }),
      ),
    [rows, search],
  );
  const selected = rows.find((i) => i.id === selectedId) ?? null;
  const printing = usePrintMenu({ title: `Sales invoices: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`, scope: "" });
  const open = (id: number) => openTab(`${invoiceBase(companyId)}?view=${id}`);
  return (
    <section className="page">
      <PageHeader
        title="Sales Invoice"
        crumbs={[{ label: "Entry › Sales", href: invoiceBase(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "invoice" : "invoices"} · made from a submitted delivery note ("Create ▾" on the note)`}
        actions={printing.buttons}
      />
      {error && <p className="error">{error}</p>}
      {printing.panel}
      <div className={selected ? "side-layout" : "full-list"}>
        <div className="side-main">
          <div className="row filters no-print">
            <span className="po-view">
              <Combobox value={view} onChange={setView} ariaLabel="Show" options={VIEWS.map(([value, label]) => ({ value, label }))} />
            </span>
            {Object.values(search).some(Boolean) && (
              <button type="button" className="link" onClick={() => setSearch({})}>
                Clear searches
              </button>
            )}
          </div>
          <table className="pick po-list">
            <thead>
              <tr>
                {COLUMNS.map(([key, label, , num]) => (
                  <th key={key} className={num ? "num" : undefined}>
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
                    No sales invoices match.
                  </td>
                </tr>
              )}
              {shown.map((i) => (
                <tr
                  key={i.id}
                  tabIndex={0}
                  className={selected?.id === i.id ? "selected" : ""}
                  onClick={() => setSelectedId(selected?.id === i.id ? null : i.id)}
                  onDoubleClick={() => open(i.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") open(i.id);
                  }}
                >
                  {COLUMNS.map(([key, , text, num]) =>
                    key === "number" ? (
                      <td key={key}>
                        <b>{text(i)}</b>
                      </td>
                    ) : key === "status" ? (
                      <td key={key}>
                        <span className={pillClass(i.status)}>{i.status_label}</span>
                      </td>
                    ) : (
                      <td key={key} className={num ? "num" : key === "date" || key === "due" ? "nowrap" : undefined}>
                        {text(i)}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small no-print">Click an invoice to see it at the right; double-click or press Enter to open it in a new tab.</p>}
        </div>
        {selected && (
          <div className="side-col" aria-label="Sales invoice details">
            <SidePanel title={selected.number || "Draft"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Customer", selected.customer_name],
                  ["Delivery Note", selected.delivery_note_number],
                  ["Due", shortDate(selected.first_due)],
                  ["IRN", selected.irn ? "Made" : ""],
                  ["e-Way Bill", selected.eway_bill_no],
                  ["Total", `₹${money(selected.total)}`],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => open(selected.id)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => pdf(selected.id, "invoice")}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="sales_invoice" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// One invoice ---------------------------------------------------------------------

type ChargeDraft = { key: number; item: string; basis: string; rate: string; gst: string };
type Transport = { transporter: string; mode: string; vehicle_no: string; distance_km: string; lr_no: string; lr_date: string };
type Portal = { irn: string; ack_no: string; ack_date: string; signed_qr: string; eway_bill_no: string; eway_bill_date: string; eway_valid_until: string };
let nextKey = 1;
const transportOf = (i: Invoice): Transport => ({
  transporter: i.transporter ? String(i.transporter) : "",
  mode: i.mode,
  vehicle_no: i.vehicle_no,
  distance_km: i.distance_km == null ? "" : String(i.distance_km),
  lr_no: i.lr_no,
  lr_date: i.lr_date ?? "",
});
const transportBody = (t: Transport) => ({
  ...t,
  transporter: t.transporter ? Number(t.transporter) : null,
  distance_km: t.distance_km ? Number(t.distance_km) : null,
  lr_date: t.lr_date || null,
});
const chargesOf = (i: Invoice): ChargeDraft[] =>
  (i.charges ?? []).map((c) => ({ key: nextKey++, item: String(c.item), basis: c.basis, rate: c.rate, gst: c.gst_rate }));

function InvoiceView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const [inv, setInv] = useState<Invoice | null>(null);
  const [error, setError] = useState<unknown>("");
  const [date, setDate] = useState("");
  const [term, setTerm] = useState("");
  const [notes, setNotes] = useState("");
  const [rates, setRates] = useState<Record<number, string>>({});
  const [charges, setCharges] = useState<ChargeDraft[]>([]);
  const [transport, setTransport] = useState<Transport | null>(null);
  const [editTransport, setEditTransport] = useState(false);
  const [portal, setPortal] = useState<Portal | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [noLedgers, setNoLedgers] = useState<MissingLedgers | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const [saved, setSaved] = useState(0);
  const [busy, setBusy] = useState(false);
  const take = useCallback((i: Invoice) => {
    setInv(i);
    setDate(i.invoice_date);
    setTerm(i.credit_term ? String(i.credit_term) : "");
    setNotes(i.notes);
    setRates(Object.fromEntries((i.lines ?? []).map((l) => [l.id, l.rate])));
    setCharges(chargesOf(i));
    setTransport(transportOf(i));
    setEditTransport(false);
    setPortal(null);
  }, []);
  useEffect(() => {
    api<Invoice>(`v1/sales-invoices/${id}/`).then(take, (err) => setError(err));
  }, [id, take]);
  const draft = inv?.status === "draft";
  const submitted = inv?.status === "submitted";
  const mayEdit = draft && can(session, "create");
  useEffect(() => {
    if (!inv || !can(session, "create") || inv.status === "cancelled") return;
    api<Setup>(`v1/companies/${companyId}/sales-orders/setup/`).then(setSetup, () => undefined);
    // Once per invoice: the lists do not change while the page is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inv?.id]);
  const close = () =>
    closeThisTab(() => {
      window.location.hash = invoiceBase(companyId);
    });
  const done = (i: Invoice) => {
    take(i);
    setCancelling(false);
    setSaved((k) => k + 1);
    announceSaved("sales_invoice_saved", { id: i.id, name: i.number || "Draft" });
  };
  const refusal = (err: unknown) => {
    const missing = missingLedgersOf(err);
    if (missing) return setNoLedgers(missing);
    setError(err);
  };
  const save = async (submit: boolean) => {
    if (!inv || !transport) return;
    setError("");
    setBusy(true);
    try {
      const body = {
        invoice_date: date,
        credit_term: term ? Number(term) : null,
        notes,
        ...transportBody(transport),
        rates: Object.entries(rates).map(([line, rate]) => ({ line: Number(line), rate: rate || "0" })),
        charges: charges.filter((c) => c.item).map((c) => ({ item: Number(c.item), basis: c.basis, rate: c.rate || "0", ...(c.gst !== "" ? { gst_rate: c.gst } : {}) })),
        submit,
      };
      done(await api<Invoice>(`v1/sales-invoices/${id}/`, body, "PATCH"));
    } catch (err) {
      // A refused Submit still saved the draft: read it again.
      if (submit) api<Invoice>(`v1/sales-invoices/${id}/`).then(take, () => undefined);
      refusal(err);
    }
    setBusy(false);
  };
  const act = async (path: string, body: object = {}) => {
    setError("");
    setBusy(true);
    try {
      done(await api<Invoice>(`v1/sales-invoices/${id}/${path}/`, body));
    } catch (err) {
      refusal(err);
    }
    setBusy(false);
  };
  if (!inv || !transport)
    return (
      <section className="page">
        <PageHeader title="Sales Invoice" crumbs={[{ label: CRUMB, href: invoiceBase(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const lines = inv.lines ?? [];
  // Worked out here as the person types; the server works it out again on Save.
  const rateOf = (l: Line) => (draft ? Number(rates[l.id] ?? l.rate) || 0 : Number(l.rate));
  const taxableOf = (l: Line) => (draft ? round2(Number(l.qty) * rateOf(l)) : Number(l.taxable));
  const lineTax = (l: Line) => round2((taxableOf(l) * Number(l.gst_rate)) / 100);
  const itemsValue = lines.reduce((s, l) => s + taxableOf(l), 0);
  const qtyTotal = lines.reduce((s, l) => s + Number(l.qty), 0);
  const chargeItem = (c: ChargeDraft) => setup?.charge_items.find((x) => String(x.id) === c.item);
  const chargeRows = draft
    ? charges
        .filter((c) => c.item)
        .map((c) => {
          const rate = Number(c.rate) || 0;
          const amount = round2(c.basis === "fixed" ? rate : c.basis === "percent" ? (itemsValue * rate) / 100 : qtyTotal * rate);
          const gst = Number(c.gst || chargeItem(c)?.gst_rate || 0);
          return { c, amount, tax: round2((amount * gst) / 100) };
        })
    : (inv.charges ?? []).map((x) => ({
        c: { key: x.id, item: String(x.item), basis: x.basis, rate: x.rate, gst: x.gst_rate },
        amount: Number(x.amount),
        tax: Number(x.cgst) + Number(x.sgst) + Number(x.igst),
      }));
  const chargesValue = chargeRows.reduce((s, r) => s + r.amount, 0);
  const taxable = itemsValue + chargesValue;
  const tax = lines.reduce((s, l) => s + lineTax(l), 0) + chargeRows.reduce((s, r) => s + r.tax, 0);
  const half = lines.reduce((s, l) => s + round2(lineTax(l) / 2), 0) + chargeRows.reduce((s, r) => s + round2(r.tax / 2), 0);
  const exact = round2(taxable + tax);
  const rounded = Math.round(exact);
  const totals = draft
    ? { cgst: inv.interstate ? 0 : half, sgst: inv.interstate ? 0 : round2(tax - half), igst: inv.interstate ? tax : 0, roundOff: round2(rounded - exact), total: rounded }
    : { cgst: Number(inv.cgst_total), sgst: Number(inv.sgst_total), igst: Number(inv.igst_total), roundOff: Number(inv.round_off), total: Number(inv.total) };
  const setT = (patch: Partial<Transport>) => setTransport({ ...transport, ...patch });
  const transportEditable = mayEdit || (submitted && editTransport);
  const shipText = placeText(inv.ship_address);
  return (
    <section className="page">
      <PageHeader
        title={inv.number ? `Sales Invoice ${inv.number}` : "New Sales Invoice"}
        sub={
          inv.submitted_at
            ? `Submitted as ${inv.number} on ${at(inv.submitted_at)}`
            : draft
              ? `Draft made from Delivery Note ${inv.delivery_note_number} on ${at(inv.created_at)} · nothing posted yet`
              : undefined
        }
        crumbs={[{ label: CRUMB, href: invoiceBase(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {inv.status !== "cancelled" && can(session, "cancel") && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel Invoice
              </button>
            )}
            <ActionsMenu label="Print" items={printItems(inv.id)} />
            {mayEdit && (
              <button type="button" className="link" disabled={busy} onClick={() => save(false)}>
                Save
              </button>
            )}
            {mayEdit && can(session, "submit") && (
              <button type="button" disabled={busy} onClick={() => save(true)}>
                Submit
              </button>
            )}
            {submitted && <ActionsMenu label="Create" main items={NEXT} />}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{inv.customer_name}</p>
            <p className="item-sub">
              {inv.number && <b>{inv.number}</b>}
              <span className={pillClass(inv.status)}>{inv.status_label}</span>
              {submitted && inv.needs_einvoice && <span className="tag">{inv.irn ? "e-Invoice made" : "e-Invoice pending"}</span>}
              {submitted && inv.eway_bill_no && <span className="tag">e-Way Bill made</span>}
              {submitted && inv.first_due && <span className="tag">Due {shortDate(inv.first_due)}</span>}
              <span className="tag">
                From{" "}
                <a href={`#/companies/${companyId}/delivery-notes?view=${inv.delivery_note}`} target="_blank" rel="noreferrer">
                  {inv.delivery_note_number}
                </a>
              </span>
              <span className="tag">
                Against{" "}
                <a href={`#/companies/${companyId}/sales-orders?view=${inv.order}`} target="_blank" rel="noreferrer">
                  {inv.order_number}
                </a>
              </span>
              <span className="tag">{inv.interstate ? "Interstate · IGST" : "Same state · CGST + SGST"}</span>
            </p>
          </div>
          {draft && <p className="ok-note">Filled from the delivery note: the quantities it sent, at the order's rates, with the order's charges. Change a rate or a charge if needed, then Submit.</p>}
          {inv.status === "cancelled" && <p className="use-note">Cancelled: {inv.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this invoice cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Wrong rate" />
              </label>
              <p className="small">
                {submitted
                  ? `The entries are reversed and Delivery Note ${inv.delivery_note_number} can be billed again.${inv.irn ? " Cancel the e-invoice on the portal too (allowed within 24 hours)." : ""}`
                  : "The draft is set aside; the delivery note stays unbilled."}
              </p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep it
                </button>
                <button type="button" className="link danger" onClick={() => act("cancel", { reason })}>
                  Cancel Invoice
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          {submitted && (
            <Fold title="e-Invoice and e-Way Bill" open summary={[inv.irn ? "e-Invoice made" : inv.needs_einvoice ? "e-Invoice pending" : "", inv.eway_bill_no ? `e-Way Bill ${inv.eway_bill_no}` : ""].filter(Boolean).join(" · ") || "Not made yet"}>
              {portal ? (
                <>
                  <div className="item-fields">
                    <label className="wide">
                      IRN
                      <input value={portal.irn} maxLength={64} placeholder="64 letters and digits, from the portal" onChange={(e) => setPortal({ ...portal, irn: e.target.value.trim() })} />
                    </label>
                    <label>
                      Ack No
                      <input value={portal.ack_no} maxLength={20} inputMode="numeric" onChange={(e) => setPortal({ ...portal, ack_no: e.target.value.trim() })} />
                    </label>
                    <label>
                      Ack Date
                      <input type="datetime-local" value={portal.ack_date} onChange={(e) => setPortal({ ...portal, ack_date: e.target.value })} />
                    </label>
                    <label className="wide">
                      Signed QR Code
                      <textarea rows={2} value={portal.signed_qr} placeholder="Paste the signed QR text from the portal; it prints on the invoice" onChange={(e) => setPortal({ ...portal, signed_qr: e.target.value })} />
                    </label>
                    <label>
                      e-Way Bill No
                      <input value={portal.eway_bill_no} maxLength={14} inputMode="numeric" placeholder="12 digits" onChange={(e) => setPortal({ ...portal, eway_bill_no: e.target.value })} />
                    </label>
                    <label>
                      e-Way Bill Date
                      <input type="datetime-local" value={portal.eway_bill_date} onChange={(e) => setPortal({ ...portal, eway_bill_date: e.target.value })} />
                    </label>
                    <label>
                      Valid Until
                      <input type="datetime-local" value={portal.eway_valid_until} onChange={(e) => setPortal({ ...portal, eway_valid_until: e.target.value })} />
                    </label>
                  </div>
                  <div className="buttons">
                    <button type="button" className="link" onClick={() => setPortal(null)}>
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        act("e-invoice", {
                          ...portal,
                          ack_date: portal.ack_date || null,
                          eway_bill_date: portal.eway_bill_date || null,
                          eway_valid_until: portal.eway_valid_until || null,
                        })
                      }
                    >
                      Save
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <Facts
                    rows={[
                      ["IRN", inv.irn],
                      ["Ack No", inv.ack_no],
                      ["Ack Date", when(inv.ack_date)],
                      ["Signed QR", inv.has_signed_qr ? "Given · prints on the invoice" : ""],
                      ["e-Way Bill No", inv.eway_bill_no],
                      ["e-Way Bill Date", when(inv.eway_bill_date)],
                      ["Valid Until", when(inv.eway_valid_until)],
                    ]}
                  />
                  {!inv.irn && !inv.eway_bill_no && <p className="small">Not made yet.</p>}
                  <div className="buttons">
                    {inv.needs_einvoice && (
                      <button type="button" className="link" onClick={() => openTab(`/api/v1/sales-invoices/${inv.id}/json/`)}>
                        Download e-Invoice JSON
                      </button>
                    )}
                    {can(session, "submit") && (
                      <button
                        type="button"
                        className="link"
                        onClick={() =>
                          setPortal({
                            irn: inv.irn,
                            ack_no: inv.ack_no,
                            ack_date: localInput(inv.ack_date),
                            signed_qr: "",
                            eway_bill_no: inv.eway_bill_no,
                            eway_bill_date: localInput(inv.eway_bill_date),
                            eway_valid_until: localInput(inv.eway_valid_until),
                          })
                        }
                      >
                        Enter Portal Numbers
                      </button>
                    )}
                    {can(session, "create") && !editTransport && (
                      <button type="button" className="link" onClick={() => setEditTransport(true)}>
                        Update Transport
                      </button>
                    )}
                  </div>
                  <p className="small">
                    {inv.needs_einvoice
                      ? 'Upload the JSON on the e-invoice portal: it makes the e-invoice and, with the transport details, the e-way bill. Then type the numbers it gives here with "Enter Portal Numbers". '
                      : "This customer needs no e-invoice; make the e-way bill on its portal if the goods need one. "}
                    {inv.has_signed_qr ? "Paste the signed QR again only to change it." : ""}
                  </p>
                </>
              )}
            </Fold>
          )}
          <Fold title="Customer and Billing" open={!submitted} summary={`${inv.customer_name} · ${shortDate(mayEdit ? date : inv.invoice_date)}`}>
            {mayEdit && (
              <div className="item-fields">
                <label>
                  <span className="req">Invoice Date</span>
                  <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
                </label>
              </div>
            )}
            <Facts
              rows={[
                ["Customer", [inv.customer_name, inv.customer_gstin && `GSTIN ${inv.customer_gstin}`].filter(Boolean).join(" · ")],
                ["Invoice Date", mayEdit ? "" : shortDate(inv.invoice_date)],
                ["Bill From", [inv.bill_from_name, inv.bill_from_gstin && `GSTIN ${inv.bill_from_gstin}`].filter(Boolean).join(" · ")],
                ["Place of Supply", inv.place_of_supply_name],
                ["Bill To", placeText(inv.bill_address)],
                ["Ship To", shipText && shipText !== placeText(inv.bill_address) ? shipText : "As billed"],
                ["Customer's PO", [inv.customer_po_no, inv.customer_po_date && `of ${shortDate(inv.customer_po_date)}`].filter(Boolean).join(" ")],
                ["Salesman", inv.salesman_name],
              ]}
            />
          </Fold>
          <Fold title="Payment" open={!submitted} summary={[inv.credit_term_name, inv.first_due && `due ${shortDate(inv.first_due)}`].filter(Boolean).join(" · ") || "Due on the invoice date"}>
            {mayEdit && (
              <div className="item-fields">
                <label>
                  Credit Term
                  <Combobox
                    value={term}
                    onChange={setTerm}
                    empty="None (due on the invoice date)"
                    options={(setup?.credit_terms ?? []).filter((t) => t.is_active || String(t.id) === term).map((t) => ({ value: String(t.id), label: t.name }))}
                  />
                  <span className="small">From the sales order; can be changed until Submit</span>
                </label>
              </div>
            )}
            {!mayEdit && <Facts rows={[["Credit Term", [inv.credit_term_name, inv.credit_term_summary && `(${inv.credit_term_summary})`].filter(Boolean).join(" ")]]} />}
            <table className="grid">
              <thead>
                <tr>
                  <th>Due On</th>
                  <th className="num">Amount ₹</th>
                </tr>
              </thead>
              <tbody>
                {inv.dues.map((d) => (
                  <tr key={d.due_date}>
                    <td>{shortDate(d.due_date)}</td>
                    <td className="num">{money(d.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {draft && <p className="small">Due dates split by the credit term, counted from the invoice date; "Save" works them out again.</p>}
          </Fold>
          <Fold title="Items" open summary={`${lines.length} ${lines.length === 1 ? "item" : "items"} · ₹${money(itemsValue)}`}>
            <div className="table-scroll">
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th className="num">Qty</th>
                    <th>Unit</th>
                    <th className="num">Rate ₹</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th className="num">GST ₹</th>
                    <th className="num">Amount ₹</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l) => {
                    const changed = draft && Number(rates[l.id] ?? l.rate) !== Number(l.order_rate);
                    return (
                      <tr key={l.id}>
                        <td>{l.position}</td>
                        <td>
                          <b>{l.item_name}</b>
                          <div className="small">
                            HSN {l.hsn}
                            {changed ? ` · order rate ${money(l.order_rate)}` : l.rate_source ? ` · ${l.rate_source}` : ""}
                          </div>
                        </td>
                        <td className="num">{l.qty}</td>
                        <td>{l.unit_name}</td>
                        <td className="num">
                          {mayEdit ? (
                            <input className="num" inputMode="decimal" aria-label={`Rate of ${l.item_name}`} value={rates[l.id] ?? l.rate} onChange={(e) => setRates({ ...rates, [l.id]: e.target.value })} />
                          ) : (
                            money(l.rate)
                          )}
                        </td>
                        <td className="num">{money(taxableOf(l))}</td>
                        <td className="num">{l.gst_rate}</td>
                        <td className="num">{money(lineTax(l))}</td>
                        <td className="num">{money(taxableOf(l) + lineTax(l))}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="small">
              {mayEdit
                ? "Quantities are what the delivery note sent and cannot change here. A rate can be changed before Submit; the change shows in the activity."
                : "Quantities are what the delivery note sent."}
            </p>
          </Fold>
          <Fold title="Charges" open={chargeRows.length > 0 || charges.length > 0} summary={chargeRows.length ? `${chargeRows.length} · ₹${money(chargesValue)}` : "None"}>
            {(mayEdit ? charges.length > 0 : chargeRows.length > 0) && (
              <div className="table-scroll">
                <table className="grid po-lines po-charges">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Charge</th>
                      <th>Basis</th>
                      <th className="num">Rate</th>
                      <th className="num">Amount ₹</th>
                      <th>GST %</th>
                      <th className="num">GST ₹</th>
                      {mayEdit && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {mayEdit
                      ? charges.map((c, i) => {
                          const row = chargeRows.find((r) => r.c.key === c.key);
                          const set = (patch: Partial<ChargeDraft>) =>
                            setCharges((cs) =>
                              cs.map((x) => {
                                if (x.key !== c.key) return x;
                                const next = { ...x, ...patch };
                                if ("item" in patch) next.gst = setup?.charge_items.find((k) => String(k.id) === patch.item)?.gst_rate ?? "";
                                return next;
                              }),
                            );
                          return (
                            <tr key={c.key}>
                              <td>{i + 1}</td>
                              <td className="po-item">
                                <Combobox
                                  value={c.item}
                                  onChange={(v) => set({ item: v })}
                                  placeholder="Type to search charges…"
                                  ariaLabel={`Charge ${i + 1}`}
                                  options={(setup?.charge_items ?? []).map((k) => ({ value: String(k.id), label: k.name, hint: k.sac }))}
                                />
                              </td>
                              <td className="po-basis">
                                <Combobox value={c.basis} onChange={(v) => set({ basis: v || "fixed" })} ariaLabel={`Basis ${i + 1}`} options={BASES.map(([value, label]) => ({ value, label }))} />
                              </td>
                              <td className="num">
                                {c.basis === "fixed" ? "–" : <input className="num" inputMode="decimal" aria-label={`Rate ${i + 1}`} value={c.rate} onChange={(e) => set({ rate: e.target.value })} />}
                              </td>
                              <td className="num">
                                {c.basis === "fixed" ? (
                                  <input className="num" inputMode="decimal" aria-label={`Amount ${i + 1}`} value={c.rate} onChange={(e) => set({ rate: e.target.value })} />
                                ) : (
                                  money(row?.amount ?? 0)
                                )}
                              </td>
                              <td className="po-gst">
                                <Combobox value={c.gst} onChange={(v) => set({ gst: v })} ariaLabel={`GST rate ${i + 1}`} options={(setup?.gst_rates ?? []).map((r) => ({ value: r, label: r }))} />
                              </td>
                              <td className="num">{money(row?.tax ?? 0)}</td>
                              <td>
                                <button type="button" className="link danger" aria-label={`Remove charge ${i + 1}`} onClick={() => setCharges((cs) => cs.filter((x) => x.key !== c.key))}>
                                  ✕
                                </button>
                              </td>
                            </tr>
                          );
                        })
                      : (inv.charges ?? []).map((c, i) => (
                          <tr key={c.id}>
                            <td>{i + 1}</td>
                            <td>
                              <b>{c.item_name}</b>
                              <div className="small">SAC {c.sac}</div>
                            </td>
                            <td>{c.basis_label}</td>
                            <td className="num">{c.basis === "fixed" ? "–" : c.rate}</td>
                            <td className="num">{money(c.amount)}</td>
                            <td>{c.gst_rate}</td>
                            <td className="num">{money(Number(c.cgst) + Number(c.sgst) + Number(c.igst))}</td>
                          </tr>
                        ))}
                  </tbody>
                </table>
              </div>
            )}
            {mayEdit ? (
              <>
                <p>
                  <button type="button" className="link" onClick={() => setCharges((cs) => [...cs, { key: nextKey++, item: "", basis: "fixed", rate: "", gst: "" }])}>
                    + Add charge
                  </button>
                </p>
                <p className="small">The order's charges go on its first invoice. A share of the items' value or a rate per unit counts what is billed here.</p>
              </>
            ) : (
              chargeRows.length === 0 && <p className="small">No charges.</p>
            )}
          </Fold>
          <Fold title="Transport (for the e-way bill)" open={!submitted || editTransport} summary={[inv.transporter_name, inv.mode_label, inv.vehicle_no, inv.distance_km ? `${inv.distance_km} km` : ""].filter(Boolean).join(" · ")}>
            {transportEditable ? (
              <>
                <div className="item-fields">
                  <label>
                    Transporter
                    <Combobox
                      value={transport.transporter}
                      onChange={(v) => setT({ transporter: v })}
                      empty="By Customer"
                      options={(setup?.transporters ?? []).filter((t) => t.is_active || String(t.id) === transport.transporter).map((t) => ({ value: String(t.id), label: t.name }))}
                    />
                    <span className="small">From the delivery note; "By Customer" if the customer collects</span>
                  </label>
                  <label>
                    Mode
                    <Combobox value={transport.mode} onChange={(v) => setT({ mode: v || "road" })} options={MODES.map(([value, label]) => ({ value, label }))} />
                  </label>
                  <label>
                    Vehicle No
                    <input value={transport.vehicle_no} maxLength={20} placeholder="e.g. WB11D2290" onChange={(e) => setT({ vehicle_no: e.target.value })} />
                  </label>
                  <label>
                    Distance (km)
                    <input className="num" inputMode="numeric" value={transport.distance_km} onChange={(e) => setT({ distance_km: e.target.value.replace(/\D/g, "") })} />
                  </label>
                  <label>
                    LR / Docket No
                    <input value={transport.lr_no} maxLength={40} onChange={(e) => setT({ lr_no: e.target.value })} />
                  </label>
                  <label>
                    LR Date
                    <input type="date" value={transport.lr_date} onChange={(e) => setT({ lr_date: e.target.value })} />
                  </label>
                </div>
                {submitted && (
                  <>
                    <p className="small">
                      These touch no ledger, so they can change after Submit. Until the portal is connected, make the same change on the e-way bill portal too.
                    </p>
                    <div className="buttons">
                      <button
                        type="button"
                        className="link"
                        onClick={() => {
                          setTransport(transportOf(inv));
                          setEditTransport(false);
                        }}
                      >
                        Cancel
                      </button>
                      <button type="button" disabled={busy} onClick={() => act("transport", transportBody(transport))}>
                        Save Transport
                      </button>
                    </div>
                  </>
                )}
              </>
            ) : (
              <>
                <Facts
                  rows={[
                    ["Transporter", inv.transporter_name],
                    ["Mode", inv.mode_label],
                    ["Vehicle No", inv.vehicle_no],
                    ["Distance (km)", inv.distance_km == null ? "" : String(inv.distance_km)],
                    ["LR / Docket No", inv.lr_no],
                    ["LR Date", shortDate(inv.lr_date)],
                    ["Packages", inv.packages == null ? "" : String(inv.packages)],
                    ["Gross Weight (kg)", inv.gross_weight],
                  ]}
                />
                {submitted && can(session, "create") && (
                  <p>
                    <button type="button" className="link" onClick={() => setEditTransport(true)}>
                      Update Transport
                    </button>
                  </p>
                )}
              </>
            )}
          </Fold>
          {mayEdit && (
            <Fold title="Notes" summary={notes ? "Internal note" : "None"} open={!!notes}>
              <div className="item-fields">
                <label className="wide">
                  Internal Note
                  <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="For your own people; not printed" />
                </label>
              </div>
            </Fold>
          )}
          <LedgerPosting url={`v1/sales-invoices/${inv.id}/ledger-posting/`} stamp={`${saved}-${inv.status}`} />
        </div>
        <DocSide type="sales_invoice" id={inv.id} onChange={() => setFiles((n) => n + 1)}>
          <TotalsPanel
            items={chargeRows.length ? itemsValue : undefined}
            charges={chargeRows.length ? chargesValue : undefined}
            taxable={taxable}
            cgst={totals.cgst}
            sgst={totals.sgst}
            igst={totals.igst}
            roundOff={totals.roundOff}
            total={totals.total}
            note={inv.interstate ? "Customer in another state, so IGST." : Number(inv.igst_total) + Number(inv.cgst_total) ? "Same state as the customer, so CGST + SGST." : "No GST: an export."}
          />
          <SidePanel title="Details">
            <SideRows
              rows={[
                ["Delivery Note", `${inv.delivery_note_number}${submitted ? " (Billed)" : ""}`],
                ["Sales Order", inv.order_number],
                ["Number", inv.number || "Given on Submit"],
                ["Made By", inv.created_by_name],
                ...(inv.submitted_at ? ([["Submitted By", inv.submitted_by_name]] as [string, string][]) : []),
              ]}
            />
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="sales_invoice" id={inv.id} stamp={JSON.stringify(inv) + files} />
          </SidePanel>
        </DocSide>
      </div>
      {noLedgers && <MissingLedgersPopup refusal={noLedgers} document={`the sales invoice to ${inv.customer_name}`} onClose={() => setNoLedgers(null)} />}
    </section>
  );
}

/** Read-only facts in the one look (label over value); empty ones are left out. */
function Facts({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="kv">
      {rows
        .filter(([, v]) => v)
        .map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
    </dl>
  );
}
