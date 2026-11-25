import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useTransporterSearch } from "./Shipments";
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
import { EntriesBox, type Entry } from "./PurchaseInvoices";
import { useReturns } from "./Refresh";
import { useKept } from "./Keep";

/** Entry > Purchase > Purchase Return (Sidharth, 2026-11-15, preview 74): goods sent back
 * to the supplier against a goods receipt. Submit takes them out of the bin they were put
 * in and out of "Goods Received but Bills not Received"; the supplier's account is touched
 * only by the Debit Note made once the bill is in. Served by buying/returns.py. */

type Line = {
  id?: number;
  receipt_line: number;
  item: number;
  item_name: string;
  hsn: string;
  unit_name: string;
  location: number;
  location_name: string;
  batch: number | null;
  batch_number: string;
  on_hand?: string;
  received_qty: string;
  returned_before: string;
  returnable?: string;
  receipt_rate: string;
  receipt_value: string;
  billed: boolean;
  qty: string;
  value?: string;
  debited_qty?: string;
};
type Return = {
  id: number;
  number: string;
  status: string;
  status_label: string;
  supplier: number;
  supplier_name: string;
  branch_name: string;
  receipt: number;
  receipt_number: string;
  receipt_date: string;
  challan_no: string;
  return_date: string;
  reason: string;
  reason_label: string;
  transporter: number | null;
  transporter_name: string;
  lr_no: string;
  vehicle_no: string;
  eway_bill_no: string;
  notes: string;
  value: string;
  cancel_reason: string;
  created_by_name: string;
  submitted_at: string | null;
  lines?: Line[];
  to_debit?: boolean;
  entries?: Entry[];
};
type DraftFrom = {
  receipt: number;
  receipt_number: string;
  receipt_date: string;
  challan_no: string;
  supplier_name: string;
  branch_name: string;
  transporter: number | null;
  vehicle_no: string;
  lines: Line[];
};
type Returnable = { id: number; number: string; receipt_date: string; supplier_name: string; challan_no: string };

const REASONS = [
  { value: "damaged", label: "Damaged in transit" },
  { value: "short", label: "Short supplied" },
  { value: "quality", label: "Quality rejected" },
  { value: "wrong", label: "Wrong item" },
  { value: "other", label: "Other" },
];

const base = (companyId: number) => `#/companies/${companyId}/purchase-returns`;
const showDate = (iso: string | null) => (iso ? longDate(iso) : "");
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const num = (v: string | undefined) => Number(v) || 0;
const r2 = (n: number) => Math.round(n * 100) / 100;
const pillClass = (status: string) => (status === "submitted" ? "pill on" : "pill");
const today = () => new Date().toISOString().slice(0, 10);
const placeKey = (l: { receipt_line: number; location: number; batch: number | null }) => `${l.receipt_line}-${l.location}-${l.batch ?? ""}`;
const receiptLabel = (r: { number: string; receipt_date: string; challan_no: string }) =>
  [r.number, showDate(r.receipt_date), r.challan_no ? `Challan ${r.challan_no}` : ""].filter(Boolean).join(" · ");
/** "Print ▾": the return challan as this page prints, and a PDF through the browser's own "Save as PDF". */
const printItems = [
  { label: "Return Challan", onClick: () => window.print() },
  { label: "Download PDF", onClick: () => window.print() },
];

export function PurchaseReturnsPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  // Goods go back through the stores or purchase: either role's right will do (as for receipts).
  const can = (p: string) => session.permissions.includes(`purchase.${p}`) || session.permissions.includes(`stock.${p}`);
  const form = hashParam("form");
  const view = Number(hashParam("view"));
  if (form && can("create")) return <ReturnFormTab companyId={companyId} form={form} canSubmit={can("submit")} />;
  if (view > 0) return <ReturnView companyId={companyId} id={view} can={can} canDebit={session.permissions.includes("purchase.create")} />;
  return <ReturnList companyId={companyId} canCreate={can("create")} />;
}

// The list ----------------------------------------------------------------------

const VIEWS = [
  { value: "submitted", label: "Submitted" },
  { value: "draft", label: "Drafts" },
  { value: "cancelled", label: "Cancelled" },
  { value: "all", label: "All" },
];
const COLUMNS: [key: string, label: string, text: (r: Return) => string, num?: boolean][] = [
  ["number", "Return No", (r) => r.number || "Draft"],
  ["date", "Return Date", (r) => `${shortDate(r.return_date)} ${showDate(r.return_date)}`],
  ["supplier", "Supplier", (r) => r.supplier_name],
  ["receipt", "Goods Receipt", (r) => r.receipt_number],
  ["reason", "Reason", (r) => r.reason_label],
  ["value", "Value ₹", (r) => `${r.value} ${money(r.value)}`, true],
  ["status", "Status", (r) => r.status_label],
];

function ReturnList({ companyId, canCreate }: { companyId: number; canCreate: boolean }) {
  const [view, setView] = useKept("PurchaseReturns.view", "submitted");
  const [rows, setRows] = useState<Return[]>([]);
  const [search, setSearch] = useKept<Record<string, string>>("PurchaseReturns.search", {});
  const [selectedId, setSelectedId] = useKept<number | null>("PurchaseReturns.selectedId", null);
  const [error, setError] = useState<unknown>("");
  const reload = useCallback(() => {
    api<Return[]>(`v1/companies/${companyId}/purchase-returns/?view=${view}`).then(setRows, setError);
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("purchase_return_saved", (c) => {
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
  const printing = usePrintMenu({ title: `Purchase returns: ${VIEWS.find((v) => v.value === view)?.label ?? ""}`, scope: "" });
  const total = shown.reduce((sum, r) => sum + Number(r.value), 0);
  return (
    <section className="page">
      <PageHeader
        title="Purchase Return"
        crumbs={[{ label: "Entry › Purchase", href: base(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "return" : "returns"}`}
        actions={
          <>
            {canCreate && (
              <button
                type="button"
                className="secondary"
                disabled={selected?.status !== "draft"}
                title={selected ? (selected.status === "draft" ? "" : "Only a draft can be changed") : "Click a draft return first"}
                onClick={() => selected && openTab(`${base(companyId)}?form=${selected.id}`)}
              >
                Edit
              </button>
            )}
            {canCreate && <button onClick={() => openTab(`${base(companyId)}?form=new`)}>New purchase return</button>}
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
                    No purchase returns match.
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
                  <td className="nowrap">{shortDate(r.return_date)}</td>
                  <td>{r.supplier_name}</td>
                  <td className="nowrap">{r.receipt_number}</td>
                  <td>{r.reason_label}</td>
                  <td className="num">{money(r.value)}</td>
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
            <p className="small no-print">Click a return to see it at the right (click it again to close the panel); double-click or press Enter to open it; "Close" there brings you back here.</p>
          )}
        </div>
        {selected && (
          <div className="side-col" aria-label="Return details">
            <SidePanel title={selected.number || "Draft return"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Supplier", selected.supplier_name],
                  ["Goods Receipt", selected.receipt_number],
                  ["Return Date", showDate(selected.return_date)],
                  ["Reason", selected.reason_label],
                  ["Value", `₹${money(selected.value)}`],
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
              <ChangeLog company={companyId} type="purchase_return" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// The form ------------------------------------------------------------------------

function ReturnFormTab({ companyId, form, canSubmit }: { companyId: number; form: string; canSubmit: boolean }) {
  const [ret, setRet] = useState<Return | null>(null);
  const [from, setFrom] = useState<DraftFrom | null>(null);
  const [error, setError] = useState<unknown>("");
  const receipt = hashParam("receipt");
  useEffect(() => {
    if (form !== "new") {
      api<Return>(`v1/purchase-returns/${Number(form)}/`).then((r) => {
        setRet(r);
        return api<DraftFrom>(`v1/companies/${companyId}/purchase-returns/draft-from/?receipt=${r.receipt}`).then(setFrom);
      }, setError).catch(setError);
      return;
    }
    if (receipt) api<DraftFrom>(`v1/companies/${companyId}/purchase-returns/draft-from/?receipt=${receipt}`).then(setFrom, setError);
  }, [companyId, form, receipt]);
  const title = form === "new" ? "New Purchase Return" : "Edit Purchase Return";
  const shell = (note?: unknown) => (
    <section className="page">
      <PageHeader title={title} crumbs={[{ label: "Entry › Purchase › Purchase Return", href: base(companyId) }]} />
      <ErrorNote error={note} />
    </section>
  );
  if (error) return shell(error);
  if (form !== "new" && (!ret || !from)) return shell();
  if (receipt && !from) return shell();
  if (ret && ret.status !== "draft") return shell("A submitted return cannot be changed. Cancel it and make a new one.");
  return <ReturnForm companyId={companyId} title={title} ret={ret} from={from} canSubmit={canSubmit} />;
}

/** The receipt's rows (one per bin and batch), with the draft's own quantities filled in. */
function mergeLines(from: DraftFrom | null, ret: Return | null): Line[] {
  const saved = new Map((ret?.lines ?? []).map((l) => [placeKey(l), l.qty]));
  return (from?.lines ?? []).map((l) => ({ ...l, qty: saved.get(placeKey(l)) ?? "0" }));
}

function ReturnForm(props: { companyId: number; title: string; ret: Return | null; from: DraftFrom | null; canSubmit: boolean }) {
  const { companyId, ret } = props;
  const [from, setFrom] = useState<DraftFrom | null>(props.from);
  const [receipts, setReceipts] = useState<Returnable[]>([]);
  const [receipt, setReceipt] = useState(String(ret?.receipt ?? props.from?.receipt ?? ""));
  const [returnDate, setReturnDate] = useState(ret?.return_date ?? today());
  const [reason, setReason] = useState(ret?.reason ?? "damaged");
  const [transporter, setTransporter] = useState(String(ret?.transporter ?? props.from?.transporter ?? ""));
  // Transporters come from the server as the person types (useTransporterSearch), never all at once.
  const { transporters, onType: findTransporters } = useTransporterSearch(companyId, [transporter]);
  const [lrNo, setLrNo] = useState(ret?.lr_no ?? "");
  const [vehicleNo, setVehicleNo] = useState(ret?.vehicle_no ?? props.from?.vehicle_no ?? "");
  const [ewayNo, setEwayNo] = useState(ret?.eway_bill_no ?? "");
  const [notes, setNotes] = useState(ret?.notes ?? "");
  const [lines, setLines] = useState<Line[]>(() => mergeLines(props.from, ret));
  const [saved, setSaved] = useState<Return | null>(ret);
  const [draftId, setDraftId] = useState<number | null>(ret?.id ?? null);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState("");

  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  useEffect(() => {
    api<Returnable[]>(`v1/companies/${companyId}/purchase-returns/returnable/`).then(setReceipts, () => setReceipts([]));
  }, [companyId, visits]);

  const pickReceipt = async (v: string) => {
    setReceipt(v);
    setError("");
    if (!v) {
      setFrom(null);
      setLines([]);
      return;
    }
    try {
      const got = await api<DraftFrom>(`v1/companies/${companyId}/purchase-returns/draft-from/?receipt=${v}`);
      setFrom(got);
      setLines(got.lines);
      setTransporter(String(got.transporter ?? ""));
      setVehicleNo(got.vehicle_no);
    } catch (err) {
      setError(err);
    }
  };
  const changeLine = (i: number, qty: string) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, qty } : l)));
  // At the receipt's own value per unit, as the server works it out.
  const value = (l: Line) => (num(l.received_qty) ? r2((num(l.qty) * num(l.receipt_value)) / num(l.received_qty)) : 0);
  const total = r2(lines.reduce((s, l) => s + value(l), 0));

  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      receipt: Number(receipt) || 0,
      return_date: returnDate || null,
      reason,
      transporter: transporter ? Number(transporter) : null,
      lr_no: lrNo,
      vehicle_no: vehicleNo,
      eway_bill_no: ewayNo,
      notes,
      lines: lines.filter((l) => num(l.qty) > 0).map((l) => ({ receipt_line: l.receipt_line, location: l.location, batch: l.batch, qty: l.qty })),
      submit,
    };
    try {
      const done = draftId
        ? await api<Return>(`v1/purchase-returns/${draftId}/`, body, "PATCH")
        : await api<Return>(`v1/companies/${companyId}/purchase-returns/`, body);
      announceSaved("purchase_return_saved", { id: done.id, name: done.number || "Draft" });
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
  const receiptOptions = [
    ...receipts,
    ...(from && !receipts.some((r) => r.id === from.receipt) ? [{ id: from.receipt, number: from.receipt_number, receipt_date: from.receipt_date, challan_no: from.challan_no, supplier_name: from.supplier_name }] : []),
  ].map((r) => ({ value: String(r.id), label: `${receiptLabel(r)} · ${r.supplier_name}` }));

  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId && !ret ? "Edit Purchase Return" : props.title}
        sub={savedAt ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.` : from ? `From goods receipt ${from.receipt_number}` : undefined}
        crumbs={[{ label: "Entry › Purchase › Purchase Return", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu label="Print" items={printItems} />
            <button type="submit" form="pret-form" className={props.canSubmit ? "secondary" : undefined} disabled={busy}>
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
      <form id="pret-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{from?.supplier_name ?? "Pick a goods receipt"}</p>
            <p className="item-sub">
              <b>{ret?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              {from && <span className="tag">{from.branch_name}</span>}
              {from && <span className="tag">Against {from.receipt_number}</span>}
            </p>
          </div>
          <ErrorNote error={error} />
          <Fold title="Return Details" open>
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <label>
                <span className="req">Supplier</span>
                <input value={from?.supplier_name ?? ""} readOnly placeholder="Comes from the goods receipt" />
              </label>
              <label>
                <span className="req">Return Date</span>
                <input type="date" value={returnDate} onChange={(e) => setReturnDate(e.target.value)} />
              </label>
              <label>
                <span className="req">Goods Receipt</span>
                <Combobox required value={receipt} onChange={pickReceipt} options={receiptOptions} />
              </label>
              <label>
                <span className="req">Reason</span>
                <Combobox required value={reason} onChange={(v) => setReason(v || "damaged")} options={REASONS} />
              </label>
              <label>
                Transporter
                <Combobox value={transporter} onChange={setTransporter} empty="By Supplier" onType={findTransporters} options={transporters.filter((t) => t.is_active || String(t.id) === transporter).map((t) => ({ value: String(t.id), label: t.name }))} />
              </label>
              <label>
                Vehicle No
                <input value={vehicleNo} maxLength={20} onChange={(e) => setVehicleNo(e.target.value)} />
              </label>
              <label>
                LR / Docket No
                <input value={lrNo} maxLength={40} onChange={(e) => setLrNo(e.target.value)} />
              </label>
              <label>
                E-way Bill No
                <input value={ewayNo} maxLength={20} onChange={(e) => setEwayNo(e.target.value)} />
                <span className="small">Needed only above ₹50,000 of goods</span>
              </label>
            </div>
          </Fold>
          <Fold title="Items Going Back" open summary={total ? `₹${money(String(total))}` : ""}>
            {lines.length === 0 ? (
              <p className="small">Pick the goods receipt, or open this from a Goods Receipt's "Create ▾".</p>
            ) : (
              <>
                <div className="table-scroll">
                  <table className="grid po-lines">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Item</th>
                        <th>Batch</th>
                        <th>From Bin</th>
                        <th className="num">Received</th>
                        <th className="num">Returned Before</th>
                        <th className="num">Return Qty</th>
                        <th>Unit</th>
                        <th className="num">Receipt Rate</th>
                        <th className="num">Value ₹</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l, i) => (
                        <tr key={placeKey(l)}>
                          <td>{i + 1}</td>
                          <td className="po-item">
                            <b>{l.item_name}</b>
                            <span className="small">
                              HSN {l.hsn}
                              {num(l.qty) > 0 && !l.billed && " · not billed yet: the bill will need a Debit Note for what goes back"}
                            </span>
                          </td>
                          <td>{l.batch_number || "—"}</td>
                          <td>
                            {l.location_name}
                            {l.on_hand !== undefined && <span className="small"> ({Number(l.on_hand)} there now)</span>}
                          </td>
                          <td className="num">{Number(l.received_qty)}</td>
                          <td className="num">{Number(l.returned_before)}</td>
                          <td className="num">
                            <input className="num-in" inputMode="decimal" value={l.qty} onChange={(e) => changeLine(i, e.target.value)} aria-label="Return quantity" />
                          </td>
                          <td>{l.unit_name}</td>
                          <td className="num">{money(l.receipt_rate)}</td>
                          <td className="num">{money(String(value(l)))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="small">Every line of the receipt is listed; type the quantity going back. It cannot be more than what is still in that bin.</p>
              </>
            )}
          </Fold>
          {saved && (
            <EntriesBox entries={saved.entries ?? []} dues={[]} draft>
              <p className="small">
                The supplier's account is touched only by the Debit Note, which also reverses the input GST. Until then the ₹{money(saved.value)} waits in "Goods
                Received but Bills not Received".
              </p>
            </EntriesBox>
          )}
          <Fold title="Notes" open={!!notes}>
            <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Notes" />
          </Fold>
        </div>
        <DocSide type="purchase_return" id={draftId} />
      </form>
    </section>
  );
}

// The view ------------------------------------------------------------------------

function ReturnView({ companyId, id, can, canDebit }: { companyId: number; id: number; can: (p: string) => boolean; canDebit: boolean }) {
  const [ret, setRet] = useState<Return | null>(null);
  const [error, setError] = useState<unknown>("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const reload = useCallback(() => {
    api<Return>(`v1/purchase-returns/${id}/`).then(setRet, setError);
  }, [id]);
  useEffect(reload, [reload]);
  useCreated("purchase_return_saved", (c) => {
    if (c.id === id) reload();
  });
  useCreated("debit_note_saved", reload);
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const cancel = async () => {
    setError("");
    try {
      const done = await api<Return>(`v1/purchase-returns/${id}/cancel/`, { reason });
      setRet(done);
      setCancelling(false);
      announceSaved("purchase_return_saved", { id, name: done.number || "Draft" });
    } catch (err) {
      setError(err);
    }
  };
  if (!ret)
    return (
      <section className="page">
        <PageHeader title="Purchase Return" crumbs={[{ label: "Entry › Purchase › Purchase Return", href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const draft = ret.status === "draft";
  const lines = ret.lines ?? [];
  const notBilled = lines.some((l) => !l.billed && num(l.qty) > num(l.debited_qty));
  return (
    <section className="page">
      <PageHeader
        title={ret.number ? `Purchase Return ${ret.number}` : "Purchase Return (draft)"}
        sub={
          ret.number && ret.submitted_at
            ? `Submitted as ${ret.number} on ${showDate(ret.submitted_at.slice(0, 10))} at ${new Date(ret.submitted_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`
            : undefined
        }
        crumbs={[{ label: "Entry › Purchase › Purchase Return", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {draft && can("create") && (
              <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?form=${ret.id}`)}>
                Edit
              </button>
            )}
            {can("cancel") && ret.status !== "cancelled" && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel return
              </button>
            )}
            <ActionsMenu label="Print" items={printItems} />
            {draft && can("create") && (
              <button type="button" onClick={() => openTab(`${base(companyId)}?form=${ret.id}`)}>
                Open to Submit
              </button>
            )}
            {ret.status === "submitted" && (
              <ActionsMenu
                label="Create"
                main
                items={[
                  {
                    label: "Debit Note",
                    disabled: !ret.to_debit || !canDebit,
                    onClick: () => openTab(`#/companies/${companyId}/debit-notes?form=new&return=${ret.id}`),
                  },
                ]}
                note={
                  !canDebit
                    ? "Your role cannot make debit notes"
                    : ret.to_debit
                      ? undefined
                      : notBilled
                        ? "Once the supplier's bill is entered. If the bill leaves these goods out, no Debit Note is needed."
                        : "Everything sent back is already debited"
                }
              />
            )}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{ret.supplier_name}</p>
            <p className="item-sub">
              <b>{ret.number || "Number given on Submit"}</b>
              <span className={pillClass(ret.status)}>{ret.status_label}</span>
              <span className="tag">{ret.branch_name}</span>
              <span className="tag">Against {ret.receipt_number}</span>
            </p>
          </div>
          {ret.status === "cancelled" && <p className="use-note">Cancelled: {ret.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this return cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. The supplier took the goods back as they were" />
              </label>
              <p className="small">The goods come back into the bins they left and the entries are reversed.</p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep the return
                </button>
                <button type="button" className="link danger" onClick={cancel}>
                  Cancel return
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="Return Details" open>
            <dl className="kv">
              {(
                [
                  ["Supplier", ret.supplier_name],
                  ["Return Date", showDate(ret.return_date)],
                  ["Goods Receipt", receiptLabel({ number: ret.receipt_number, receipt_date: ret.receipt_date, challan_no: ret.challan_no })],
                  ["Reason", ret.reason_label],
                  ["Transporter", ret.transporter_name],
                  ["Vehicle No", ret.vehicle_no],
                  ["LR / Docket No", ret.lr_no],
                  ["E-way Bill No", ret.eway_bill_no],
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
          <Fold title="Items Going Back" open summary={`₹${money(ret.value)}`}>
            <div className="table-scroll">
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th>Batch</th>
                    <th>From Bin</th>
                    <th className="num">Qty</th>
                    <th>Unit</th>
                    <th className="num">Receipt Rate</th>
                    <th className="num">Value ₹</th>
                    <th className="num">Debited</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l, i) => (
                    <tr key={l.id ?? i}>
                      <td>{i + 1}</td>
                      <td className="po-item">
                        <b>{l.item_name}</b>
                        <span className="small">HSN {l.hsn}</span>
                      </td>
                      <td>{l.batch_number || "—"}</td>
                      <td>{l.location_name}</td>
                      <td className="num">{Number(l.qty)}</td>
                      <td>{l.unit_name}</td>
                      <td className="num">{money(l.receipt_rate)}</td>
                      <td className="num">{money(l.value ?? "0")}</td>
                      <td className="num">{Number(l.debited_qty ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Fold>
          <EntriesBox entries={ret.entries ?? []} dues={[]} draft={draft} />
          {ret.notes && (
            <Fold title="Notes" open>
              <p className="pre">{ret.notes}</p>
            </Fold>
          )}
        </div>
        <DocSide type="purchase_return" id={ret.id} onChange={() => setFiles((n) => n + 1)}>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="purchase_return" id={ret.id} stamp={JSON.stringify(ret) + files} />
          </SidePanel>
        </DocSide>
      </div>
    </section>
  );
}
