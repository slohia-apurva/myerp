import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, type SignedIn } from "./api";
import { DocSide } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { useItemSearch } from "./ItemSearch";
import { usePeopleSearch } from "./SalesPeople";
import { money } from "./Companies";
import { announceSaved, closeThisTab, creatable, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { Cells, ListHeads, matching, useColumns, type Column } from "./Columns";
import { LedgerPosting, MissingLedgersPopup, missingLedgersOf, type MissingLedgers } from "./LedgerPosting";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useKept } from "./Keep";

/** Entry > Stock > Own Use: our own stock used inside the company, for the office, canteen,
 * maintenance, R&D, or damaged and thrown away (Sidharth, 2026-11-22, preview 9c in
 * mockups/planning). Draft → Submit: the goods leave their bins at FIFO cost, Dr each line's Expense
 * Ledger (the item's Expense Account to start with), Cr Stock. A draft counts as Reserved in the
 * Stock Check. */

type Bin = { id: number; location_name: string; batch_number: string; package_number: string; qty: string; qty_unit: string; cost: string };
type Line = {
  id: number;
  position: number;
  item: number;
  item_name: string;
  item_number: string;
  unit: number;
  unit_name: string;
  qty: string;
  picked: string;
  short_picked: boolean;
  expense_ledger: number | null;
  ledger: number | null;
  ledger_name: string;
  cost: string;
  bins: Bin[];
};
type Entry = {
  id: number;
  company: number;
  number: string;
  status: string;
  status_label: string;
  branch: number;
  branch_name: string;
  area: number | null;
  place_name: string;
  entry_date: string;
  reason: string;
  stores_person: number | null;
  stores_person_name: string;
  notes: string;
  value: string;
  cancel_reason: string;
  created_by_name: string;
  created_at: string;
  submitted_at: string | null;
  submitted_by_name: string;
  items?: string;
  lines?: Line[];
};
type FormItem = {
  id: number;
  name: string;
  item_number: string;
  stock_unit: number;
  units: { unit: number; name: string; whole_numbers: boolean; factor: string }[];
  ledger: number | null;
  ledger_name: string;
  in_stock: string | null;
};
type Setup = {
  branches: { id: number; name: string; is_active: boolean; areas: { id: number; name: string; is_active: boolean }[] }[];
  ledgers: { id: number; name: string; group_name: string }[];
  items: FormItem[];
};
type Problem = { line: number | null; text: string };

const VIEWS: [string, string][] = [
  ["all", "All"],
  ["draft", "Draft"],
  ["submitted", "Submitted"],
  ["cancelled", "Cancelled"],
];
export const ownUseBase = (companyId: number) => `#/companies/${companyId}/own-use`;
const CRUMB = "Entry › Stock › Own Use";
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const at = (iso: string) => `${shortDate(iso)} at ${new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`;
const pillClass = (s: string) => (s === "submitted" ? "pill on" : s === "draft" ? "pill warn" : "pill");
const plain = (n: number) => String(Number(n.toFixed(3)));
const can = (session: SignedIn, action: string) => session.permissions.includes(`stock.${action}`);
const today = () => new Date().toLocaleDateString("en-CA");
const pdf = (id: number, download = false) => openTab(`/api/v1/own-use/${id}/pdf/${download ? "?download=1" : ""}`);
const printItems = (id: number) => [
  { label: "Issue Slip", onClick: () => pdf(id) },
  { label: "Download PDF", onClick: () => pdf(id, true) },
];
/** One part per bin and batch: "FG-R1-B1 · B2611-07 (24)". */
const binsText = (bins: Bin[]) => {
  const parts: { where: string; qty: number; bags: string[] }[] = [];
  for (const b of bins) {
    const where = [b.location_name, b.batch_number].filter(Boolean).join(" · ");
    let part = parts.find((x) => x.where === where);
    if (!part) parts.push((part = { where, qty: 0, bags: [] }));
    part.qty += Number(b.qty_unit);
    if (b.package_number) part.bags.push(b.package_number);
  }
  return parts
    .map((x) => `${x.where} (${plain(x.qty)})${x.bags.length === 1 ? ` · ${x.bags[0]}` : x.bags.length ? ` · ${x.bags.length} bags ${x.bags[0]} to ${x.bags[x.bags.length - 1]}` : ""}`)
    .join("; ");
};

export function OwnUsePage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const view = Number(hashParam("view"));
  if (view > 0) return <EntryView companyId={companyId} id={view} session={session} />;
  if (hashParam("form") === "new") return <EntryView companyId={companyId} id={0} session={session} />;
  return <EntryList companyId={companyId} session={session} />;
}

const cost = (e: Entry) => (e.status === "draft" ? "" : money(e.value));
const COLUMNS: Column<Entry>[] = [
  { key: "number", label: "Entry No", fixed: true, text: (e) => e.number || "Draft", cell: (e) => <b>{e.number || "Draft"}</b> },
  { key: "date", label: "Date", standard: true, nowrap: true, text: (e) => shortDate(e.entry_date), cell: (e) => shortDate(e.entry_date) },
  { key: "place", label: "Branch", standard: true, text: (e) => e.place_name, cell: (e) => e.place_name },
  { key: "items", label: "Items", standard: true, text: (e) => e.items ?? "", cell: (e) => e.items },
  { key: "reason", label: "Reason", standard: true, text: (e) => e.reason, cell: (e) => e.reason },
  { key: "value", label: "Cost ₹", standard: true, num: true, text: cost, cell: cost },
  { key: "status", label: "Status", standard: true, text: (e) => e.status_label, cell: (e) => <span className={pillClass(e.status)}>{e.status_label}</span> },
];

function EntryList({ companyId, session }: { companyId: number; session: SignedIn }) {
  const [view, setView] = useKept("OwnUse.view", hashParam("status") ?? "all");
  const [rows, setRows] = useState<Entry[]>([]);
  const [search, setSearch] = useKept<Record<string, string>>("OwnUse.search", {});
  const [selectedId, setSelectedId] = useKept<number | null>("OwnUse.selectedId", null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Entry[]>(`v1/companies/${companyId}/own-use/?view=${view}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("own_use_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(() => matching(rows, COLUMNS, search), [rows, search]);
  const columns = useColumns("own-use", COLUMNS, { sort: false });
  const selected = rows.find((e) => e.id === selectedId) ?? null;
  const printing = usePrintMenu({ title: `Own use: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`, scope: "" });
  const open = (id: number) => openTab(`${ownUseBase(companyId)}?view=${id}`);
  return (
    <section className="page">
      <PageHeader
        title="Own Use"
        crumbs={[{ label: "Entry › Stock", href: ownUseBase(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "entry" : "entries"} · our own stock used inside the company`}
        actions={
          <>
            {printing.menu([...printing.items, columns.item])}
            {can(session, "create") && (
              <button type="button" onClick={() => openTab(`${ownUseBase(companyId)}?form=new`)}>
                New Own Use
              </button>
            )}
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {printing.panel}
      {columns.panel}
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
              <ListHeads shown={columns.shown} search={search} setSearch={setSearch} />
            </thead>
            <tbody>
              {shown.length === 0 && (
                <tr>
                  <td colSpan={columns.shown.length} className="small">
                    No own use entries match.
                  </td>
                </tr>
              )}
              {shown.map((e) => (
                <tr
                  key={e.id}
                  tabIndex={0}
                  className={selected?.id === e.id ? "selected" : ""}
                  onClick={() => setSelectedId(selected?.id === e.id ? null : e.id)}
                  onDoubleClick={() => open(e.id)}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter") open(e.id);
                  }}
                >
                  <Cells shown={columns.shown} row={e} />
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small no-print">Click an entry to see it at the right; double-click or press Enter to open it; "Close" there brings you back here.</p>}
        </div>
        {selected && (
          <div className="side-col" aria-label="Own use details">
            <SidePanel title={selected.number || "Draft"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Branch", selected.place_name],
                  ["Date", shortDate(selected.entry_date)],
                  ["Reason", selected.reason],
                  ["Cost", selected.status === "draft" ? "" : `₹${money(selected.value)}`],
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
              <ChangeLog company={companyId} type="own_use" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// One entry ------------------------------------------------------------------------

type Fields = { branch: string; area: string; entry_date: string; reason: string; stores_person: string; notes: string };
type DraftLine = { key: number; item: string; unit: string; qty: string; expense_ledger: string };
let nextKey = 1;
const emptyLine = (): DraftLine => ({ key: nextKey++, item: "", unit: "", qty: "", expense_ledger: "" });
const blank = (): Fields => ({ branch: "", area: "", entry_date: today(), reason: "", stores_person: "", notes: "" });
const fieldsOf = (e: Entry): Fields => ({
  branch: String(e.branch),
  area: e.area ? String(e.area) : "",
  entry_date: e.entry_date,
  reason: e.reason,
  stores_person: e.stores_person ? String(e.stores_person) : "",
  notes: e.notes,
});
const linesOf = (e: Entry): DraftLine[] =>
  (e.lines ?? []).map((l) => ({ key: nextKey++, item: String(l.item), unit: String(l.unit), qty: l.qty, expense_ledger: l.expense_ledger ? String(l.expense_ledger) : "" }));

function EntryView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const base = ownUseBase(companyId);
  const [e, setE] = useState<Entry | null>(null);
  const [error, setError] = useState<unknown>("");
  const [fields, setFields] = useState<Fields>(blank);
  const [lines, setLines] = useState<DraftLine[]>(() => [emptyLine()]);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [noLedgers, setNoLedgers] = useState<MissingLedgers | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const [saved, setSaved] = useState(0);
  const [busy, setBusy] = useState(false);
  const take = useCallback((x: Entry) => {
    setE(x);
    setFields(fieldsOf(x));
    setLines(linesOf(x));
  }, []);
  useEffect(() => {
    if (id) api<Entry>(`v1/own-use/${id}/`).then(take, (err) => setError(err));
  }, [id, take]);
  const draft = !e || e.status === "draft";
  const mayEdit = draft && can(session, "create");
  const setupUrl = `v1/companies/${companyId}/own-use/form/?branch=${fields.branch}&area=${fields.area}`;
  const refreshSetup = useCallback(() => api<Setup>(`${setupUrl}&search=1`).then(setSetup, (err) => setError(err)), [setupUrl]);
  // Items come from the server as the person types (ItemSearch.ts), never all at once.
  const { items, onType: findItems } = useItemSearch<FormItem>(mayEdit ? setupUrl : null, lines.map((l) => l.item), undefined, (a) => (a as Setup).items);
  // Stores people come from the server as the person types (usePeopleSearch), never all at once.
  const { people: storesPeople, onType: findPeople } = usePeopleSearch("stores", [fields.stores_person]);
  useEffect(() => {
    if (mayEdit) refreshSetup();
  }, [mayEdit, refreshSetup]);
  const mayAddMasters = session.permissions.includes("masters.edit");
  const newPerson = mayAddMasters ? creatable("sales_person", "sales-people", refreshSetup, "as=stores") : undefined;
  const newItem = mayAddMasters ? creatable("item", "items", refreshSetup) : undefined;
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base;
    });
  const done = (x: Entry) => {
    take(x);
    setCancelling(false);
    setSaved((k) => k + 1);
    announceSaved("own_use_saved", { id: x.id, name: x.number || "Draft" });
    if (!id) window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${base}?view=${x.id}`);
  };
  const refusal = (err: unknown) => {
    const missing = missingLedgersOf(err);
    if (missing) return setNoLedgers(missing);
    const data = err instanceof ApiError ? (err.data as { problems?: Problem[] } | undefined) : undefined;
    if (data?.problems?.length) return setProblems(data.problems);
    setError(err);
  };
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      ...fields,
      branch: Number(fields.branch) || null,
      area: Number(fields.area) || null,
      stores_person: Number(fields.stores_person) || null,
      lines: lines.filter((l) => l.item).map((l) => ({ item: Number(l.item), unit: Number(l.unit), qty: l.qty || "0", expense_ledger: Number(l.expense_ledger) || null })),
      submit,
    };
    const current = e?.id ?? 0;
    try {
      done(current ? await api<Entry>(`v1/own-use/${current}/`, body, "PATCH") : await api<Entry>(`v1/companies/${companyId}/own-use/`, body));
    } catch (err) {
      // A refused Submit still saved the draft: read it again.
      const kept = err instanceof ApiError ? (err.data as { id?: number } | undefined)?.id : undefined;
      if (submit && (kept || current)) api<Entry>(`v1/own-use/${kept || current}/`).then(done, () => undefined);
      refusal(err);
    }
    setBusy(false);
  };
  const cancel = async () => {
    if (!e) return;
    setError("");
    setBusy(true);
    try {
      done(await api<Entry>(`v1/own-use/${e.id}/cancel/`, { reason }));
    } catch (err) {
      refusal(err);
    }
    setBusy(false);
  };
  const goTo = (position: number | null) => {
    setProblems(null);
    if (position) window.setTimeout(() => document.getElementById(`ou-line-${position}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };
  if (id && !e)
    return (
      <section className="page">
        <PageHeader title="Own Use" crumbs={[{ label: CRUMB, href: base }]} />
        <ErrorNote error={error} />
      </section>
    );
  const set = (patch: Partial<Fields>) => setFields({ ...fields, ...patch });
  const status = e?.status ?? "draft";
  const branches = setup?.branches ?? [];
  const branch = branches.find((b) => String(b.id) === fields.branch);
  const itemOf = (v: string) => items.find((i) => String(i.id) === v);
  const ledgerOptions = (setup?.ledgers ?? []).map((l) => ({ value: String(l.id), label: l.name, hint: l.group_name }));
  const savedLines = e?.lines ?? [];
  const title = e?.number ? `Own Use ${e.number}` : e ? "Own Use (Draft)" : "New Own Use";
  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={e?.submitted_at ? `Submitted as ${e.number} on ${at(e.submitted_at)}` : e ? `Draft made ${at(e.created_at)} · nothing posted yet` : "Nothing is saved until you press Save"}
        crumbs={[{ label: CRUMB, href: base }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {e && status !== "cancelled" && can(session, "cancel") && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel
              </button>
            )}
            {e && <ActionsMenu label="Print" items={printItems(e.id)} />}
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
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{e ? `${e.place_name}${e.reason ? ` · ${e.reason}` : ""}` : "Own Use"}</p>
            <p className="item-sub">
              {e?.number && <b>{e.number}</b>}
              <span className={pillClass(status)}>{e?.status_label ?? "New"}</span>
            </p>
          </div>
          {e?.status === "cancelled" && <p className="use-note">Cancelled: {e.cancel_reason}</p>}
          {cancelling && e && (
            <div className="use-note no-print">
              <label>
                <b>Why is this entry cancelled?</b>
                <input autoFocus value={reason} onChange={(ev) => setReason(ev.target.value)} placeholder="e.g. Not used after all" />
              </label>
              <p className="small">{status === "submitted" ? "The goods go back into the bins they came from and the ledger entries are reversed." : "The draft is set aside."}</p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep it
                </button>
                <button type="button" className="link danger" disabled={busy} onClick={cancel}>
                  Cancel Own Use
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="Where and Why" open summary={e ? `${e.place_name} · ${shortDate(e.entry_date)}` : ""}>
            {mayEdit ? (
              <div className="item-fields">
                <label>
                  <span className="req">Branch</span>
                  <Combobox value={fields.branch} onChange={(v) => set({ branch: v, area: "" })} required options={branches.filter((b) => b.is_active || String(b.id) === fields.branch).map((b) => ({ value: String(b.id), label: b.name }))} />
                </label>
                <label>
                  Area
                  <Combobox value={fields.area} onChange={(v) => set({ area: v })} empty="Whole branch" options={(branch?.areas ?? []).filter((a) => a.is_active || String(a.id) === fields.area).map((a) => ({ value: String(a.id), label: a.name }))} />
                  <span className="small">Bins and batches are picked from here (earliest expiry first)</span>
                </label>
                <label>
                  <span className="req">Date</span>
                  <input type="date" required value={fields.entry_date} onChange={(ev) => set({ entry_date: ev.target.value })} />
                </label>
                <label>
                  Issued By
                  <Combobox value={fields.stores_person} onChange={(v) => set({ stores_person: v })} create={newPerson} onType={findPeople} options={storesPeople.map((p) => ({ value: String(p.id), label: p.name }))} />
                </label>
                <label className="wide">
                  Reason
                  <input value={fields.reason} maxLength={200} placeholder="e.g. Office pantry, November" onChange={(ev) => set({ reason: ev.target.value })} />
                </label>
              </div>
            ) : (
              e && (
                <Facts
                  rows={[
                    ["Branch", e.place_name],
                    ["Date", shortDate(e.entry_date)],
                    ["Reason", e.reason],
                    ["Issued By", e.stores_person_name],
                    ["Cost", status === "draft" ? "" : `₹${money(e.value)}`],
                  ]}
                />
              )
            )}
          </Fold>
          <Fold title="Items" open summary={`${mayEdit ? lines.filter((l) => l.item).length : savedLines.length} items${e && status !== "draft" ? ` · ₹${money(e.value)}` : ""}`}>
            {mayEdit ? (
              <>
                <div className="table-scroll">
                  <table className="grid po-lines">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th style={{ minWidth: 200 }}>Item</th>
                        <th className="num">Qty</th>
                        <th>Unit</th>
                        <th className="num">Free Here</th>
                        <th style={{ minWidth: 170 }}>Taken From (bin · batch)</th>
                        <th style={{ minWidth: 180 }}>Expense Ledger</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l, k) => {
                        const item = itemOf(l.item);
                        const unit = item?.units.find((u) => String(u.unit) === l.unit);
                        const free = item?.in_stock != null && unit ? Number(item.in_stock) / Number(unit.factor || 1) : null;
                        const was = savedLines.find((s) => s.position === k + 1 && String(s.item) === l.item);
                        const setLine = (patch: Partial<DraftLine>) => setLines((ls) => ls.map((x) => (x.key === l.key ? { ...x, ...patch } : x)));
                        return (
                          <tr key={l.key} id={`ou-line-${k + 1}`}>
                            <td>{k + 1}</td>
                            <td className="po-item">
                              <Combobox
                                value={l.item}
                                ariaLabel={`Item on line ${k + 1}`}
                                placeholder="Type to search items…"
                                create={newItem}
                                onChange={(v) => setLine({ item: v, unit: String(itemOf(v)?.stock_unit ?? ""), expense_ledger: "" })}
                                options={items.map((i) => ({ value: String(i.id), label: i.name, hint: i.item_number }))}
                                onType={findItems}
                              />
                            </td>
                            <td className="num">
                              <input className="num" inputMode="decimal" aria-label={`Qty on line ${k + 1}`} value={l.qty} onChange={(ev) => setLine({ qty: ev.target.value })} />
                            </td>
                            <td>
                              <Combobox value={l.unit} ariaLabel={`Unit on line ${k + 1}`} onChange={(v) => setLine({ unit: v })} options={(item?.units ?? []).map((u) => ({ value: String(u.unit), label: u.name }))} />
                            </td>
                            <td className="num">{free == null ? "" : free < Number(l.qty || 0) ? <b className="error">{plain(free)}</b> : plain(free)}</td>
                            <td className="small">
                              {was ? binsText(was.bins) || <span className="error">Nothing free</span> : "Picked on Save"}
                              {was?.short_picked && was.bins.length > 0 && <span className="error"> · only {was.picked} free</span>}
                            </td>
                            <td className="po-item">
                              <Combobox
                                value={l.expense_ledger}
                                ariaLabel={`Expense ledger on line ${k + 1}`}
                                onChange={(v) => setLine({ expense_ledger: v })}
                                empty={item ? item.ledger_name || "Not set: pick one" : ""}
                                options={ledgerOptions}
                              />
                            </td>
                            <td>
                              <button type="button" className="link danger" aria-label="Remove line" onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))}>
                                ✕
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="buttons">
                  <button type="button" className="link" onClick={() => setLines((ls) => [...ls, emptyLine()])}>
                    + Add item
                  </button>
                </div>
                <p className="small">
                  Each line is charged to the item's own "Expense Account" for the company (else its item group's COGS/Expense Ledger) unless you pick another expense ledger. Bins and batches are picked each time the draft is saved,
                  and again on Submit. A draft counts as Reserved in the Stock Check.
                </p>
              </>
            ) : (
              <div className="table-scroll">
                <table className="grid po-lines">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item</th>
                      <th className="num">Qty</th>
                      <th>Unit</th>
                      <th>Taken From (bin · batch)</th>
                      <th>Expense Ledger</th>
                      <th className="num">Cost ₹</th>
                    </tr>
                  </thead>
                  <tbody>
                    {savedLines.map((l) => (
                      <tr key={l.id} id={`ou-line-${l.position}`}>
                        <td>{l.position}</td>
                        <td>
                          <b>{l.item_name}</b>
                        </td>
                        <td className="num">{l.qty}</td>
                        <td>{l.unit_name}</td>
                        <td className="small">{binsText(l.bins)}</td>
                        <td>{l.ledger_name}</td>
                        <td className="num">{status === "draft" || status === "cancelled" ? "" : money(l.cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Fold>
          {e && <LedgerPosting url={`v1/own-use/${e.id}/ledger-posting/`} stamp={`${saved}-${e.status}`} />}
        </div>
        <DocSide type="own_use" id={e?.id ?? null} onChange={() => setFiles((n) => n + 1)}>
          {e && (
            <>
              <SidePanel title="Details">
                <SideRows
                  rows={[
                    ["Made By", e.created_by_name],
                    ["Submitted By", e.submitted_by_name],
                  ]}
                />
              </SidePanel>
              <SidePanel title="Activity">
                <ChangeLog company={companyId} type="own_use" id={e.id} stamp={JSON.stringify(e) + files} />
              </SidePanel>
            </>
          )}
        </DocSide>
      </div>
      {problems && <ProblemsPopup problems={problems} onGo={goTo} onClose={() => setProblems(null)} />}
      {noLedgers && <MissingLedgersPopup refusal={noLedgers} document="the own use entry" onClose={() => setNoLedgers(null)} />}
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

/** Everything that stopped Submit, each with "Go to line". */
function ProblemsPopup(props: { problems: Problem[]; onGo: (line: number | null) => void; onClose: () => void }) {
  return (
    <div className="popup-back" role="presentation">
      <div className="popup grn-check" role="dialog" aria-modal="true" aria-label="This entry cannot be submitted yet">
        <h3>This entry cannot be submitted yet ({props.problems.length})</h3>
        <table className="grid">
          <tbody>
            {props.problems.map((p) => (
              <tr key={p.text}>
                <td className="bad-note">✕</td>
                <td>{p.text}</td>
                <td>
                  {p.line && (
                    <button type="button" className="link" onClick={() => props.onGo(p.line)}>
                      Go to line
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small">Nothing has been submitted; the draft is kept.</p>
        <div className="popup-actions">
          <button type="button" onClick={props.onClose}>
            OK
          </button>
        </div>
      </div>
    </div>
  );
}
