import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, useOpenParam } from "./ErrorNote";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { Combobox } from "./Combobox";
import { HsnPicker } from "./Hsn";
import { FormBody } from "./RowActions";
import { useBrands } from "./Brands";
import { creatable } from "./Create";
import { groupPaths, useItemGroups } from "./ItemGroups";
import { useUnits, type Unit } from "./Units";

/** Items: one catalogue for every company in the group, each item with its chain of units. */
export type ItemUnit = {
  unit: number;
  unit_name: string;
  contains_qty: string | null;
  contains_unit: number | null;
  contains_unit_name: string | null;
  factor: string;
  length_cm: string | null;
  breadth_cm: string | null;
  height_cm: string | null;
  net_kg: string | null;
  gross_kg: string | null;
  volume_m3: string | null;
  barcode: string;
  whole_numbers: boolean;
  used_for: string[];
};
export type Item = {
  id: number;
  item_number: string;
  name: string;
  item_type: string;
  stock_unit: number;
  stock_unit_name: string;
  hsn: string;
  item_group: number | null;
  item_group_name: string | null;
  brand: number | null;
  brand_name: string | null;
  sales_description: string;
  sales_unit: number | null;
  sales_unit_name: string | null;
  purchase_description: string;
  purchase_unit: number | null;
  purchase_unit_name: string | null;
  mrp: string | null;
  usp: string;
  best_before_value: number | null;
  best_before_unit: string;
  batch_no: string;
  lead_time_days: number | null;
  safety_stock_qty: string | null;
  min_order_qty: string | null;
  max_stock_qty: string | null;
  batch_tracked: boolean;
  qc_required: boolean;
  default_request_type: string;
  maintain_stock: boolean;
  allow_purchase: boolean;
  allow_sales: boolean;
  notes: string;
  is_active: boolean;
  units: ItemUnit[];
  gst_rates: GstRate[];
  warnings: string[];
};
export type GstRate = { valid_from: string; rate: string };

const TYPES: [string, string][] = [
  ["goods", "Goods"],
  ["service", "Service"],
];
const REQUEST_TYPES: [string, string][] = [
  ["manufacture", "Manufacture"],
  ["purchase", "Purchase"],
  ["customer_provided", "Customer Provided"],
];
const requestLabel = (code: string) => REQUEST_TYPES.find(([c]) => c === code)?.[1] ?? "";
const USED_FOR: [string, string][] = [
  ["purchase", "Purchase"],
  ["sales", "Sales"],
  ["stock", "Stock"],
  ["production", "Production"],
];
const typeLabel = (code: string) => TYPES.find(([c]) => c === code)?.[1] ?? code;
const usedLabel = (code: string) => USED_FOR.find(([c]) => c === code)?.[1] ?? code;
const plain = (v: string | null) => (v === null || v === "" ? "" : String(Number(v)));
const showDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
/** The rate in force today: the latest row whose "from" date has come. */
const rateToday = (rates: GstRate[]) => {
  const today = new Date().toISOString().slice(0, 10);
  return [...rates].filter((r) => r.valid_from <= today).pop();
};

export function ItemsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const [items, setItems] = useState<Item[]>([]);
  const [query, setQuery] = useState("");
  const [editing, setEditingNow] = useState<Item | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<Item | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const setEditing = (value: Item | "new" | null) => {
    setCopyOf(null); // only the Duplicate button sets it again
    setEditingNow(value);
  };
  const reload = useCallback(() => {
    api<Item[]>("v1/items/")
      .then(setItems)
      .catch((err: Error) => setError(err.message));
  }, []);
  useEffect(reload, [reload]);
  const io = useExchange({ master: "items", noun: "items", session, onImported: reload });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && items.some((i) => i.id === openId)) {
      setQuery("");
      setSelectedId(openId);
      setEditing(null);
      opened();
    }
  }, [openId, items, opened]);

  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return items.filter((i) => {
      const text = [i.name, i.item_number, i.hsn, ...i.units.map((u) => u.barcode)].join(" ").toLowerCase();
      return words.every((w) => text.includes(w));
    });
  }, [items, query]);
  const selected = items.find((i) => i.id === selectedId) ?? shown[0] ?? null;
  const pick = (i: Item) => {
    setSelectedId(i.id);
    setEditing(null);
  };
  const onListKey = (e: KeyboardEvent<HTMLTableSectionElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const at = selected ? shown.findIndex((i) => i.id === selected.id) : -1;
    const next = shown[Math.min(shown.length - 1, Math.max(0, at + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) {
      pick(next);
      document.getElementById(`item-${next.id}`)?.focus();
    }
  };

  return (
    <section className="page">
      <PageHeader
        title="Items"
        sub={`${items.length} ${items.length === 1 ? "item" : "items"}${query ? `, ${shown.length} match` : ""} · one catalogue for every company in the group`}
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => setEditing("new")}>Add item</button>}
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {io.panel}
      <div className={`split${editing ? " editing" : ""}`}>
        <div className="split-list">
          <div className="row filters">
            <input
              type="search"
              placeholder="Search by name, item number, HSN or barcode"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <table className="pick">
            <thead>
              <tr>
                <th>Item</th>
                <th>Stock unit</th>
              </tr>
            </thead>
            <tbody onKeyDown={onListKey}>
              {shown.length === 0 && (
                <tr>
                  <td colSpan={2} className="small">
                    No items match.
                  </td>
                </tr>
              )}
              {shown.map((i) => (
                <tr
                  key={i.id}
                  id={`item-${i.id}`}
                  tabIndex={0}
                  aria-selected={selected?.id === i.id}
                  className={["ledger-row", i.is_active ? "" : "inactive", selected?.id === i.id ? "selected" : ""].join(" ")}
                  onClick={() => pick(i)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") pick(i);
                  }}
                >
                  <td>
                    {i.name}
                    {!i.is_active && <span className="small"> · inactive</span>}
                    <div className="small">{i.item_number}</div>
                  </td>
                  <td>{i.stock_unit_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 1 && <p className="small">Tip: click an item, then use ↑ and ↓ to move through the list.</p>}
        </div>
        <aside className="split-panel" aria-label="Item details">
          {editing ? (
            <ItemForm
              key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
              item={editing === "new" ? null : editing}
              copyOf={copyOf}
              onDone={(saved) => {
                setEditing(null);
                if (saved) setSelectedId(saved);
                reload();
              }}
              onCancel={() => setEditing(null)}
            />
          ) : selected ? (
            <ItemPanel
              item={selected}
              canEdit={canEdit}
              onEdit={() => setEditing(selected)}
              onDuplicate={() => {
                setEditingNow("new");
                setCopyOf(selected);
              }}
            />
          ) : (
            <div className="card">
              <p className="small">Pick an item to see its details here.</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

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

function ItemPanel(props: { item: Item; canEdit: boolean; onEdit: () => void; onDuplicate: () => void }) {
  const { item: i, canEdit } = props;
  return (
    <div className="card panel">
      <div className="panel-head">
        <div>
          <h2>{i.name}</h2>
          <p className="small">
            {i.item_number} · {typeLabel(i.item_type)}
            {!i.is_active && " · inactive"}
          </p>
        </div>
        {canEdit && (
          <div className="buttons">
            <button onClick={props.onEdit}>Edit</button>
            <button type="button" className="link" onClick={props.onDuplicate}>
              Duplicate
            </button>
          </div>
        )}
      </div>
      <Section title="Item">
        <Facts
          rows={[
            ["Item number", i.item_number],
            ["Goods or service", typeLabel(i.item_type)],
            ["Maintain stock", i.maintain_stock ? "Yes" : "No"],
            ["Allow purchase", i.allow_purchase ? "Yes" : "No"],
            ["Allow sales", i.allow_sales ? "Yes" : "No"],
            ["Default unit (stock unit)", i.stock_unit_name],
            ["Item group", i.item_group_name ?? ""],
            ["Brand", i.brand_name ?? ""],
            ["HSN", i.hsn],
          ]}
        />
      </Section>
      {(i.sales_description || i.sales_unit_name || i.mrp || i.usp || i.best_before_value || i.batch_no) && (
        <Section title="Sales">
          <Facts
            rows={[
              ["Default sales unit", i.sales_unit_name ?? ""],
              ["MRP", i.mrp === null ? "" : `₹ ${plain(i.mrp)}`],
              ["USP", i.usp],
              ["Best before", i.best_before_value === null ? "" : `${i.best_before_value} ${i.best_before_unit}`],
              ["Batch No", i.batch_no],
            ]}
          />
          {i.sales_description && <p className="pre">{i.sales_description}</p>}
        </Section>
      )}
      {(i.purchase_description ||
        i.purchase_unit_name ||
        i.lead_time_days !== null ||
        i.safety_stock_qty ||
        i.min_order_qty ||
        i.max_stock_qty) && (
        <Section title="Purchase">
          <Facts
            rows={[
              ["Default purchase unit", i.purchase_unit_name ?? ""],
              ["Lead time", i.lead_time_days === null ? "" : `${i.lead_time_days} days`],
              ["Safety stock qty", i.safety_stock_qty === null ? "" : plain(i.safety_stock_qty)],
              ["Minimum order qty", i.min_order_qty === null ? "" : plain(i.min_order_qty)],
              ["Max stock qty", i.max_stock_qty === null ? "" : plain(i.max_stock_qty)],
            ]}
          />
          {i.purchase_description && <p className="pre">{i.purchase_description}</p>}
        </Section>
      )}
      {i.gst_rates.length > 0 && (
        <Section title="GST rates">
          <table className="grid">
            <thead>
              <tr>
                <th>From</th>
                <th className="num">GST rate</th>
              </tr>
            </thead>
            <tbody>
              {[...i.gst_rates].reverse().map((r) => (
                <tr key={r.valid_from}>
                  <td>
                    {showDate(r.valid_from)}
                    {r === rateToday(i.gst_rates) && <span className="pill on">In force</span>}
                  </td>
                  <td className="num">{plain(r.rate)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
      <Section title="Stock and quality">
        <Facts
          rows={[
            ["Batches tracked", i.batch_tracked ? "Yes" : "No"],
            ["Quality check on receipt", i.qc_required ? "Yes" : "No"],
            ["Default material request type", requestLabel(i.default_request_type)],
          ]}
        />
      </Section>
      {i.units.length > 0 && (
        <Section title="Units of measure">
          <ul className="address-list cards-2">
            {i.units.map((u) => {
              const size =
                u.length_cm && u.breadth_cm && u.height_cm
                  ? `${plain(u.length_cm)} × ${plain(u.breadth_cm)} × ${plain(u.height_cm)} cm${u.volume_m3 ? ` · ${u.volume_m3} m³` : ""}`
                  : "";
              const weight = [u.net_kg && `Net ${plain(u.net_kg)} kg`, u.gross_kg && `Gross ${plain(u.gross_kg)} kg`]
                .filter(Boolean)
                .join(" · ");
              return (
                <li key={u.unit} className="address-card">
                  <div>
                    <strong>{u.unit_name}</strong>
                  </div>
                  <div>
                    {u.contains_unit_name
                      ? `${plain(u.contains_qty)} ${u.contains_unit_name}${
                          u.contains_unit_name === i.stock_unit_name ? "" : ` = ${plain(u.factor)} ${i.stock_unit_name}`
                        }`
                      : "Stock unit"}
                  </div>
                  {size && <div className="small">{size}</div>}
                  {weight && <div className="small">{weight}</div>}
                  {u.barcode && <div className="small">Barcode {u.barcode}</div>}
                  {u.used_for.length > 0 && (
                    <div>
                      {u.used_for.map((c) => (
                        <span key={c} className="pill on">
                          {usedLabel(c)}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {i.warnings.map((w) => (
            <p key={w} className="small">
              {w}
            </p>
          ))}
        </Section>
      )}
      {i.notes && (
        <Section title="Notes">
          <p className="pre">{i.notes}</p>
        </Section>
      )}
      <div className="panel-activity">
        <h3>Activity</h3>
        <ChangeLog type="item" id={i.id} stamp={JSON.stringify(i)} />
      </div>
    </div>
  );
}

type Row = {
  unit: string;
  contains_qty: string;
  contains_unit: string;
  length_cm: string;
  breadth_cm: string;
  height_cm: string;
  net_kg: string;
  gross_kg: string;
  barcode: string;
  whole_numbers: boolean;
  used_for: string[];
};
const blankRow = (unit = ""): Row => ({
  unit,
  contains_qty: "",
  contains_unit: "",
  length_cm: "",
  breadth_cm: "",
  height_cm: "",
  net_kg: "",
  gross_kg: "",
  barcode: "",
  whole_numbers: true,
  used_for: [],
});
const rowOf = (u: ItemUnit): Row => ({
  unit: String(u.unit),
  contains_qty: plain(u.contains_qty),
  contains_unit: u.contains_unit === null ? "" : String(u.contains_unit),
  length_cm: plain(u.length_cm),
  breadth_cm: plain(u.breadth_cm),
  height_cm: plain(u.height_cm),
  net_kg: plain(u.net_kg),
  gross_kg: plain(u.gross_kg),
  barcode: u.barcode,
  whole_numbers: u.whole_numbers,
  used_for: u.used_for,
});

/** How many stock units each row holds, worked out down the chain (as the server does). */
function factors(stock: string, rows: Row[]): Map<string, number> {
  const f = new Map<string, number>([[stock, 1]]);
  for (let pass = 0; pass < rows.length; pass++)
    for (const r of rows) {
      if (f.has(r.unit) || !r.unit) continue;
      const below = f.get(r.contains_unit);
      const qty = Number(r.contains_qty);
      if (below !== undefined && qty > 0) f.set(r.unit, qty * below);
    }
  return f;
}

function ItemForm(props: { item: Item | null; copyOf: Item | null; onDone: (savedId?: number) => void; onCancel: () => void }) {
  const it = props.item;
  const from = it ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const { units, refresh: refreshUnits } = useUnits();
  const newUnit = creatable("unit", "units", refreshUnits);
  const [name, setName] = useState(props.copyOf ? `${props.copyOf.name} (copy)` : (it?.name ?? ""));
  const [type, setType] = useState(from?.item_type ?? "goods");
  const [stocked, setStocked] = useState(from?.maintain_stock ?? true); // "Maintain stock", whatever the type
  const [disabled, setDisabled] = useState(it ? !it.is_active : false);
  const [allowPurchase, setAllowPurchase] = useState(from?.allow_purchase ?? true);
  const [allowSales, setAllowSales] = useState(from?.allow_sales ?? true);
  const [stock, setStock] = useState(from ? String(from.stock_unit) : "");
  const { groups: itemGroups, refresh: refreshGroups } = useItemGroups();
  const newGroup = creatable("item_group", "item-groups", refreshGroups);
  const groupNames = groupPaths(itemGroups);
  const parents = new Set(itemGroups.map((g) => g.parent)); // groups with sub-groups are not offered
  const [group, setGroup] = useState(from?.item_group == null ? "" : String(from.item_group));
  const { brands, refresh: refreshBrands } = useBrands();
  const newBrand = creatable("brand", "brands", refreshBrands);
  const [brand, setBrand] = useState(from?.brand == null ? "" : String(from.brand));
  const [hsn, setHsn] = useState(from?.hsn ?? "");
  const [mrp, setMrp] = useState(from?.mrp == null ? "" : plain(from.mrp));
  const [usp, setUsp] = useState(from?.usp ?? "");
  const [bestBefore, setBestBefore] = useState(from?.best_before_value == null ? "" : String(from.best_before_value));
  const [bestBeforeUnit, setBestBeforeUnit] = useState(from?.best_before_unit ?? "days");
  const [batchNo, setBatchNo] = useState(from?.batch_no ?? "");
  const [leadTime, setLeadTime] = useState(from?.lead_time_days == null ? "" : String(from.lead_time_days));
  const [safety, setSafety] = useState(from?.safety_stock_qty == null ? "" : plain(from.safety_stock_qty));
  const [minOrder, setMinOrder] = useState(from?.min_order_qty == null ? "" : plain(from.min_order_qty));
  const [maxStock, setMaxStock] = useState(from?.max_stock_qty == null ? "" : plain(from.max_stock_qty));
  const [batches, setBatches] = useState(from?.batch_tracked ?? false);
  const [qc, setQc] = useState(from?.qc_required ?? false);
  const [requestType, setRequestType] = useState(from?.default_request_type ?? "");
  const [notes, setNotes] = useState(from?.notes ?? "");
  const changeName = (v: string) => setName(v);
  const [salesText, setSalesText] = useState(from?.sales_description ?? "");
  const [salesUnit, setSalesUnit] = useState(from?.sales_unit == null ? "" : String(from.sales_unit));
  const [buyText, setBuyText] = useState(from?.purchase_description ?? "");
  const [buyUnit, setBuyUnit] = useState(from?.purchase_unit == null ? "" : String(from.purchase_unit));
  const [rates, setRates] = useState<GstRate[]>((from?.gst_rates ?? []).map((r) => ({ ...r, rate: plain(r.rate) })));
  const [rows, setRows] = useState<Row[]>(
    (from?.units ?? []).map((u) => {
      const r = rowOf(u);
      return props.copyOf ? { ...r, barcode: "" } : r; // barcodes belong to one item
    }),
  );
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"general" | "sales" | "purchase" | "gst" | "stock" | "units">("general");

  const used = new Set(rows.map((r) => r.unit));
  const offered = (current: string) =>
    units.filter((u) => (u.is_active || String(u.id) === current) && (!used.has(String(u.id)) || String(u.id) === current));
  const unitName = (id: string) => units.find((u) => String(u.id) === id)?.name ?? "";
  const fac = factors(stock, rows);
  const stockName = unitName(stock);
  const listed = [stock, ...rows.map((r) => r.unit)].filter((id, k, all) => id && all.indexOf(id) === k);
  const unitChoices = listed.map((id) => ({ value: id, label: unitName(id) }));
  const setRate = (i: number, change: Partial<GstRate>) => setRates(rates.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const setRow = (i: number, change: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const toggleUsed = (i: number, code: string, on: boolean) =>
    setRow(i, { used_for: on ? [...rows[i].used_for, code] : rows[i].used_for.filter((c) => c !== code) });

  const num = (v: string) => (v.trim() === "" ? null : v.trim());
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    // The General tab's boxes are not on screen while another tab is open, so
    // the browser cannot check them: check here and take the person there.
    if (!name.trim() || !stock) {
      setTab("general");
      setError(!name.trim() ? "Give the item name on the General tab." : "Pick the default unit of measure on the General tab.");
      return;
    }
    setBusy(true);
    const body = {
      name,
      item_type: type,
      maintain_stock: stocked,
      allow_purchase: allowPurchase,
      allow_sales: allowSales,
      is_active: !disabled,
      stock_unit: Number(stock),
      hsn,
      item_group: group === "" ? null : Number(group),
      brand: brand === "" ? null : Number(brand),
      mrp: num(mrp),
      usp,
      best_before_value: num(bestBefore),
      best_before_unit: bestBeforeUnit,
      batch_no: batchNo,
      lead_time_days: num(leadTime),
      safety_stock_qty: num(safety),
      min_order_qty: num(minOrder),
      max_stock_qty: num(maxStock),
      batch_tracked: batches,
      qc_required: qc,
      default_request_type: requestType,
      notes,
      sales_description: salesText,
      sales_unit: salesUnit ? Number(salesUnit) : null,
      purchase_description: buyText,
      purchase_unit: buyUnit ? Number(buyUnit) : null,
      gst_rates: rates.filter((r) => r.valid_from || r.rate).map((r) => ({ valid_from: r.valid_from, rate: r.rate.trim() })),
      units: rows
        .filter((r) => r.unit)
        .map((r) => ({
          unit: Number(r.unit),
          contains_qty: r.unit === stock ? null : num(r.contains_qty),
          contains_unit: r.unit === stock || !r.contains_unit ? null : Number(r.contains_unit),
          length_cm: num(r.length_cm),
          breadth_cm: num(r.breadth_cm),
          height_cm: num(r.height_cm),
          net_kg: num(r.net_kg),
          gross_kg: num(r.gross_kg),
          barcode: r.barcode,
          whole_numbers: r.whole_numbers,
          used_for: r.used_for,
        })),
    };
    try {
      const saved = it ? await api<Item>(`v1/items/${it.id}/`, body, "PATCH") : await api<Item>("v1/items/", body);
      props.onDone(saved.id);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h3>{it ? `Edit ${it.name}` : props.copyOf ? `Duplicate ${props.copyOf.name}` : "Add item"}</h3>
      <div className="form-tabs" role="tablist">
        {(
          [
            ["general", "General"],
            ["sales", "Sales"],
            ["purchase", "Purchase"],
            ["gst", `GST rates (${rates.length})`],
            ["stock", "Stock and quality"],
            ["units", `Units of measure (${rows.length})`],
          ] as const
        ).map(([code, label]) => (
          <button
            key={code}
            type="button"
            role="tab"
            aria-selected={tab === code}
            className={tab === code ? "active" : ""}
            onClick={() => setTab(code)}
          >
            {label}
          </button>
        ))}
      </div>
      <FormBody>
        {tab === "general" && (
        <Section title="Item">
          <div className="item-general">
            <div>
              <label>
                Item number
                <input readOnly disabled value={it?.item_number ?? "Given when you save"} />
              </label>
              <label>
                Item name
                <input required autoFocus value={name} onChange={(e) => changeName(e.target.value)} />
              </label>
              <label>
                Goods or service
                <Combobox value={type} onChange={setType} options={TYPES.map(([value, label]) => ({ value, label }))} />
              </label>
              <label>
                Item group
                <Combobox
                  value={group}
                  empty="No group"
                  placeholder="Type to search groups…"
                  options={itemGroups
                    .filter((g) => (g.is_active && !parents.has(g.id)) || String(g.id) === group)
                    .map((g) => ({ value: String(g.id), label: groupNames.get(g.id) ?? g.name }))}
                  onChange={setGroup}
                  create={newGroup}
                />
              </label>
              <label>
                HSN code
                <HsnPicker value={hsn} onChange={setHsn} />
              </label>
              <label>
                Default unit of measure
                <Combobox
                  required
                  value={stock}
                  placeholder="Type to search units…"
                  options={units
                    .filter((u: Unit) => u.is_active || String(u.id) === stock)
                    .map((u) => ({ value: String(u.id), label: u.name }))}
                  onChange={setStock}
                  create={newUnit}
                />
              </label>
                <label>
                  Brand
                  <Combobox
                    value={brand}
                    empty="No brand"
                    placeholder="Type to search brands…"
                    options={brands
                      .filter((b) => b.is_active || String(b.id) === brand)
                      .map((b) => ({ value: String(b.id), label: b.name }))}
                    onChange={setBrand}
                    create={newBrand}
                  />
                </label>
            </div>
            <div className="item-checks">
              <label className="check">
                <input type="checkbox" checked={disabled} onChange={(e) => setDisabled(e.target.checked)} />
                Disabled
              </label>
              <label className="check">
                <input type="checkbox" checked={allowPurchase} onChange={(e) => setAllowPurchase(e.target.checked)} />
                Allow purchase
              </label>
              <label className="check">
                <input type="checkbox" checked={allowSales} onChange={(e) => setAllowSales(e.target.checked)} />
                Allow sales
              </label>
              <label className="check">
                <input type="checkbox" checked={stocked} onChange={(e) => setStocked(e.target.checked)} />
                Maintain stock
              </label>
              <p className="small">"Maintain stock" says whether stock of this item is kept, goods or service.</p>
            </div>
          </div>
        </Section>
        )}
        {tab === "general" && (
        <Section title="Notes">
          <div className="row">
            <label>
              Notes
              <input value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
          </div>
        </Section>
        )}
        {tab === "sales" && (
          <Section title="Sales">
            <label>
              Sales description
              <textarea rows={3} maxLength={500} value={salesText} onChange={(e) => setSalesText(e.target.value)} />
            </label>
            <p className="small">The wording customers see for this item on quotations, orders and sales bills.</p>
            <div className="row">
              <label>
                Default sales unit
                <Combobox value={salesUnit} onChange={setSalesUnit} empty="Same as the stock unit" options={unitChoices} />
              </label>
              <label>
                MRP (₹)
                <input className="num" inputMode="decimal" value={mrp} onChange={(e) => setMrp(e.target.value)} />
              </label>
            </div>
            <label>
              USP
              <input maxLength={200} value={usp} onChange={(e) => setUsp(e.target.value)} />
            </label>
            <div className="row">
              <label>
                Best before (counted from the manufacturing date)
                <input className="num" inputMode="numeric" value={bestBefore} onChange={(e) => setBestBefore(e.target.value)} />
              </label>
              <label>
                Best before in
                <Combobox
                  value={bestBeforeUnit}
                  onChange={setBestBeforeUnit}
                  options={[
                    { value: "days", label: "Days" },
                    { value: "months", label: "Months" },
                  ]}
                />
              </label>
              <label>
                Batch No
                <input maxLength={60} value={batchNo} onChange={(e) => setBatchNo(e.target.value)} />
              </label>
            </div>
          </Section>
        )}
        {tab === "purchase" && (
          <Section title="Purchase">
            <label>
              Purchase description
              <textarea rows={3} maxLength={500} value={buyText} onChange={(e) => setBuyText(e.target.value)} />
            </label>
            <p className="small">The wording suppliers see for this item on purchase orders.</p>
            <div className="row">
              <label>
                Default purchase unit
                <Combobox value={buyUnit} onChange={setBuyUnit} empty="Same as the stock unit" options={unitChoices} />
              </label>
              <label>
                Lead time in days
                <input className="num" inputMode="numeric" value={leadTime} onChange={(e) => setLeadTime(e.target.value)} />
              </label>
            </div>
            <div className="row">
              <label>
                Safety stock qty
                <input className="num" inputMode="decimal" value={safety} onChange={(e) => setSafety(e.target.value)} />
              </label>
              <label>
                Minimum order qty
                <input className="num" inputMode="decimal" value={minOrder} onChange={(e) => setMinOrder(e.target.value)} />
              </label>
              <label>
                Max stock qty
                <input className="num" inputMode="decimal" value={maxStock} onChange={(e) => setMaxStock(e.target.value)} />
              </label>
            </div>
            <p className="small">The quantities are in the item's default unit.</p>
          </Section>
        )}
        {tab === "gst" && (
          <Section title="GST rates">
            <p className="small">
              When the law changes, click "Add rate" and give the new rate and the date it starts. Keep the old rows: bills
              take the rate in force on the bill date.
            </p>
            {rates.length > 0 && (
              <table className="grid">
                <thead>
                  <tr>
                    <th>From</th>
                    <th className="num">GST rate (%)</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rates.map((r, i) => (
                    <tr key={i}>
                      <td>
                        <input required type="date" aria-label="From" value={r.valid_from} onChange={(e) => setRate(i, { valid_from: e.target.value })} />
                      </td>
                      <td>
                        <input required className="num" inputMode="decimal" aria-label="GST rate (%)" value={r.rate} onChange={(e) => setRate(i, { rate: e.target.value })} />
                      </td>
                      <td>
                        <button type="button" className="link danger" onClick={() => setRates(rates.filter((_, j) => j !== i))}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div>
              <button type="button" className="link" onClick={() => setRates([...rates, { valid_from: "", rate: "" }])}>
                Add rate
              </button>
            </div>
          </Section>
        )}
        {tab === "stock" && (
        <Section title="Stock and quality">
          <div className="row">
            <label>
              Default material request type
              <Combobox
                value={requestType}
                onChange={setRequestType}
                empty="Not set"
                options={REQUEST_TYPES.map(([value, label]) => ({ value, label }))}
              />
            </label>
          </div>
          <label className="check">
            <input type="checkbox" checked={batches} onChange={(e) => setBatches(e.target.checked)} />
            Track batches (batch number and expiry on every receipt and issue)
          </label>
          <label className="check">
            <input type="checkbox" checked={qc} onChange={(e) => setQc(e.target.checked)} />
            Quality check on receipt
          </label>
        </Section>
        )}
        {tab === "units" && (
        <Section title="Units of measure">
          <p className="small">
            The stock unit is added for you. For every other unit say how many of which unit it contains; "= {stockName || "stock unit"}" is
            worked out from that.
          </p>
          <ul className="address-list">
            {rows.map((r, i) => {
              const isStock = r.unit !== "" && r.unit === stock;
              return (
                <li key={i} className="address-card">
                  <div className="row">
                    <label>
                      Unit
                      <Combobox
                        required
                        value={r.unit}
                        placeholder="Type to search units…"
                        options={offered(r.unit).map((u) => ({ value: String(u.id), label: u.name }))}
                        create={newUnit}
                        onChange={(v) => {
                          const picked = units.find((u) => String(u.id) === v);
                          setRow(i, { unit: v, whole_numbers: picked ? picked.whole_numbers : true });
                        }}
                      />
                    </label>
                    {!isStock && (
                      <label>
                        Contains how many
                        <input required inputMode="decimal" value={r.contains_qty} onChange={(e) => setRow(i, { contains_qty: e.target.value })} />
                      </label>
                    )}
                    {!isStock && (
                      <label>
                        Of
                        <Combobox
                          required
                          value={r.contains_unit}
                          onChange={(v) => setRow(i, { contains_unit: v })}
                          empty="Choose…"
                          options={[stock, ...rows.map((x) => x.unit)]
                            .filter((id, k, all) => id && id !== r.unit && all.indexOf(id) === k)
                            .map((id) => ({ value: id, label: unitName(id) }))}
                        />
                      </label>
                    )}
                  </div>
                  <p className="small">
                    {isStock
                      ? "This is the stock unit."
                      : r.unit && fac.has(r.unit)
                        ? `One ${unitName(r.unit)} = ${Number(fac.get(r.unit)!.toFixed(6))} ${stockName || "stock units"}`
                        : "Fill in how many of which unit it contains."}
                  </p>
                  <div className="row">
                    {(
                      [
                        ["length_cm", "Length (cm)"],
                        ["breadth_cm", "Breadth (cm)"],
                        ["height_cm", "Height (cm)"],
                      ] as const
                    ).map(([k, label]) => (
                      <label key={k}>
                        {label}
                        <input inputMode="decimal" value={r[k]} onChange={(e) => setRow(i, { [k]: e.target.value })} />
                      </label>
                    ))}
                  </div>
                  <div className="row">
                    <label>
                      Net weight (kg)
                      <input inputMode="decimal" value={r.net_kg} onChange={(e) => setRow(i, { net_kg: e.target.value })} />
                    </label>
                    <label>
                      Gross weight (kg)
                      <input inputMode="decimal" value={r.gross_kg} onChange={(e) => setRow(i, { gross_kg: e.target.value })} />
                    </label>
                    <label>
                      Barcode
                      <input value={r.barcode} maxLength={30} onChange={(e) => setRow(i, { barcode: e.target.value })} />
                    </label>
                  </div>
                  <div className="checks">
                    <label className="check">
                      <input type="checkbox" checked={r.whole_numbers} onChange={(e) => setRow(i, { whole_numbers: e.target.checked })} />
                      Whole numbers only
                    </label>
                    <span className="small">Used for:</span>
                    {USED_FOR.map(([code, label]) => (
                      <label key={code} className="check">
                        <input type="checkbox" checked={r.used_for.includes(code)} onChange={(e) => toggleUsed(i, code, e.target.checked)} />
                        {label}
                      </label>
                    ))}
                  </div>
                  <div>
                    <button type="button" className="link danger" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                      Remove
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          <div>
            <button type="button" className="link" onClick={() => setRows([...rows, blankRow()])}>
              Add unit
            </button>
          </div>
        </Section>
        )}
      </FormBody>
      <ErrorNote error={error} />
      <div className="buttons">
        <button disabled={busy}>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
