import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { DocSide } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { longDate } from "./Companies";
import { announceSaved, closeThisTab, useCreated } from "./Create";
import { makeDeliveryNote } from "./DeliveryNotes";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useOnReturn } from "./Refresh";

/** Entry > Sales > Pick List: where the stores take a sales order's goods from,
 * bin and batch per item (Sidharth, 2026-11-19, preview 6). Made by itself when
 * the order is submitted; an open list can be changed; Submit makes it final. */

type Row = {
  id?: number;
  location: number;
  location_name: string;
  batch: number | null;
  batch_number: string;
  expiry: string | null;
  area?: number | null;
  area_name?: string;
  package?: number | null;
  package_number?: string;
  package_label?: string;
  package_left?: string;
  /** In the item's stock unit. */
  qty: string;
  qty_unit?: string;
};
type PickItem = {
  order_line: number;
  position: number;
  item: number;
  item_name: string;
  unit_name: string;
  stock_unit_name: string;
  factor: string;
  ordered: string;
  picked: string;
  picked_stock: string;
  short: string;
  short_stock: string;
  rows: Row[];
};
export type PickBrief = {
  id: number;
  number: string;
  status: string;
  status_label: string;
  all_in: boolean;
  full_count: number;
  item_count: number;
  text: string;
  despatch_from: string;
};
type PickList = PickBrief & {
  order: number;
  order_number: string;
  customer_name: string;
  delivery_date: string | null;
  branch: number;
  area: number | null;
  order_place: string;
  notes: string;
  cancel_reason: string;
  created_at: string;
  created_by_name: string;
  submitted_at: string | null;
  submitted_by_name: string;
  items?: PickItem[];
};
type Place = { value: string; label: string; full: number; count: number };
type Spot = {
  location: number;
  location_name: string;
  area: number | null;
  area_name: string;
  batch: number | null;
  batch_number: string;
  package: number | null;
  package_number: string;
  package_label: string;
  expiry: string | null;
  free: string;
};

const VIEWS: [string, string][] = [
  ["open", "Open"],
  ["picked", "Picked"],
  ["delivered", "Delivered"],
  ["cancelled", "Cancelled"],
  ["all", "All"],
];
const base = (companyId: number) => `#/companies/${companyId}/pick-lists`;
const CRUMB = "Entry › Sales › Pick List";
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const at = (iso: string) => `${shortDate(iso)} at ${new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`;
const pillClass = (s: string) => (s === "open" || s === "picked" || s === "delivered" ? "pill on" : "pill");
const plain = (n: number) => String(Number(n.toFixed(3)));
const can = (session: SignedIn, action: string) => session.permissions.includes(`sales.${action}`) || session.permissions.includes(`stock.${action}`);

export const pickPdf = (id: number, download = false) => openTab(`/api/v1/pick-lists/${id}/pdf/${download ? "?download=1" : ""}`);

export function PickListsPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const view = Number(hashParam("view"));
  if (view > 0) return <PickView companyId={companyId} id={view} session={session} />;
  return <PickListList companyId={companyId} />;
}

const COLUMNS: [key: string, label: string, text: (p: PickList) => string][] = [
  ["number", "Pick List No", (p) => p.number],
  ["date", "Made On", (p) => shortDate(p.created_at)],
  ["order", "Sales Order", (p) => p.order_number],
  ["customer", "Customer", (p) => p.customer_name],
  ["despatch", "Despatch From", (p) => p.despatch_from],
  ["stock", "Stock", (p) => (p.all_in ? "All in stock" : "Short")],
  ["status", "Status", (p) => p.status_label],
];

function PickListList({ companyId }: { companyId: number }) {
  const [view, setView] = useState("open");
  const [lists, setLists] = useState<PickList[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<PickList[]>(`v1/companies/${companyId}/pick-lists/?view=${view}`)
      .then(setLists)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("pick_list_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      lists.filter((p) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          return words.every((w) => text(p).toLowerCase().includes(w));
        }),
      ),
    [lists, search],
  );
  const selected = lists.find((p) => p.id === selectedId) ?? null;
  const printing = usePrintMenu({ title: `Pick lists: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`, scope: "" });
  const open = (id: number) => openTab(`${base(companyId)}?view=${id}`);
  return (
    <section className="page">
      <PageHeader
        title="Pick List"
        crumbs={[{ label: "Entry › Sales", href: base(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "pick list" : "pick lists"} · made when a sales order is submitted`}
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
                {COLUMNS.map(([key, label]) => (
                  <th key={key}>{label}</th>
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
                    No pick lists match.
                  </td>
                </tr>
              )}
              {shown.map((p) => (
                <tr
                  key={p.id}
                  tabIndex={0}
                  className={selected?.id === p.id ? "selected" : ""}
                  onClick={() => setSelectedId(selected?.id === p.id ? null : p.id)}
                  onDoubleClick={() => open(p.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") open(p.id);
                  }}
                >
                  <td>
                    <b>{p.number}</b>
                  </td>
                  <td className="nowrap">{shortDate(p.created_at)}</td>
                  <td>{p.order_number}</td>
                  <td>{p.customer_name}</td>
                  <td>{p.despatch_from}</td>
                  <td>
                    <span className={p.all_in ? "pill on" : "pill warn"}>{p.all_in ? "All in stock" : "Short"}</span>
                  </td>
                  <td>
                    <span className={pillClass(p.status)}>{p.status_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small no-print">Click a pick list to see it at the right; double-click or press Enter to open it in a new tab.</p>}
        </div>
        {selected && (
          <div className="side-col" aria-label="Pick list details">
            <SidePanel title={selected.number} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Sales Order", selected.order_number],
                  ["Customer", selected.customer_name],
                  ["Despatch From", selected.despatch_from],
                  ["Made On", at(selected.created_at)],
                  ["Stock", `${selected.full_count} of ${selected.item_count} items fully picked`],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => open(selected.id)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => pickPdf(selected.id)}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="pick_list" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// One list --------------------------------------------------------------------

/** One row being edited: area › bin › batch › package, each a picker value
 * ("" not chosen yet, "none" for no batch or no package). */
type DraftRow = { key: number; line: number; area: string; bin: string; batch: string; pkg: string; qty: string };
let nextKey = 1;
const idOr = (n: number | null | undefined) => (n == null ? "none" : String(n));

function PickView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const [pick, setPick] = useState<PickList | null>(null);
  const [error, setError] = useState<unknown>("");
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [spots, setSpots] = useState<Record<number, Spot[]>>({});
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const [busy, setBusy] = useState(false);
  const reload = useCallback(() => {
    api<PickList>(`v1/pick-lists/${id}/`)
      .then(setPick)
      .catch((err) => setError(err));
  }, [id]);
  useEffect(reload, [reload]);
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const done = (p: PickList) => {
    setPick(p);
    setEditing(false);
    setCancelling(false);
    announceSaved("pick_list_saved", { id: p.id, name: p.number });
  };
  const act = async (path: string, body: object = {}) => {
    setError("");
    setBusy(true);
    try {
      done(await api<PickList>(`v1/pick-lists/${id}/${path}/`, body));
    } catch (err) {
      setError(err);
    }
    setBusy(false);
  };
  const startEdit = () => {
    if (!pick?.items) return;
    setRows(
      pick.items.flatMap((i) =>
        i.rows.map((r) => ({
          key: nextKey++,
          line: i.order_line,
          area: idOr(r.area),
          bin: String(r.location),
          batch: idOr(r.batch),
          pkg: idOr(r.package),
          qty: r.qty,
        })),
      ),
    );
    for (const i of pick.items)
      api<Spot[]>(`v1/pick-lists/${id}/places/?item=${i.item}`).then((s) => setSpots((all) => ({ ...all, [i.item]: s })), () => undefined);
    setEditing(true);
  };
  const save = async () => {
    setError("");
    setBusy(true);
    try {
      const body = {
        rows: rows
          .filter((r) => r.bin)
          .map((r) => ({
            order_line: r.line,
            location: Number(r.bin),
            batch: r.batch && r.batch !== "none" ? Number(r.batch) : null,
            package: r.pkg && r.pkg !== "none" ? Number(r.pkg) : null,
            qty: r.qty || "0",
          })),
      };
      done(await api<PickList>(`v1/pick-lists/${id}/`, body, "PATCH"));
    } catch (err) {
      setError(err);
    }
    setBusy(false);
  };
  if (!pick)
    return (
      <section className="page">
        <PageHeader title="Pick List" crumbs={[{ label: CRUMB, href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const isOpen = pick.status === "open";
  const printItems = [
    { label: "Pick list", onClick: () => pickPdf(pick.id) },
    { label: "Download PDF", onClick: () => pickPdf(pick.id, true) },
  ];
  return (
    <section className="page">
      <PageHeader
        title={`Pick List ${pick.number}`}
        sub={pick.submitted_at ? `Submitted on ${at(pick.submitted_at)} by ${pick.submitted_by_name}` : undefined}
        crumbs={[{ label: CRUMB, href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {isOpen && can(session, "create") && !editing && (
              <button type="button" className="link" onClick={startEdit}>
                Edit
              </button>
            )}
            {editing && (
              <button type="button" className="link" onClick={() => setEditing(false)}>
                Discard changes
              </button>
            )}
            {pick.status !== "cancelled" && can(session, "cancel") && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel
              </button>
            )}
            <ActionsMenu label="Print" items={printItems} />
            {editing && (
              <button type="button" disabled={busy} onClick={save}>
                Save
              </button>
            )}
            {isOpen && !editing && can(session, "submit") && (
              <button type="button" disabled={busy} onClick={() => act("submit")}>
                Submit
              </button>
            )}
            {(pick.status === "picked" || pick.status === "delivered") && (
              <ActionsMenu
                label="Create"
                main
                items={[
                  {
                    label: "Delivery Note",
                    onClick: () => makeDeliveryNote(companyId, pick.id).catch((err) => setError(err)),
                    disabled: pick.status !== "picked" || !can(session, "create"),
                    title: pick.status === "delivered" ? "This list has gone out on a delivery note" : undefined,
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
            <p className="doc-title">{pick.customer_name}</p>
            <p className="item-sub">
              <b>
                Made from Sales Order{" "}
                <a href={`#/companies/${companyId}/sales-orders?view=${pick.order}`} target="_blank" rel="noreferrer">
                  {pick.order_number}
                </a>{" "}
                on {at(pick.created_at)}
              </b>
              <span className={pillClass(pick.status)}>{pick.status_label}</span>
              <span className="tag">{pick.despatch_from}</span>
            </p>
          </div>
          {pick.status === "cancelled" && <p className="use-note">Cancelled: {pick.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this pick list cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Order on hold" />
              </label>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep it
                </button>
                <button type="button" className="link danger" onClick={() => act("cancel", { reason })}>
                  Cancel pick list
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          {pick.status !== "cancelled" && <p className={pick.all_in ? "ok-note" : "use-note"}>{pick.text}</p>}
          {isOpen && !editing && can(session, "create") && (
            <DespatchFrom pick={pick} busy={busy} onPick={(place) => act("despatch", { place })} />
          )}
          <Fold title="What to Pick" open>
            {editing ? (
              <EditRows pick={pick} rows={rows} setRows={setRows} spots={spots} />
            ) : (
              <div className="table-scroll">
                <table className="grid">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item</th>
                      <th className="num">Ordered</th>
                      <th>Area</th>
                      <th>Bin</th>
                      <th>Batch</th>
                      <th>Expiry</th>
                      <th>Package</th>
                      <th className="num">Pick Qty</th>
                      <th className="num">In Stock Unit</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(pick.items ?? []).flatMap((i) => {
                      const status =
                        Number(i.short) > 0 ? <b className="error">Short {i.short} {i.unit_name}</b> : <span className="ok-note">✓ Full</span>;
                      const rowsHere = i.rows.length ? i.rows : [null];
                      return rowsHere.map((r, n) => (
                        <tr key={`${i.order_line}-${r?.id ?? "none"}`}>
                          <td>{n === 0 ? i.position : ""}</td>
                          <td>{n === 0 ? i.item_name : ""}</td>
                          <td className="num">{n === 0 ? `${i.ordered} ${i.unit_name}` : ""}</td>
                          <td>{r?.area_name}</td>
                          <td>{r ? r.location_name : <span className="small">Nothing found</span>}</td>
                          <td>{r?.batch_number}</td>
                          <td>{shortDate(r?.expiry ?? null)}</td>
                          <td>
                            {r?.package_number ? (
                              <>
                                <b>{r.package_number}</b>
                                {Number(r.qty) < Number(r.package_left) && (
                                  <span className="small">
                                    {" "}
                                    · opened: {r.qty} of {r.package_left} {i.stock_unit_name}
                                  </span>
                                )}
                              </>
                            ) : r ? (
                              <span className="small">No package</span>
                            ) : (
                              ""
                            )}
                          </td>
                          <td className="num">{r ? `${r.qty_unit} ${i.unit_name}` : ""}</td>
                          <td className="num">{r ? `${r.qty} ${i.stock_unit_name}` : ""}</td>
                          <td>{n === 0 ? status : ""}</td>
                        </tr>
                      ));
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="small">
              Chosen automatically on Submit of the sales order: only bins in the Despatch From area (or the whole branch), earliest expiry first, then
              oldest received. Numbered packages are taken whole, lowest number first, and only the last one is opened. A batch held back (Quarantine
              or Rejected) is never picked. Stock and packages on an open or picked pick list are kept aside, so the next order does not pick the same
              bags.
            </p>
          </Fold>
        </div>
        <DocSide type="pick_list" id={pick.id} onChange={() => setFiles((n) => n + 1)}>
          <SidePanel title="Details">
            <SideRows
              rows={[
                ["Sales Order", pick.order_number],
                ["Delivery Date", pick.delivery_date ? longDate(pick.delivery_date) : ""],
                ["Despatch From", pick.despatch_from],
                ["Made By", pick.created_by_name],
                ["Items", `${pick.full_count} of ${pick.item_count} fully picked`],
              ]}
            />
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="pick_list" id={pick.id} stamp={JSON.stringify(pick) + files} />
          </SidePanel>
        </DocSide>
      </div>
    </section>
  );
}

/** "Despatch From" on an open list (Sidharth, 2026-11-20, preview 10): any
 * stock-keeping branch or area of one, each showing how many of the order's
 * items it holds in full; "Pick again" chooses bins and batches there by the
 * same rule. The order's Bill From does not change. */
function DespatchFrom({ pick, busy, onPick }: { pick: PickList; busy: boolean; onPick: (place: string) => void }) {
  const here = pick.area ? `a${pick.area}` : `b${pick.branch}`;
  const [places, setPlaces] = useState<Place[]>([]);
  const [place, setPlace] = useState(here);
  const load = useCallback(() => {
    api<Place[]>(`v1/pick-lists/${pick.id}/despatch/`).then(setPlaces, () => undefined);
  }, [pick.id]);
  useEffect(load, [load, pick]);
  useOnReturn(load);
  useEffect(() => setPlace(here), [here]);
  const chosen = places.find((p) => p.value === place);
  const options = places.map((p) => ({
    value: p.value,
    label: p.label,
    hint: `${p.value === pick.order_place ? "(the order's) · " : ""}${p.full} of ${p.count} items${p.count && p.full === p.count ? " ✓" : ""}`,
  }));
  return (
    <Fold title="Despatch From" open={!pick.all_in} summary={pick.despatch_from}>
      <div className="item-fields">
        <label>
          <span>Despatch From</span>
          <Combobox value={place} onChange={setPlace} ariaLabel="Despatch From" options={options} />
        </label>
        <div className="buttons">
          <button type="button" disabled={busy || !chosen || place === here} onClick={() => onPick(place)}>
            {chosen && place !== here ? `Pick again from ${chosen.label}` : "Pick again"}
          </button>
          <p className="small">
            Chooses bins and batches again by the same rule, in the new place only. The sales order&apos;s Bill From does not change.
          </p>
        </div>
      </div>
    </Fold>
  );
}

/** The rows of an open list, to change: per item, Area › Bin › Batch ›
 * Package (each offering only what is free in the one before it) and the
 * quantity in the stock unit; "+ Add package" for another row. */
function EditRows(p: { pick: PickList; rows: DraftRow[]; setRows: (f: (r: DraftRow[]) => DraftRow[]) => void; spots: Record<number, Spot[]> }) {
  const set = (key: number, patch: Partial<DraftRow>) => p.setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const uniq = (list: { value: string; label: string; hint?: string }[]) => list.filter((o, n) => list.findIndex((x) => x.value === o.value) === n);
  return (
    <div className="table-scroll">
      <table className="grid po-lines">
        <thead>
          <tr>
            <th>#</th>
            <th>Item</th>
            <th className="num">Ordered</th>
            <th>Area</th>
            <th>Bin</th>
            <th>Batch</th>
            <th>Package</th>
            <th className="num">Pick Qty (Stock Unit)</th>
            <th className="num">Still Short</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(p.pick.items ?? []).flatMap((i) => {
            const mine = p.rows.filter((r) => r.line === i.order_line);
            const want = Number(i.ordered) * Number(i.factor);
            const got = mine.reduce((s, r) => s + (Number(r.qty) || 0), 0);
            const short = Math.max(want - got, 0);
            const all = p.spots[i.item] ?? [];
            const lines = [...mine, null];
            return lines.map((r, n) => {
              const inArea = r ? all.filter((s) => idOr(s.area) === r.area) : [];
              const inBin = r ? inArea.filter((s) => String(s.location) === r.bin) : [];
              const inBatch = r ? inBin.filter((s) => idOr(s.batch) === r.batch) : [];
              const free = (list: Spot[]) => `${plain(list.reduce((t, s) => t + Number(s.free), 0))} ${i.stock_unit_name} free`;
              const areas = uniq(all.map((s) => ({ value: idOr(s.area), label: s.area_name || s.location_name, hint: free(all.filter((x) => x.area === s.area)) })));
              const bins = uniq(inArea.map((s) => ({ value: String(s.location), label: s.location_name, hint: free(inArea.filter((x) => x.location === s.location)) })));
              const batches = uniq(
                inBin.map((s) => ({
                  value: idOr(s.batch),
                  label: s.batch_number || "No batch",
                  hint: [s.expiry && `exp ${shortDate(s.expiry)}`, free(inBin.filter((x) => x.batch === s.batch))].filter(Boolean).join(" · "),
                })),
              );
              const packages = uniq(
                inBatch.map((s) => ({
                  value: idOr(s.package),
                  label: s.package_number || "No package",
                  hint: free([s]),
                })),
              );
              const cell = (value: string, options: { value: string; label: string; hint?: string }[], label: string, patch: (v: string) => Partial<DraftRow>) => (
                <Combobox value={value} onChange={(v) => r && set(r.key, patch(v))} ariaLabel={`${label} for ${i.item_name}`} placeholder="Type to search…" options={options} />
              );
              return (
                <tr key={`${i.order_line}-${r?.key ?? "add"}`}>
                  <td>{n === 0 ? i.position : ""}</td>
                  <td>{n === 0 ? i.item_name : ""}</td>
                  <td className="num">{n === 0 ? `${i.ordered} ${i.unit_name} (${plain(want)} ${i.stock_unit_name})` : ""}</td>
                  {r ? (
                    <>
                      <td>{cell(r.area, areas, "Area", (v) => ({ area: v, bin: "", batch: "", pkg: "" }))}</td>
                      <td>{cell(r.bin, bins, "Bin", (v) => ({ bin: v, batch: "", pkg: "" }))}</td>
                      <td>{cell(r.batch, batches, "Batch", (v) => ({ batch: v, pkg: "" }))}</td>
                      <td>{cell(r.pkg, packages, "Package", (v) => ({ pkg: v }))}</td>
                    </>
                  ) : (
                    <td colSpan={4}>
                      <button
                        type="button"
                        className="link"
                        onClick={() => p.setRows((rs) => [...rs, { key: nextKey++, line: i.order_line, area: "", bin: "", batch: "", pkg: "", qty: plain(short) }])}
                      >
                        + Add package
                      </button>
                    </td>
                  )}
                  <td className="num">
                    {r && (
                      <span>
                        <input className="num" inputMode="decimal" aria-label={`Pick qty for ${i.item_name}`} value={r.qty} onChange={(e) => set(r.key, { qty: e.target.value })} />{" "}
                        {i.stock_unit_name}
                      </span>
                    )}
                  </td>
                  <td className="num">{n === 0 ? (short > 0 ? <b className="error">{plain(short)} {i.stock_unit_name}</b> : "✓") : ""}</td>
                  <td>
                    {r && (
                      <button type="button" className="link danger" aria-label="Remove row" onClick={() => p.setRows((rs) => rs.filter((x) => x.key !== r.key))}>
                        ✕
                      </button>
                    )}
                  </td>
                </tr>
              );
            });
          })}
        </tbody>
      </table>
    </div>
  );
}
