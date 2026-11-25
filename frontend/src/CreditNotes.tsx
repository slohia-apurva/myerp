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
import { TotalsPanel } from "./PurchaseOrders";
import { portalNumbers } from "./SalesInvoices";
import { useKept } from "./Keep";

/** Entry > Sales > Credit Note: a GST credit note against a submitted sales invoice (Sidharth,
 * 2026-11-21, previews 18a/18b/18c in mockups/sales), of one of three types, all with GST:
 * "Sales Return – goods come back" (goods go back into a bin at the cost they left at),
 * "Sales Return – goods not coming back" (no stock) and "Rate Difference" (a lower rate on what was
 * billed). Made from the invoice with "Create ▾ › Credit Note". */

type Line = {
  id: number;
  position: number;
  item_name: string;
  item_number: string;
  hsn: string;
  unit_name: string;
  billed_qty: string;
  bill_rate: string;
  batch: number | null;
  batch_number: string;
  location: number | null;
  location_name: string;
  keeps_stock: boolean;
  qty: string;
  rate: string;
  new_rate: string;
  taxable: string;
  gst_rate: string;
  amount: string;
  cost: string;
  returned?: string;
  most?: string;
  rate_left?: string;
  sent?: string;
  sent_from?: string;
  cost_rate?: string;
};
type Note = {
  id: number;
  company: number;
  number: string;
  status: string;
  status_label: string;
  kind: string;
  kind_label: string;
  reason: string;
  reason_label: string;
  customer_name: string;
  customer_gstin: string;
  invoice: number;
  invoice_number: string;
  invoice_date: string;
  invoice_total: string;
  branch_name: string;
  bill_from_name: string;
  note_date: string;
  customer_ref: string;
  remarks: string;
  place_of_supply_name: string;
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
  needs_einvoice: boolean;
  cancel_reason: string;
  created_at: string;
  created_by_name: string;
  submitted_at: string | null;
  submitted_by_name: string;
  lines?: Line[];
  dues_after?: { due_date: string; invoice: string; less: string; now_due: string }[];
  places?: { id: number; name: string; is_default: boolean }[];
};
type Edit = { qty: string; location: string; new_rate: string };
type Portal = { irn: string; ack_no: string; ack_date: string; signed_qr: string };

export const KINDS: [string, string][] = [
  ["goods_back", "Sales Return – goods come back"],
  ["goods_kept", "Sales Return – goods not coming back"],
  ["rate", "Rate Difference"],
];
const REASONS: [string, string][] = [
  ["damaged", "Damaged in transit"],
  ["destroyed", "Damaged, destroyed at customer"],
  ["wrong_item", "Wrong item sent"],
  ["excess", "Excess sent"],
  ["quality", "Quality complaint"],
  ["short", "Short received by customer"],
  ["rate_lower", "Rate agreed lower"],
  ["wrong_rate", "Billed at wrong rate"],
  ["other", "Other"],
];
const VIEWS: [string, string][] = [
  ["all", "All"],
  ["draft", "Draft"],
  ["submitted", "Submitted"],
  ["cancelled", "Cancelled"],
];
export const creditBase = (companyId: number) => `#/companies/${companyId}/credit-notes`;
const CRUMB = "Entry › Sales › Credit Note";
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const at = (iso: string) => `${new Date(iso).toLocaleDateString("en-GB")} at ${new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`;
const pillClass = (s: string) => (s === "submitted" ? "pill on" : s === "draft" ? "pill warn" : "pill");
const can = (session: SignedIn, action: string) => session.permissions.includes(`sales.${action}`);
const pdf = (id: number, download = false) => openTab(`/api/v1/credit-notes/${id}/pdf/${download ? "?download=1" : ""}`);
const printItems = (id: number) => [
  { label: "Credit Note", onClick: () => pdf(id) },
  { label: "Download PDF", onClick: () => pdf(id, true) },
];
/** "Create ▾" on a submitted credit note: what follows from it, built one by one. */
const NEXT = [{ label: "Refund Payment (later)", disabled: true }];
const localInput = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const round2 = (n: number) => Math.round(n * 100) / 100;

/** "Create ▾ › Credit Note" on a submitted invoice: its open draft (made if new), in a new tab. */
export async function makeCreditNote(companyId: number, invoiceId: number): Promise<void> {
  const note = await api<Note>(`v1/sales-invoices/${invoiceId}/credit-note/`, { kind: "goods_back" });
  openTab(`${creditBase(companyId)}?view=${note.id}`);
}

export function CreditNotesPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const view = Number(hashParam("view"));
  if (view > 0) return <NoteView companyId={companyId} id={view} session={session} />;
  return <NoteList companyId={companyId} />;
}

const COLUMNS: [key: string, label: string, text: (n: Note) => string, num?: boolean][] = [
  ["number", "Credit Note No", (n) => n.number || "Draft"],
  ["date", "Date", (n) => shortDate(n.note_date)],
  ["customer", "Customer", (n) => n.customer_name],
  ["kind", "Type", (n) => n.kind_label],
  ["invoice", "Against Invoice", (n) => n.invoice_number],
  ["einvoice", "e-Invoice", (n) => (n.irn ? "Made" : n.status === "submitted" && n.needs_einvoice ? "Pending" : "")],
  ["total", "Total ₹", (n) => money(n.total), true],
  ["status", "Status", (n) => n.status_label],
];

function NoteList({ companyId }: { companyId: number }) {
  const [view, setView] = useKept("CreditNotes.view", "all");
  const [rows, setRows] = useState<Note[]>([]);
  const [search, setSearch] = useKept<Record<string, string>>("CreditNotes.search", {});
  const [selectedId, setSelectedId] = useKept<number | null>("CreditNotes.selectedId", null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Note[]>(`v1/companies/${companyId}/credit-notes/?view=${view}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("credit_note_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      rows.filter((n) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          return words.every((w) => text(n).toLowerCase().includes(w));
        }),
      ),
    [rows, search],
  );
  const selected = rows.find((n) => n.id === selectedId) ?? null;
  const printing = usePrintMenu({ title: `Credit notes: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`, scope: "" });
  const open = (id: number) => openTab(`${creditBase(companyId)}?view=${id}`);
  return (
    <section className="page">
      <PageHeader
        title="Credit Note"
        crumbs={[{ label: "Entry › Sales", href: creditBase(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "credit note" : "credit notes"} · made from a submitted sales invoice ("Create ▾" on the invoice)`}
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
                    No credit notes match.
                  </td>
                </tr>
              )}
              {shown.map((n) => (
                <tr
                  key={n.id}
                  tabIndex={0}
                  className={selected?.id === n.id ? "selected" : ""}
                  onClick={() => setSelectedId(selected?.id === n.id ? null : n.id)}
                  onDoubleClick={() => open(n.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") open(n.id);
                  }}
                >
                  {COLUMNS.map(([key, , text, num]) =>
                    key === "number" ? (
                      <td key={key}>
                        <b>{text(n)}</b>
                      </td>
                    ) : key === "status" ? (
                      <td key={key}>
                        <span className={pillClass(n.status)}>{n.status_label}</span>
                      </td>
                    ) : (
                      <td key={key} className={num ? "num" : key === "date" ? "nowrap" : undefined}>
                        {text(n)}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small no-print">Click a credit note to see it at the right; double-click or press Enter to open it; "Close" there brings you back here.</p>}
        </div>
        {selected && (
          <div className="side-col" aria-label="Credit note details">
            <SidePanel title={selected.number || "Draft"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Customer", selected.customer_name],
                  ["Type", selected.kind_label],
                  ["Against Invoice", selected.invoice_number],
                  ["IRN", selected.irn ? "Made" : ""],
                  ["Total", `₹${money(selected.total)}`],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => open(selected.id)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => pdf(selected.id)}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="credit_note" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// One credit note ---------------------------------------------------------------------

const editsOf = (n: Note): Record<number, Edit> =>
  Object.fromEntries(
    (n.lines ?? []).map((l) => [
      l.id,
      {
        qty: n.kind === "rate" || Number(l.qty) ? l.qty : "",
        location: l.location ? String(l.location) : "",
        new_rate: l.new_rate,
      },
    ]),
  );

function NoteView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const [note, setNote] = useState<Note | null>(null);
  const [error, setError] = useState<unknown>("");
  const [kind, setKind] = useState("");
  const [reason, setReason] = useState("");
  const [date, setDate] = useState("");
  const [ref, setRef] = useState("");
  const [remarks, setRemarks] = useState("");
  const [edits, setEdits] = useState<Record<number, Edit>>({});
  const [portal, setPortal] = useState<Portal | null>(null);
  const portalFile = useRef<HTMLInputElement>(null);
  const [noLedgers, setNoLedgers] = useState<MissingLedgers | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [why, setWhy] = useState("");
  const [files, setFiles] = useState(0);
  const [saved, setSaved] = useState(0);
  const [busy, setBusy] = useState(false);
  const take = useCallback((n: Note) => {
    setNote(n);
    setKind(n.kind);
    setReason(n.reason);
    setDate(n.note_date);
    setRef(n.customer_ref);
    setRemarks(n.remarks);
    setEdits(editsOf(n));
    setPortal(null);
  }, []);
  useEffect(() => {
    api<Note>(`v1/credit-notes/${id}/`).then(take, (err) => setError(err));
  }, [id, take]);
  const draft = note?.status === "draft";
  const submitted = note?.status === "submitted";
  const mayEdit = draft && can(session, "create");
  const close = () =>
    closeThisTab(() => {
      window.location.hash = creditBase(companyId);
    });
  const done = (n: Note) => {
    take(n);
    setCancelling(false);
    setSaved((k) => k + 1);
    announceSaved("credit_note_saved", { id: n.id, name: n.number || "Draft" });
  };
  const refusal = (err: unknown) => {
    const missing = missingLedgersOf(err);
    if (missing) return setNoLedgers(missing);
    setError(err);
  };
  const save = async (submit: boolean, newKind?: string) => {
    if (!note) return;
    setError("");
    setBusy(true);
    try {
      const body = {
        kind: newKind ?? kind,
        reason,
        note_date: date,
        customer_ref: ref,
        remarks,
        lines: newKind
          ? []
          : (note.lines ?? []).map((l) => {
              const e = edits[l.id];
              return note.kind === "rate"
                ? { id: l.id, new_rate: e?.new_rate === "" ? null : e?.new_rate }
                : { id: l.id, qty: e?.qty || "0", ...(l.keeps_stock && note.kind === "goods_back" ? { location: e?.location ? Number(e.location) : null } : {}) };
            }),
        submit,
      };
      done(await api<Note>(`v1/credit-notes/${id}/`, body, "PATCH"));
    } catch (err) {
      if (submit) api<Note>(`v1/credit-notes/${id}/`).then(take, () => undefined);
      refusal(err);
    }
    setBusy(false);
  };
  const act = async (path: string, body: object = {}) => {
    setError("");
    setBusy(true);
    try {
      done(await api<Note>(`v1/credit-notes/${id}/${path}/`, body));
    } catch (err) {
      refusal(err);
    }
    setBusy(false);
  };
  if (!note)
    return (
      <section className="page">
        <PageHeader title="Credit Note" crumbs={[{ label: CRUMB, href: creditBase(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const lines = note.lines ?? [];
  const isRate = note.kind === "rate";
  const back = note.kind === "goods_back";
  const setE = (lineId: number, patch: Partial<Edit>) => setEdits({ ...edits, [lineId]: { ...edits[lineId], ...patch } });
  /** A line as typed: the credit per unit, the quantity and the money, worked out here until Save. */
  const shown = (l: Line) => {
    const e = edits[l.id];
    if (!mayEdit || !e) return { qty: Number(l.qty), rate: Number(l.rate), taxable: Number(l.taxable), tax: Number(l.amount) - Number(l.taxable), amount: Number(l.amount) };
    const qty = isRate ? Number(l.qty) : Number(e.qty || 0);
    const rate = isRate ? Math.max(Number(l.rate_left) - Number(e.new_rate || l.rate_left), 0) : Number(l.bill_rate);
    const taxable = round2(qty * rate);
    const tax = round2((taxable * Number(l.gst_rate)) / 100);
    return { qty, rate, taxable, tax, amount: taxable + tax };
  };
  const sums = lines.map(shown);
  const taxable = sums.reduce((s, x) => s + x.taxable, 0);
  const tax = sums.reduce((s, x) => s + x.tax, 0);
  const exact = taxable + tax;
  const total = Math.round(exact);
  const editedTotals = mayEdit && Math.abs(taxable - Number(note.taxable_total)) > 0.001;
  const kindChanged = mayEdit && kind !== note.kind;
  const credited = lines.filter((_, k) => sums[k].taxable > 0).length;
  return (
    <section className="page">
      <PageHeader
        title={note.number ? `Credit Note ${note.number}` : "New Credit Note"}
        sub={
          note.submitted_at
            ? `Submitted as ${note.number} on ${at(note.submitted_at)}`
            : draft
              ? `Draft made from Sales Invoice ${note.invoice_number} on ${at(note.created_at)} · nothing posted yet`
              : undefined
        }
        crumbs={[{ label: CRUMB, href: creditBase(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {note.status !== "cancelled" && can(session, "cancel") && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel Credit Note
              </button>
            )}
            <ActionsMenu label="Print" items={printItems(note.id)} />
            {mayEdit && (
              <button type="button" className="link" disabled={busy} onClick={() => save(false)}>
                Save
              </button>
            )}
            {mayEdit && can(session, "submit") && (
              <button type="button" disabled={busy || kindChanged} onClick={() => save(true)}>
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
            <p className="doc-title">{note.customer_name}</p>
            <p className="item-sub">
              {note.number && <b>{note.number}</b>}
              <span className={pillClass(note.status)}>{note.status_label}</span>
              <span className="tag">{note.kind_label}</span>
              {submitted && note.needs_einvoice && <span className="tag">{note.irn ? "e-Invoice made" : "e-Invoice pending"}</span>}
              <span className="tag">
                Invoice{" "}
                <a href={`#/companies/${companyId}/sales-invoices?view=${note.invoice}`}>
                  {note.invoice_number}
                </a>
              </span>
              <span className="tag">{note.interstate ? "Interstate · IGST" : "Same state · CGST + SGST"}</span>
            </p>
          </div>
          {note.status === "cancelled" && <p className="use-note">Cancelled: {note.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this credit note cancelled?</b>
                <input autoFocus value={why} onChange={(e) => setWhy(e.target.value)} placeholder="e.g. Wrong quantity" />
              </label>
              <p className="small">
                {submitted
                  ? `The entries are reversed${back && Number(note.cost_total) ? " and the goods taken out of stock again" : ""}.${note.irn ? " Cancel the e-invoice on the portal too (allowed within 24 hours)." : ""}`
                  : "The draft is set aside."}
              </p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep it
                </button>
                <button type="button" className="link danger" onClick={() => act("cancel", { reason: why })}>
                  Cancel Credit Note
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="Credit Note Details" open={!submitted} summary={`${note.kind_label} · ${note.reason_label} · ${shortDate(mayEdit ? date : note.note_date)}`}>
            {mayEdit && (
              <>
                <div className="kind-pick">
                  <span className="fact-label req">Type</span>
                  <div className="checks" role="radiogroup" aria-label="Type">
                    {KINDS.map(([value, label]) => (
                      <label key={value} className="check">
                        <input type="radio" name="kind" checked={kind === value} onChange={() => setKind(value)} />
                        {label}
                      </label>
                    ))}
                  </div>
                </div>
                {kindChanged && (
                  <div className="use-note">
                    <p>A new type starts the lines again from the invoice; what was typed on them is dropped.</p>
                    <div className="buttons">
                      <button type="button" className="link" onClick={() => setKind(note.kind)}>
                        Keep {KINDS.find(([v]) => v === note.kind)?.[1]}
                      </button>
                      <button type="button" disabled={busy} onClick={() => save(false, kind)}>
                        Change Type
                      </button>
                    </div>
                  </div>
                )}
                <div className="item-fields">
                  <label>
                    <span className="req">Credit Note Date</span>
                    <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
                  </label>
                  <label>
                    <span className="req">Reason</span>
                    <Combobox value={reason} onChange={(v) => setReason(v || reason)} ariaLabel="Reason" options={REASONS.map(([value, label]) => ({ value, label }))} />
                  </label>
                  <label>
                    Customer's Ref
                    <input value={ref} maxLength={60} placeholder="Their return or debit note number" onChange={(e) => setRef(e.target.value)} />
                  </label>
                  <label>
                    Remarks
                    <input value={remarks} maxLength={200} onChange={(e) => setRemarks(e.target.value)} />
                  </label>
                </div>
              </>
            )}
            <Facts
              rows={[
                ["Customer", [note.customer_name, note.customer_gstin && `GSTIN ${note.customer_gstin}`].filter(Boolean).join(" · ")],
                ["Type", mayEdit ? "" : note.kind_label],
                ["Credit Note Date", mayEdit ? "" : shortDate(note.note_date)],
                ["Reason", mayEdit ? "" : note.reason_label],
                ["Against Invoice", `${note.invoice_number} of ${shortDate(note.invoice_date)} · ₹${money(note.invoice_total)}`],
                ["Bill From", note.bill_from_name],
                ["Place of Supply", note.place_of_supply_name],
                ["Customer's Ref", mayEdit ? "" : note.customer_ref],
                ["Remarks", mayEdit ? "" : note.remarks],
              ]}
            />
          </Fold>
          <Fold
            title="Items"
            open
            summary={`${credited} of ${lines.length} ${lines.length === 1 ? "line" : "lines"} credited · ₹${money(taxable)}`}
          >
            <div className="table-scroll">
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    {back && <th>Batch</th>}
                    <th className="num">{isRate ? "Billed Qty" : "Billed"}</th>
                    {!isRate && draft && <th className="num">Already Returned</th>}
                    {!isRate && <th className="num">Return Qty</th>}
                    <th>Unit</th>
                    {back && <th>Into Bin</th>}
                    <th className="num">{isRate ? "Bill Rate ₹" : "Rate ₹"}</th>
                    {isRate && <th className="num">Correct Rate ₹</th>}
                    {isRate && <th className="num">Less / Unit ₹</th>}
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th className="num">GST ₹</th>
                    <th className="num">Amount ₹</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l, k) => {
                    const x = sums[k];
                    const e = edits[l.id];
                    return (
                      <tr key={l.id}>
                        <td>{l.position}</td>
                        <td>
                          <b>{l.item_name}</b>
                          <div className="small">
                            {[l.item_number, `HSN ${l.hsn}`, back && l.sent_from && `went out from ${l.sent_from}`, back && l.cost_rate && `back at cost ₹${money(l.cost_rate)} a ${l.unit_name}`]
                              .filter(Boolean)
                              .join(" · ")}
                          </div>
                        </td>
                        {back && <td>{l.batch_number || "–"}</td>}
                        <td className="num">{isRate ? l.qty : l.sent ?? l.billed_qty}</td>
                        {!isRate && draft && <td className="num">{l.returned}</td>}
                        {!isRate && (
                          <td className="num">
                            {mayEdit ? (
                              <input
                                className="num-in"
                                inputMode="decimal"
                                aria-label={`Return Qty ${l.position}`}
                                placeholder="0"
                                value={e?.qty ?? ""}
                                title={l.most ? `At most ${l.most}` : undefined}
                                onChange={(ev) => setE(l.id, { qty: ev.target.value.replace(/[^\d.]/g, "") })}
                              />
                            ) : (
                              l.qty
                            )}
                          </td>
                        )}
                        <td>{l.unit_name}</td>
                        {back && (
                          <td className="cn-bin">
                            {!l.keeps_stock ? (
                              <span className="small">No stock</span>
                            ) : mayEdit ? (
                              <Combobox
                                value={e?.location ?? ""}
                                onChange={(v) => setE(l.id, { location: v })}
                                ariaLabel={`Into Bin ${l.position}`}
                                options={(note.places ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
                              />
                            ) : (
                              l.location_name
                            )}
                          </td>
                        )}
                        <td className="num">{money(isRate ? l.rate_left ?? l.bill_rate : l.bill_rate)}</td>
                        {isRate && (
                          <td className="num">
                            {mayEdit ? (
                              <input
                                className="num-in"
                                inputMode="decimal"
                                aria-label={`Correct Rate ${l.position}`}
                                value={e?.new_rate ?? ""}
                                onChange={(ev) => setE(l.id, { new_rate: ev.target.value.replace(/[^\d.]/g, "") })}
                              />
                            ) : (
                              money(l.new_rate)
                            )}
                          </td>
                        )}
                        {isRate && <td className="num">{money(x.rate)}</td>}
                        <td className="num">{money(x.taxable)}</td>
                        <td className="num">{l.gst_rate}</td>
                        <td className="num">{money(x.tax)}</td>
                        <td className="num">{money(x.amount)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="small">
              {isRate
                ? "Billed Qty is what the invoice billed less what earlier credit notes returned. Give the correct (lower) rate; lines left at the bill rate are dropped on Submit."
                : back
                  ? "Rate and GST come from the invoice. The goods go back into the same batch, into the bin you pick, at the cost they left at. Return Qty cannot be more than went out less what was returned before; lines left at 0 are dropped on Submit."
                  : "Rate and GST come from the invoice. No stock moves: the goods stay with the customer. Return Qty cannot be more than was billed less what was returned before; lines left at 0 are dropped on Submit."}
            </p>
          </Fold>
          <Fold title="e-Invoice" open={submitted && note.needs_einvoice} summary={note.irn ? "Made" : submitted ? (note.needs_einvoice ? "Pending" : "Not needed") : "Made after Submit"}>
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
                    onChange={async (ev) => {
                      const file = ev.target.files?.[0];
                      ev.target.value = "";
                      if (!file) return;
                      try {
                        const got = portalNumbers(await file.text());
                        if (!got.irn) throw new Error("No IRN found in that file.");
                        setPortal({ ...portal, irn: got.irn, ack_no: got.ack_no ?? portal.ack_no, ack_date: got.ack_date ?? portal.ack_date, signed_qr: got.signed_qr ?? portal.signed_qr });
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
                    <input value={portal.irn} maxLength={64} placeholder="64 letters and digits, from the portal" onChange={(ev) => setPortal({ ...portal, irn: ev.target.value.trim() })} />
                  </label>
                  <label>
                    Ack No
                    <input value={portal.ack_no} maxLength={20} inputMode="numeric" onChange={(ev) => setPortal({ ...portal, ack_no: ev.target.value.trim() })} />
                  </label>
                  <label>
                    Ack Date
                    <input type="datetime-local" value={portal.ack_date} onChange={(ev) => setPortal({ ...portal, ack_date: ev.target.value })} />
                  </label>
                  <label className="wide">
                    Signed QR Code
                    <textarea rows={2} value={portal.signed_qr} placeholder="Paste the signed QR text from the portal; it prints on the credit note" onChange={(ev) => setPortal({ ...portal, signed_qr: ev.target.value })} />
                  </label>
                </div>
                <div className="buttons">
                  <button type="button" className="link" onClick={() => setPortal(null)}>
                    Cancel
                  </button>
                  <button type="button" disabled={busy} onClick={() => act("e-invoice", { ...portal, ack_date: portal.ack_date || null })}>
                    Save
                  </button>
                </div>
              </>
            ) : (
              <>
                <Facts
                  rows={[
                    ["IRN", note.irn],
                    ["Ack No", note.ack_no],
                    ["Ack Date", note.ack_date ? at(note.ack_date) : ""],
                    ["Signed QR", note.has_signed_qr ? "Given · prints on the credit note" : ""],
                  ]}
                />
                <div className="buttons">
                  {note.needs_einvoice && (
                    <button type="button" className="link" disabled={!submitted} onClick={() => openTab(`/api/v1/credit-notes/${note.id}/json/`)}>
                      Download e-Invoice JSON
                    </button>
                  )}
                  {can(session, "submit") && note.needs_einvoice && (
                    <button
                      type="button"
                      className="link"
                      disabled={!submitted}
                      onClick={() => setPortal({ irn: note.irn, ack_no: note.ack_no, ack_date: localInput(note.ack_date), signed_qr: "" })}
                    >
                      Enter Portal Numbers
                    </button>
                  )}
                </div>
                <p className="small">
                  {note.needs_einvoice
                    ? 'A credit note to a registered customer needs an e-invoice (document type CRN), as the invoice did. After Submit, upload the JSON on the e-invoice portal, then fill the IRN with "Enter Portal Numbers" (or "Read Portal File" there). No e-way bill is made for a credit note.'
                    : "This customer needs no e-invoice."}
                </p>
              </>
            )}
          </Fold>
          <LedgerPosting url={`v1/credit-notes/${note.id}/ledger-posting/`} stamp={`${saved}-${note.status}`} />
          <Fold title="Invoice Due After This Note" open={!draft || !editedTotals} summary={note.dues_after?.length ? `Now due ₹${money(note.dues_after.reduce((s, d) => s + Number(d.now_due), 0))}` : ""}>
            <table className="grid">
              <thead>
                <tr>
                  <th>Due On</th>
                  <th className="num">Invoice ₹</th>
                  <th className="num">Less Credit Notes ₹</th>
                  <th className="num">Now Due ₹</th>
                </tr>
              </thead>
              <tbody>
                {(note.dues_after ?? []).map((d) => (
                  <tr key={d.due_date}>
                    <td>{shortDate(d.due_date)}</td>
                    <td className="num">{money(d.invoice)}</td>
                    <td className="num">{money(d.less)}</td>
                    <td className="num">{money(d.now_due)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="small">The invoice's due dates less its submitted credit notes and this one, taken off the latest due first{editedTotals ? ". Save to see this note's change." : "."}</p>
          </Fold>
        </div>
        <DocSide type="credit_note" id={note.id} onChange={() => setFiles((n) => n + 1)}>
          <TotalsPanel
            taxable={mayEdit ? taxable : Number(note.taxable_total)}
            cgst={mayEdit ? (note.interstate ? 0 : round2(tax / 2)) : Number(note.cgst_total)}
            sgst={mayEdit ? (note.interstate ? 0 : round2(tax - round2(tax / 2))) : Number(note.sgst_total)}
            igst={mayEdit ? (note.interstate ? tax : 0) : Number(note.igst_total)}
            roundOff={mayEdit ? round2(total - exact) : Number(note.round_off)}
            total={mayEdit ? total : Number(note.total)}
            note={note.interstate ? "Customer in another state, so IGST, as on the invoice." : "Same state as the customer, so CGST + SGST, as on the invoice."}
          />
          <SidePanel title="Details">
            <SideRows
              rows={[
                ["Sales Invoice", note.invoice_number],
                ["Type", note.kind_label],
                ["Number", note.number || "Given on Submit"],
                ...(back && Number(note.cost_total) ? ([["Cost Back", `₹${money(note.cost_total)}`]] as [string, string][]) : []),
                ["Made By", note.created_by_name],
                ...(note.submitted_at ? ([["Submitted By", note.submitted_by_name]] as [string, string][]) : []),
              ]}
            />
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="credit_note" id={note.id} stamp={JSON.stringify(note) + files} />
          </SidePanel>
        </DocSide>
      </div>
      {noLedgers && <MissingLedgersPopup refusal={noLedgers} document={`the credit note to ${note.customer_name}`} onClose={() => setNoLedgers(null)} />}
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
