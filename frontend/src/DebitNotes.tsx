import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { DocSide, keptDraft } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { longDate, money } from "./Companies";
import { announceSaved, closeThisTab, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { EntriesBox, Totals, type Entry } from "./PurchaseInvoices";
import { rateCalc, RateLinesTable, type RateLine } from "./RateLines";
import { useReturns } from "./Refresh";
import { useKept } from "./Keep";
import { Connections } from "./Connections";

/** Entry > Purchase > Debit Note (Sidharth, 2026-11-15, preview 75): goods sent back on a
 * Purchase Return, debited against the supplier's bill at the bill's rate and GST. Submit
 * debits the supplier, clears the returned goods from "Goods Received but Bills not
 * Received" and reverses the input GST. A note "Rate charged higher" (preview 78) takes a lower
 * agreed rate off goods billed and kept instead. Served by buying/debit_notes.py. */

type Line = RateLine & {
  return_line: number | null;
  return_number: string;
  item?: number;
};
type Due = { due_date: string; bill: string; less: string; now_due: string };
/** A charge debited back (preview 106): the bill's charge's share, or one added by hand. */
type Charge = {
  item: number;
  item_name?: string;
  sac?: string;
  bill_charge: number | null;
  bill_amount?: string | null;
  amount: string;
  gst_rate: string;
  in_stock_cost: boolean;
  cgst?: string;
  sgst?: string;
  igst?: string;
};
type ChargeItem = { id: number; name: string; sac: string; add_to_stock: string; gst_rate: string | null };
type ChargeDraft = { key: number; item: string; bill_charge: number | null; bill_amount: string | null; amount: string; gst_rate: string; in_stock_cost: boolean };
let nextKey = 1;
const draftOf = (c: Charge): ChargeDraft => ({ key: nextKey++, item: String(c.item), bill_charge: c.bill_charge, bill_amount: c.bill_amount ?? null, amount: String(c.amount), gst_rate: c.gst_rate, in_stock_cost: c.in_stock_cost });
type Note = {
  id: number;
  number: string;
  status: string;
  status_label: string;
  supplier: number;
  supplier_name: string;
  supplier_gstin: string;
  branch_name: string;
  invoice: number;
  invoice_number: string;
  bill_no: string;
  bill_date: string | null;
  note_date: string;
  reason: string;
  reason_label: string;
  supplier_note_no: string;
  supplier_note_date: string | null;
  interstate: boolean;
  taxable_total: string;
  cgst_total: string;
  sgst_total: string;
  igst_total: string;
  round_off: string;
  total: string;
  notes: string;
  cancel_reason: string;
  created_by_name: string;
  submitted_at: string | null;
  lines?: Line[];
  returns?: string[];
  dues_after?: Due[];
  entries?: Entry[];
  charges?: Charge[];
  charge_items?: ChargeItem[];
};
type DraftFrom = {
  invoice: number;
  invoice_number: string;
  bill_no: string;
  bill_date: string | null;
  supplier_name: string;
  interstate: boolean;
  reason?: string;
  lines: Line[];
  charges?: Charge[];
  charge_items?: ChargeItem[];
};
type InvoiceRow = { id: number; number: string; bill_no: string; bill_date: string | null; supplier_name: string };

const REASONS = [
  { value: "returned", label: "Goods returned" },
  { value: "rate", label: "Rate charged higher" },
];

const base = (companyId: number) => `#/companies/${companyId}/debit-notes`;
const showDate = (iso: string | null) => (iso ? longDate(iso) : "");
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const num = (v: string | undefined) => Number(v) || 0;
const r2 = (n: number) => Math.round(n * 100) / 100;
const pillClass = (status: string) => (status === "submitted" ? "pill on" : "pill");
const today = () => new Date().toISOString().slice(0, 10);
const invoiceLabel = (i: { number: string; bill_no: string; bill_date: string | null }) => `${i.number} · Bill ${i.bill_no}${i.bill_date ? ` of ${showDate(i.bill_date)}` : ""}`;
/** "Print ▾": the debit note as a PDF made on the server (buying/purchase_prints.py), in the
 * one print tab or downloaded; a new entry prints once it is saved. */
const pdf = (id: number, download = false) => openTab(`/api/v1/debit-notes/${id}/pdf/${download ? "?download=1" : ""}`);
const printItems = (id: number | null) => {
  const why = id ? undefined : "Save it first";
  return [
    { label: "Debit Note", onClick: () => id && pdf(id), disabled: !id, title: why },
    { label: "Download PDF", onClick: () => id && pdf(id, true), disabled: !id, title: why },
  ];
};

export function DebitNotesPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const can = (p: string) => session.permissions.includes(`purchase.${p}`);
  const form = hashParam("form");
  const view = Number(hashParam("view"));
  if (form && can("create")) return <NoteFormTab companyId={companyId} form={form} canSubmit={can("submit")} />;
  if (view > 0) return <NoteView companyId={companyId} id={view} can={can} />;
  return <NoteList companyId={companyId} canCreate={can("create")} />;
}

// The list ----------------------------------------------------------------------

const VIEWS = [
  { value: "submitted", label: "Submitted" },
  { value: "draft", label: "Drafts" },
  { value: "cancelled", label: "Cancelled" },
  { value: "all", label: "All" },
];
const COLUMNS: [key: string, label: string, text: (r: Note) => string, num?: boolean][] = [
  ["number", "DN No", (r) => r.number || "Draft"],
  ["date", "Date", (r) => `${shortDate(r.note_date)} ${showDate(r.note_date)}`],
  ["supplier", "Supplier", (r) => r.supplier_name],
  ["invoice", "Against Invoice", (r) => `${r.invoice_number} ${r.bill_no}`],
  ["reason", "Reason", (r) => r.reason_label],
  ["total", "Amount ₹", (r) => `${r.total} ${money(r.total)}`, true],
  ["status", "Status", (r) => r.status_label],
];

function NoteList({ companyId, canCreate }: { companyId: number; canCreate: boolean }) {
  const [view, setView] = useKept("DebitNotes.view", "submitted");
  const [rows, setRows] = useState<Note[]>([]);
  const [search, setSearch] = useKept<Record<string, string>>("DebitNotes.search", {});
  const [selectedId, setSelectedId] = useKept<number | null>("DebitNotes.selectedId", null);
  const [error, setError] = useState<unknown>("");
  const reload = useCallback(() => {
    api<Note[]>(`v1/companies/${companyId}/debit-notes/?view=${view}`).then(setRows, setError);
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("debit_note_saved", (c) => {
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
  const selected = rows.find((r) => r.id === selectedId) ?? null;
  const printing = usePrintMenu({ title: `Debit notes: ${VIEWS.find((v) => v.value === view)?.label ?? ""}`, scope: "" });
  const total = shown.reduce((sum, r) => sum + Number(r.total), 0);
  return (
    <section className="page">
      <PageHeader
        title="Debit Note"
        crumbs={[{ label: "Entry › Purchase", href: base(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "debit note" : "debit notes"}`}
        actions={
          <>
            {canCreate && (
              <button
                type="button"
                className="secondary"
                disabled={selected?.status !== "draft"}
                title={selected ? (selected.status === "draft" ? "" : "Only a draft can be changed") : "Click a draft debit note first"}
                onClick={() => selected && openTab(`${base(companyId)}?form=${selected.id}`)}
              >
                Edit
              </button>
            )}
            {canCreate && <button onClick={() => openTab(`${base(companyId)}?form=new`)}>New debit note</button>}
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
            {Object.values(search).some(Boolean) && (
              <button type="button" className="link" onClick={() => setSearch({})}>
                Clear searches
              </button>
            )}
          </div>
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
                    No debit notes match.
                  </td>
                </tr>
              )}
              {shown.map((r) => (
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
                  <td className="nowrap">{shortDate(r.note_date)}</td>
                  <td>{r.supplier_name}</td>
                  <td>
                    {r.invoice_number} <span className="small">Bill {r.bill_no}</span>
                  </td>
                  <td>{r.reason_label}</td>
                  <td className="num">{money(r.total)}</td>
                  <td>
                    <span className={pillClass(r.status)}>{r.status_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
            {shown.length > 1 && (
              <tfoot>
                <tr>
                  <td colSpan={5}>Total</td>
                  <td className="num">{money(String(r2(total)))}</td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
          {shown.length > 0 && (
            <p className="small no-print">Click a debit note to see it at the right (click it again to close the panel); double-click or press Enter to open it; "Close" there brings you back here.</p>
          )}
        </div>
        {selected && (
          <div className="side-col" aria-label="Debit note details">
            <SidePanel title={selected.number || "Draft debit note"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Supplier", selected.supplier_name],
                  ["Against Invoice", invoiceLabel({ number: selected.invoice_number, bill_no: selected.bill_no, bill_date: selected.bill_date })],
                  ["Date", showDate(selected.note_date)],
                  ["Amount", `₹${money(selected.total)}`],
                  ["Made By", selected.created_by_name],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => openTab(`${base(companyId)}?view=${selected.id}`)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => pdf(selected.id)}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="debit_note" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// The form ------------------------------------------------------------------------

function NoteFormTab({ companyId, form, canSubmit }: { companyId: number; form: string; canSubmit: boolean }) {
  const [note, setNote] = useState<Note | null>(null);
  const [from, setFrom] = useState<DraftFrom | null>(null);
  const [error, setError] = useState<unknown>("");
  const invoice = hashParam("invoice");
  const ret = hashParam("return");
  const rate = hashParam("reason") === "rate";
  useEffect(() => {
    if (form !== "new") {
      api<Note>(`v1/debit-notes/${Number(form)}/`).then(setNote, setError);
      return;
    }
    const q = invoice ? `invoice=${invoice}${rate ? "&reason=rate" : ""}` : ret ? `return=${ret}` : "";
    if (q) api<DraftFrom>(`v1/companies/${companyId}/debit-notes/draft-from/?${q}`).then(setFrom, setError);
  }, [companyId, form, invoice, ret, rate]);
  const title = form === "new" ? "New Debit Note" : "Edit Debit Note";
  const shell = (msg?: unknown) => (
    <section className="page">
      <PageHeader title={title} crumbs={[{ label: "Entry › Purchase › Debit Note", href: base(companyId) }]} />
      <ErrorNote error={msg} />
    </section>
  );
  if (error) return shell(error);
  if (form !== "new" && !note) return shell();
  if ((invoice || ret) && !from) return shell();
  if (note && note.status !== "draft") return shell("A submitted debit note cannot be changed. Cancel it and make a new one.");
  return <NoteForm companyId={companyId} title={title} note={note} from={from} canSubmit={canSubmit} />;
}

function NoteForm(props: { companyId: number; title: string; note: Note | null; from: DraftFrom | null; canSubmit: boolean }) {
  const { companyId, note } = props;
  const [from, setFrom] = useState<DraftFrom | null>(props.from);
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [invoice, setInvoice] = useState(String(note?.invoice ?? props.from?.invoice ?? ""));
  const [noteDate, setNoteDate] = useState(note?.note_date ?? today());
  const [reason, setReason] = useState(note?.reason ?? props.from?.reason ?? "returned");
  const isRate = reason === "rate";
  const [supNo, setSupNo] = useState(note?.supplier_note_no ?? "");
  const [supDate, setSupDate] = useState(note?.supplier_note_date ?? "");
  const [notes, setNotes] = useState(note?.notes ?? "");
  const [lines, setLines] = useState<Line[]>(note?.lines ?? props.from?.lines ?? []);
  const [charges, setCharges] = useState<ChargeDraft[]>(() => (note?.charges ?? props.from?.charges ?? []).map(draftOf));
  const chargeItems = from?.charge_items ?? note?.charge_items ?? [];
  const changeCharge = (key: number, patch: Partial<ChargeDraft>) => setCharges((cs) => cs.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  const [saved, setSaved] = useState<Note | null>(note);
  const [draftId, setDraftId] = useState<number | null>(note?.id ?? null);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState("");

  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  useEffect(() => {
    api<InvoiceRow[]>(`v1/companies/${companyId}/purchase-invoices/?view=submitted`).then(setInvoices, () => setInvoices([]));
  }, [companyId, visits]);

  const head = {
    supplier: from?.supplier_name ?? note?.supplier_name ?? "",
    number: from?.invoice_number ?? note?.invoice_number ?? "",
    bill_no: from?.bill_no ?? note?.bill_no ?? "",
    bill_date: from?.bill_date ?? note?.bill_date ?? null,
    interstate: from?.interstate ?? note?.interstate ?? false,
  };
  const loadLines = async (v: string, why: string) => {
    setInvoice(v);
    setError("");
    setLines([]);
    setCharges([]);
    if (!v) {
      setFrom(null);
      return;
    }
    try {
      const got = await api<DraftFrom>(`v1/companies/${companyId}/debit-notes/draft-from/?invoice=${v}${why === "rate" ? "&reason=rate" : ""}`);
      setFrom(got);
      setLines(got.lines);
      setCharges((got.charges ?? []).map(draftOf));
    } catch (err) {
      setError(err);
    }
  };
  const pickInvoice = (v: string) => loadLines(v, reason);
  const pickReason = (v: string) => {
    const why = v || "returned";
    setReason(why);
    if (why !== reason && invoice) loadLines(invoice, why);
  };
  const changeLine = (i: number, qty: string) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, qty } : l)));
  const changeRate = (i: number, patch: Partial<RateLine>) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, ...patch } : l)));

  // Totals as the server works them out: GST per line, the total to the rupee.
  const calc = lines.map((l) => {
    const taxable = r2(num(l.qty) * num(l.rate));
    const t = r2((taxable * num(l.gst_rate)) / 100);
    const g = head.interstate ? { c: 0, s: 0, i: t } : { c: r2(t / 2), s: r2(t - r2(t / 2)), i: 0 };
    return { taxable, ...g, amount: r2(taxable + t) };
  });
  const ccalc = (isRate ? [] : charges).map((c) => {
    const taxable = r2(num(c.amount));
    const t = r2((taxable * num(c.gst_rate)) / 100);
    return head.interstate ? { taxable, c: 0, s: 0, i: t } : { taxable, c: r2(t / 2), s: r2(t - r2(t / 2)), i: 0 };
  });
  const both = [...calc, ...ccalc];
  const rated = rateCalc(lines, "down", head.interstate);
  const taxable = isRate ? rated.taxable : r2(both.reduce((s, x) => s + x.taxable, 0));
  const cgst = isRate ? rated.cgst : r2(both.reduce((s, x) => s + x.c, 0));
  const sgst = isRate ? rated.sgst : r2(both.reduce((s, x) => s + x.s, 0));
  const igst = isRate ? rated.igst : r2(both.reduce((s, x) => s + x.i, 0));
  const exact = r2(taxable + cgst + sgst + igst);
  const total = Math.round(exact);
  const returns = [...new Set(lines.map((l) => l.return_number).filter(Boolean))];

  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      invoice: Number(invoice) || 0,
      note_date: noteDate || null,
      reason,
      supplier_note_no: supNo,
      supplier_note_date: supDate || null,
      notes,
      lines: isRate
        ? lines
            .filter((_, i) => rated.rows[i].taxable > 0)
            .map((l) => ({
              invoice_line: l.invoice_line,
              qty: l.qty,
              new_rate: l.new_rate,
            }))
        : lines
            .filter((l) => num(l.qty) > 0)
            .map((l) => ({
              invoice_line: l.invoice_line,
              return_line: l.return_line,
              qty: l.qty,
            })),
      charges: isRate
        ? []
        : charges
            .filter((c) => c.item && num(c.amount) > 0)
            .map((c) => ({ item: Number(c.item), bill_charge: c.bill_charge, amount: c.amount, gst_rate: c.gst_rate || "0", in_stock_cost: c.in_stock_cost })),
      submit,
    };
    try {
      const done = draftId
        ? await api<Note>(`v1/debit-notes/${draftId}/`, body, "PATCH")
        : await api<Note>(`v1/companies/${companyId}/debit-notes/`, body);
      announceSaved("debit_note_saved", { id: done.id, name: done.number || "Draft" });
      if (submit) {
        window.location.hash = `${base(companyId)}?view=${done.id}`;
        return;
      }
      if (!draftId) {
        setDraftId(done.id);
        window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${done.id}`);
      }
      setSaved(done);
      setSavedAt(new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }));
    } catch (err) {
      const kept = keptDraft(err);
      if (kept && !draftId) {
        setDraftId(kept);
        window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${kept}`);
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
  const invoiceOptions = [
    ...invoices,
    ...(head.number && !invoices.some((x) => String(x.id) === invoice) ? [{ id: Number(invoice), number: head.number, bill_no: head.bill_no, bill_date: head.bill_date, supplier_name: head.supplier }] : []),
  ].map((x) => ({ value: String(x.id), label: `${invoiceLabel(x)} · ${x.supplier_name}` }));

  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId && !note ? "Edit Debit Note" : props.title}
        sub={
          savedAt
            ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.`
            : head.number
              ? `${isRate ? "Rate charged higher · purchase invoice" : "From purchase invoice"} ${head.number} (Bill ${head.bill_no})`
              : undefined
        }
        crumbs={[{ label: "Entry › Purchase › Debit Note", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu label="Print" items={printItems(draftId)} />
            <button type="submit" form="dn-form" className={props.canSubmit ? "secondary" : undefined} disabled={busy}>
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
      <form id="dn-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{head.supplier || "Pick the purchase invoice"}</p>
            <p className="item-sub">
              <b>{note?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              {head.bill_no && <span className="tag">Bill {head.bill_no}</span>}
              {isRate && <span className="tag">Rate charged higher</span>}
              {returns.map((n) => (
                <span key={n} className="tag">
                  Return {n}
                </span>
              ))}
            </p>
          </div>
          <ErrorNote error={error} />
          <Fold title="Debit Note Details" open>
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <label>
                <span className="req">Supplier</span>
                <input value={head.supplier} readOnly placeholder="Comes from the invoice" />
              </label>
              <label>
                <span className="req">Debit Note Date</span>
                <input type="date" value={noteDate} onChange={(e) => setNoteDate(e.target.value)} />
              </label>
              <label>
                <span className="req">Against Invoice</span>
                <Combobox required value={invoice} onChange={pickInvoice} options={invoiceOptions} />
              </label>
              <label>
                <span className="req">Reason</span>
                <Combobox required value={reason} onChange={pickReason} options={REASONS} />
              </label>
              <label>
                Supplier's Credit Note No
                <input value={supNo} maxLength={40} onChange={(e) => setSupNo(e.target.value)} />
                <span className="small">If the supplier sends a credit note for it</span>
              </label>
              <label>
                Supplier's Credit Note Date
                <input type="date" value={supDate} onChange={(e) => setSupDate(e.target.value)} />
              </label>
            </div>
          </Fold>
          <Fold title="Items" open summary={lines.length ? `${lines.length} ${lines.length === 1 ? "line" : "lines"}` : ""}>
            {lines.length === 0 ? (
              <p className="small">Pick the purchase invoice, or open this from a Purchase Invoice's or Purchase Return's "Create ▾".</p>
            ) : isRate ? (
              <>
                <RateLinesTable lines={lines} way="down" interstate={head.interstate} onChange={changeRate} />
                <p className="small">
                  Every line of the bill is listed at the quantity billed and kept. Type the "Agreed Rate" on the lines whose price came down; lines left at the bill rate are not on the note. Qty can
                  be lowered when only part of it gets the new rate. GST % comes from the bill.
                </p>
              </>
            ) : (
              <>
                <div className="table-scroll">
                  <table className="grid po-lines">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Item</th>
                        <th>Return</th>
                        <th className="num">Returned, Not Debited</th>
                        <th className="num">Qty</th>
                        <th>Unit</th>
                        <th className="num">Bill Rate</th>
                        <th className="num">Taxable ₹</th>
                        <th className="num">GST %</th>
                        <th className="num">GST ₹</th>
                        <th className="num">Amount ₹</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l, i) => (
                        <tr key={`${l.invoice_line}-${l.return_line}`}>
                          <td>{i + 1}</td>
                          <td className="po-item">
                            <b>{l.item_name}</b>
                            <span className="small">
                              {l.item_number && `${l.item_number} · `}HSN {l.hsn} · billed {Number(l.billed_qty)} {l.unit_name} at ₹{money(l.rate)}
                            </span>
                          </td>
                          <td className="nowrap">{l.return_number}</td>
                          <td className="num">{Number(l.left_qty)}</td>
                          <td className="num">
                            <input className="num-in" inputMode="decimal" value={l.qty} onChange={(e) => changeLine(i, e.target.value)} aria-label="Debit quantity" />
                          </td>
                          <td>{l.unit_name}</td>
                          <td className="num">{money(l.rate)}</td>
                          <td className="num">{money(String(calc[i].taxable))}</td>
                          <td className="num">{Number(l.gst_rate)}</td>
                          <td className="num">{money(String(r2(calc[i].c + calc[i].s + calc[i].i)))}</td>
                          <td className="num">{money(String(calc[i].amount))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="small">Rate and GST come from the bill. Qty cannot be more than was returned and not yet debited.</p>
              </>
            )}
          </Fold>
          {!isRate && (
            <Fold title="Charges" open summary={charges.length ? `${charges.length}` : "None"}>
              <p className="small">
                Filled in from the bill: each charge's share for the goods sent back. Change an amount, remove a line, or add a charge (for example return freight we
                paid).
              </p>
              {charges.length > 0 && (
                <table className="grid">
                  <thead>
                    <tr>
                      <th>Charge</th>
                      <th>From the Bill</th>
                      <th className="num">Taxable ₹</th>
                      <th className="num">GST %</th>
                      <th>In Stock Cost</th>
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
                              changeCharge(c.key, { item: v, gst_rate: it?.gst_rate ?? c.gst_rate, in_stock_cost: c.bill_charge ? c.in_stock_cost : false });
                            }}
                            options={chargeItems.map((x) => ({ value: String(x.id), label: x.name }))}
                            ariaLabel="Charge"
                          />
                        </td>
                        <td className="small">{c.bill_charge ? `₹${money(c.bill_amount ?? "0")} on the bill · share for the goods sent back` : "Added by hand"}</td>
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
              <button
                type="button"
                className="link"
                onClick={() => setCharges([...charges, { key: nextKey++, item: "", bill_charge: null, bill_amount: null, amount: "", gst_rate: "", in_stock_cost: false }])}
              >
                Add charge
              </button>
            </Fold>
          )}
          <Fold title="Totals" open summary={`₹${money(String(total))}`}>
            <Totals taxable={taxable} cgst={cgst} sgst={sgst} igst={igst} roundOff={r2(total - exact)} total={total} />
          </Fold>
          {saved && (
            <EntriesBox entries={saved.entries ?? []} dues={[]} draft>
              {isRate && <p className="small">No quantity moves: only the value of the stock still on hand changes.</p>}
            </EntriesBox>
          )}
          {saved && <DuesAfter dues={saved.dues_after ?? []} />}
          <Fold title="Notes" open={!!notes}>
            <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Notes" />
          </Fold>
        </div>
        <DocSide type="debit_note" id={draftId} />
      </form>
    </section>
  );
}

/** "Bill Due After This Note": the bill's due dates less its debit notes, latest due first. */
function DuesAfter({ dues }: { dues: Due[] }) {
  if (!dues.length) return null;
  return (
    <Fold title="Bill Due After This Note" open>
      <table className="grid totals-box">
        <thead>
          <tr>
            <th>Due On</th>
            <th className="num">Bill ₹</th>
            <th className="num">Less Debit Notes ₹</th>
            <th className="num">Now Due ₹</th>
          </tr>
        </thead>
        <tbody>
          {dues.map((d) => (
            <tr key={d.due_date + d.bill}>
              <td className="nowrap">{shortDate(d.due_date)}</td>
              <td className="num">{money(d.bill)}</td>
              <td className="num">{num(d.less) ? money(d.less) : ""}</td>
              <td className="num">{money(d.now_due)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Fold>
  );
}

// The view ------------------------------------------------------------------------

function NoteView({ companyId, id, can }: { companyId: number; id: number; can: (p: string) => boolean }) {
  const [note, setNote] = useState<Note | null>(null);
  const [error, setError] = useState<unknown>("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const reload = useCallback(() => {
    api<Note>(`v1/debit-notes/${id}/`).then(setNote, setError);
  }, [id]);
  useEffect(reload, [reload]);
  useCreated("debit_note_saved", (c) => {
    if (c.id === id) reload();
  });
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const cancel = async () => {
    setError("");
    try {
      const done = await api<Note>(`v1/debit-notes/${id}/cancel/`, { reason });
      setNote(done);
      setCancelling(false);
      announceSaved("debit_note_saved", { id, name: done.number || "Draft" });
    } catch (err) {
      setError(err);
    }
  };
  if (!note)
    return (
      <section className="page">
        <PageHeader title="Debit Note" crumbs={[{ label: "Entry › Purchase › Debit Note", href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const draft = note.status === "draft";
  return (
    <section className="page">
      <PageHeader
        title={note.number ? `Debit Note ${note.number}` : "Debit Note (draft)"}
        sub={
          note.number && note.submitted_at
            ? `Submitted as ${note.number} on ${showDate(note.submitted_at.slice(0, 10))} at ${new Date(note.submitted_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`
            : undefined
        }
        crumbs={[{ label: "Entry › Purchase › Debit Note", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {draft && can("create") && (
              <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?form=${note.id}`)}>
                Edit
              </button>
            )}
            {can("cancel") && note.status !== "cancelled" && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel debit note
              </button>
            )}
            <ActionsMenu label="Print" items={printItems(id)} />
            {draft && can("create") && (
              <button type="button" onClick={() => openTab(`${base(companyId)}?form=${note.id}`)}>
                Open to Submit
              </button>
            )}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{note.supplier_name}</p>
            <p className="item-sub">
              <b>{note.number || "Number given on Submit"}</b>
              <span className={pillClass(note.status)}>{note.status_label}</span>
              <span className="tag">Bill {note.bill_no}</span>
              {note.reason === "rate" && <span className="tag">Rate charged higher</span>}
              {(note.returns ?? []).map((n) => (
                <span key={n} className="tag">
                  Return {n}
                </span>
              ))}
            </p>
          </div>
          {note.status === "cancelled" && <p className="use-note">Cancelled: {note.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this debit note cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Made against the wrong bill" />
              </label>
              <p className="small">The entries are reversed and the returned goods show as not debited again.</p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep the debit note
                </button>
                <button type="button" className="link danger" onClick={cancel}>
                  Cancel debit note
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="Debit Note Details" open>
            <dl className="kv">
              {(
                [
                  ["Supplier", note.supplier_name + (note.supplier_gstin ? ` · ${note.supplier_gstin}` : "")],
                  ["Debit Note Date", showDate(note.note_date)],
                  ["Against Invoice", invoiceLabel({ number: note.invoice_number, bill_no: note.bill_no, bill_date: note.bill_date })],
                  ["Reason", note.reason_label],
                  ["Supplier's Credit Note No", note.supplier_note_no],
                  ["Supplier's Credit Note Date", showDate(note.supplier_note_date)],
                  ["Branch", note.branch_name],
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
          <Fold title="Items" open>
            {note.reason === "rate" ? (
              <RateLinesTable lines={note.lines ?? []} way="down" interstate={note.interstate} />
            ) : (
              <div className="table-scroll">
                <table className="grid po-lines">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item</th>
                      <th>Return</th>
                      <th className="num">Qty</th>
                      <th>Unit</th>
                      <th className="num">Bill Rate</th>
                      <th className="num">Taxable ₹</th>
                      <th className="num">GST %</th>
                      <th className="num">GST ₹</th>
                      <th className="num">Amount ₹</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(note.lines ?? []).map((l, i) => (
                      <tr key={l.id ?? i}>
                        <td>{i + 1}</td>
                        <td className="po-item">
                          <b>{l.item_name}</b>
                          <span className="small">{l.item_number && `${l.item_number} · `}HSN {l.hsn}</span>
                        </td>
                        <td className="nowrap">{l.return_number}</td>
                        <td className="num">{Number(l.qty)}</td>
                        <td>{l.unit_name}</td>
                        <td className="num">{money(l.rate)}</td>
                        <td className="num">{money(l.taxable ?? "0")}</td>
                        <td className="num">{Number(l.gst_rate)}</td>
                        <td className="num">{money(String(r2(num(l.cgst) + num(l.sgst) + num(l.igst))))}</td>
                        <td className="num">{money(l.amount ?? "0")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Fold>
          {(note.charges ?? []).length > 0 && (
            <Fold title="Charges" open>
              <table className="grid">
                <thead>
                  <tr>
                    <th>Charge</th>
                    <th>SAC</th>
                    <th>From the Bill</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th>In Stock Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {(note.charges ?? []).map((c, i) => (
                    <tr key={i}>
                      <td>{c.item_name}</td>
                      <td>{c.sac}</td>
                      <td className="small">{c.bill_charge ? `Share of ₹${money(c.bill_amount ?? "0")} on the bill` : "Added by hand"}</td>
                      <td className="num">{money(c.amount)}</td>
                      <td className="num">{c.gst_rate}</td>
                      <td>{c.in_stock_cost ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Fold>
          )}
          <Fold title="Totals" open summary={`₹${money(note.total)}`}>
            <Totals taxable={note.taxable_total} cgst={note.cgst_total} sgst={note.sgst_total} igst={note.igst_total} roundOff={note.round_off} total={note.total} />
          </Fold>
          <EntriesBox entries={note.entries ?? []} dues={[]} draft={draft} />
          {note.status !== "cancelled" && <DuesAfter dues={note.dues_after ?? []} />}
          {note.notes && (
            <Fold title="Notes" open>
              <p className="pre">{note.notes}</p>
            </Fold>
          )}
          <Connections companyId={companyId} kind="debit_note" id={note.id} stamp={note.status} />
        </div>
        <DocSide type="debit_note" id={note.id} onChange={() => setFiles((n) => n + 1)}>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="debit_note" id={note.id} stamp={JSON.stringify(note) + files} />
          </SidePanel>
        </DocSide>
      </div>
    </section>
  );
}
