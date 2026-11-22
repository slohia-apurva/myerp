import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { DocSide } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { money } from "./Companies";
import { announceSaved, closeThisTab, creatable, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";

/** Entry > Production > Manufacturing Order (Sidharth, 2026-11-23, preview 15d in mockups/planning):
 * what to make, how much, by when and with which BOM version (the item's ★ default to start with, or
 * any other active version). The BOM's materials are fixed by the version; "+ Add material" adds extra
 * lines that stay open until the order is completed or closed. Pack Details (MRP, USP, Batch No, Pkd
 * Date, Best Before, Expiry Date, Packing Notes) are copied from the item and the version and print on
 * the batch sheet. The order posts nothing: a draft or open order reserves its materials and counts
 * its output as Incoming in the Stock Check. */

type Line = {
  position: number;
  item: number;
  item_name: string;
  item_number: string;
  unit: number;
  unit_name: string;
  per_unit: string;
  loss_pct: string;
  required: string;
  issued: string;
  from_bom: boolean;
  source_text: string;
  free: string | null;
  short: boolean;
  bom_note: string;
};
type Byproduct = {
  item: number;
  item_name: string;
  qty: string;
  unit_name: string;
  kind_label: string;
};
type Cost = {
  materials: string;
  per_unit: string | null;
  unit_name: string;
  per_stock_unit: string | null;
  stock_unit_name: string;
  missing: string[];
};
type Materials = {
  lines: Line[];
  byproducts: Byproduct[];
  cost: Cost | null;
  bom?: number | null;
};
type Order = Materials & {
  id: number;
  company: number;
  number: string;
  status: string;
  status_label: string;
  branch: number;
  branch_name: string;
  order_date: string;
  item: number;
  item_name: string;
  item_number: string;
  qty: string;
  unit: number;
  unit_name: string;
  stock_qty: string;
  stock_unit_name: string;
  made_qty: string;
  bom: number;
  bom_number: string;
  bom_version: number;
  bom_name: string;
  bom_default: boolean;
  kind: string;
  kind_label: string;
  customer: number | null;
  customer_name: string;
  start_date: string;
  due_date: string;
  sales_order: number | null;
  sales_order_number: string;
  materials_from: number | null;
  materials_from_name: string;
  goods_to: number | null;
  goods_to_name: string;
  supervisor: number | null;
  supervisor_name: string;
  notes: string;
  mrp: string | null;
  usp: string | null;
  usp_per: number | null;
  usp_per_name: string;
  batch_no: string;
  pkd_date: string | null;
  best_before_value: number | null;
  best_before_unit: string;
  expiry_date: string | null;
  packing_notes: string;
  cancel_reason: string;
  created_by_name: string;
  created_at: string;
  submitted_at: string | null;
  submitted_by_name: string;
  closed_at: string | null;
};
type Unit = {
  unit: number;
  name: string;
  whole_numbers: boolean;
  factor: string;
};
type Version = {
  id: number;
  number: string;
  version: number;
  name: string;
  is_default: boolean;
  kind: string;
  customer: number | null;
  packing_notes: string;
};
type Make = {
  id: number;
  name: string;
  item_number: string;
  stock_unit: number;
  sales_unit: number | null;
  units: Unit[];
  mrp: string | null;
  usp: string | null;
  usp_per: number | null;
  batch_no: string;
  best_before_value: number | null;
  best_before_unit: string;
  versions: Version[];
};
type Material = {
  id: number;
  name: string;
  item_number: string;
  stock_unit: number;
  customer_goods: boolean;
  units: Unit[];
};
type Setup = {
  branches: {
    id: number;
    name: string;
    is_active: boolean;
    areas: { id: number; name: string; is_active: boolean }[];
  }[];
  people: { id: number; name: string }[];
  makes: Make[];
  materials: Material[];
  customers: { id: number; name: string }[];
  units: { id: number; name: string }[];
  sales_orders: { id: number; number: string; customer_name: string }[];
};

const VIEWS: [string, string][] = [
  ["open", "Open (Not Started, In Process)"],
  ["draft", "Draft"],
  ["completed", "Completed"],
  ["closed", "Closed"],
  ["cancelled", "Cancelled"],
  ["all", "All"],
];
const PERIODS = [
  { value: "days", label: "Days" },
  { value: "months", label: "Months" },
];
export const ordersBase = (companyId: number) =>
  `#/companies/${companyId}/manufacturing-orders`;
const CRUMB = "Entry › Production › Manufacturing Order";
const shortDate = (iso: string | null) =>
  iso ? iso.slice(0, 10).split("-").reverse().join("/") : "";
const at = (iso: string) =>
  `${shortDate(iso)} at ${new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`;
const pillClass = (s: string) =>
  s === "not_started" || s === "in_process"
    ? "pill on"
    : s === "draft"
      ? "pill warn"
      : "pill";
const plain = (n: number) => String(Number(n.toFixed(3)));
const can = (session: SignedIn, action: string) =>
  session.permissions.includes(`production.${action}`);
const today = () => new Date().toLocaleDateString("en-CA");
const versionLabel = (v: {
  version: number;
  name: string;
  is_default: boolean;
}) =>
  `${v.is_default ? "★ " : ""}Version ${v.version}${v.name ? ` · ${v.name}` : ""}`;
const pdf = (id: number, download = false) =>
  openTab(
    `/api/v1/manufacturing-orders/${id}/pdf/${download ? "?download=1" : ""}`,
  );
const printItems = (id: number) => [
  { label: "Manufacturing Order (Batch Sheet)", onClick: () => pdf(id) },
  { label: "Download PDF", onClick: () => pdf(id, true) },
];
const NEXT_DOCS = [
  { label: "Material Issue (coming later)", disabled: true },
  { label: "Production Entry (coming later)", disabled: true },
];

/** The Pkd Date plus the Best Before period, the day before it ends (as the server works it out). */
export function expiryOf(pkd: string, value: string, unit: string): string {
  const n = Number(value);
  if (!pkd || !value || !Number.isInteger(n) || n <= 0) return "";
  const [y, m, d] = pkd.split("-").map(Number);
  let day: Date;
  if (unit === "months") {
    const month = m - 1 + n;
    const year = y + Math.floor(month / 12);
    const last = new Date(Date.UTC(year, (month % 12) + 1, 0)).getUTCDate();
    day = new Date(Date.UTC(year, month % 12, Math.min(d, last)));
  } else day = new Date(Date.UTC(y, m - 1, d + n));
  day.setUTCDate(day.getUTCDate() - 1);
  return day.toISOString().slice(0, 10);
}

export function ManufacturingOrdersPage({
  companyId,
  session,
}: {
  companyId: number;
  session: SignedIn;
}) {
  const view = Number(hashParam("view"));
  if (view > 0)
    return <OrderView companyId={companyId} id={view} session={session} />;
  if (hashParam("form") === "new")
    return <OrderView companyId={companyId} id={0} session={session} />;
  return <OrderList companyId={companyId} session={session} />;
}

const COLUMNS: [
  key: string,
  label: string,
  text: (o: Order) => string,
  num?: boolean,
][] = [
  ["number", "MO No", (o) => o.number || "Draft"],
  ["date", "Date", (o) => shortDate(o.order_date)],
  ["branch", "Branch", (o) => o.branch_name],
  ["item", "Item", (o) => o.item_name],
  ["qty", "Qty", (o) => `${o.qty} ${o.unit_name}`, true],
  ["bom", "BOM Version", (o) => `${o.bom_number} · ${o.bom_version}`],
  ["batch", "Batch No", (o) => o.batch_no],
  ["due", "Due", (o) => shortDate(o.due_date)],
  ["status", "Status", (o) => o.status_label],
];

function OrderList({
  companyId,
  session,
}: {
  companyId: number;
  session: SignedIn;
}) {
  const [view, setView] = useState(hashParam("status") ?? "open");
  const [rows, setRows] = useState<Order[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Order[]>(`v1/companies/${companyId}/manufacturing-orders/?view=${view}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("manufacturing_order_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      rows.filter((o) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "")
            .toLowerCase()
            .split(/\s+/)
            .filter(Boolean);
          return words.every((w) => text(o).toLowerCase().includes(w));
        }),
      ),
    [rows, search],
  );
  const selected = rows.find((o) => o.id === selectedId) ?? null;
  const printing = usePrintMenu({
    title: `Manufacturing orders: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`,
    scope: "",
  });
  const open = (id: number) => openTab(`${ordersBase(companyId)}?view=${id}`);
  return (
    <section className="page">
      <PageHeader
        title="Manufacturing Orders"
        crumbs={[{ label: "Entry › Production", href: ordersBase(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "order" : "orders"} · what to make, how much, by when and with which BOM version`}
        actions={
          <>
            {printing.buttons}
            {can(session, "create") && (
              <button
                type="button"
                onClick={() => openTab(`${ordersBase(companyId)}?form=new`)}
              >
                New Manufacturing Order
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
              <Combobox
                value={view}
                onChange={setView}
                ariaLabel="Show"
                options={VIEWS.map(([value, label]) => ({ value, label }))}
              />
            </span>
            {Object.values(search).some(Boolean) && (
              <button
                type="button"
                className="link"
                onClick={() => setSearch({})}
              >
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
                      onChange={(ev) =>
                        setSearch({ ...search, [key]: ev.target.value })
                      }
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && (
                <tr>
                  <td colSpan={COLUMNS.length} className="small">
                    No manufacturing orders match.
                  </td>
                </tr>
              )}
              {shown.map((o) => (
                <tr
                  key={o.id}
                  tabIndex={0}
                  className={selected?.id === o.id ? "selected" : ""}
                  onClick={() =>
                    setSelectedId(selected?.id === o.id ? null : o.id)
                  }
                  onDoubleClick={() => open(o.id)}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter") open(o.id);
                  }}
                >
                  <td>
                    <b>{o.number || "Draft"}</b>
                  </td>
                  <td className="nowrap">{shortDate(o.order_date)}</td>
                  <td>{o.branch_name}</td>
                  <td>{o.item_name}</td>
                  <td className="num nowrap">
                    {o.qty} {o.unit_name}
                  </td>
                  <td>
                    {o.bom_number} · {o.bom_default ? "★ " : ""}
                    {o.bom_version}
                  </td>
                  <td>{o.batch_no}</td>
                  <td className="nowrap">{shortDate(o.due_date)}</td>
                  <td>
                    <span className={pillClass(o.status)}>
                      {o.status_label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && (
            <p className="small no-print">
              Click an order to see it at the right; double-click or press Enter
              to open it in a new tab.
            </p>
          )}
        </div>
        {selected && (
          <div className="side-col" aria-label="Manufacturing order details">
            <SidePanel
              title={selected.number || "Draft"}
              tag={selected.status_label}
            >
              <SideRows
                rows={[
                  ["Item", selected.item_name],
                  ["Qty", `${selected.qty} ${selected.unit_name}`],
                  [
                    "BOM Version",
                    `${selected.bom_number} · ${versionLabel({ version: selected.bom_version, name: selected.bom_name, is_default: selected.bom_default })}`,
                  ],
                  ["Branch", selected.branch_name],
                  ["Start", shortDate(selected.start_date)],
                  ["Due", shortDate(selected.due_date)],
                  ["Batch No", selected.batch_no],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => open(selected.id)}>
                  Open
                </button>
                <button
                  type="button"
                  className="link"
                  onClick={() => pdf(selected.id)}
                >
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog
                company={companyId}
                type="manufacturing_order"
                id={selected.id}
                stamp={JSON.stringify(selected)}
              />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// One order ------------------------------------------------------------------------

type Fields = {
  branch: string;
  order_date: string;
  item: string;
  qty: string;
  unit: string;
  bom: string;
  customer: string;
  start_date: string;
  due_date: string;
  sales_order: string;
  materials_from: string;
  goods_to: string;
  supervisor: string;
  notes: string;
  mrp: string;
  usp: string;
  usp_per: string;
  batch_no: string;
  pkd_date: string;
  best_before_value: string;
  best_before_unit: string;
  expiry_date: string;
  packing_notes: string;
};
type Added = {
  key: number;
  item: string;
  unit: string;
  per_unit: string;
  loss_pct: string;
};
let nextKey = 1;
const emptyAdded = (): Added => ({
  key: nextKey++,
  item: "",
  unit: "",
  per_unit: "",
  loss_pct: "",
});
const str = (v: number | string | null | undefined) =>
  v == null ? "" : String(v);
const blank = (): Fields => ({
  branch: "",
  order_date: today(),
  item: "",
  qty: "",
  unit: "",
  bom: "",
  customer: "",
  start_date: today(),
  due_date: today(),
  sales_order: "",
  materials_from: "",
  goods_to: "",
  supervisor: "",
  notes: "",
  mrp: "",
  usp: "",
  usp_per: "",
  batch_no: "",
  pkd_date: today(),
  best_before_value: "",
  best_before_unit: "days",
  expiry_date: "",
  packing_notes: "",
});
const fieldsOf = (o: Order): Fields => ({
  branch: str(o.branch),
  order_date: o.order_date,
  item: str(o.item),
  qty: o.qty,
  unit: str(o.unit),
  bom: str(o.bom),
  customer: str(o.customer),
  start_date: o.start_date,
  due_date: o.due_date,
  sales_order: str(o.sales_order),
  materials_from: str(o.materials_from),
  goods_to: str(o.goods_to),
  supervisor: str(o.supervisor),
  notes: o.notes,
  mrp: str(o.mrp),
  usp: str(o.usp),
  usp_per: str(o.usp_per),
  batch_no: o.batch_no,
  pkd_date: str(o.pkd_date),
  best_before_value: str(o.best_before_value),
  best_before_unit: o.best_before_unit || "days",
  expiry_date: str(o.expiry_date),
  packing_notes: o.packing_notes,
});
const addedOf = (o: Order): Added[] =>
  o.lines
    .filter((l) => !l.from_bom)
    .map((l) => ({
      key: nextKey++,
      item: str(l.item),
      unit: str(l.unit),
      per_unit: l.per_unit,
      loss_pct: Number(l.loss_pct) ? l.loss_pct : "",
    }));

function OrderView({
  companyId,
  id,
  session,
}: {
  companyId: number;
  id: number;
  session: SignedIn;
}) {
  const base = ordersBase(companyId);
  const [o, setO] = useState<Order | null>(null);
  const [error, setError] = useState<unknown>("");
  const [fields, setFields] = useState<Fields>(blank);
  const [added, setAdded] = useState<Added[]>([]);
  const [expiryTyped, setExpiryTyped] = useState(false);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [preview, setPreview] = useState<Materials | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [closing, setClosing] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const [busy, setBusy] = useState(false);
  const take = useCallback((x: Order) => {
    setO(x);
    setFields(fieldsOf(x));
    setAdded(addedOf(x));
    setExpiryTyped(
      !!x.expiry_date &&
        x.expiry_date !==
          expiryOf(
            str(x.pkd_date),
            str(x.best_before_value),
            x.best_before_unit,
          ),
    );
  }, []);
  useEffect(() => {
    if (id)
      api<Order>(`v1/manufacturing-orders/${id}/`).then(take, (err) =>
        setError(err),
      );
  }, [id, take]);
  const status = o?.status ?? "draft";
  const draft = status === "draft";
  const open = status === "not_started" || status === "in_process";
  const mayEdit = (draft || open) && can(session, "create");
  const refreshSetup = useCallback(
    () =>
      api<Setup>(`v1/companies/${companyId}/manufacturing-orders/form/`).then(
        setSetup,
        (err) => setError(err),
      ),
    [companyId],
  );
  useEffect(() => {
    if (mayEdit) refreshSetup();
  }, [mayEdit, refreshSetup]);
  // A draft shows the materials of its version for the quantity as the fields change.
  const previewUrl =
    mayEdit && draft && fields.item && Number(fields.qty) > 0
      ? `v1/companies/${companyId}/manufacturing-orders/materials/?item=${fields.item}&bom=${fields.bom}&qty=${encodeURIComponent(fields.qty)}&unit=${fields.unit}&branch=${fields.branch}&customer=${fields.customer}`
      : "";
  useEffect(() => {
    if (!previewUrl) return setPreview(null);
    const timer = window.setTimeout(
      () => api<Materials>(previewUrl).then(setPreview, () => setPreview(null)),
      300,
    );
    return () => window.clearTimeout(timer);
  }, [previewUrl]);
  const mayAddMasters = session.permissions.includes("masters.edit");
  const newPerson = mayAddMasters
    ? creatable("sales_person", "sales-people", refreshSetup)
    : undefined;
  const newMaterial = mayAddMasters
    ? creatable("item", "items", refreshSetup)
    : undefined;
  const newCustomer = mayAddMasters
    ? creatable("customer", "customers", refreshSetup)
    : undefined;
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base;
    });
  const done = (x: Order) => {
    take(x);
    setCancelling(false);
    setClosing(false);
    announceSaved("manufacturing_order_saved", {
      id: x.id,
      name: x.number || "Draft",
    });
    if (!id)
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}${base}?view=${x.id}`,
      );
  };
  const run = async (call: () => Promise<Order>, afterRefusal?: () => void) => {
    setError("");
    setBusy(true);
    try {
      done(await call());
    } catch (err) {
      afterRefusal?.();
      setError(err);
    }
    setBusy(false);
  };
  const save = (submit: boolean) => {
    const num = (v: string) => (v.trim() === "" ? null : v.trim());
    const body = {
      ...fields,
      branch: Number(fields.branch) || null,
      item: Number(fields.item) || null,
      unit: Number(fields.unit) || null,
      bom: Number(fields.bom) || null,
      customer: Number(fields.customer) || null,
      sales_order: Number(fields.sales_order) || null,
      materials_from: Number(fields.materials_from) || null,
      goods_to: Number(fields.goods_to) || null,
      supervisor: Number(fields.supervisor) || null,
      usp_per: Number(fields.usp_per) || null,
      mrp: num(fields.mrp),
      usp: num(fields.usp),
      pkd_date: fields.pkd_date || null,
      best_before_value: num(fields.best_before_value),
      expiry_date: fields.expiry_date || null,
      added: added
        .filter((a) => a.item)
        .map((a) => ({
          item: Number(a.item),
          unit: Number(a.unit),
          per_unit: a.per_unit || "0",
          loss_pct: a.loss_pct || "0",
        })),
      submit,
    };
    const current = o?.id ?? 0;
    // A refused Submit still saved the draft: read it again.
    return run(
      () =>
        current
          ? api<Order>(`v1/manufacturing-orders/${current}/`, body, "PATCH")
          : api<Order>(`v1/companies/${companyId}/manufacturing-orders/`, body),
      () => {
        if (submit && current)
          api<Order>(`v1/manufacturing-orders/${current}/`).then(
            take,
            () => undefined,
          );
      },
    );
  };
  if (id && !o)
    return (
      <section className="page">
        <PageHeader
          title="Manufacturing Order"
          crumbs={[{ label: CRUMB, href: base }]}
        />
        <ErrorNote error={error} />
      </section>
    );
  const branches = setup?.branches ?? [];
  const branch = branches.find((b) => String(b.id) === fields.branch);
  const areaOptions = (branch?.areas ?? [])
    .filter((a) => a.is_active)
    .map((a) => ({ value: String(a.id), label: a.name }));
  const makes = setup?.makes ?? [];
  const make = makes.find((i) => String(i.id) === fields.item);
  const versions = make?.versions ?? [];
  const version =
    versions.find((v) => String(v.id) === fields.bom) ?? versions[0];
  const jobWork = (version?.kind ?? o?.kind) === "job_work";
  const materials = setup?.materials ?? [];
  const materialOf = (v: string) => materials.find((i) => String(i.id) === v);
  const unitOptions = (setup?.units ?? []).map((u) => ({
    value: String(u.id),
    label: u.name,
  }));
  const withExpiry = (next: Fields): Fields =>
    expiryTyped
      ? next
      : {
          ...next,
          expiry_date: expiryOf(
            next.pkd_date,
            next.best_before_value,
            next.best_before_unit,
          ),
        };
  const set = (patch: Partial<Fields>) =>
    setFields(withExpiry({ ...fields, ...patch }));
  /** A new item: its units, its ★ version and its Pack Details from the item master. */
  const pickItem = (value: string) => {
    const m = makes.find((i) => String(i.id) === value);
    const v = m?.versions[0];
    set({
      item: value,
      unit: str(m?.sales_unit ?? m?.stock_unit),
      bom: str(v?.id),
      customer: v?.kind === "job_work" ? str(v.customer) : "",
      mrp: str(m?.mrp),
      usp: str(m?.usp),
      usp_per: str(m?.usp_per),
      batch_no: m?.batch_no ?? "",
      best_before_value: str(m?.best_before_value),
      best_before_unit: m?.best_before_unit || "days",
      packing_notes: v?.packing_notes ?? "",
    });
  };
  const pickVersion = (value: string) => {
    const v = versions.find((x) => String(x.id) === value);
    set({
      bom: value,
      packing_notes: v?.packing_notes ?? "",
      customer:
        v?.kind === "job_work" ? fields.customer || str(v.customer) : "",
    });
  };
  // Pkd Date follows the Start Date until it is changed by hand.
  const setStart = (value: string) =>
    set({
      start_date: value,
      pkd_date: fields.pkd_date === fields.start_date ? value : fields.pkd_date,
      due_date: fields.due_date < value ? value : fields.due_date,
    });
  const shown: Materials | null = draft && mayEdit ? preview : o;
  const bomLines = (shown?.lines ?? []).filter((l) => l.from_bom);
  const savedAdded = (o?.lines ?? []).filter((l) => !l.from_bom);
  const qtyNow = Number(fields.qty) || 0;
  const unitOf = make?.units.find((u) => String(u.unit) === fields.unit);
  const title = o?.number
    ? `Manufacturing Order ${o.number}`
    : o
      ? "Manufacturing Order (Draft)"
      : "New Manufacturing Order";
  const sub = o?.submitted_at
    ? `Submitted as ${o.number} on ${at(o.submitted_at)}`
    : o
      ? `Draft made ${at(o.created_at)} · nothing reserved until saved`
      : "Nothing is saved until you press Save";
  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={sub}
        crumbs={[{ label: CRUMB, href: base }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {o && (draft || open) && can(session, "cancel") && !cancelling && (
              <button
                type="button"
                className="link danger"
                onClick={() => setCancelling(true)}
              >
                Cancel
              </button>
            )}
            {o && open && can(session, "submit") && !closing && (
              <button
                type="button"
                className="link danger"
                onClick={() => setClosing(true)}
              >
                Close MO
              </button>
            )}
            {o && <ActionsMenu label="Print" items={printItems(o.id)} />}
            {mayEdit && (
              <button
                type="button"
                className={draft ? "link" : undefined}
                disabled={busy}
                onClick={() => save(false)}
              >
                Save
              </button>
            )}
            {mayEdit && draft && can(session, "submit") && (
              <button type="button" disabled={busy} onClick={() => save(true)}>
                Submit
              </button>
            )}
            {o && !draft && status !== "cancelled" && (
              <ActionsMenu label="Create" main items={NEXT_DOCS} />
            )}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">
              {o
                ? `${o.item_name} · ${o.qty} ${o.unit_name}`
                : "Manufacturing Order"}
            </p>
            <p className="item-sub">
              {o?.number && <b>{o.number}</b>}
              <span className={pillClass(status)}>
                {o?.status_label ?? "New"}
              </span>
              {o && Number(o.made_qty) > 0 && (
                <span className="small">Made so far: {o.made_qty}</span>
              )}
            </p>
          </div>
          {o?.status === "cancelled" && (
            <p className="use-note">Cancelled: {o.cancel_reason}</p>
          )}
          {cancelling && o && (
            <div className="use-note no-print">
              <label>
                <b>Why is this order cancelled?</b>
                <input
                  autoFocus
                  value={reason}
                  onChange={(ev) => setReason(ev.target.value)}
                  placeholder="e.g. Customer's order changed"
                />
              </label>
              <p className="small">
                An order can be cancelled only while nothing has been issued to
                it. Its materials stop being reserved.
              </p>
              <div className="buttons">
                <button
                  type="button"
                  className="link"
                  onClick={() => setCancelling(false)}
                >
                  Keep it
                </button>
                <button
                  type="button"
                  className="link danger"
                  disabled={busy}
                  onClick={() =>
                    run(() =>
                      api<Order>(`v1/manufacturing-orders/${o.id}/cancel/`, {
                        reason,
                      }),
                    )
                  }
                >
                  Cancel Order
                </button>
              </div>
            </div>
          )}
          {closing && o && (
            <div className="use-note no-print">
              <p>
                <b>Close this order as it stands?</b> What is still to make is
                no longer planned, and materials not yet issued stop being
                reserved.
              </p>
              <div className="buttons">
                <button
                  type="button"
                  className="link"
                  onClick={() => setClosing(false)}
                >
                  Keep it open
                </button>
                <button
                  type="button"
                  className="link danger"
                  disabled={busy}
                  onClick={() =>
                    run(() =>
                      api<Order>(`v1/manufacturing-orders/${o.id}/close/`, {}),
                    )
                  }
                >
                  Close MO
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold
            title="What to Make"
            open
            summary={
              o
                ? `${o.item_name} · ${o.qty} ${o.unit_name} · due ${shortDate(o.due_date)}`
                : ""
            }
          >
            {mayEdit ? (
              <div className="item-fields">
                {draft ? (
                  <>
                    <label>
                      <span className="req">Branch</span>
                      <Combobox
                        value={fields.branch}
                        onChange={(v) =>
                          set({ branch: v, materials_from: "", goods_to: "" })
                        }
                        required
                        options={branches
                          .filter(
                            (b) =>
                              b.is_active || String(b.id) === fields.branch,
                          )
                          .map((b) => ({ value: String(b.id), label: b.name }))}
                      />
                    </label>
                    <label className="wide">
                      <span className="req">Item</span>
                      <Combobox
                        value={fields.item}
                        onChange={pickItem}
                        required
                        placeholder="Items that have an active BOM…"
                        options={makes.map((i) => ({
                          value: String(i.id),
                          label: i.name,
                          hint: i.item_number,
                        }))}
                      />
                    </label>
                    <label>
                      <span className="req">Qty</span>
                      <input
                        className="num"
                        inputMode="decimal"
                        required
                        value={fields.qty}
                        onChange={(ev) => set({ qty: ev.target.value })}
                      />
                      {unitOf && Number(unitOf.factor) !== 1 && qtyNow > 0 && (
                        <span className="small">
                          = {plain(qtyNow * Number(unitOf.factor))}{" "}
                          {
                            make?.units.find((u) => u.unit === make.stock_unit)
                              ?.name
                          }
                        </span>
                      )}
                    </label>
                    <label>
                      <span className="req">Unit</span>
                      <Combobox
                        value={fields.unit}
                        onChange={(v) => set({ unit: v })}
                        required
                        options={(make?.units ?? []).map((u) => ({
                          value: String(u.unit),
                          label: u.name,
                        }))}
                      />
                    </label>
                    <label className="wide">
                      <span className="req">BOM Version</span>
                      <Combobox
                        value={str(version?.id)}
                        onChange={pickVersion}
                        required
                        options={versions.map((v) => ({
                          value: String(v.id),
                          label: versionLabel(v),
                          hint: v.number,
                        }))}
                      />
                      <span className="small">
                        Starts on the ★ default version; any active version can
                        be picked.
                      </span>
                    </label>
                  </>
                ) : (
                  o && (
                    <div className="wide">
                      <Facts
                        rows={[
                          ["Branch", o.branch_name],
                          ["Item", o.item_name],
                          [
                            "Qty",
                            `${o.qty} ${o.unit_name}${o.stock_unit_name !== o.unit_name ? ` (${o.stock_qty} ${o.stock_unit_name})` : ""}`,
                          ],
                          [
                            "BOM Version",
                            `${o.bom_number} · ${versionLabel({ version: o.bom_version, name: o.bom_name, is_default: o.bom_default })}`,
                          ],
                          ["Customer", o.customer_name],
                          ["Order Date", shortDate(o.order_date)],
                          ["Due Date", shortDate(o.due_date)],
                          ["Sales Order", o.sales_order_number],
                          ["Materials From", o.materials_from_name],
                          ["Goods Go To", o.goods_to_name],
                        ]}
                      />
                      <p className="small">
                        Once submitted, only the Start Date, Supervisor, Notes
                        and added materials can change. Close the order and make
                        a new one to change the rest.
                      </p>
                    </div>
                  )
                )}
                {jobWork && draft && (
                  <label>
                    <span className="req">Customer</span>
                    <Combobox
                      value={fields.customer}
                      onChange={(v) => set({ customer: v })}
                      required
                      create={newCustomer}
                      options={(setup?.customers ?? []).map((c) => ({
                        value: String(c.id),
                        label: c.name,
                      }))}
                    />
                    <span className="small">
                      Job work: only this customer's goods are counted
                    </span>
                  </label>
                )}
                {draft && (
                  <label>
                    <span className="req">Order Date</span>
                    <input
                      type="date"
                      required
                      value={fields.order_date}
                      onChange={(ev) => set({ order_date: ev.target.value })}
                    />
                  </label>
                )}
                <label>
                  <span className="req">Start Date</span>
                  <input
                    type="date"
                    required
                    value={fields.start_date}
                    max={draft ? undefined : fields.due_date}
                    onChange={(ev) =>
                      draft
                        ? setStart(ev.target.value)
                        : set({ start_date: ev.target.value })
                    }
                  />
                </label>
                {draft && (
                  <>
                    <label>
                      <span className="req">Due Date</span>
                      <input
                        type="date"
                        required
                        value={fields.due_date}
                        min={fields.start_date}
                        onChange={(ev) => set({ due_date: ev.target.value })}
                      />
                    </label>
                    <label>
                      Sales Order
                      <Combobox
                        value={fields.sales_order}
                        onChange={(v) => set({ sales_order: v })}
                        empty="None"
                        options={(setup?.sales_orders ?? []).map((s) => ({
                          value: String(s.id),
                          label: s.number,
                          hint: s.customer_name,
                        }))}
                      />
                    </label>
                    <label>
                      Materials From
                      <Combobox
                        value={fields.materials_from}
                        onChange={(v) => set({ materials_from: v })}
                        empty="Whole branch"
                        options={areaOptions}
                      />
                    </label>
                    <label>
                      Goods Go To
                      <Combobox
                        value={fields.goods_to}
                        onChange={(v) => set({ goods_to: v })}
                        empty="Default store"
                        options={areaOptions}
                      />
                    </label>
                  </>
                )}
                <label>
                  Supervisor
                  <Combobox
                    value={fields.supervisor}
                    onChange={(v) => set({ supervisor: v })}
                    empty="None"
                    create={newPerson}
                    options={(setup?.people ?? []).map((p) => ({
                      value: String(p.id),
                      label: p.name,
                    }))}
                  />
                </label>
                <label className="wide">
                  Notes
                  <input
                    value={fields.notes}
                    maxLength={500}
                    onChange={(ev) => set({ notes: ev.target.value })}
                  />
                </label>
              </div>
            ) : (
              o && (
                <Facts
                  rows={[
                    ["Branch", o.branch_name],
                    ["Item", o.item_name],
                    [
                      "Qty",
                      `${o.qty} ${o.unit_name}${o.stock_unit_name !== o.unit_name ? ` (${o.stock_qty} ${o.stock_unit_name})` : ""}`,
                    ],
                    [
                      "BOM Version",
                      `${o.bom_number} · ${versionLabel({ version: o.bom_version, name: o.bom_name, is_default: o.bom_default })}`,
                    ],
                    ["Customer", o.customer_name],
                    ["Order Date", shortDate(o.order_date)],
                    ["Start Date", shortDate(o.start_date)],
                    ["Due Date", shortDate(o.due_date)],
                    ["Sales Order", o.sales_order_number],
                    ["Materials From", o.materials_from_name],
                    ["Goods Go To", o.goods_to_name],
                    ["Supervisor", o.supervisor_name],
                    ["Notes", o.notes],
                  ]}
                />
              )
            )}
          </Fold>
          <Fold
            title="Pack Details"
            open
            summary={[
              fields.batch_no && `Batch ${fields.batch_no}`,
              fields.expiry_date && `Expiry ${shortDate(fields.expiry_date)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          >
            {mayEdit && draft ? (
              <>
                <div className="item-fields">
                  <label>
                    MRP (₹)
                    <input
                      className="num"
                      inputMode="decimal"
                      value={fields.mrp}
                      onChange={(ev) => set({ mrp: ev.target.value })}
                    />
                  </label>
                  <label>
                    USP (₹)
                    <input
                      className="num"
                      inputMode="decimal"
                      value={fields.usp}
                      onChange={(ev) => set({ usp: ev.target.value })}
                    />
                    <span className="small">Unit Selling Price</span>
                  </label>
                  <label>
                    USP Per
                    <Combobox
                      value={fields.usp_per}
                      onChange={(v) => set({ usp_per: v })}
                      empty="None"
                      options={unitOptions}
                    />
                  </label>
                  <label>
                    Batch No
                    <input
                      value={fields.batch_no}
                      maxLength={60}
                      onChange={(ev) => set({ batch_no: ev.target.value })}
                    />
                  </label>
                  <label>
                    Pkd Date
                    <input
                      type="date"
                      value={fields.pkd_date}
                      onChange={(ev) => set({ pkd_date: ev.target.value })}
                    />
                  </label>
                  <label>
                    Best Before
                    <span className="row">
                      <input
                        className="num"
                        inputMode="numeric"
                        style={{ width: 80 }}
                        value={fields.best_before_value}
                        onChange={(ev) =>
                          set({ best_before_value: ev.target.value })
                        }
                      />
                      <Combobox
                        value={fields.best_before_unit}
                        onChange={(v) => set({ best_before_unit: v })}
                        ariaLabel="Best before in"
                        options={PERIODS}
                      />
                    </span>
                  </label>
                  <label>
                    Expiry Date
                    <input
                      type="date"
                      value={fields.expiry_date}
                      onChange={(ev) => {
                        setExpiryTyped(!!ev.target.value);
                        setFields({
                          ...fields,
                          expiry_date:
                            ev.target.value ||
                            expiryOf(
                              fields.pkd_date,
                              fields.best_before_value,
                              fields.best_before_unit,
                            ),
                        });
                      }}
                    />
                    <span className="small">
                      {expiryTyped ? "Typed over" : "Pkd Date + Best Before"}
                    </span>
                  </label>
                  <label className="wide">
                    Packing Notes
                    <textarea
                      rows={2}
                      value={fields.packing_notes}
                      onChange={(ev) => set({ packing_notes: ev.target.value })}
                    />
                  </label>
                </div>
                <p className="small">
                  Copied from the item and the BOM version; changing them here
                  does not change the item or the BOM. They print on the batch
                  sheet.
                </p>
              </>
            ) : (
              o && (
                <Facts
                  rows={[
                    ["MRP", o.mrp ? `₹ ${money(o.mrp)}` : ""],
                    [
                      "USP",
                      o.usp
                        ? `₹ ${money(o.usp)}${o.usp_per_name ? ` per ${o.usp_per_name}` : ""}`
                        : "",
                    ],
                    ["Batch No", o.batch_no],
                    ["Pkd Date", shortDate(o.pkd_date)],
                    [
                      "Best Before",
                      o.best_before_value
                        ? `${o.best_before_value} ${o.best_before_unit}`
                        : "",
                    ],
                    ["Expiry Date", shortDate(o.expiry_date)],
                    ["Packing Notes", o.packing_notes],
                  ]}
                />
              )
            )}
          </Fold>
          <Fold
            title="Materials"
            open
            summary={`${bomLines.length} from the BOM${(mayEdit ? added.filter((a) => a.item).length : savedAdded.length) ? ` · ${mayEdit ? added.filter((a) => a.item).length : savedAdded.length} added` : ""}`}
          >
            <div className="table-scroll">
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th style={{ minWidth: 200 }}>Material</th>
                    <th className="num">Per Unit</th>
                    <th className="num">Loss %</th>
                    <th className="num">Required</th>
                    <th>Unit</th>
                    <th className="num">Issued</th>
                    <th className="num">Free Here</th>
                    <th>Source</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {bomLines.length === 0 && (
                    <tr>
                      <td colSpan={10} className="small">
                        {fields.item
                          ? qtyNow > 0
                            ? "Working out the materials…"
                            : "Type the quantity to see the materials."
                          : "Pick the item to make."}
                      </td>
                    </tr>
                  )}
                  {bomLines.map((l, k) => (
                    <tr key={`b${l.item}`}>
                      <td>{k + 1}</td>
                      <td>
                        <b>{l.item_name}</b> <span className="pill">BOM</span>
                        {l.bom_note && (
                          <span className="small error"> {l.bom_note}</span>
                        )}
                      </td>
                      <td className="num">{l.per_unit}</td>
                      <td className="num">
                        {Number(l.loss_pct) ? l.loss_pct : ""}
                      </td>
                      <td className="num">
                        <b>{l.required}</b>
                      </td>
                      <td>{l.unit_name}</td>
                      <td className="num">
                        {Number(l.issued) ? l.issued : ""}
                      </td>
                      <td className="num">
                        {l.free == null ? (
                          ""
                        ) : l.short ? (
                          <b className="error">{l.free}</b>
                        ) : (
                          l.free
                        )}
                      </td>
                      <td className="small">{l.source_text}</td>
                      <td />
                    </tr>
                  ))}
                  {mayEdit
                    ? added.map((a, k) => {
                        const m = materialOf(a.item);
                        const was = savedAdded.find(
                          (s) => String(s.item) === a.item,
                        );
                        const need =
                          Number(a.per_unit || 0) *
                          qtyNow *
                          (1 + Number(a.loss_pct || 0) / 100);
                        const setLine = (patch: Partial<Added>) =>
                          setAdded((ls) =>
                            ls.map((x) =>
                              x.key === a.key ? { ...x, ...patch } : x,
                            ),
                          );
                        return (
                          <tr key={a.key}>
                            <td>{bomLines.length + k + 1}</td>
                            <td className="po-item">
                              <Combobox
                                value={a.item}
                                ariaLabel={`Added material ${k + 1}`}
                                placeholder="Type to search items…"
                                create={newMaterial}
                                onChange={(v) =>
                                  setLine({
                                    item: v,
                                    unit: str(materialOf(v)?.stock_unit),
                                  })
                                }
                                options={materials
                                  .filter((i) => jobWork || !i.customer_goods)
                                  .map((i) => ({
                                    value: String(i.id),
                                    label: i.name,
                                    hint: i.item_number,
                                  }))}
                              />
                              <span className="pill warn">Added</span>
                            </td>
                            <td className="num">
                              <input
                                className="num"
                                inputMode="decimal"
                                aria-label={`Per unit on added line ${k + 1}`}
                                value={a.per_unit}
                                onChange={(ev) =>
                                  setLine({ per_unit: ev.target.value })
                                }
                              />
                            </td>
                            <td className="num">
                              <input
                                className="num"
                                inputMode="decimal"
                                aria-label={`Loss % on added line ${k + 1}`}
                                value={a.loss_pct}
                                onChange={(ev) =>
                                  setLine({ loss_pct: ev.target.value })
                                }
                              />
                            </td>
                            <td className="num">
                              <b>{need ? plain(need) : ""}</b>
                            </td>
                            <td>
                              <Combobox
                                value={a.unit}
                                ariaLabel={`Unit on added line ${k + 1}`}
                                onChange={(v) => setLine({ unit: v })}
                                options={(m?.units ?? []).map((u) => ({
                                  value: String(u.unit),
                                  label: u.name,
                                }))}
                              />
                            </td>
                            <td className="num">
                              {was && Number(was.issued) ? was.issued : ""}
                            </td>
                            <td className="num">
                              {was?.free == null ? (
                                ""
                              ) : was.short ? (
                                <b className="error">{was.free}</b>
                              ) : (
                                was.free
                              )}
                            </td>
                            <td className="small">{was?.source_text ?? ""}</td>
                            <td>
                              {!(was && Number(was.issued)) && (
                                <button
                                  type="button"
                                  className="link danger"
                                  aria-label="Remove line"
                                  onClick={() =>
                                    setAdded((ls) =>
                                      ls.filter((x) => x.key !== a.key),
                                    )
                                  }
                                >
                                  ✕
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })
                    : savedAdded.map((l) => (
                        <tr key={`a${l.item}`}>
                          <td>{l.position}</td>
                          <td>
                            <b>{l.item_name}</b>{" "}
                            <span className="pill warn">Added</span>
                          </td>
                          <td className="num">{l.per_unit}</td>
                          <td className="num">
                            {Number(l.loss_pct) ? l.loss_pct : ""}
                          </td>
                          <td className="num">
                            <b>{l.required}</b>
                          </td>
                          <td>{l.unit_name}</td>
                          <td className="num">
                            {Number(l.issued) ? l.issued : ""}
                          </td>
                          <td className="num">
                            {l.free == null ? "" : l.free}
                          </td>
                          <td className="small">{l.source_text}</td>
                          <td />
                        </tr>
                      ))}
                </tbody>
              </table>
            </div>
            {mayEdit && (
              <div className="buttons">
                <button
                  type="button"
                  className="link"
                  onClick={() => setAdded((ls) => [...ls, emptyAdded()])}
                >
                  + Add material
                </button>
              </div>
            )}
            <p className="small">
              Materials marked "BOM" come from the chosen version and cannot be
              changed here; to change them, change the BOM (or duplicate it as a
              new version). "Added" materials can be changed or removed until
              the order is completed or closed, but not below what was already
              issued. "Free Here" is the stock free in the branch after other
              orders' reservations; red means short. Required = Per Unit × Qty,
              plus the loss.
            </p>
          </Fold>
          {(shown?.byproducts.length ?? 0) > 0 && (
            <Fold
              title="By-products"
              summary={`${shown?.byproducts.length} expected`}
            >
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th className="num">Expected Qty</th>
                    <th>Unit</th>
                    <th>Kind</th>
                  </tr>
                </thead>
                <tbody>
                  {shown?.byproducts.map((b) => (
                    <tr key={b.item}>
                      <td>{b.item_name}</td>
                      <td className="num">{b.qty}</td>
                      <td>{b.unit_name}</td>
                      <td>{b.kind_label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Fold>
          )}
        </div>
        <DocSide
          type="manufacturing_order"
          id={o?.id ?? null}
          onChange={() => setFiles((n) => n + 1)}
        >
          {shown?.cost && (
            <SidePanel title="Cost (Estimate)">
              <SideRows
                rows={[
                  ["Materials", `₹ ${money(shown.cost.materials)}`],
                  [
                    "Per Unit",
                    shown.cost.per_unit
                      ? `₹ ${money(shown.cost.per_unit)} per ${shown.cost.unit_name}`
                      : "",
                  ],
                  [
                    "Per Stock Unit",
                    shown.cost.per_stock_unit &&
                    shown.cost.stock_unit_name !== shown.cost.unit_name
                      ? `₹ ${money(shown.cost.per_stock_unit)} per ${shown.cost.stock_unit_name}`
                      : "",
                  ],
                ]}
              />
              {shown.cost.missing.length > 0 && (
                <p className="small error">
                  No rate yet for {shown.cost.missing.join(", ")}.
                </p>
              )}
              <p className="small">
                Today's FIFO rate, else the last receipt's. A customer's goods
                are counted, never valued.
              </p>
            </SidePanel>
          )}
          {o && (
            <>
              <SidePanel title="Details">
                <SideRows
                  rows={[
                    ["Made By", o.created_by_name],
                    ["Submitted By", o.submitted_by_name],
                    ["Closed On", o.closed_at ? at(o.closed_at) : ""],
                  ]}
                />
              </SidePanel>
              <SidePanel title="Activity">
                <ChangeLog
                  company={companyId}
                  type="manufacturing_order"
                  id={o.id}
                  stamp={JSON.stringify(o) + files}
                />
              </SidePanel>
            </>
          )}
        </DocSide>
      </div>
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
