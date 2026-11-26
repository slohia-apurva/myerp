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
import { LedgerPosting } from "./LedgerPosting";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useKept } from "./Keep";

/** Entry › Accounts › TDS Adjustment (Sidharth, 2026-11-19, preview 95c): TDS missed on submitted bills
 * is deducted now (Dr supplier, Cr "TDS Payable <section>"), or TDS deducted in excess is given back.
 * Made from the TDS Check (TdsCheck.tsx); each line's amount is the gap the check finds, never typed.
 * Bills in a quarter whose TDS return is filed cannot be adjusted. Served by buying/tds_check.py. */

type Line = {
  invoice: number;
  number: string;
  posting_date: string;
  bill_no: string;
  base: string;
  rate: string;
  due: string;
  deducted: string;
  amount: string;
  months: number;
  interest: string;
};
type Adjustment = {
  id: number;
  number: string;
  status: string;
  status_label: string;
  supplier: number;
  supplier_name: string;
  branch_name: string;
  adj_date: string;
  section: string;
  section_shown: string;
  kind_label: string;
  remarks: string;
  total: string;
  interest: string;
  late_interest: string;
  cancel_reason: string;
  created_by_name: string;
  submitted_at: string | null;
  lines?: Line[];
};
type DraftFrom = { supplier: number; supplier_name: string; section: string; invoices: number[] };
type Preview = { lines: Line[]; total: string; interest: string; late_interest: string };

const base = (companyId: number) => `#/companies/${companyId}/tds-adjustments`;
const showDate = (iso: string | null) => (iso ? longDate(iso.slice(0, 10)) : "");
const dmy = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const today = () => new Date().toISOString().slice(0, 10);
const signed = (v: string) => (Number(v) < 0 ? `(${money(-Number(v))})` : money(v));
const pillClass = (status: string) => (status === "submitted" ? "pill on" : "pill");
const kindOf = (total: number) => (total > 0 ? "Deduct short TDS" : total < 0 ? "Give back excess TDS" : "Set section only");
/** "Print ▾": the adjustment as a PDF made on the server (buying/purchase_prints.py), in the
 * one print tab or downloaded; a new entry prints once it is saved. */
const pdf = (id: number, download = false) => openTab(`/api/v1/tds-adjustments/${id}/pdf/${download ? "?download=1" : ""}`);
const printItems = (id: number | null) => {
  const why = id ? undefined : "Save it first";
  return [
    { label: "TDS Adjustment", onClick: () => id && pdf(id), disabled: !id, title: why },
    { label: "Download PDF", onClick: () => id && pdf(id, true), disabled: !id, title: why },
  ];
};

export function TdsAdjustmentsPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const can = (p: string) => session.user.is_owner || session.permissions.includes(`accounts.${p}`);
  const form = hashParam("form");
  const view = Number(hashParam("view"));
  if (form && can("create")) return <FormTab companyId={companyId} form={form} canSubmit={can("submit")} />;
  if (view > 0) return <AdjustmentView companyId={companyId} id={view} can={can} />;
  return <AdjustmentList companyId={companyId} />;
}

// The list ------------------------------------------------------------------------------------

const VIEWS = [
  { value: "submitted", label: "Submitted" },
  { value: "draft", label: "Drafts" },
  { value: "cancelled", label: "Cancelled" },
  { value: "all", label: "All" },
];
const COLUMNS: [key: string, label: string, text: (r: Adjustment) => string, num?: boolean][] = [
  ["number", "Adjustment No", (r) => r.number || "Draft"],
  ["date", "Date", (r) => `${dmy(r.adj_date)} ${showDate(r.adj_date)}`],
  ["supplier", "Supplier", (r) => r.supplier_name],
  ["section", "Section", (r) => `${r.section} ${r.section_shown}`],
  ["kind", "Kind", (r) => r.kind_label],
  ["total", "TDS ₹", (r) => `${r.total} ${signed(r.total)}`, true],
  ["status", "Status", (r) => r.status_label],
];

function AdjustmentList({ companyId }: { companyId: number }) {
  const [view, setView] = useKept("TdsAdjustments.view", "submitted");
  const [rows, setRows] = useState<Adjustment[]>([]);
  const [search, setSearch] = useKept<Record<string, string>>("TdsAdjustments.search", {});
  const [selectedId, setSelectedId] = useKept<number | null>("TdsAdjustments.selectedId", null);
  const [error, setError] = useState<unknown>("");
  const reload = useCallback(() => {
    api<Adjustment[]>(`v1/companies/${companyId}/tds-adjustments/?view=${view}`).then(setRows, setError);
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("tds_adjustment_saved", (c) => {
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
  const printing = usePrintMenu({ title: `TDS adjustments: ${VIEWS.find((v) => v.value === view)?.label ?? ""}`, scope: "" });
  return (
    <section className="page">
      <PageHeader
        title="TDS Adjustment"
        crumbs={[{ label: "Entry › Accounts", href: base(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "adjustment" : "adjustments"}. New ones are made from Entry › Accounts › TDS Check.`}
        actions={
          <>
            <button type="button" className="secondary" onClick={() => openTab(`#/companies/${companyId}/tds-check`)}>
              TDS Check
            </button>
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
                    <input type="search" aria-label={`Search ${label}`} placeholder="Search" value={search[key] ?? ""} onChange={(e) => setSearch({ ...search, [key]: e.target.value })} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && (
                <tr>
                  <td colSpan={COLUMNS.length} className="small">
                    No TDS adjustments match.
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
                  <td className="nowrap">{dmy(r.adj_date)}</td>
                  <td>{r.supplier_name}</td>
                  <td className="nowrap">{r.section}</td>
                  <td>{r.kind_label}</td>
                  <td className="num">{signed(r.total)}</td>
                  <td>
                    <span className={pillClass(r.status)}>{r.status_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small no-print">Click an adjustment to see it at the right (click it again to close the panel); double-click or press Enter to open it; "Close" there brings you back here.</p>}
        </div>
        {selected && (
          <div className="side-col" aria-label="TDS adjustment details">
            <SidePanel title={selected.number || "Draft TDS adjustment"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Supplier", selected.supplier_name],
                  ["Section", selected.section_shown],
                  ["Date", showDate(selected.adj_date)],
                  ["TDS", `₹${signed(selected.total)}`],
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
              <ChangeLog company={companyId} type="tds_adjustment" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// The bills table -----------------------------------------------------------------------------

function BillsTable(props: { lines: Line[]; lateInterest?: string; picked?: Set<number>; onPick?: (invoice: number) => void }) {
  const { lines } = props;
  const total = lines.filter((l) => !props.picked || props.picked.has(l.invoice));
  const sum = (key: "amount" | "interest") => total.reduce((n, l) => n + Number(l[key]), 0);
  return (
    <div className="table-scroll">
      <table className="grid po-lines">
        <thead>
          <tr>
            {props.onPick && <th className="no-print">Take</th>}
            <th>Bill No</th>
            <th>Date</th>
            <th>Supplier Bill</th>
            <th className="num">TDS On ₹</th>
            <th className="num">Rate %</th>
            <th className="num">TDS Due ₹</th>
            <th className="num">Deducted ₹</th>
            <th className="num">This Adjustment ₹</th>
            <th className="num">Months Late</th>
            <th className="num">Interest ₹{props.lateInterest ? ` (${props.lateInterest}% a month)` : ""}</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l) => (
            <tr key={l.invoice} className={props.picked && !props.picked.has(l.invoice) ? "off" : undefined}>
              {props.onPick && (
                <td className="no-print">
                  <input type="checkbox" aria-label={`Take bill ${l.number}`} checked={props.picked?.has(l.invoice) ?? true} onChange={() => props.onPick?.(l.invoice)} />
                </td>
              )}
              <td className="nowrap">{l.number}</td>
              <td className="nowrap">{dmy(l.posting_date)}</td>
              <td>{l.bill_no}</td>
              <td className="num">{money(l.base)}</td>
              <td className="num">{l.rate}</td>
              <td className="num">{money(l.due)}</td>
              <td className="num">{money(l.deducted)}</td>
              <td className="num">{Number(l.amount) ? signed(l.amount) : <span className="small">Section only</span>}</td>
              <td className="num">{l.months || ""}</td>
              <td className="num">{Number(l.interest) ? money(l.interest) : ""}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={props.onPick ? 8 : 7}>Total</td>
            <td className="num">{signed(String(sum("amount")))}</td>
            <td />
            <td className="num">{money(sum("interest"))}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

// The form ------------------------------------------------------------------------------------

function FormTab({ companyId, form, canSubmit }: { companyId: number; form: string; canSubmit: boolean }) {
  const [adj, setAdj] = useState<Adjustment | null>(null);
  const [from, setFrom] = useState<DraftFrom | null>(null);
  const [error, setError] = useState<unknown>("");
  const ledger = hashParam("ledger");
  const section = hashParam("section");
  const year = hashParam("year");
  useEffect(() => {
    if (form !== "new") {
      api<Adjustment>(`v1/tds-adjustments/${Number(form)}/`).then(setAdj, setError);
      return;
    }
    if (!ledger || !section) {
      setError('Make a TDS adjustment from Entry › Accounts › TDS Check: open a supplier and click "Make TDS Adjustment".');
      return;
    }
    api<DraftFrom>(`v1/companies/${companyId}/tds-adjustments/draft-from/?ledger=${ledger}&section=${encodeURIComponent(section)}${year ? `&year=${year}` : ""}`).then(setFrom, setError);
  }, [companyId, form, ledger, section, year]);
  const title = form === "new" ? "New TDS Adjustment" : "Edit TDS Adjustment";
  const shell = (msg?: unknown) => (
    <section className="page">
      <PageHeader title={title} crumbs={[{ label: "Entry › Accounts › TDS Adjustment", href: base(companyId) }]} />
      <ErrorNote error={msg} />
    </section>
  );
  if (error) return shell(error);
  if (form === "new" ? !from : !adj) return shell();
  if (adj && adj.status !== "draft") return shell("A submitted TDS adjustment cannot be changed. Cancel it instead.");
  return <AdjustmentForm companyId={companyId} title={title} adj={adj} from={from} canSubmit={canSubmit} />;
}

function AdjustmentForm(props: { companyId: number; title: string; adj: Adjustment | null; from: DraftFrom | null; canSubmit: boolean }) {
  const { companyId, adj, from } = props;
  const supplier = adj?.supplier ?? from?.supplier ?? 0;
  const supplierName = adj?.supplier_name ?? from?.supplier_name ?? "";
  const section = adj?.section ?? from?.section ?? "";
  const all = useMemo(() => adj?.lines?.map((l) => l.invoice) ?? from?.invoices ?? [], [adj, from]);
  const [date, setDate] = useState(adj?.adj_date ?? today());
  const [remarks, setRemarks] = useState(adj?.remarks ?? "");
  const [picked, setPicked] = useState<Set<number>>(new Set(all));
  const [lines, setLines] = useState<Line[]>(adj?.lines ?? []);
  const [late, setLate] = useState(adj?.late_interest ?? "");
  const [draftId, setDraftId] = useState<number | null>(adj?.id ?? null);
  const [saved, setSaved] = useState(0);
  const [savedAt, setSavedAt] = useState("");
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);

  // Every bill offered, worked out for the date (the months late and interest follow the date).
  useEffect(() => {
    if (!date) return;
    api<Preview>(`v1/companies/${companyId}/tds-adjustments/preview/`, { supplier, section, adj_date: date, invoices: all }).then(
      (p) => {
        setLines(p.lines);
        setLate(p.late_interest);
        setError("");
      },
      setError,
    );
  }, [companyId, supplier, section, date, all]);
  const taken = lines.filter((l) => picked.has(l.invoice));
  const total = taken.reduce((n, l) => n + Number(l.amount), 0);
  const pick = (invoice: number) =>
    setPicked((p) => {
      const next = new Set(p);
      if (next.has(invoice)) next.delete(invoice);
      else next.add(invoice);
      return next;
    });
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = { supplier, section, adj_date: date || null, remarks, invoices: [...picked], submit };
    try {
      const done = draftId ? await api<Adjustment>(`v1/tds-adjustments/${draftId}/`, body, "PATCH") : await api<Adjustment>(`v1/companies/${companyId}/tds-adjustments/`, body);
      announceSaved("tds_adjustment_saved", { id: done.id, name: done.number || "Draft" });
      if (submit) {
        window.location.hash = `${base(companyId)}?view=${done.id}`;
        return;
      }
      if (!draftId) {
        setDraftId(done.id);
        window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${done.id}`);
      }
      setSaved((n) => n + 1);
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
  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId && !adj ? "Edit TDS Adjustment" : props.title}
        sub={savedAt ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.` : "Deducts TDS missed on submitted bills, gives back TDS deducted in excess, or sets a TDS section the bills missed."}
        crumbs={[{ label: "Entry › Accounts › TDS Adjustment", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu label="Print" items={printItems(draftId)} />
            <button type="submit" form="tdsa-form" className={props.canSubmit ? "secondary" : undefined} disabled={busy || picked.size === 0}>
              Save
            </button>
            {props.canSubmit && (
              <button type="button" disabled={busy || picked.size === 0} onClick={() => save(true)}>
                Submit
              </button>
            )}
          </>
        }
      />
      <form id="tdsa-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{supplierName}</p>
            <p className="item-sub">
              <b>{adj?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              <span className="tag">{section}</span>
            </p>
          </div>
          <ErrorNote error={error} />
          <Fold title="Adjustment" open>
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <label>
                <span className="req">Date</span>
                <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
                <span className="small">The day the TDS is deducted (or given back)</span>
              </label>
              <label>
                <span className="req">Supplier</span>
                <input value={supplierName} readOnly />
              </label>
              <label>
                <span className="req">Section</span>
                <input value={adj?.section_shown ?? section} readOnly />
              </label>
              <label>
                Kind
                <input value={kindOf(total)} readOnly />
              </label>
              <label className="wide">
                Remarks
                <textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
              </label>
            </div>
          </Fold>
          <Fold title="Bills Covered" open summary={`₹${signed(String(total))}`}>
            <BillsTable lines={lines} lateInterest={late} picked={picked} onPick={pick} />
            <p className="small">
              Each bill's amount is the gap the TDS Check finds today; it is worked out again on Submit. A bill that owes nothing but missed the section ("Section only") gets the section recorded,
              at ₹0. Untick a bill to leave it out. Interest is for information, to pay with the TDS challan; it is not posted here.
            </p>
          </Fold>
          {draftId && <LedgerPosting url={`v1/tds-adjustments/${draftId}/ledger-posting/`} stamp={saved} />}
        </div>
        <DocSide type="tds_adjustment" id={draftId} />
      </form>
    </section>
  );
}

// The view ------------------------------------------------------------------------------------

function AdjustmentView({ companyId, id, can }: { companyId: number; id: number; can: (p: string) => boolean }) {
  const [adj, setAdj] = useState<Adjustment | null>(null);
  const [error, setError] = useState<unknown>("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const reload = useCallback(() => {
    api<Adjustment>(`v1/tds-adjustments/${id}/`).then(setAdj, setError);
  }, [id]);
  useEffect(reload, [reload]);
  useCreated("tds_adjustment_saved", (c) => {
    if (c.id === id) reload();
  });
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const cancel = async () => {
    setError("");
    try {
      const done = await api<Adjustment>(`v1/tds-adjustments/${id}/cancel/`, { reason });
      setAdj(done);
      setCancelling(false);
      announceSaved("tds_adjustment_saved", { id, name: done.number || "Draft" });
    } catch (err) {
      setError(err);
    }
  };
  if (!adj)
    return (
      <section className="page">
        <PageHeader title="TDS Adjustment" crumbs={[{ label: "Entry › Accounts › TDS Adjustment", href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const draft = adj.status === "draft";
  return (
    <section className="page">
      <PageHeader
        title={adj.number ? `TDS Adjustment ${adj.number}` : "TDS Adjustment (draft)"}
        sub={
          adj.number && adj.submitted_at
            ? `Submitted as ${adj.number} on ${showDate(adj.submitted_at)} at ${new Date(adj.submitted_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`
            : undefined
        }
        crumbs={[{ label: "Entry › Accounts › TDS Adjustment", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {draft && can("create") && (
              <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?form=${adj.id}`)}>
                Edit
              </button>
            )}
            {can("cancel") && adj.status !== "cancelled" && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel adjustment
              </button>
            )}
            <ActionsMenu label="Print" items={printItems(id)} />
            {draft && can("create") && (
              <button type="button" onClick={() => openTab(`${base(companyId)}?form=${adj.id}`)}>
                Open to Submit
              </button>
            )}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{adj.supplier_name}</p>
            <p className="item-sub">
              <b>{adj.number || "Number given on Submit"}</b>
              <span className={pillClass(adj.status)}>{adj.status_label}</span>
              <span className="tag">{adj.section}</span>
            </p>
          </div>
          {adj.status === "cancelled" && <p className="use-note">Cancelled: {adj.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this TDS adjustment cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Made for the wrong section" />
              </label>
              <p className="small">The entries are reversed and the bills show their gap again on the TDS Check.</p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep the adjustment
                </button>
                <button type="button" className="link danger" onClick={cancel}>
                  Cancel adjustment
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="Adjustment" open>
            <dl className="kv">
              {(
                [
                  ["Date", showDate(adj.adj_date)],
                  ["Supplier", adj.supplier_name],
                  ["Section", adj.section_shown],
                  ["Kind", adj.kind_label],
                  ["Branch", adj.branch_name],
                  ["Remarks", adj.remarks],
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
          <Fold title="Bills Covered" open summary={`₹${signed(adj.total)}`}>
            <BillsTable lines={adj.lines ?? []} lateInterest={adj.late_interest} />
            {Number(adj.interest) > 0 && <p className="small">Interest is for information, to pay with the TDS challan; it is not posted here.</p>}
          </Fold>
          <LedgerPosting url={`v1/tds-adjustments/${adj.id}/ledger-posting/`} stamp={adj.status} />
        </div>
        <DocSide type="tds_adjustment" id={adj.id} onChange={() => setFiles((n) => n + 1)}>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="tds_adjustment" id={adj.id} stamp={JSON.stringify(adj) + files} />
          </SidePanel>
        </DocSide>
      </div>
    </section>
  );
}
