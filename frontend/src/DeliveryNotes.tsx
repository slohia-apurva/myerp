import { useCallback, useEffect, useMemo, useState } from "react";
import { useTransporterSearch } from "./Shipments";
import { api, ApiError, type SignedIn } from "./api";
import { DocSide } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { money } from "./Companies";
import { announceSaved, closeThisTab, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { LedgerPosting, MissingLedgersPopup, missingLedgersOf, type MissingLedgers } from "./LedgerPosting";
import { Fold, hashParam, openTab, SidePanel, SideRows, listStart } from "./Master";
import { invoiceBase, makeSalesInvoice } from "./SalesInvoices";
import { useKept } from "./Keep";
import { Connections } from "./Connections";

/** Entry > Sales > Delivery Note: the goods going out to the customer (Sidharth, 2026-11-20,
 * previews 7-9 in mockups/sales). Made from a picked pick list with its bins and batches; Submit
 * takes the stock out at FIFO cost into "Goods Delivered but Bills not Made". */

type Bin = {
  id: number;
  location: number;
  location_name: string;
  batch: number | null;
  batch_number: string;
  expiry: string | null;
  package: number | null;
  package_number: string;
  package_label: string;
  /** Stock unit. */
  picked: string;
  qty: string;
  qty_unit: string;
  cost: string;
};
type Line = {
  id: number;
  position: number;
  item: number;
  item_name: string;
  item_number?: string;
  hsn: string;
  unit_name: string;
  stock_unit_name: string;
  factor: string;
  ordered: string;
  sent_earlier: string;
  pending: string;
  picked: string;
  qty: string;
  rate: string;
  taxable: string;
  gst_rate: string;
  amount: string;
  cost: string;
  bins: Bin[];
};
type Note = {
  id: number;
  company: number;
  number: string;
  status: string;
  status_label: string;
  customer_name: string;
  customer_gstin: string;
  order: number;
  order_number: string;
  customer_po_no: string;
  customer_po_date: string | null;
  pick_list: number;
  pick_list_number: string;
  pick_list_status: string;
  despatch_from: string;
  note_date: string;
  bill_from_name: string;
  bill_from_gstin: string;
  ship_address: { label?: string; line1?: string; city?: string; pin?: string };
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
  total: string;
  cost_total: string;
  billed: boolean;
  invoice: { id: number; number: string; status: string; status_label: string } | null;
  cancel_reason: string;
  created_at: string;
  created_by_name: string;
  submitted_at: string | null;
  submitted_by_name: string;
  salesman_name?: string;
  lines?: Line[];
};
type Spot = {
  location: number;
  location_name: string;
  batch: number | null;
  batch_number: string;
  package: number | null;
  package_number: string;
  expiry: string | null;
  free: string;
};
type Problem = { line: number; text: string };

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
export const deliveryBase = (companyId: number) => `#/companies/${companyId}/delivery-notes`;
const CRUMB = "Entry › Sales › Delivery Note";
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const at = (iso: string) => `${shortDate(iso)} at ${new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`;
const pillClass = (s: string) => (s === "submitted" ? "pill on" : s === "draft" ? "pill warn" : "pill");
const plain = (n: number) => String(Number(n.toFixed(3)));
const can = (session: SignedIn, action: string) => session.permissions.includes(`sales.${action}`) || session.permissions.includes(`stock.${action}`);
const pdf = (id: number, layout: string, download = false) =>
  openTab(`/api/v1/delivery-notes/${id}/pdf/?layout=${layout}${download ? "&download=1" : ""}`);
const printItems = (id: number) => [
  { label: "Delivery Challan", onClick: () => pdf(id, "challan") },
  { label: "Packing List", onClick: () => pdf(id, "packing") },
  { label: "Download PDF", onClick: () => pdf(id, "challan", true) },
];
/** "Create ▾" on a submitted note: the documents that follow from it, built one by one. */
const nextOf = (companyId: number, note: Note, fail: (err: unknown) => void) => [
  note.billed
    ? { label: "Sales Invoice (made)", disabled: true }
    : { label: note.invoice ? "Sales Invoice (open the draft)" : "Sales Invoice", onClick: () => makeSalesInvoice(companyId, note.id).catch(fail) },
  { label: "Sales Return (later)", disabled: true },
];

/** "Create ▾ › Delivery Note" on a sales order or a pick list: the list's draft note (made if new),
 * opened in a new tab. */
export async function makeDeliveryNote(companyId: number, pickId: number): Promise<void> {
  const n = await api<Note>(`v1/pick-lists/${pickId}/delivery-note/`, {});
  openTab(`${deliveryBase(companyId)}?view=${n.id}`);
}

export function DeliveryNotesPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const view = Number(hashParam("view"));
  if (view > 0) return <NoteView companyId={companyId} id={view} session={session} />;
  return <NoteList companyId={companyId} />;
}

const COLUMNS: [key: string, label: string, text: (n: Note) => string, num?: boolean][] = [
  ["number", "Note No", (n) => n.number || "Draft"],
  ["date", "Date", (n) => shortDate(n.note_date)],
  ["customer", "Customer", (n) => n.customer_name],
  ["order", "Sales Order", (n) => n.order_number],
  ["despatch", "Despatch From", (n) => n.despatch_from],
  ["vehicle", "Vehicle No", (n) => n.vehicle_no],
  ["value", "Taxable ₹", (n) => money(n.taxable_total), true],
  ["status", "Status", (n) => n.status_label],
];

function NoteList({ companyId }: { companyId: number }) {
  const [view, setView] = useKept("DeliveryNotes.view", () => listStart("all").view);
  const [notes, setNotes] = useState<Note[]>([]);
  const [search, setSearch] = useKept<Record<string, string>>("DeliveryNotes.search", () => listStart("").search);
  const [selectedId, setSelectedId] = useKept<number | null>("DeliveryNotes.selectedId", null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Note[]>(`v1/companies/${companyId}/delivery-notes/?view=${view}`)
      .then(setNotes)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("delivery_note_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      notes.filter((n) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          return words.every((w) => text(n).toLowerCase().includes(w));
        }),
      ),
    [notes, search],
  );
  const selected = notes.find((n) => n.id === selectedId) ?? null;
  const printing = usePrintMenu({ title: `Delivery notes: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`, scope: "" });
  const open = (id: number) => openTab(`${deliveryBase(companyId)}?view=${id}`);
  return (
    <section className="page">
      <PageHeader
        title="Delivery Note"
        crumbs={[{ label: "Entry › Sales", href: deliveryBase(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "delivery note" : "delivery notes"} · made from a picked pick list ("Create ▾" on the order or the list)`}
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
                    No delivery notes match.
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
                  <td>
                    <b>{n.number || "Draft"}</b>
                  </td>
                  <td className="nowrap">{shortDate(n.note_date)}</td>
                  <td>{n.customer_name}</td>
                  <td>{n.order_number}</td>
                  <td>{n.despatch_from}</td>
                  <td>{n.vehicle_no}</td>
                  <td className="num">{money(n.taxable_total)}</td>
                  <td>
                    <span className={pillClass(n.status)}>{n.status_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small no-print">Click a note to see it at the right; double-click or press Enter to open it; "Close" there brings you back here.</p>}
        </div>
        {selected && (
          <div className="side-col" aria-label="Delivery note details">
            <SidePanel title={selected.number || "Draft"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Customer", selected.customer_name],
                  ["Sales Order", selected.order_number],
                  ["Pick List", selected.pick_list_number],
                  ["Despatch From", selected.despatch_from],
                  ["Transporter", selected.transporter_name],
                  ["Taxable Value", `₹${money(selected.taxable_total)}`],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => open(selected.id)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => pdf(selected.id, "challan")}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="delivery_note" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// One note ----------------------------------------------------------------------

type DraftBin = { key: number; line: number; spot: string; qty: string; picked: string };
type Fields = {
  note_date: string;
  transporter: string;
  mode: string;
  vehicle_no: string;
  distance_km: string;
  lr_no: string;
  lr_date: string;
  packages: string;
  gross_weight: string;
  notes: string;
};
let nextKey = 1;
const spotValue = (location: number, batch: number | null, pkg: number | null = null) => `${location}-${batch ?? ""}-${pkg ?? ""}`;
const fieldsOf = (n: Note): Fields => ({
  note_date: n.note_date,
  transporter: n.transporter ? String(n.transporter) : "",
  mode: n.mode,
  vehicle_no: n.vehicle_no,
  distance_km: n.distance_km == null ? "" : String(n.distance_km),
  lr_no: n.lr_no,
  lr_date: n.lr_date ?? "",
  packages: n.packages == null ? "" : String(n.packages),
  gross_weight: n.gross_weight,
  notes: n.notes,
});
const binsOf = (n: Note): DraftBin[] =>
  (n.lines ?? []).flatMap((l) => l.bins.map((b) => ({ key: nextKey++, line: l.id, spot: spotValue(b.location, b.batch, b.package), qty: b.qty, picked: b.picked })));

function NoteView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const [note, setNote] = useState<Note | null>(null);
  const [error, setError] = useState<unknown>("");
  const [fields, setFields] = useState<Fields | null>(null);
  // Transporters come from the server as the person types (useTransporterSearch), never all at once.
  const { transporters, onType: findTransporters } = useTransporterSearch(companyId, [fields?.transporter]);
  const [bins, setBins] = useState<DraftBin[]>([]);
  const [openLine, setOpenLine] = useState<number | null>(null);
  const [spots, setSpots] = useState<Record<number, Spot[]>>({});
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [noLedgers, setNoLedgers] = useState<MissingLedgers | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const [saved, setSaved] = useState(0);
  const [busy, setBusy] = useState(false);
  const take = useCallback((n: Note) => {
    setNote(n);
    setFields(fieldsOf(n));
    setBins(binsOf(n));
  }, []);
  useEffect(() => {
    api<Note>(`v1/delivery-notes/${id}/`).then(take, (err) => setError(err));
  }, [id, take]);
  const draft = note?.status === "draft";
  const mayEdit = draft && can(session, "create");
  useEffect(() => {
    if (!note || !mayEdit) return;
    for (const l of note.lines ?? [])
      api<Spot[]>(`v1/delivery-notes/${id}/places/?item=${l.item}`).then((s) => setSpots((all) => ({ ...all, [l.item]: s })), () => undefined);
    // Only once per note: the places do not change while the page is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note?.id, mayEdit]);
  const close = () =>
    closeThisTab(() => {
      window.location.hash = deliveryBase(companyId);
    });
  const done = (n: Note) => {
    take(n);
    setCancelling(false);
    setSaved((k) => k + 1);
    announceSaved("delivery_note_saved", { id: n.id, name: n.number || "Draft" });
  };
  const refusal = (err: unknown) => {
    const missing = missingLedgersOf(err);
    if (missing) return setNoLedgers(missing);
    const data = err instanceof ApiError ? (err.data as { problems?: Problem[] } | undefined) : undefined;
    if (data?.problems?.length) return setProblems(data.problems);
    setError(err);
  };
  const save = async (submit: boolean) => {
    if (!fields) return;
    setError("");
    setBusy(true);
    try {
      const body = {
        ...fields,
        transporter: fields.transporter ? Number(fields.transporter) : null,
        distance_km: fields.distance_km ? Number(fields.distance_km) : null,
        packages: fields.packages ? Number(fields.packages) : null,
        gross_weight: fields.gross_weight || null,
        lr_date: fields.lr_date || null,
        bins: bins
          .filter((b) => b.spot)
          .map((b) => {
            const [location, batch, pkg] = b.spot.split("-");
            return { line: b.line, location: Number(location), batch: batch ? Number(batch) : null, package: pkg ? Number(pkg) : null, qty: b.qty || "0" };
          }),
        submit,
      };
      done(await api<Note>(`v1/delivery-notes/${id}/`, body, "PATCH"));
    } catch (err) {
      // A refused Submit still saved the draft: read it again.
      if (submit) api<Note>(`v1/delivery-notes/${id}/`).then(take, () => undefined);
      refusal(err);
    }
    setBusy(false);
  };
  const act = async (path: string, body: object = {}) => {
    setError("");
    setBusy(true);
    try {
      done(await api<Note>(`v1/delivery-notes/${id}/${path}/`, body));
    } catch (err) {
      refusal(err);
    }
    setBusy(false);
  };
  const goTo = (position: number) => {
    setProblems(null);
    const line = note?.lines?.find((l) => l.position === position);
    if (line) setOpenLine(line.id);
    window.setTimeout(() => document.getElementById(`dn-line-${position}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };
  if (!note || !fields)
    return (
      <section className="page">
        <PageHeader title="Delivery Note" crumbs={[{ label: CRUMB, href: deliveryBase(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const set = (patch: Partial<Fields>) => setFields({ ...fields, ...patch });
  const lines = note.lines ?? [];
  const sentOf = (l: Line) => (draft ? bins.filter((b) => b.line === l.id).reduce((s, b) => s + (Number(b.qty) || 0), 0) / Number(l.factor) : Number(l.qty));
  const taxableOf = (l: Line) => (draft ? sentOf(l) * Number(l.rate) : Number(l.taxable));
  const taxable = lines.reduce((s, l) => s + taxableOf(l), 0);
  const gst = draft ? lines.reduce((s, l) => s + (taxableOf(l) * Number(l.gst_rate)) / 100, 0) : Number(note.total) - Number(note.taxable_total);
  const ship = note.ship_address ?? {};
  const shipText = [ship.label, ship.line1, ship.city, ship.pin].filter(Boolean).join(", ");
  const submitted = note.status === "submitted";
  return (
    <section className="page">
      <PageHeader
        title={note.number ? `Delivery Note ${note.number}` : "New Delivery Note"}
        sub={
          note.submitted_at
            ? `Submitted as ${note.number} on ${at(note.submitted_at)}`
            : draft
              ? `Draft made ${at(note.created_at)} · nothing posted yet`
              : undefined
        }
        crumbs={[{ label: CRUMB, href: deliveryBase(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {note.status !== "cancelled" && can(session, "cancel") && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel Note
              </button>
            )}
            <ActionsMenu label="Print" items={printItems(note.id)} />
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
            {submitted && <ActionsMenu label="Create" main items={nextOf(companyId, note, setError)} />}
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
              {submitted && !note.billed && <span className="tag">Not billed</span>}
              {note.invoice && (
                <span className="tag">
                  {note.billed ? "Billed on " : "Draft invoice "}
                  <a href={`${invoiceBase(companyId)}?view=${note.invoice.id}`}>
                    {note.invoice.number || "Open"}
                  </a>
                </span>
              )}
              <span className="tag">{note.despatch_from}</span>
              <span className="tag">
                From Pick List{" "}
                <a href={`#/companies/${companyId}/pick-lists?view=${note.pick_list}`}>
                  {note.pick_list_number}
                </a>
              </span>
              <span className="tag">
                Against{" "}
                <a href={`#/companies/${companyId}/sales-orders?view=${note.order}`}>
                  {note.order_number}
                </a>
              </span>
            </p>
          </div>
          {draft && <p className="ok-note">Filled from the picked list: every bin, batch and quantity the stores picked. Lower a quantity to send less; the rest stays pending on the order.</p>}
          {note.status === "cancelled" && <p className="use-note">Cancelled: {note.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this note cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Truck did not come" />
              </label>
              <p className="small">{submitted ? "The goods go back into their bins, the entries are reversed and the order's quantities are pending again." : "The draft is set aside; the pick list stays picked."}</p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep it
                </button>
                <button type="button" className="link danger" onClick={() => act("cancel", { reason })}>
                  Cancel Note
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="Customer and Despatch" open summary={`${note.customer_name} · ${shortDate(mayEdit ? fields.note_date : note.note_date)}`}>
            {mayEdit && (
              <div className="item-fields">
                <label>
                  <span className="req">Note Date</span>
                  <input type="date" required value={fields.note_date} onChange={(e) => set({ note_date: e.target.value })} />
                </label>
              </div>
            )}
            <Facts
              rows={[
                ["Customer", [note.customer_name, note.customer_gstin && `GSTIN ${note.customer_gstin}`].filter(Boolean).join(" · ")],
                ["Note Date", mayEdit ? "" : shortDate(note.note_date)],
                ["Despatch From", note.despatch_from],
                ["Sales Order", note.order_number],
                ["Bill From", [note.bill_from_name, note.bill_from_gstin && `GSTIN ${note.bill_from_gstin}`].filter(Boolean).join(" · ")],
                ["Ship To", shipText || "As billed"],
                ["Customer's PO", [note.customer_po_no, note.customer_po_date && `of ${shortDate(note.customer_po_date)}`].filter(Boolean).join(" ")],
                ["Salesman", note.salesman_name ?? ""],
              ]}
            />
          </Fold>
          <Fold title="Transport (for the e-way bill)" open summary={[note.transporter_name, note.vehicle_no].filter(Boolean).join(" · ")}>
            {mayEdit ? (
              <div className="item-fields">
                <label>
                  Transporter
                  <Combobox
                    value={fields.transporter}
                    onChange={(v) => set({ transporter: v })}
                    empty="By Customer"
                    onType={findTransporters}
                    options={transporters.filter((t) => t.is_active || String(t.id) === fields.transporter).map((t) => ({ value: String(t.id), label: t.name }))}
                  />
                  <span className="small">From the order; "By Customer" if the customer collects</span>
                </label>
                <label>
                  Mode
                  <Combobox value={fields.mode} onChange={(v) => set({ mode: v || "road" })} options={MODES.map(([value, label]) => ({ value, label }))} />
                </label>
                <label>
                  Vehicle No
                  <input value={fields.vehicle_no} maxLength={20} placeholder="e.g. WB11D2290" onChange={(e) => set({ vehicle_no: e.target.value })} />
                </label>
                <label>
                  Distance (km)
                  <input className="num" inputMode="numeric" value={fields.distance_km} onChange={(e) => set({ distance_km: e.target.value.replace(/\D/g, "") })} />
                </label>
                <label>
                  LR / Docket No
                  <input value={fields.lr_no} maxLength={40} onChange={(e) => set({ lr_no: e.target.value })} />
                </label>
                <label>
                  LR Date
                  <input type="date" value={fields.lr_date} onChange={(e) => set({ lr_date: e.target.value })} />
                </label>
                <label>
                  Packages
                  <input className="num" inputMode="numeric" value={fields.packages} onChange={(e) => set({ packages: e.target.value.replace(/\D/g, "") })} />
                </label>
                <label>
                  Gross Weight (kg)
                  <input className="num" inputMode="decimal" value={fields.gross_weight} onChange={(e) => set({ gross_weight: e.target.value })} />
                </label>
              </div>
            ) : (
              <Facts
                rows={[
                  ["Transporter", note.transporter_name],
                  ["Mode", note.mode_label],
                  ["Vehicle No", note.vehicle_no],
                  ["Distance (km)", note.distance_km == null ? "" : String(note.distance_km)],
                  ["LR / Docket No", note.lr_no],
                  ["LR Date", shortDate(note.lr_date)],
                  ["Packages", note.packages == null ? "" : String(note.packages)],
                  ["Gross Weight (kg)", note.gross_weight],
                ]}
              />
            )}
          </Fold>
          <Fold title="Items" open summary={`${lines.length} ${lines.length === 1 ? "item" : "items"} · ₹${money(taxable)}`}>
            <div className="table-scroll">
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th className="num">Ordered</th>
                    <th className="num">Sent Earlier</th>
                    <th className="num">Picked</th>
                    <th className="num">{submitted ? "Sent" : "This Note"}</th>
                    <th>Unit</th>
                    <th className="num">Rate ₹</th>
                    <th className="num">Taxable ₹</th>
                    {submitted && <th className="num">Cost ₹</th>}
                    <th>Bins</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.flatMap((l) => {
                    const mine = bins.filter((b) => b.line === l.id);
                    const sent = sentOf(l);
                    const over = draft && sent > Number(l.pending) + 1e-9;
                    const shown = draft ? mine : l.bins.map((b) => ({ key: b.id, line: l.id, spot: spotValue(b.location, b.batch, b.package), qty: b.qty, picked: b.picked }));
                    const count = shown.filter((b) => Number(b.qty) > 0).length;
                    const isOpen = openLine === l.id;
                    const rows = [
                      <tr key={l.id} id={`dn-line-${l.position}`}>
                        <td>{l.position}</td>
                        <td>
                          <b>{l.item_name}</b>
                          <div className="small">{l.item_number && `${l.item_number} · `}HSN {l.hsn}</div>
                        </td>
                        <td className="num">{l.ordered}</td>
                        <td className="num">{l.sent_earlier}</td>
                        <td className="num">{l.picked}</td>
                        <td className="num">{over ? <b className="error">{plain(sent)}</b> : <b>{plain(sent)}</b>}</td>
                        <td>{l.unit_name}</td>
                        <td className="num">{money(l.rate)}</td>
                        <td className="num">{money(taxableOf(l))}</td>
                        {submitted && <td className="num">{money(l.cost)}</td>}
                        <td className="nowrap">
                          <button type="button" className="link" aria-expanded={isOpen} onClick={() => setOpenLine(isOpen ? null : l.id)}>
                            {isOpen ? "▾" : "▸"} {count} {count === 1 ? "bin" : "bins"}
                          </button>{" "}
                          {draft && (over ? <span className="bad-note">✕</span> : <span className="ok-note">✓</span>)}
                        </td>
                      </tr>,
                    ];
                    if (isOpen)
                      rows.push(
                        <tr key={`${l.id}-bins`} className="dn-bins">
                          <td />
                          <td colSpan={submitted ? 10 : 9}>
                            <BinRows line={l} rows={shown} edit={!!mayEdit} spots={spots[l.item] ?? []} setBins={setBins} onDone={() => setOpenLine(null)} />
                          </td>
                        </tr>,
                      );
                    return rows;
                  })}
                  <tr>
                    <td />
                    <td colSpan={7}>
                      <b>Total</b>{" "}
                      <span className="small">
                        GST: {note.interstate ? "IGST" : "CGST + SGST"} ₹{money(gst)} · value with tax ₹{money(taxable + gst)}, as the e-way bill needs it
                      </span>
                    </td>
                    <td className="num">
                      <b>{money(taxable)}</b>
                    </td>
                    {submitted && (
                      <td className="num">
                        <b>{money(note.cost_total)}</b>
                      </td>
                    )}
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="small">
              {mayEdit
                ? 'Open a line\'s bins to send less, or to send from another bin or batch that has the stock free. Rates come from the order; they print on the challan and go on to the sales invoice. "Save" keeps the changes.'
                : "Rates come from the order; they print on the challan and go on to the sales invoice."}
            </p>
          </Fold>
          <LedgerPosting url={`v1/delivery-notes/${note.id}/ledger-posting/`} stamp={`${saved}-${note.status}`} />
          <Connections companyId={companyId} kind="delivery_note" id={note.id} stamp={`${saved}-${note.status}`} create={note.status === "submitted" && !note.billed && !note.invoice ? { sales_invoice: () => void makeSalesInvoice(companyId, note.id).catch(setError) } : undefined} />
        </div>
        <DocSide type="delivery_note" id={note.id} onChange={() => setFiles((n) => n + 1)}>
          <SidePanel title="Details">
            <SideRows
              rows={[
                ["Sales Order", note.order_number],
                ["Pick List", `${note.pick_list_number} (${note.pick_list_status})`],
                ["Made By", note.created_by_name],
                ...(note.submitted_at ? ([["Submitted By", note.submitted_by_name]] as [string, string][]) : []),
              ]}
            />
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="delivery_note" id={note.id} stamp={JSON.stringify(note) + files} />
          </SidePanel>
        </DocSide>
      </div>
      {problems && <ProblemsPopup problems={problems} onGo={goTo} onClose={() => setProblems(null)} />}
      {noLedgers && <MissingLedgersPopup refusal={noLedgers} document={`the delivery note to ${note.customer_name}`} onClose={() => setNoLedgers(null)} />}
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

/** A line's bins, folded under it: Bin, Batch, Expiry, Picked and Send. On a draft "Send" can be
 * lowered, a row moved to another bin or batch with the stock free, or a bin added. */
function BinRows(p: {
  line: Line;
  rows: DraftBin[];
  edit: boolean;
  spots: Spot[];
  setBins: (f: (b: DraftBin[]) => DraftBin[]) => void;
  onDone: () => void;
}) {
  const { line } = p;
  const set = (key: number, patch: Partial<DraftBin>) => p.setBins((bs) => bs.map((b) => (b.key === key ? { ...b, ...patch } : b)));
  const options = p.spots.map((s) => ({
    value: spotValue(s.location, s.batch, s.package),
    label: [s.location_name, s.batch_number, s.package_number].filter(Boolean).join(" · "),
    hint: [s.expiry && `exp ${shortDate(s.expiry)}`, `${plain(Number(s.free))} ${line.stock_unit_name} free`].filter(Boolean).join(" · "),
  }));
  // A picked bin stays in the list even if its place did not load.
  for (const b of line.bins) {
    const value = spotValue(b.location, b.batch, b.package);
    if (!options.some((o) => o.value === value)) options.push({ value, label: [b.location_name, b.batch_number, b.package_number].filter(Boolean).join(" · "), hint: "" });
  }
  const named = (spot: string) => {
    const b = line.bins.find((x) => spotValue(x.location, x.batch, x.package) === spot);
    const s = p.spots.find((x) => spotValue(x.location, x.batch, x.package) === spot);
    return {
      bin: b?.location_name ?? s?.location_name ?? "",
      batch: b?.batch_number ?? s?.batch_number ?? "",
      pkg: b?.package_number ?? s?.package_number ?? "",
      expiry: b?.expiry ?? s?.expiry ?? null,
    };
  };
  return (
    <div className="grn-put">
      <table className="grid">
        <thead>
          <tr>
            <th>Bin</th>
            <th>Batch</th>
            <th>Package</th>
            <th>Expiry</th>
            <th className="num">Picked ({line.stock_unit_name})</th>
            <th className="num">Send ({line.stock_unit_name})</th>
            {p.edit && <th />}
          </tr>
        </thead>
        <tbody>
          {p.rows.map((b) => {
            const n = named(b.spot);
            return (
              <tr key={b.key}>
                {p.edit && !Number(b.picked) ? (
                  <td colSpan={3} className="po-item">
                    <Combobox value={b.spot} onChange={(v) => set(b.key, { spot: v })} ariaLabel={`Bin for ${line.item_name}`} placeholder="Type to search bins…" options={options} />
                  </td>
                ) : (
                  <>
                    <td>{n.bin}</td>
                    <td>{n.batch}</td>
                    <td>{n.pkg ? <b>{n.pkg}</b> : <span className="small">No package</span>}</td>
                  </>
                )}
                <td>{shortDate(n.expiry)}</td>
                <td className="num">{Number(b.picked) ? b.picked : ""}</td>
                <td className="num">
                  {p.edit ? (
                    <input className="num" inputMode="decimal" aria-label={`Send from ${n.bin}`} value={b.qty} onChange={(e) => set(b.key, { qty: e.target.value })} />
                  ) : (
                    b.qty
                  )}
                </td>
                {p.edit && (
                  <td>
                    {!Number(b.picked) && (
                      <button type="button" className="link danger" aria-label="Remove bin" onClick={() => p.setBins((bs) => bs.filter((x) => x.key !== b.key))}>
                        ✕
                      </button>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {p.edit && (
        <div className="grn-put-foot">
          <button type="button" className="link" onClick={() => p.setBins((bs) => [...bs, { key: nextKey++, line: line.id, spot: "", qty: "", picked: "0" }])}>
            + Another bin
          </button>
          <button type="button" className="link grn-done" onClick={p.onDone}>
            Done
          </button>
        </div>
      )}
    </div>
  );
}

/** Everything that stopped Submit, each with "Go to line" (as on the goods receipt). */
function ProblemsPopup(props: { problems: Problem[]; onGo: (line: number) => void; onClose: () => void }) {
  return (
    <div className="popup-back" role="presentation">
      <div className="popup grn-check" role="dialog" aria-modal="true" aria-label="This note cannot be submitted yet">
        <h3>This note cannot be submitted yet ({props.problems.length})</h3>
        <table className="grid">
          <tbody>
            {props.problems.map((p) => (
              <tr key={p.text}>
                <td className="bad-note">✕</td>
                <td>{p.text}</td>
                <td>
                  <button type="button" className="link" onClick={() => props.onGo(p.line)}>
                    Go to line
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small">Lower the quantity, or pick another bin or batch that has the stock, then Submit again. Nothing has been submitted; the draft is kept.</p>
        <div className="popup-actions">
          <button type="button" onClick={props.onClose}>
            OK
          </button>
        </div>
      </div>
    </div>
  );
}
