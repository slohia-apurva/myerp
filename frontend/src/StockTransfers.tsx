import { useCallback, useEffect, useMemo, useState } from "react";
import { useTransporterSearch } from "./Shipments";
import { api, ApiError, type SignedIn } from "./api";
import { DocSide } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { useItemSearch } from "./ItemSearch";
import { money } from "./Companies";
import { announceSaved, closeThisTab, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { MissingLedgersPopup, missingLedgersOf, type MissingLedgers } from "./LedgerPosting";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";

/** Entry > Stock > Stock Transfer: goods moving between two branches of one company with the same
 * GSTIN (Sidharth, 2026-11-22, preview 9a in mockups/planning). Draft → Dispatch (the goods leave
 * From's bins at FIFO cost and sit in To's "In Transit" place) → Receive at To (into its bins; a
 * shortfall is a transit loss). */

type Bin = {
  id: number;
  location: number;
  location_name: string;
  batch: number | null;
  batch_number: string;
  expiry: string | null;
  package: number | null;
  package_number: string;
  whole_package: boolean;
  /** Stock unit. */
  qty: string;
  qty_unit: string;
  cost: string;
  received_qty: string | null;
  put_location: number | null;
  put_location_name: string;
};
type Line = {
  id: number;
  position: number;
  item: number;
  item_name: string;
  hsn: string;
  unit: number;
  unit_name: string;
  stock_unit_name: string;
  factor: string;
  qty: string;
  picked: string;
  short_picked: boolean;
  cost: string;
  received: string | null;
  bins: Bin[];
};
type Transfer = {
  id: number;
  company: number;
  number: string;
  status: string;
  status_label: string;
  from_branch: number;
  from_branch_name: string;
  from_area: number | null;
  from_name: string;
  from_gstin: string;
  to_branch: number;
  to_branch_name: string;
  to_area: number | null;
  to_name: string;
  to_gstin: string;
  transfer_date: string;
  expected_date: string | null;
  transporter: number | null;
  transporter_name: string;
  vehicle_no: string;
  eway_bill_no: string;
  reason: string;
  notes: string;
  value: string;
  received_date: string | null;
  shortfall_reason: string;
  shortfall_value: string;
  cancel_reason: string;
  created_by_name: string;
  created_at: string;
  dispatched_at: string | null;
  dispatched_by_name: string;
  received_at: string | null;
  received_by_name: string;
  items?: string;
  lines?: Line[];
};
type FormItem = {
  id: number;
  name: string;
  item_number: string;
  stock_unit: number;
  stock_unit_name: string;
  units: { unit: number; name: string; whole_numbers: boolean; factor: string }[];
  in_stock: string | null;
};
type Setup = {
  branches: { id: number; name: string; gstin: string; is_active: boolean; areas: { id: number; name: string; is_active: boolean }[] }[];
  items: FormItem[];
};
type Problem = { line: number | null; text: string };
type Posting = { steps: { step: string; done: boolean; stock: string; books: string; value: string }[]; cancelled: boolean };

const VIEWS: [string, string][] = [
  ["all", "All"],
  ["draft", "Draft"],
  ["in_transit", "In Transit"],
  ["received", "Received"],
  ["cancelled", "Cancelled"],
];
export const transferBase = (companyId: number) => `#/companies/${companyId}/stock-transfers`;
const CRUMB = "Entry › Stock › Stock Transfer";
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const at = (iso: string) => `${shortDate(iso)} at ${new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`;
const pillClass = (s: string) => (s === "received" ? "pill on" : s === "draft" || s === "in_transit" ? "pill warn" : "pill");
const plain = (n: number) => String(Number(n.toFixed(3)));
const can = (session: SignedIn, action: string) => session.permissions.includes(`stock.${action}`);
const today = () => new Date().toLocaleDateString("en-CA");
const pdf = (id: number, download = false) => openTab(`/api/v1/stock-transfers/${id}/pdf/${download ? "?download=1" : ""}`);
const printItems = (id: number) => [
  { label: "Delivery Challan", onClick: () => pdf(id) },
  { label: "Download PDF", onClick: () => pdf(id, true) },
];

export function StockTransfersPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const view = Number(hashParam("view"));
  if (view > 0) return <TransferView companyId={companyId} id={view} session={session} />;
  if (hashParam("form") === "new") return <TransferView companyId={companyId} id={0} session={session} />;
  return <TransferList companyId={companyId} session={session} />;
}

const COLUMNS: [key: string, label: string, text: (t: Transfer) => string, num?: boolean][] = [
  ["number", "Transfer No", (t) => t.number || "Draft"],
  ["date", "Date", (t) => shortDate(t.transfer_date)],
  ["from", "From", (t) => t.from_name],
  ["to", "To", (t) => t.to_name],
  ["items", "Items", (t) => t.items ?? ""],
  ["vehicle", "Vehicle No", (t) => t.vehicle_no],
  ["value", "Value ₹", (t) => (t.status === "draft" ? "" : money(t.value)), true],
  ["status", "Status", (t) => t.status_label],
];

function TransferList({ companyId, session }: { companyId: number; session: SignedIn }) {
  const [view, setView] = useState(hashParam("status") ?? "all");
  const [rows, setRows] = useState<Transfer[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Transfer[]>(`v1/companies/${companyId}/stock-transfers/?view=${view}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("stock_transfer_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      rows.filter((t) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          return words.every((w) => text(t).toLowerCase().includes(w));
        }),
      ),
    [rows, search],
  );
  const selected = rows.find((t) => t.id === selectedId) ?? null;
  const printing = usePrintMenu({ title: `Stock transfers: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`, scope: "" });
  const open = (id: number) => openTab(`${transferBase(companyId)}?view=${id}`);
  return (
    <section className="page">
      <PageHeader
        title="Stock Transfer"
        crumbs={[{ label: "Entry › Stock", href: transferBase(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "transfer" : "transfers"} · goods between branches with the same GSTIN`}
        actions={
          <>
            {printing.buttons}
            {can(session, "create") && (
              <button type="button" onClick={() => openTab(`${transferBase(companyId)}?form=new`)}>
                New Transfer
              </button>
            )}
          </>
        }
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
                    No stock transfers match.
                  </td>
                </tr>
              )}
              {shown.map((t) => (
                <tr
                  key={t.id}
                  tabIndex={0}
                  className={selected?.id === t.id ? "selected" : ""}
                  onClick={() => setSelectedId(selected?.id === t.id ? null : t.id)}
                  onDoubleClick={() => open(t.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") open(t.id);
                  }}
                >
                  <td>
                    <b>{t.number || "Draft"}</b>
                  </td>
                  <td className="nowrap">{shortDate(t.transfer_date)}</td>
                  <td>{t.from_name}</td>
                  <td>{t.to_name}</td>
                  <td>{t.items}</td>
                  <td>{t.vehicle_no}</td>
                  <td className="num">{t.status === "draft" ? "" : money(t.value)}</td>
                  <td>
                    <span className={pillClass(t.status)}>{t.status_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small no-print">Click a transfer to see it at the right; double-click or press Enter to open it in a new tab.</p>}
        </div>
        {selected && (
          <div className="side-col" aria-label="Stock transfer details">
            <SidePanel title={selected.number || "Draft"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["From", selected.from_name],
                  ["To", selected.to_name],
                  ["Transfer Date", shortDate(selected.transfer_date)],
                  ["Expected Arrival", shortDate(selected.expected_date)],
                  ["Transporter", selected.transporter_name],
                  ["Value (At Cost)", selected.status === "draft" ? "" : `₹${money(selected.value)}`],
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
              <ChangeLog company={companyId} type="stock_transfer" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// One transfer --------------------------------------------------------------------

type Fields = {
  from_branch: string;
  from_area: string;
  to_branch: string;
  to_area: string;
  transfer_date: string;
  expected_date: string;
  transporter: string;
  vehicle_no: string;
  eway_bill_no: string;
  reason: string;
  notes: string;
};
type DraftLine = { key: number; item: string; unit: string; qty: string };
type ReceiveRow = { received_qty: string; put_location: string };
let nextKey = 1;
const blank = (): Fields => ({
  from_branch: hashParam("from") ?? "",
  from_area: "",
  to_branch: hashParam("to") ?? "",
  to_area: "",
  transfer_date: today(),
  expected_date: "",
  transporter: "",
  vehicle_no: "",
  eway_bill_no: "",
  reason: "",
  notes: "",
});
const fieldsOf = (t: Transfer): Fields => ({
  from_branch: String(t.from_branch),
  from_area: t.from_area ? String(t.from_area) : "",
  to_branch: String(t.to_branch),
  to_area: t.to_area ? String(t.to_area) : "",
  transfer_date: t.transfer_date,
  expected_date: t.expected_date ?? "",
  transporter: t.transporter ? String(t.transporter) : "",
  vehicle_no: t.vehicle_no,
  eway_bill_no: t.eway_bill_no,
  reason: t.reason,
  notes: t.notes,
});
const linesOf = (t: Transfer): DraftLine[] => (t.lines ?? []).map((l) => ({ key: nextKey++, item: String(l.item), unit: String(l.unit), qty: l.qty }));
const binText = (b: Bin) => [b.location_name, b.batch_number, b.package_number].filter(Boolean).join(" · ");

function TransferView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const [t, setT] = useState<Transfer | null>(null);
  const [error, setError] = useState<unknown>("");
  const [fields, setFields] = useState<Fields>(blank);
  // Transporters come from the server as the person types (useTransporterSearch), never all at once.
  const { transporters, onType: findTransporters } = useTransporterSearch(companyId, [fields.transporter]);
  const [lines, setLines] = useState<DraftLine[]>(() => [{ key: nextKey++, item: "", unit: "", qty: "" }]);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [noLedgers, setNoLedgers] = useState<MissingLedgers | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [receiving, setReceiving] = useState(false);
  const [places, setPlaces] = useState<{ id: number; label: string }[]>([]);
  const [got, setGot] = useState<Record<number, ReceiveRow>>({});
  const [gotDate, setGotDate] = useState(today);
  const [shortReason, setShortReason] = useState("");
  const [files, setFiles] = useState(0);
  const [saved, setSaved] = useState(0);
  const [busy, setBusy] = useState(false);
  const take = useCallback((x: Transfer) => {
    setT(x);
    setFields(fieldsOf(x));
    setLines(linesOf(x));
  }, []);
  useEffect(() => {
    if (id) api<Transfer>(`v1/stock-transfers/${id}/`).then(take, (err) => setError(err));
  }, [id, take]);
  const draft = !t || t.status === "draft";
  const mayEdit = draft && can(session, "create");
  const setupUrl = `v1/companies/${companyId}/stock-transfers/form/?branch=${fields.from_branch}&area=${fields.from_area}`;
  useEffect(() => {
    if (!mayEdit) return;
    api<Setup>(`${setupUrl}&search=1`).then(setSetup, (err) => setError(err));
  }, [mayEdit, setupUrl]);
  // Items come from the server as the person types (ItemSearch.ts), never all at once.
  const { items, onType: findItems } = useItemSearch<FormItem>(mayEdit ? setupUrl : null, lines.map((l) => l.item), undefined, (a) => (a as Setup).items);
  const close = () =>
    closeThisTab(() => {
      window.location.hash = transferBase(companyId);
    });
  const done = (x: Transfer) => {
    take(x);
    setCancelling(false);
    setReceiving(false);
    setSaved((k) => k + 1);
    announceSaved("stock_transfer_saved", { id: x.id, name: x.number || "Draft" });
    if (!id) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${transferBase(companyId)}?view=${x.id}`);
  };
  const refusal = (err: unknown) => {
    const missing = missingLedgersOf(err);
    if (missing) return setNoLedgers(missing);
    const data = err instanceof ApiError ? (err.data as { problems?: Problem[] } | undefined) : undefined;
    if (data?.problems?.length) return setProblems(data.problems);
    setError(err);
  };
  const save = async (dispatch: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      ...fields,
      from_branch: Number(fields.from_branch) || null,
      from_area: Number(fields.from_area) || null,
      to_branch: Number(fields.to_branch) || null,
      to_area: Number(fields.to_area) || null,
      expected_date: fields.expected_date || null,
      transporter: Number(fields.transporter) || null,
      lines: lines.filter((l) => l.item).map((l) => ({ item: Number(l.item), unit: Number(l.unit), qty: l.qty || "0" })),
      dispatch,
    };
    const current = t?.id ?? 0;
    try {
      done(current ? await api<Transfer>(`v1/stock-transfers/${current}/`, body, "PATCH") : await api<Transfer>(`v1/companies/${companyId}/stock-transfers/`, body));
    } catch (err) {
      // A refused Dispatch still saved the draft: read it again.
      const kept = err instanceof ApiError ? (err.data as { id?: number } | undefined)?.id : undefined;
      if (dispatch && (kept || current)) api<Transfer>(`v1/stock-transfers/${kept || current}/`).then(done, () => undefined);
      refusal(err);
    }
    setBusy(false);
  };
  const act = async (path: string, body: object = {}) => {
    if (!t) return;
    setError("");
    setBusy(true);
    try {
      done(await api<Transfer>(`v1/stock-transfers/${t.id}/${path}/`, body));
    } catch (err) {
      refusal(err);
    }
    setBusy(false);
  };
  const startReceive = async () => {
    if (!t) return;
    const where = await api<{ default: number | null; places: { id: number; label: string }[] }>(`v1/stock-transfers/${t.id}/receive/`);
    setPlaces(where.places);
    const rows: Record<number, ReceiveRow> = {};
    for (const l of t.lines ?? []) for (const b of l.bins) rows[b.id] = { received_qty: b.qty, put_location: where.default ? String(where.default) : "" };
    setGot(rows);
    setGotDate(today());
    setReceiving(true);
    window.setTimeout(() => document.getElementById("st-receive")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };
  const goTo = (position: number | null) => {
    setProblems(null);
    if (position) window.setTimeout(() => document.getElementById(`st-line-${position}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };
  if (id && !t)
    return (
      <section className="page">
        <PageHeader title="Stock Transfer" crumbs={[{ label: CRUMB, href: transferBase(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const set = (patch: Partial<Fields>) => setFields({ ...fields, ...patch });
  const status = t?.status ?? "draft";
  const branches = setup?.branches ?? [];
  const branchOptions = (keep: string) => branches.filter((b) => b.is_active || String(b.id) === keep).map((b) => ({ value: String(b.id), label: b.name, hint: b.gstin && `GSTIN ${b.gstin}` }));
  const areaOptions = (branch: string, keep: string) =>
    (branches.find((b) => String(b.id) === branch)?.areas ?? []).filter((a) => a.is_active || String(a.id) === keep).map((a) => ({ value: String(a.id), label: a.name }));
  const from = branches.find((b) => String(b.id) === fields.from_branch);
  const to = branches.find((b) => String(b.id) === fields.to_branch);
  const otherGstin = !!from && !!to && from.gstin !== to.gstin;
  const itemOf = (v: string) => items.find((i) => String(i.id) === v);
  const savedLines = t?.lines ?? [];
  const shortAny = receiving && savedLines.some((l) => l.bins.some((b) => Number(got[b.id]?.received_qty ?? b.qty) < Number(b.qty)));
  const title = t?.number ? `Stock Transfer ${t.number}` : t ? "Stock Transfer (Draft)" : "New Stock Transfer";
  const steps: [string, boolean, boolean][] = [
    ["1 Draft", status !== "draft", status === "draft"],
    [`2 Dispatched${t ? ` (goods leave ${t.from_branch_name})` : ""}`, status === "in_transit" || status === "received", false],
    ["3 In Transit", status === "received", status === "in_transit"],
    [`4 Received${t ? ` at ${t.to_branch_name}` : ""}`, status === "received", false],
  ];
  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={
          t?.received_at
            ? `Dispatched as ${t.number}${t.dispatched_at ? ` on ${at(t.dispatched_at)}` : ""} · received on ${at(t.received_at)}`
            : t?.dispatched_at
              ? `Dispatched as ${t.number} on ${at(t.dispatched_at)}`
              : t
                ? `Draft made ${at(t.created_at)} · nothing posted yet`
                : "Nothing is saved until you press Save"
        }
        crumbs={[{ label: CRUMB, href: transferBase(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {t && (status === "draft" || status === "in_transit") && can(session, "cancel") && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel
              </button>
            )}
            {t && <ActionsMenu label="Print" items={printItems(t.id)} />}
            {mayEdit && (
              <button type="button" className="link" disabled={busy} onClick={() => save(false)}>
                Save
              </button>
            )}
            {mayEdit && can(session, "submit") && (
              <button type="button" disabled={busy} onClick={() => save(true)}>
                Dispatch
              </button>
            )}
            {status === "in_transit" && can(session, "submit") && !receiving && (
              <button type="button" disabled={busy} onClick={() => startReceive().catch(setError)}>
                Receive
              </button>
            )}
            {status === "received" && (
              <ActionsMenu
                label="Create"
                main
                items={[{ label: "Transfer back (send goods back)", onClick: () => t && openTab(`${transferBase(companyId)}?form=new&from=${t.to_branch}&to=${t.from_branch}`) }]}
              />
            )}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">
              {t ? `${t.from_branch_name} → ${t.to_branch_name}` : from && to ? `${from.name} → ${to.name}` : "Stock Transfer"}
            </p>
            <p className="item-sub">
              {t?.number && <b>{t.number}</b>}
              <span className={pillClass(status)}>{t?.status_label ?? "New"}</span>
            </p>
            {status !== "cancelled" && (
              <p className="item-sub">
                {steps.map(([label, isDone, now], k) => (
                  <span key={label}>
                    {k > 0 && <span aria-hidden="true"> → </span>}
                    <span className={now ? "pill warn" : isDone ? "pill on" : "pill"}>{label}</span>
                  </span>
                ))}
              </p>
            )}
          </div>
          {status === "in_transit" && (
            <p className="use-note">
              <b>Receive</b> is done at {t?.to_branch_name} when the goods arrive: enter what came per line and the bins they go to. A shortfall needs a reason and goes out of stock as a transit loss (Stock Adjustment), so nothing is left hanging in transit.
            </p>
          )}
          {t?.status === "cancelled" && <p className="use-note">Cancelled: {t.cancel_reason}</p>}
          {cancelling && t && (
            <div className="use-note no-print">
              <label>
                <b>Why is this transfer cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Truck did not come" />
              </label>
              <p className="small">{status === "in_transit" ? `The goods go back into their bins at ${t.from_branch_name} and the stock entries are reversed.` : "The draft is set aside."}</p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep it
                </button>
                <button type="button" className="link danger" onClick={() => act("cancel", { reason })}>
                  Cancel Transfer
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="From and To" open summary={t ? `${t.from_name} → ${t.to_name}` : ""}>
            {mayEdit ? (
              <>
                <div className="item-fields">
                  <label>
                    <span className="req">From Branch</span>
                    <Combobox value={fields.from_branch} onChange={(v) => set({ from_branch: v, from_area: "" })} required options={branchOptions(fields.from_branch)} />
                  </label>
                  <label>
                    From Area
                    <Combobox value={fields.from_area} onChange={(v) => set({ from_area: v })} empty="Whole branch" options={areaOptions(fields.from_branch, fields.from_area)} />
                    <span className="small">Bins and batches are picked from here (earliest expiry first)</span>
                  </label>
                  <label>
                    <span className="req">To Branch</span>
                    <Combobox value={fields.to_branch} onChange={(v) => set({ to_branch: v, to_area: "" })} required options={branchOptions(fields.to_branch).filter((o) => o.value !== fields.from_branch)} />
                    {otherGstin && <span className="error small">Another GSTIN: that is a sale, not a transfer, and cannot be made here.</span>}
                  </label>
                  <label>
                    To Area
                    <Combobox value={fields.to_area} onChange={(v) => set({ to_area: v })} empty="Default store" options={areaOptions(fields.to_branch, fields.to_area)} />
                    <span className="small">Where the goods go on Receive, unless another place is picked then</span>
                  </label>
                  <label>
                    <span className="req">Transfer Date</span>
                    <input type="date" required value={fields.transfer_date} onChange={(e) => set({ transfer_date: e.target.value })} />
                  </label>
                  <label>
                    Expected Arrival
                    <input type="date" value={fields.expected_date} onChange={(e) => set({ expected_date: e.target.value })} />
                  </label>
                  <label>
                    Transporter
                    <Combobox value={fields.transporter} onChange={(v) => set({ transporter: v })} empty="Own vehicle" onType={findTransporters} options={transporters.filter((c) => c.is_active || String(c.id) === fields.transporter).map((c) => ({ value: String(c.id), label: c.name }))} />
                  </label>
                  <label>
                    Vehicle No
                    <input value={fields.vehicle_no} maxLength={20} placeholder="e.g. WB23C4410" onChange={(e) => set({ vehicle_no: e.target.value })} />
                  </label>
                  <label>
                    E-way Bill No
                    <input value={fields.eway_bill_no} maxLength={20} onChange={(e) => set({ eway_bill_no: e.target.value })} />
                  </label>
                  <label>
                    Reason
                    <input value={fields.reason} maxLength={200} placeholder="e.g. Depot stock below safety stock" onChange={(e) => set({ reason: e.target.value })} />
                  </label>
                </div>
              </>
            ) : (
              t && (
                <Facts
                  rows={[
                    ["From Branch", [t.from_branch_name, t.from_gstin && `GSTIN ${t.from_gstin}`].filter(Boolean).join(" · ")],
                    ["From Area", t.from_area ? t.from_name.split(" › ")[1] ?? "" : "Whole branch"],
                    ["To Branch", t.to_branch_name],
                    ["To Area", t.to_area ? t.to_name.split(" › ")[1] ?? "" : "Default store"],
                    ["Transfer Date", shortDate(t.transfer_date)],
                    ["Expected Arrival", shortDate(t.expected_date)],
                    ["Transporter", t.transporter_name || "Own vehicle"],
                    ["Vehicle No", t.vehicle_no],
                    ["E-way Bill No", t.eway_bill_no],
                    ["Value (At Cost)", status === "draft" ? "" : `₹${money(t.value)}`],
                    ["Made By", t.created_by_name],
                    ["Reason", t.reason],
                    ["Received On", shortDate(t.received_date)],
                    ["Shortfall", t.shortfall_reason ? `${t.shortfall_reason} (₹${money(t.shortfall_value)} transit loss)` : ""],
                  ]}
                />
              )
            )}
          </Fold>
          <Fold title="Items" open summary={`${mayEdit ? lines.filter((l) => l.item).length : savedLines.length} items${t && status !== "draft" ? ` · ₹${money(t.value)}` : ""}`}>
            {mayEdit ? (
              <>
                <div className="table-scroll">
                  <table className="grid po-lines">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Item</th>
                        <th className="num">Qty</th>
                        <th>Unit</th>
                        <th className="num">Free at From</th>
                        <th>Taken From (bin · batch)</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l, k) => {
                        const item = itemOf(l.item);
                        const unit = item?.units.find((u) => String(u.unit) === l.unit);
                        const free = item?.in_stock != null && unit ? Number(item.in_stock) / Number(unit.factor || 1) : null;
                        const saved = savedLines.find((s) => s.position === k + 1 && String(s.item) === l.item);
                        const setLine = (patch: Partial<DraftLine>) => setLines((ls) => ls.map((x) => (x.key === l.key ? { ...x, ...patch } : x)));
                        return (
                          <tr key={l.key} id={`st-line-${k + 1}`}>
                            <td>{k + 1}</td>
                            <td className="po-item">
                              <Combobox
                                value={l.item}
                                ariaLabel={`Item on line ${k + 1}`}
                                placeholder="Type to search items…"
                                onChange={(v) => setLine({ item: v, unit: String(itemOf(v)?.stock_unit ?? "") })}
                                options={items.map((i) => ({ value: String(i.id), label: i.name, hint: i.item_number }))}
                                onType={findItems}
                              />
                            </td>
                            <td className="num">
                              <input className="num" inputMode="decimal" aria-label={`Qty on line ${k + 1}`} value={l.qty} onChange={(e) => setLine({ qty: e.target.value })} />
                            </td>
                            <td>
                              <Combobox value={l.unit} ariaLabel={`Unit on line ${k + 1}`} onChange={(v) => setLine({ unit: v })} options={(item?.units ?? []).map((u) => ({ value: String(u.unit), label: u.name }))} />
                            </td>
                            <td className="num">{free == null ? "" : free < Number(l.qty || 0) ? <b className="error">{plain(free)}</b> : plain(free)}</td>
                            <td className="small">
                              {saved ? saved.bins.map((b) => `${binText(b)} (${b.qty_unit})`).join("; ") || <span className="error">Nothing free</span> : "Picked on Save"}
                              {saved?.short_picked && saved.bins.length > 0 && <span className="error"> · only {saved.picked} free</span>}
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
                  <button type="button" className="link" onClick={() => setLines((ls) => [...ls, { key: nextKey++, item: "", unit: "", qty: "" }])}>
                    + Add item
                  </button>
                </div>
                <p className="small">Bins and batches are picked by the rule each time the draft is saved, and again on Dispatch with the stock as it is then. A draft already counts in the Stock Check: Reserved at From and Incoming at To.</p>
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
                      <th className="num">Cost ₹</th>
                      <th className="num">Received</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {savedLines.map((l) => (
                      <tr key={l.id} id={`st-line-${l.position}`}>
                        <td>{l.position}</td>
                        <td>
                          <b>{l.item_name}</b>
                          <div className="small">HSN {l.hsn}</div>
                        </td>
                        <td className="num">{l.qty}</td>
                        <td>{l.unit_name}</td>
                        <td className="small">{l.bins.map((b) => `${binText(b)} (${b.qty_unit})`).join("; ")}</td>
                        <td className="num">{status === "draft" || status === "cancelled" ? "" : money(l.cost)}</td>
                        <td className="num">{l.received ?? "–"}</td>
                        <td>
                          {status === "received" ? (
                            <span className={Number(l.received) < Number(l.qty) ? "pill warn" : "pill on"}>{Number(l.received) < Number(l.qty) ? "Short" : "Received"}</span>
                          ) : status === "in_transit" ? (
                            <span className="pill warn">In transit</span>
                          ) : (
                            <span className="pill">{t?.status_label}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Fold>
          {receiving && t && (
            <div id="st-receive">
              <Fold title={`Receive at ${t.to_branch_name}`} open summary="what came and where it goes">
                <div className="item-fields">
                  <label>
                    <span className="req">Received On</span>
                    <input type="date" required value={gotDate} onChange={(e) => setGotDate(e.target.value)} />
                  </label>
                  {shortAny && (
                    <label className="wide">
                      <span className="req">Shortfall Reason</span>
                      <input value={shortReason} maxLength={200} placeholder="e.g. 2 cartons wet in the truck" onChange={(e) => setShortReason(e.target.value)} />
                      <span className="small">What did not arrive goes out of stock as a transit loss: Dr Stock Adjustment, Cr Stock.</span>
                    </label>
                  )}
                </div>
                <div className="table-scroll">
                  <table className="grid po-lines">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Item</th>
                        <th>Batch · Package</th>
                        <th className="num">Sent</th>
                        <th className="num">Received</th>
                        <th>Put Into</th>
                      </tr>
                    </thead>
                    <tbody>
                      {savedLines.flatMap((l) =>
                        l.bins.map((b) => {
                          const row = got[b.id] ?? { received_qty: b.qty, put_location: "" };
                          const setRow = (patch: Partial<ReceiveRow>) => setGot((g) => ({ ...g, [b.id]: { ...row, ...patch } }));
                          return (
                            <tr key={b.id}>
                              <td>{l.position}</td>
                              <td>{l.item_name}</td>
                              <td>{[b.batch_number, b.package_number].filter(Boolean).join(" · ") || "–"}</td>
                              <td className="num">
                                {b.qty} {l.stock_unit_name}
                              </td>
                              <td className="num">
                                <input className="num" inputMode="decimal" aria-label={`Received of ${l.item_name}`} value={row.received_qty} onChange={(e) => setRow({ received_qty: e.target.value })} />
                              </td>
                              <td className="po-item">
                                <Combobox value={row.put_location} ariaLabel={`Put ${l.item_name} into`} onChange={(v) => setRow({ put_location: v })} options={places.map((p) => ({ value: String(p.id), label: p.label }))} />
                              </td>
                            </tr>
                          );
                        }),
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="buttons">
                  <button type="button" className="link" onClick={() => setReceiving(false)}>
                    Not now
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      act("receive", {
                        received_date: gotDate,
                        shortfall_reason: shortReason,
                        rows: Object.entries(got).map(([bin, r]) => ({ bin: Number(bin), received_qty: r.received_qty || "0", put_location: Number(r.put_location) || null })),
                      })
                    }
                  >
                    Receive
                  </button>
                </div>
              </Fold>
            </div>
          )}
          {t && <StockPosting id={t.id} stamp={`${saved}-${t.status}`} />}
          <p className="small">Only between branches with the same GSTIN. A move to a branch with another GSTIN is a sale in GST law (a tax invoice and a matching purchase) and cannot be made here.</p>
        </div>
        <DocSide type="stock_transfer" id={t?.id ?? null} onChange={() => setFiles((n) => n + 1)}>
          {t && (
            <>
              <SidePanel title="Details">
                <SideRows
                  rows={[
                    ["Made By", t.created_by_name],
                    ["Dispatched By", t.dispatched_by_name],
                    ["Received By", t.received_by_name],
                  ]}
                />
              </SidePanel>
              <SidePanel title="Activity">
                <ChangeLog company={companyId} type="stock_transfer" id={t.id} stamp={JSON.stringify(t) + files} />
              </SidePanel>
            </>
          )}
        </DocSide>
      </div>
      {problems && <ProblemsPopup problems={problems} onGo={goTo} onClose={() => setProblems(null)} />}
      {noLedgers && <MissingLedgersPopup refusal={noLedgers} document="the stock transfer" onClose={() => setNoLedgers(null)} />}
    </section>
  );
}

/** The "Stock Posting" section: each step with what moves in the stock ledger and the books. */
function StockPosting({ id, stamp }: { id: number; stamp: string }) {
  const [data, setData] = useState<Posting | null>(null);
  useEffect(() => {
    api<Posting>(`v1/stock-transfers/${id}/stock-posting/`).then(setData, () => setData(null));
  }, [id, stamp]);
  if (!data) return null;
  return (
    <Fold title="Stock Posting" open summary={data.cancelled ? "Reversed on cancel" : data.steps.filter((s) => s.done).map((s) => s.step).join(", ") || "Posts on Dispatch"}>
      <table className="grid">
        <thead>
          <tr>
            <th>Step</th>
            <th>Stock Ledger</th>
            <th>Books (GL)</th>
            <th className="num">Value ₹</th>
          </tr>
        </thead>
        <tbody>
          {data.steps.map((s) => (
            <tr key={s.step}>
              <td>
                {s.step} {s.done && <span className="ok-note">✓</span>}
              </td>
              <td>{s.stock}</td>
              <td>{s.books}</td>
              <td className="num">{s.value ? money(s.value) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Fold>
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

/** Everything that stopped Dispatch, each with "Go to line". */
function ProblemsPopup(props: { problems: Problem[]; onGo: (line: number | null) => void; onClose: () => void }) {
  return (
    <div className="popup-back" role="presentation">
      <div className="popup grn-check" role="dialog" aria-modal="true" aria-label="This transfer cannot be dispatched yet">
        <h3>This transfer cannot be dispatched yet ({props.problems.length})</h3>
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
        <p className="small">Lower the quantity or pick another From Area, then Dispatch again. Nothing has been dispatched; the draft is kept.</p>
        <div className="popup-actions">
          <button type="button" onClick={props.onClose}>
            OK
          </button>
        </div>
      </div>
    </div>
  );
}
