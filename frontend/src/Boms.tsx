import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { Chevron, LevelPicker, PageHeader, Section } from "./Brand";
import { ColumnSearch } from "./ColumnSearch";
import { Combobox } from "./Combobox";
import { announceCreated, announceSaved, closeThisTab, creatable, useCreated, useNewName } from "./Create";
import { ErrorNote, useOpenParam } from "./ErrorNote";
import { ActionsMenu, useExchange } from "./Exchange";
import { type Item } from "./Items";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { Fold, FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useOnReturn } from "./Refresh";
import { dmy, rupees } from "./Reports";
import { ActionCells, ActionHeads } from "./RowActions";
import { useUnits } from "./Units";

/** Bills of materials (Masters › BOMs; Sidharth, 2026-11-22, preview 14): what one batch
 * of an item needs. An item can have several versions; exactly one is its Default (★). */

type Line = { item: number; item_name: string; qty: string; unit: number; unit_short: string; loss_pct: string };
type Byproduct = { item: number; item_name: string; qty: string; unit: number; unit_short: string; kind: string; kind_label: string; rate: string };
type Material = {
  item: number;
  item_name: string;
  qty: string;
  unit_short: string;
  loss_pct: string;
  issue_qty?: string;
  source: string;
  source_text: string;
  sub_bom: number | null;
  rate?: string | null;
  rate_from?: string;
  cost?: string | null;
  children: Material[];
};
type Version = {
  id: number;
  number: string;
  version: number;
  name: string;
  valid_from: string | null;
  is_default: boolean;
  status: string;
  status_label: string;
  is_active: boolean;
  per_unit: string | null;
};
export type Bom = {
  id: number;
  number: string;
  item: number;
  item_name: string;
  item_number: string;
  version: number;
  name: string;
  is_default: boolean;
  kind: string;
  kind_label: string;
  customer: number | null;
  customer_name: string;
  makes_qty: string;
  makes_unit: number;
  makes_unit_short: string;
  valid_from: string | null;
  notes: string;
  status: string;
  status_label: string;
  is_active: boolean;
  lines: Line[];
  byproducts: Byproduct[];
  material_count: number;
  lock?: LockInfo;
};
type BomDetail = Bom & {
  materials: Material[];
  byproduct_rows: (Byproduct & { value: string })[];
  versions: Version[];
  cost: { materials: string; byproducts: string; net: string; per_unit: string | null; stock_unit: string; missing: string[] };
  job: { sac: string; hsn: string; note: string } | null;
  used_by: string[];
};

const KINDS = [
  { value: "own", label: "Own production" },
  { value: "job_work", label: "Job work for a customer" },
];
const STATUSES = [
  { value: "active", label: "Active" },
  { value: "draft", label: "Draft" },
];
const BY_KINDS = [
  { value: "scrap", label: "Scrap" },
  { value: "by_product", label: "By-product" },
];

/** Quantities as typed: no trailing zeros. */
const plain = (v: string | null | undefined) => (v === null || v === undefined || v === "" ? "" : String(Number(v)));

export function useBoms(item?: number) {
  const [boms, setBoms] = useState<Bom[]>([]);
  const refresh = useCallback(() => api<Bom[]>(`v1/boms/${item ? `?item=${item}` : ""}`).then(setBoms), [item]);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { boms, reload, refresh };
}

function useItemList() {
  const [items, setItems] = useState<Item[]>([]);
  const refresh = useCallback(() => api<Item[]>("v1/items/").then(setItems), []);
  useEffect(() => {
    refresh();
  }, [refresh]);
  useOnReturn(refresh);
  return { items, refresh };
}

const bomTitle = (b: { number: string; item_name: string; version: number }) => `${b.number} · ${b.item_name} · Version ${b.version}`;

/** Masters › BOMs: the list, a BOM's own page (?view=ID) and its form (?form=new|ID|copy-ID). */
export function BomsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const form = hashParam("form");
  const view = Number(hashParam("view")) || null;
  if (form && canEdit) return <BomFormTab form={form} session={session} />;
  if (view) return <BomView id={view} canEdit={canEdit} />;
  return <BomList session={session} canEdit={canEdit} />;
}

function BomList({ session, canEdit }: { session: SignedIn; canEdit: boolean }) {
  const { boms, reload } = useBoms();
  const [selectedId, setSelected] = useState<number | null>(null);
  useCreated("bom_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    if (startName && canEdit) window.location.hash = `#/boms?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const io = useExchange({ master: "boms", noun: "BOMs", session, onImported: reload });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && boms.some((b) => b.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, boms, opened]);
  const selected = boms.find((b) => b.id === selectedId) ?? null;
  return (
    <section className="page">
      <PageHeader
        title="BOMs"
        sub="What one batch of an item needs. An item can have several versions; the ★ default is the one orders start with."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => openTab("#/boms?form=new")}>New BOM</button>}
          </>
        }
      />
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          <table className="pick">
            <thead>
              <tr>
                <th>BOM No</th>
                <th>Item</th>
                <th className="num">Version</th>
                <th>Name</th>
                <th>Default</th>
                <th>Makes</th>
                <th className="num">Materials</th>
                <th>Status</th>
                <ActionHeads />
              </tr>
              <ColumnSearch />
            </thead>
            <tbody>
              {boms.length === 0 && (
                <tr>
                  <td colSpan={10} className="small">
                    No BOMs yet.
                  </td>
                </tr>
              )}
              {boms.map((b) => (
                <tr
                  key={b.id}
                  className={`${b.is_active ? "" : "off"}${selectedId === b.id ? " selected" : ""}`}
                  onClick={() => setSelected(b.id)}
                  onDoubleClick={() => openTab(`#/boms?view=${b.id}`)}
                >
                  <td>{b.number}</td>
                  <td>{b.item_name}</td>
                  <td className="num">{b.version}</td>
                  <td>{b.name}</td>
                  <td>{b.is_default ? <span className="star">★ Default</span> : ""}</td>
                  <td>
                    {plain(b.makes_qty)} {b.makes_unit_short}
                  </td>
                  <td className="num">{b.material_count || ""}</td>
                  <td>{b.is_active ? b.status_label : "Disabled"}</td>
                  <ActionCells
                    canEdit={canEdit}
                    onOpen={() => openTab(canEdit ? `#/boms?form=${b.id}` : `#/boms?view=${b.id}`)}
                    onDuplicate={() => openTab(`#/boms?form=copy-${b.id}`)}
                  />
                </tr>
              ))}
            </tbody>
          </table>
          {boms.length > 0 && <p className="small">Click a BOM to see its details at the right; double-click to open its page.</p>}
        </div>
        <div className="side-col">
          <SidePanel title="BOM Details">
            {selected ? (
              <>
                <SideRows
                  rows={[
                    ["BOM No", selected.number],
                    ["Item", selected.item_name],
                    ["Version", `${selected.version} · ${selected.name}`],
                    ["Default", selected.is_default ? "★ Yes" : "No"],
                    ["Kind", selected.kind_label],
                    ["Customer", selected.customer_name],
                    ["Makes", `${plain(selected.makes_qty)} ${selected.makes_unit_short}`],
                    ["Materials", String(selected.material_count)],
                    ["Status", selected.is_active ? selected.status_label : "Disabled"],
                  ]}
                />
                <p>
                  <button type="button" className="link" onClick={() => openTab(`#/boms?view=${selected.id}`)}>
                    Open
                  </button>
                </p>
              </>
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="bom" id={selected?.id} stamp={JSON.stringify(selected ?? boms.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The materials as a tree: a material with its own BOM folds open to its materials. */
function MaterialRows(props: { rows: Material[]; depth: number; prefix: string; open: Set<string>; toggle: (key: string) => void; costs: boolean }) {
  return (
    <>
      {props.rows.map((m, i) => {
        const key = `${props.prefix}${i + 1}`;
        const isOpen = props.open.has(key);
        return [
          <tr key={key} className={props.depth ? "sub" : ""}>
            <td style={{ paddingLeft: `${8 + props.depth * 20}px`, whiteSpace: "nowrap" }}>
              {m.children.length > 0 ? (
                <button type="button" className="link quiet fold-arrow" aria-expanded={isOpen} onClick={() => props.toggle(key)}>
                  <Chevron open={isOpen} />
                </button>
              ) : null}
              {key}
            </td>
            <td>
              {props.depth ? m.item_name : <b>{m.item_name}</b>}
              {m.children.length > 0 && <> <span className="pill">has its own BOM</span></>}
            </td>
            <td className="num">{plain(m.qty)}</td>
            <td>{m.unit_short}</td>
            <td className="num">{plain(m.loss_pct)}</td>
            <td>
              {m.source === "customer" ? <span className="pill warn">Customer's stock</span> : null}
              {m.source === "customer" ? " quantity only" : m.sub_bom ? <a href={`#/boms?view=${m.sub_bom}`}>{m.source_text}</a> : m.source_text}
            </td>
            {props.costs && <td className="num">{props.depth ? "" : m.rate ? rupees(m.rate) : "no rate"}</td>}
            {props.costs && <td className="num">{props.depth ? <span className="small">(in {key.split(".")[0]})</span> : m.cost ? rupees(m.cost) : "—"}</td>}
          </tr>,
          isOpen && <MaterialRows key={`${key}-c`} rows={m.children} depth={props.depth + 1} prefix={`${key}.`} open={props.open} toggle={props.toggle} costs={props.costs} />,
        ];
      })}
    </>
  );
}

const depthOf = (rows: Material[]): number => (rows.length ? 1 + Math.max(...rows.map((r) => depthOf(r.children))) : 0);
const keysTo = (rows: Material[], level: number, prefix = "", depth = 1): string[] =>
  rows.flatMap((m, i) => {
    const key = `${prefix}${i + 1}`;
    if (!m.children.length || depth >= level) return [];
    return [key, ...keysTo(m.children, level, `${key}.`, depth + 1)];
  });

/** A BOM's own page (preview 14): what it makes, its materials unfolded, by-products, and at
 * the right its versions (★ default, "Make default"), the cost estimate and Activity. */
function BomView({ id, canEdit }: { id: number; canEdit: boolean }) {
  const [b, setB] = useState<BomDetail | null>(null);
  const [error, setError] = useState<unknown>("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [level, setLevel] = useState<number | null>(1);
  const load = useCallback(() => {
    api<BomDetail>(`v1/boms/${id}/`).then(setB, setError);
  }, [id]);
  useEffect(load, [load]);
  useOnReturn(load);
  useCreated("bom_saved", load);
  const close = () =>
    closeThisTab(() => {
      window.location.hash = "#/boms";
    });
  const makeDefault = async (v: number) => {
    setError("");
    try {
      await api(`v1/boms/${v}/make-default/`, {});
      load();
    } catch (err) {
      setError(err);
    }
  };
  if (!b)
    return (
      <section className="page">
        <PageHeader title="BOM" />
        <ErrorNote error={error} />
      </section>
    );
  const toggle = (key: string) => {
    const next = new Set(open);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setOpen(next);
    setLevel(null);
  };
  const pickLevel = (n: number) => {
    setLevel(n);
    setOpen(new Set(keysTo(b.materials, n)));
  };
  const depth = depthOf(b.materials);
  const makes = `${plain(b.makes_qty)} ${b.makes_unit_short}`;
  return (
    <section className="page">
      <PageHeader
        title={bomTitle(b)}
        sub={[b.is_default ? "Default ★" : "", b.is_active ? b.status_label : "Disabled", b.used_by.length ? `used by ${b.used_by.join(", ")}` : ""].filter(Boolean).join(" · ")}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu label="Print" items={[{ label: "Print", onClick: () => window.print() }]} />
            {canEdit && (
              <button type="button" className="link" onClick={() => openTab(`#/boms?form=copy-${b.id}`)}>
                Duplicate as new version
              </button>
            )}
            {canEdit && <button onClick={() => openTab(`#/boms?form=${b.id}`)}>Edit</button>}
          </>
        }
      />
      <ErrorNote error={error} />
      <div className="side-layout">
        <div className="side-main">
          <Fold open title="What It Makes" summary={`${b.item_name} · ${makes} · ${b.kind_label}`}>
            <dl className="kv">
              {(
                [
                  ["Item", `${b.item_name} (${b.item_number})`],
                  ["Version", `${b.version} · "${b.name}"`],
                  ["Makes", makes],
                  ["Default", b.is_default ? "★ Yes (the one orders start with)" : "No"],
                  ["Kind", b.kind_label],
                  ["Customer", b.kind === "job_work" ? b.customer_name || "Any customer" : ""],
                  ["Billed Under SAC", b.job?.sac ?? ""],
                  ["Despatched Under HSN", b.job?.hsn ?? ""],
                  ["Valid From", dmy(b.valid_from)],
                  ["Notes", b.notes],
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
            {b.job?.note && <p className="error">{b.job.note}</p>}
          </Fold>
          <Fold open title={`Materials (for ${makes})`} summary={`${b.materials.length} ${b.materials.length === 1 ? "material" : "materials"} · ₹ ${rupees(b.cost.materials)}`}>
            {depth > 1 && <LevelPicker levels={Math.min(depth - 1, 3)} value={level} onPick={pickLevel} />}
            <div className="wrap">
              <table className="grid">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th className="num">Qty</th>
                    <th>Unit</th>
                    <th className="num">Loss %</th>
                    <th>Comes From</th>
                    <th className="num">Rate ₹</th>
                    <th className="num">Cost ₹</th>
                  </tr>
                </thead>
                <tbody>
                  <MaterialRows rows={b.materials} depth={0} prefix="" open={open} toggle={toggle} costs />
                  <tr>
                    <td colSpan={7} className="num">
                      <b>Materials for {makes}</b>
                    </td>
                    <td className="num">
                      <b>{rupees(b.cost.materials)}</b>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="small">
              "Loss %" is added on top when the order works out what to issue. A material with its own BOM unfolds to its materials; orders and planning use
              that BOM's default version. A customer's goods are counted, never valued. Rates are today's FIFO rate, else the last receipt's: an estimate only.
            </p>
          </Fold>
          <Fold title="By-products and Scrap" open={b.byproduct_rows.length > 0} summary={b.byproduct_rows.length ? `${b.byproduct_rows.length} · ₹ ${rupees(b.cost.byproducts)}` : "None"}>
            {b.byproduct_rows.length > 0 ? (
              <table className="grid">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th className="num">Qty</th>
                    <th>Unit</th>
                    <th>Kind</th>
                    <th className="num">Value ₹</th>
                  </tr>
                </thead>
                <tbody>
                  {b.byproduct_rows.map((x, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>{x.item_name}</td>
                      <td className="num">{plain(x.qty)}</td>
                      <td>{x.unit_short}</td>
                      <td>{Number(x.rate) ? x.kind_label : `${x.kind_label}, no value`}</td>
                      <td className="num">{rupees(x.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="small">None.</p>
            )}
            <p className="small">Received into stock by the production entry later. One with a value lowers the cost of the main item.</p>
          </Fold>
        </div>
        <div className="side-col">
          <SidePanel title={`Versions of ${b.item_name}`}>
            <table className="grid">
              <thead>
                <tr>
                  <th>Ver</th>
                  <th>Name</th>
                  <th>Valid From</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {b.versions.map((v) => (
                  <tr key={v.id} className={v.id === b.id ? "selected" : ""}>
                    <td>
                      <a href={`#/boms?view=${v.id}`}>{v.id === b.id ? <b>{v.version}</b> : v.version}</a>
                    </td>
                    <td>{v.name}</td>
                    <td>{dmy(v.valid_from) || "–"}</td>
                    <td>
                      {v.is_default ? (
                        <span className="pill on">★ Default</span>
                      ) : (
                        <>
                          <span className={v.status === "draft" ? "pill warn" : "pill"}>{v.is_active ? v.status_label : "Disabled"}</span>
                          {canEdit && v.status === "active" && v.is_active && (
                            <button type="button" className="link quiet" onClick={() => makeDefault(v.id)}>
                              Make default
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="small">"Make default" moves the ★: one version is the default at a time. A version used by an order keeps its materials: use "Duplicate as new version".</p>
          </SidePanel>
          <SidePanel title="Cost (Estimate)">
            <SideRows
              rows={[
                ["Materials", `₹ ${rupees(b.cost.materials)}`],
                ["Less By-products", Number(b.cost.byproducts) ? `₹ ${rupees(b.cost.byproducts)}` : ""],
                [`Per ${b.cost.stock_unit}`, b.cost.per_unit ? `₹ ${rupees(b.cost.per_unit)}` : "not known"],
                ...b.versions
                  .filter((v) => v.id !== b.id && v.per_unit)
                  .map((v) => [`Version ${v.version} Per ${b.cost.stock_unit}`, `₹ ${rupees(v.per_unit!)}`] as [string, string]),
              ]}
            />
            {b.cost.missing.length > 0 && <p className="small">No rate yet for {b.cost.missing.join(", ")}.</p>}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="bom" id={b.id} stamp={JSON.stringify(b)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one BOM, alone in its own tab. "copy-ID" starts a new version of the same item. */
function BomFormTab({ form, session }: { form: string; session: SignedIn }) {
  const copy = form.startsWith("copy-");
  const key = Number(form.replace("copy-", ""));
  const [target, setTarget] = useState<BomDetail | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    if (form === "new") return;
    api<BomDetail>(`v1/boms/${key}/`).then(setTarget, setError);
  }, [form, key]);
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("bom_saved", saved);
    closeThisTab(() => {
      window.location.hash = saved ? `#/boms?view=${saved.id}` : "#/boms";
    });
  };
  const title = form === "new" ? "New BOM" : copy ? "Duplicate as new version" : "Edit BOM";
  if (form !== "new" && !target)
    return (
      <section className="page">
        <PageHeader title={title} />
        <ErrorNote error={error} />
      </section>
    );
  return <BomForm title={title} bom={copy ? null : target} copyOf={copy ? target : null} session={session} onDone={finish} />;
}

type LineRow = { item: string; qty: string; unit: string; loss_pct: string };
type ByRow = { item: string; qty: string; unit: string; kind: string; rate: string };

function BomForm(props: { title: string; bom: BomDetail | null; copyOf: BomDetail | null; session: SignedIn; onDone: (saved?: { id: number; name: string }) => void }) {
  const b = props.bom;
  const from = b ?? props.copyOf;
  const mayAddMasters = props.session.permissions.includes("masters.edit");
  const { items, refresh: refreshItems } = useItemList();
  const { units } = useUnits();
  const [parties, setParties] = useState<{ id: number; name: string; customer_number: string }[]>([]);
  useEffect(() => {
    api<{ id: number; name: string; customer_number: string }[]>("v1/parties/").then(setParties, () => setParties([]));
  }, []);
  const startItem = hashParam("item");
  const startName = useNewName();
  const [item, setItem] = useState(from ? String(from.item) : (startItem ?? ""));
  const [name, setName] = useState(b ? b.name : (startName ?? ""));
  const [makesQty, setMakesQty] = useState(from ? plain(from.makes_qty) : "1");
  const [makesUnit, setMakesUnit] = useState(from ? String(from.makes_unit) : "");
  const [kind, setKind] = useState(from?.kind ?? "own");
  const [customer, setCustomer] = useState(from?.customer ? String(from.customer) : "");
  const [validFrom, setValidFrom] = useState(b?.valid_from ?? "");
  const [status, setStatus] = useState(b?.status ?? "active");
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [makeDefault, setMakeDefault] = useState(false);
  const [disabled, setDisabled] = useState(b ? !b.is_active : false);
  const [lines, setLines] = useState<LineRow[]>(
    from ? from.lines.map((l) => ({ item: String(l.item), qty: plain(l.qty), unit: String(l.unit), loss_pct: plain(l.loss_pct) })) : [{ item: "", qty: "", unit: "", loss_pct: "0" }],
  );
  const [byRows, setByRows] = useState<ByRow[]>(
    from ? from.byproducts.map((x) => ({ item: String(x.item), qty: plain(x.qty), unit: String(x.unit), kind: x.kind, rate: plain(x.rate) })) : [],
  );
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const locked = (field: string) => isLocked(b?.lock, field);
  const materialsLocked = !!b?.lock?.in_use.length;
  const itemById = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);
  const unitById = useMemo(() => new Map(units.map((u) => [u.id, u])), [units]);
  const unitsOf = (id: string) =>
    (itemById.get(Number(id))?.units ?? []).map((u) => unitById.get(u.unit)).filter((u): u is NonNullable<typeof u> => !!u).map((u) => ({ value: String(u.id), label: u.short_name }));
  const stockUnit = (id: string) => {
    const it = itemById.get(Number(id));
    return it ? String(it.stock_unit) : "";
  };
  useEffect(() => {
    if (item && !makesUnit && items.length) setMakesUnit(stockUnit(item));
  }, [item, items]); // eslint-disable-line react-hooks/exhaustive-deps
  const newItem = mayAddMasters ? creatable("item", "items", refreshItems) : undefined;
  const itemOptions = (keep: string) =>
    items.filter((x) => (x.is_active && x.maintain_stock) || String(x.id) === keep).map((x) => ({ value: String(x.id), label: `${x.name} (${x.item_number})` }));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = {
      item: Number(item) || null,
      name,
      makes_qty: makesQty,
      makes_unit: Number(makesUnit) || null,
      kind,
      customer: kind === "job_work" && customer ? Number(customer) : null,
      valid_from: validFrom || null,
      status,
      notes,
      lines: lines.filter((l) => l.item).map((l) => ({ item: Number(l.item), qty: l.qty || "0", unit: Number(l.unit) || null, loss_pct: l.loss_pct || "0" })),
      byproducts: byRows.filter((x) => x.item).map((x) => ({ item: Number(x.item), qty: x.qty || "0", unit: Number(x.unit) || null, kind: x.kind, rate: x.rate || "0" })),
    };
    try {
      if (b) {
        const saved = await api<BomDetail>(`v1/boms/${b.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: saved.id, name: bomTitle(saved) });
      } else {
        const made = await api<BomDetail>("v1/boms/", { ...body, is_default: makeDefault });
        announceCreated("bom", { id: made.id, name: bomTitle(made) });
        props.onDone({ id: made.id, name: bomTitle(made) });
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };
  const setLine = (i: number, change: Partial<LineRow>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...change } : l)));
  const setBy = (i: number, change: Partial<ByRow>) => setByRows(byRows.map((l, j) => (j === i ? { ...l, ...change } : l)));
  const chosen = itemById.get(Number(item));
  return (
    <FormPage
      title={props.title}
      sub={b ? bomTitle(b) : props.copyOf ? `New version of ${props.copyOf.item_name}, copied from version ${props.copyOf.version}` : undefined}
      formId="bom-form"
      onSubmit={save}
      onCancel={() => props.onDone()}
      busy={busy}
      error={error}
      disabled={b ? { value: disabled, set: setDisabled } : undefined}
      switches={
        !b ? (
          <label className="check">
            <input type="checkbox" checked={makeDefault} onChange={(e) => setMakeDefault(e.target.checked)} />
            Make this the default
          </label>
        ) : undefined
      }
      tips={
        <p className="small">
          The first active version of an item becomes its default by itself. A Draft is never offered to orders. A material that is a customer's own goods
          (Customer Provided) may only be on a job work BOM.
        </p>
      }
      activity={b ? <ChangeLog type="bom" id={b.id} stamp={JSON.stringify(b)} /> : undefined}
    >
      <InUseNote lock={b?.lock} />
      <Section title="What It Makes">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Item</span>
            {b || props.copyOf ? (
              <input value={`${from!.item_name} (${from!.item_number})`} disabled />
            ) : (
              <Combobox
                value={item}
                required
                placeholder="Type to search items…"
                onChange={(v) => {
                  setItem(v);
                  setMakesUnit(stockUnit(v));
                }}
                options={itemOptions(item)}
                create={newItem}
              />
            )}
          </label>
          <label>
            Version Name
            <input value={name} placeholder={b ? `Version ${b.version}` : "e.g. New pouch, Nov 2026"} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            <span className="req">Makes Qty</span>
            <Locked on={locked("makes_qty")}>
              <input className="num" inputMode="decimal" required value={makesQty} onChange={(e) => setMakesQty(e.target.value)} />
            </Locked>
          </label>
          <label>
            <span className="req">Makes Unit</span>
            <Locked on={locked("makes_unit")}>
              <Combobox value={makesUnit} required onChange={setMakesUnit} options={unitsOf(item)} />
            </Locked>
          </label>
          <label>
            <span className="req">Kind</span>
            <Locked on={locked("kind")}>
              <Combobox value={kind} onChange={setKind} options={KINDS} />
            </Locked>
          </label>
          {kind === "job_work" && (
            <label>
              Customer
              <Combobox value={customer} onChange={setCustomer} empty="Any customer" options={parties.filter((p) => p.customer_number).map((p) => ({ value: String(p.id), label: p.name }))} />
            </label>
          )}
          <label>
            Valid From
            <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </label>
          <label>
            <span className="req">Status</span>
            <Combobox value={status} onChange={setStatus} options={STATUSES} />
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
        {kind === "job_work" && chosen && !(chosen.item_type === "service" && chosen.delivery_hsn) && (
          <p className="small">
            Job work is billed under a SAC code and despatched under an HSN code: make {chosen.name} a Service that keeps stock, with its SAC code and its
            Delivery HSN (Masters › Items).
          </p>
        )}
      </Section>
      <Section title={`Materials (for ${makesQty || "1"} ${unitById.get(Number(makesUnit))?.short_name ?? ""})`}>
        {materialsLocked && <p className="small">This version is in use, so its materials cannot change. Use "Duplicate as new version".</p>}
        <div className="wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>#</th>
                <th>Item</th>
                <th className="num">Qty</th>
                <th>Unit</th>
                <th className="num">Loss %</th>
                <th>Comes From</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => {
                const it = itemById.get(Number(l.item));
                const from = !it ? "" : it.default_request_type === "customer_provided" ? "Customer's stock" : it.default_request_type === "manufacture" ? "Manufactured" : "Purchased";
                return (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td style={{ minWidth: "16rem" }}>
                      <Combobox
                        value={l.item}
                        ariaLabel="Material"
                        placeholder="Type to search items…"
                        onChange={(v) => setLine(i, { item: v, unit: stockUnit(v) })}
                        options={itemOptions(l.item).filter((o) => o.value !== item)}
                        create={newItem}
                      />
                    </td>
                    <td>
                      <input className="num" inputMode="decimal" aria-label="Quantity" disabled={materialsLocked} value={l.qty} onChange={(e) => setLine(i, { qty: e.target.value })} />
                    </td>
                    <td>
                      <Combobox value={l.unit} ariaLabel="Unit" onChange={(v) => setLine(i, { unit: v })} options={unitsOf(l.item)} />
                    </td>
                    <td>
                      <input className="num" inputMode="decimal" aria-label="Loss %" disabled={materialsLocked} value={l.loss_pct} onChange={(e) => setLine(i, { loss_pct: e.target.value })} />
                    </td>
                    <td className="small">{from}</td>
                    <td>
                      {!materialsLocked && (
                        <button type="button" className="link danger" onClick={() => setLines(lines.filter((_, j) => j !== i))}>
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!materialsLocked && (
          <div className="buttons">
            <button type="button" className="link" onClick={() => setLines([...lines, { item: "", qty: "", unit: "", loss_pct: "0" }])}>
              + Add material
            </button>
          </div>
        )}
        <p className="small">
          Quantities are for the quantity this BOM makes. "Loss %" is added on top when an order works out what to issue (2.4 kg + 0.5% = 2.412 kg). "Comes
          From" follows the item's Main Fulfilment; a material with a default BOM of its own is Manufactured.
        </p>
      </Section>
      <Section title="By-products and Scrap">
        {byRows.length > 0 && (
          <div className="wrap">
            <table className="grid">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Item</th>
                  <th className="num">Qty</th>
                  <th>Unit</th>
                  <th>Kind</th>
                  <th className="num">Value per Unit ₹</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {byRows.map((x, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td style={{ minWidth: "14rem" }}>
                      <Combobox value={x.item} ariaLabel="By-product" placeholder="Type to search items…" onChange={(v) => setBy(i, { item: v, unit: stockUnit(v) })} options={itemOptions(x.item)} create={newItem} />
                    </td>
                    <td>
                      <input className="num" inputMode="decimal" aria-label="Quantity" value={x.qty} onChange={(e) => setBy(i, { qty: e.target.value })} />
                    </td>
                    <td>
                      <Combobox value={x.unit} ariaLabel="Unit" onChange={(v) => setBy(i, { unit: v })} options={unitsOf(x.item)} />
                    </td>
                    <td>
                      <Combobox value={x.kind} ariaLabel="Kind" onChange={(v) => setBy(i, { kind: v })} options={BY_KINDS} />
                    </td>
                    <td>
                      <input className="num" inputMode="decimal" aria-label="Value per unit" value={x.rate} onChange={(e) => setBy(i, { rate: e.target.value })} />
                    </td>
                    <td>
                      <button type="button" className="link danger" onClick={() => setByRows(byRows.filter((_, j) => j !== i))}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="buttons">
          <button type="button" className="link" onClick={() => setByRows([...byRows, { item: "", qty: "", unit: "", kind: "scrap", rate: "0" }])}>
            + Add by-product or scrap
          </button>
        </div>
        <p className="small">Scrap with no value is just counted. A by-product with a value lowers the cost of the main item.</p>
      </Section>
    </FormPage>
  );
}

/** The "BOMs" box on an item's own page: its versions, the ★ default, Open and New BOM. */
export function ItemBoms({ item, canEdit }: { item: number; canEdit: boolean }) {
  const { boms } = useBoms(item);
  const def = boms.find((x) => x.is_default);
  return (
    <Fold title="BOMs" open={boms.length > 0} summary={boms.length ? `${boms.length} ${boms.length === 1 ? "version" : "versions"}${def ? `, default version ${def.version}` : ", no default"}` : "No BOM yet"}>
      {boms.length > 0 && (
        <table className="grid">
          <thead>
            <tr>
              <th>BOM No</th>
              <th className="num">Version</th>
              <th>Name</th>
              <th>Makes</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {boms.map((x) => (
              <tr key={x.id}>
                <td>{x.number}</td>
                <td className="num">{x.version}</td>
                <td>{x.name}</td>
                <td>
                  {plain(x.makes_qty)} {x.makes_unit_short}
                </td>
                <td>{x.is_default ? <span className="pill on">★ Default</span> : x.is_active ? x.status_label : "Disabled"}</td>
                <td>
                  <button type="button" className="link" onClick={() => openTab(`#/boms?view=${x.id}`)}>
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && (
        <div className="buttons">
          <button type="button" className="link" onClick={() => openTab(`#/boms?form=new&item=${item}`)}>
            New BOM
          </button>
        </div>
      )}
    </Fold>
  );
}
