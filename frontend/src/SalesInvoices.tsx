import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { makeCreditNote } from "./CreditNotes";
import { TotalsPanel } from "./PurchaseOrders";

/** Entry > Sales > Sales Invoice: the tax invoice for one or more submitted delivery notes of a
 * customer (Sidharth, 2026-11-20, previews 14a/14b in mockups/sales). Quantities are what the notes
 * sent; rates, charges and the credit term are the orders' and cannot change here. Submit books the
 * sale and moves the notes' cost to Cost of Goods Sold. The e-invoice and e-way bill numbers come
 * from the portal for now (typed in, or read from the portal's file). */

type Line = {
  id: number;
  position: number;
  item: number;
  item_name: string;
  hsn: string;
  unit_name: string;
  qty: string;
  rate: string;
  note_number: string;
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
type Place = {
  label?: string;
  address?: string;
  city?: string;
  pincode?: string;
  state?: string;
};
type Invoice = {
  id: number;
  company: number;
  number: string;
  status: string;
  status_label: string;
  customer_name: string;
  customer_gstin: string;
  delivery_notes: {
    id: number;
    number: string;
    note_date: string;
    order: number;
    order_number: string;
    cost_total: string;
  }[];
  delivery_note_number: string;
  orders: { id: number; number: string }[];
  order_number: string;
  customer_po_no: string;
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
  eway_with_einvoice: boolean;
  cancel_reason: string;
  created_at: string;
  created_by_name: string;
  submitted_at: string | null;
  submitted_by_name: string;
  lines?: Line[];
  charges?: Charge[];
  credit_notes?: { id: number; number: string; status: string; status_label: string; kind_label: string; note_date: string; total: string }[];
};
type Setup = {
  transporters: { id: number; name: string; is_active: boolean }[];
};
type MoreNote = {
  id: number;
  number: string;
  note_date: string;
  order_number: string;
  customer_po_no: string;
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
export const invoiceBase = (companyId: number) => `#/companies/${companyId}/sales-invoices`;
const CRUMB = "Entry › Sales › Sales Invoice";
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
  });
const at = (iso: string) => `${shortDate(iso)} at ${time(iso)}`;
const when = (iso: string | null) => (iso ? at(iso) : "");
const pillClass = (s: string) => (s === "submitted" ? "pill on" : s === "draft" ? "pill warn" : "pill");
const can = (session: SignedIn, action: string) => session.permissions.includes(`sales.${action}`);
const pdf = (id: number, layout: string, download = false) => openTab(`/api/v1/sales-invoices/${id}/pdf/?layout=${layout}${download ? "&download=1" : ""}`);
const printItems = (id: number) => [
  {
    label: "Tax Invoice (Original for Recipient)",
    onClick: () => pdf(id, "invoice"),
  },
  {
    label: "Tax Invoice (3 copies: Original, Duplicate, Triplicate)",
    onClick: () => pdf(id, "copies"),
  },
  { label: "e-Way Bill", onClick: () => pdf(id, "eway") },
  { label: "Download PDF", onClick: () => pdf(id, "invoice", true) },
];
/** "Create ▾" on a submitted invoice: the documents that follow from it, built one by one. */
const next = (companyId: number, id: number, onError: (e: unknown) => void) => [
  { label: "Credit Note (sales return or rate difference)", onClick: () => makeCreditNote(companyId, id).catch(onError) },
  { label: "Receipt (later)", disabled: true },
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
  const printing = usePrintMenu({
    title: `Sales invoices: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`,
    scope: "",
  });
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
                    <input type="search" aria-label={`Search ${label}`} placeholder="Search" value={search[key] ?? ""} onChange={(e) => setSearch({ ...search, [key]: e.target.value })} />
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

type Transport = {
  transporter: string;
  mode: string;
  vehicle_no: string;
  distance_km: string;
  lr_no: string;
  lr_date: string;
};
type Portal = {
  irn: string;
  ack_no: string;
  ack_date: string;
  signed_qr: string;
  eway_bill_no: string;
  eway_bill_date: string;
  eway_valid_until: string;
};
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

/** What the e-invoice portal gives back (its JSON file, any shape it nests it in): IRN, Ack,
 * signed QR and the e-way bill, by the portal's own names. */
export function portalNumbers(text: string): Partial<Portal> {
  const found: Record<string, string> = {};
  const walk = (x: unknown) => {
    if (Array.isArray(x)) x.forEach(walk);
    else if (x && typeof x === "object")
      for (const [k, v] of Object.entries(x)) {
        if (v && typeof v === "object") walk(v);
        else if (v != null && v !== "" && !(k.toLowerCase() in found)) found[k.toLowerCase()] = String(v);
      }
  };
  walk(JSON.parse(text));
  const stamp = (v?: string) => {
    if (!v) return "";
    const m = v.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/) || v.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})/);
    if (!m) return "";
    return m[1].length === 4 ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}` : `${m[3]}-${m[2]}-${m[1]}T${m[4]}:${m[5]}`;
  };
  const out: Partial<Portal> = {};
  if (found.irn) out.irn = found.irn.toLowerCase();
  if (found.ackno) out.ack_no = found.ackno;
  if (found.ackdt) out.ack_date = stamp(found.ackdt);
  if (found.signedqrcode) out.signed_qr = found.signedqrcode;
  if (found.ewbno) out.eway_bill_no = found.ewbno;
  if (found.ewbdt) out.eway_bill_date = stamp(found.ewbdt);
  if (found.ewbvalidtill) out.eway_valid_until = stamp(found.ewbvalidtill);
  return out;
}

function InvoiceView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const [inv, setInv] = useState<Invoice | null>(null);
  const [error, setError] = useState<unknown>("");
  const [date, setDate] = useState("");
  const [notes, setNotes] = useState("");
  const [more, setMore] = useState<MoreNote[] | null>(null);
  const portalFile = useRef<HTMLInputElement>(null);
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
    setNotes(i.notes);
    setMore(null);
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
    announceSaved("sales_invoice_saved", {
      id: i.id,
      name: i.number || "Draft",
    });
  };
  const refusal = (err: unknown) => {
    const missing = missingLedgersOf(err);
    if (missing) return setNoLedgers(missing);
    setError(err);
  };
  const save = async (submit: boolean, noteIds?: number[]) => {
    if (!inv || !transport) return;
    setError("");
    setBusy(true);
    try {
      const body = {
        invoice_date: date,
        notes,
        ...transportBody(transport),
        delivery_notes: noteIds ?? inv.delivery_notes.map((n) => n.id),
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
  const charges = inv.charges ?? [];
  const lineTax = (l: Line) => Number(l.amount) - Number(l.taxable);
  const itemsValue = lines.reduce((s, l) => s + Number(l.taxable), 0);
  const chargesValue = charges.reduce((s, c) => s + Number(c.amount), 0);
  const several = inv.delivery_notes.length > 1;
  const noteIds = inv.delivery_notes.map((n) => n.id);
  const findMore = () => api<MoreNote[]>(`v1/sales-invoices/${inv.id}/more-notes/`).then(setMore, (err) => setError(err));
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
              ? `Draft made from ${several ? "Delivery Notes" : "Delivery Note"} ${inv.delivery_note_number} on ${at(inv.created_at)} · nothing posted yet`
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
            {submitted && <ActionsMenu label="Create" main items={next(companyId, inv.id, setError)} />}
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
                {inv.delivery_notes.map((n, k) => (
                  <span key={n.id}>
                    {k > 0 && ", "}
                    <a href={`#/companies/${companyId}/delivery-notes?view=${n.id}`} target="_blank" rel="noreferrer">
                      {n.number}
                    </a>
                  </span>
                ))}
              </span>
              <span className="tag">
                Against{" "}
                {inv.orders.map((o, k) => (
                  <span key={o.id}>
                    {k > 0 && ", "}
                    <a href={`#/companies/${companyId}/sales-orders?view=${o.id}`} target="_blank" rel="noreferrer">
                      {o.number}
                    </a>
                  </span>
                ))}
              </span>
              <span className="tag">{inv.interstate ? "Interstate · IGST" : "Same state · CGST + SGST"}</span>
            </p>
          </div>
          {draft && (
            <p className="ok-note">
              Filled from the delivery {several ? "notes: the quantities they" : "note: the quantities it"} sent, at the order's rates, with the order's charges and credit term. To bill more of this
              customer's delivery notes on this one invoice, use "Add Delivery Notes".
            </p>
          )}
          {inv.status === "cancelled" && <p className="use-note">Cancelled: {inv.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this invoice cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Wrong rate" />
              </label>
              <p className="small">
                {submitted
                  ? `The entries are reversed and ${several ? "Delivery Notes" : "Delivery Note"} ${inv.delivery_note_number} can be billed again.${inv.irn ? " Cancel the e-invoice on the portal too (allowed within 24 hours)." : ""}`
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
            <Fold
              title="e-Invoice and e-Way Bill"
              open
              summary={
                [inv.irn ? "e-Invoice made" : inv.needs_einvoice ? "e-Invoice pending" : "", inv.eway_bill_no ? `e-Way Bill ${inv.eway_bill_no}` : ""].filter(Boolean).join(" · ") || "Not made yet"
              }
            >
              {portal ? (
                <>
                  <p>
                    <button type="button" className="link" onClick={() => portalFile.current?.click()}>
                      Read Portal File
                    </button>
                    <input
                      ref={portalFile}
                      type="file"
                      accept=".json,application/json"
                      hidden
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        e.target.value = "";
                        if (!file) return;
                        try {
                          const got = portalNumbers(await file.text());
                          if (!Object.keys(got).length) throw new Error("No IRN or e-way bill number found in that file.");
                          setPortal({ ...portal, ...got });
                        } catch (err) {
                          setError(err instanceof SyntaxError ? "That file is not the portal's JSON." : err);
                        }
                      }}
                    />
                    <span className="small"> The JSON the portal gives back after the upload; it fills the numbers and the signed QR below.</span>
                  </p>
                  <div className="item-fields">
                    <label className="wide">
                      IRN
                      <input value={portal.irn} maxLength={64} placeholder="64 letters and digits, from the portal" onChange={(e) => setPortal({ ...portal, irn: e.target.value.trim() })} />
                    </label>
                    <label>
                      Ack No
                      <input
                        value={portal.ack_no}
                        maxLength={20}
                        inputMode="numeric"
                        onChange={(e) =>
                          setPortal({
                            ...portal,
                            ack_no: e.target.value.trim(),
                          })
                        }
                      />
                    </label>
                    <label>
                      Ack Date
                      <input type="datetime-local" value={portal.ack_date} onChange={(e) => setPortal({ ...portal, ack_date: e.target.value })} />
                    </label>
                    <label className="wide">
                      Signed QR Code
                      <textarea
                        rows={2}
                        value={portal.signed_qr}
                        placeholder="Paste the signed QR text from the portal; it prints on the invoice"
                        onChange={(e) => setPortal({ ...portal, signed_qr: e.target.value })}
                      />
                    </label>
                    <label>
                      e-Way Bill No
                      <input value={portal.eway_bill_no} maxLength={14} inputMode="numeric" placeholder="12 digits" onChange={(e) => setPortal({ ...portal, eway_bill_no: e.target.value })} />
                    </label>
                    <label>
                      e-Way Bill Date
                      <input
                        type="datetime-local"
                        value={portal.eway_bill_date}
                        onChange={(e) =>
                          setPortal({
                            ...portal,
                            eway_bill_date: e.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      Valid Until
                      <input
                        type="datetime-local"
                        value={portal.eway_valid_until}
                        onChange={(e) =>
                          setPortal({
                            ...portal,
                            eway_valid_until: e.target.value,
                          })
                        }
                      />
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
                    {inv.needs_einvoice && !inv.eway_with_einvoice
                      ? "This invoice has services only (job work), so the portal makes no e-way bill with the e-invoice: make it on the e-way bill portal under the goods' Delivery HSN, as on the \"e-Way Bill\" print. "
                      : ""}
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
                ["Customer's PO", inv.customer_po_no],
                ["Salesman", inv.salesman_name],
              ]}
            />
          </Fold>
          <Fold title="Delivery Notes" open={!submitted} summary={inv.delivery_note_number}>
            <div className="table-scroll">
              <table className="grid">
                <thead>
                  <tr>
                    <th>Delivery Note</th>
                    <th>Date</th>
                    <th>Sales Order</th>
                    <th className="num">Cost ₹</th>
                    {mayEdit && several && <th />}
                  </tr>
                </thead>
                <tbody>
                  {inv.delivery_notes.map((n) => (
                    <tr key={n.id}>
                      <td>
                        <a href={`#/companies/${companyId}/delivery-notes?view=${n.id}`} target="_blank" rel="noreferrer">
                          {n.number}
                        </a>
                      </td>
                      <td>{shortDate(n.note_date)}</td>
                      <td>{n.order_number}</td>
                      <td className="num">{money(n.cost_total)}</td>
                      {mayEdit && several && (
                        <td>
                          <button
                            type="button"
                            className="link danger"
                            disabled={busy}
                            onClick={() =>
                              save(
                                false,
                                noteIds.filter((x) => x !== n.id),
                              )
                            }
                          >
                            Remove
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {mayEdit && more && (
              <>
                <p className="small">
                  {more.length
                    ? "This customer's other delivery notes not billed yet, from the same place to the same address on the same credit term:"
                    : "No other delivery note of this customer can go on this invoice (unbilled, from the same place to the same address, on the same credit term)."}
                </p>
                {more.length > 0 && (
                  <table className="grid">
                    <thead>
                      <tr>
                        <th>Delivery Note</th>
                        <th>Date</th>
                        <th>Sales Order</th>
                        <th>Customer's PO</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {more.map((n) => (
                        <tr key={n.id}>
                          <td>{n.number}</td>
                          <td>{shortDate(n.note_date)}</td>
                          <td>{n.order_number}</td>
                          <td>{n.customer_po_no}</td>
                          <td>
                            <button type="button" className="link" disabled={busy} onClick={() => save(false, [...noteIds, n.id])}>
                              Add
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
            {mayEdit && (
              <div className="buttons">
                {more ? (
                  <button type="button" className="link" onClick={() => setMore(null)}>
                    Done
                  </button>
                ) : (
                  <button type="button" className="link" onClick={findMore}>
                    Add Delivery Notes
                  </button>
                )}
              </div>
            )}
            <p className="small">Several delivery notes on one invoice make one e-invoice and one e-way bill. Adding or removing a note saves the draft.</p>
          </Fold>
          <Fold title="Payment" open={!submitted} summary={[inv.credit_term_name, inv.first_due && `due ${shortDate(inv.first_due)}`].filter(Boolean).join(" · ") || "Due on the invoice date"}>
            <Facts rows={[["Credit Term", [inv.credit_term_name || "None (due on the invoice date)", inv.credit_term_summary && `(${inv.credit_term_summary})`].filter(Boolean).join(" ")]]} />
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
            <p className="small">The credit term is the sales order's and cannot be changed here. Due dates are counted from the invoice date.</p>
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
                  {lines.map((l) => (
                    <tr key={l.id}>
                      <td>{l.position}</td>
                      <td>
                        <b>{l.item_name}</b>
                        <div className="small">{[`HSN ${l.hsn}`, several && l.note_number, l.rate_source].filter(Boolean).join(" · ")}</div>
                      </td>
                      <td className="num">{l.qty}</td>
                      <td>{l.unit_name}</td>
                      <td className="num">{money(l.rate)}</td>
                      <td className="num">{money(l.taxable)}</td>
                      <td className="num">{l.gst_rate}</td>
                      <td className="num">{money(lineTax(l))}</td>
                      <td className="num">{money(l.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small">Quantities are what the delivery {several ? "notes" : "note"} sent, at the sales order's rates; neither can be changed here.</p>
          </Fold>
          <Fold title="Charges" open={charges.length > 0} summary={charges.length ? `${charges.length} · ₹${money(chargesValue)}` : "None"}>
            {charges.length > 0 && (
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
                    </tr>
                  </thead>
                  <tbody>
                    {charges.map((c, i) => (
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
            <p className="small">{charges.length ? "The sales order's charges, on its first invoice." : "No charges."}</p>
          </Fold>
          <Fold
            title="Transport (for the e-way bill)"
            open={!submitted || editTransport}
            summary={[inv.transporter_name, inv.mode_label, inv.vehicle_no, inv.distance_km ? `${inv.distance_km} km` : ""].filter(Boolean).join(" · ")}
          >
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
                    <Combobox
                      value={transport.mode}
                      onChange={(v) => setT({ mode: v || "road" })}
                      options={MODES.map(([value, label]) => ({
                        value,
                        label,
                      }))}
                    />
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
                    <p className="small">These touch no ledger, so they can change after Submit. Until the portal is connected, make the same change on the e-way bill portal too.</p>
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
            items={charges.length ? itemsValue : undefined}
            charges={charges.length ? chargesValue : undefined}
            taxable={Number(inv.taxable_total)}
            cgst={Number(inv.cgst_total)}
            sgst={Number(inv.sgst_total)}
            igst={Number(inv.igst_total)}
            roundOff={Number(inv.round_off)}
            total={Number(inv.total)}
            note={inv.interstate ? "Customer in another state, so IGST." : Number(inv.igst_total) + Number(inv.cgst_total) ? "Same state as the customer, so CGST + SGST." : "No GST: an export."}
          />
          {(inv.credit_notes ?? []).length > 0 && (
            <SidePanel title="Credit Notes">
              {(inv.credit_notes ?? []).map((c) => (
                <div key={c.id} className="side-row">
                  <span>
                    <a href={`#/companies/${companyId}/credit-notes?view=${c.id}`} target="_blank" rel="noreferrer">
                      {c.number || "Draft"}
                    </a>
                    <span className="small"> · {c.kind_label.replace("Sales Return – ", "Return, ")}</span>
                  </span>
                  <span>₹{money(c.total)}</span>
                </div>
              ))}
            </SidePanel>
          )}
          <SidePanel title="Details">
            <SideRows
              rows={[
                [several ? "Delivery Notes" : "Delivery Note", `${inv.delivery_note_number}${submitted ? " (Billed)" : ""}`],
                [inv.orders.length > 1 ? "Sales Orders" : "Sales Order", inv.order_number],
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
