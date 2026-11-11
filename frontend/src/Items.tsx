import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { HsnPicker } from "./Hsn";
import { ActiveButton, FormBody } from "./RowActions";
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
  shelf_life_days: number | null;
  batch_tracked: boolean;
  qc_required: boolean;
  notes: string;
  is_active: boolean;
  units: ItemUnit[];
  warnings: string[];
};

const TYPES: [string, string][] = [
  ["goods", "Goods (stocked)"],
  ["service", "Service"],
];
const USED_FOR: [string, string][] = [
  ["purchase", "Purchase"],
  ["sales", "Sales"],
  ["stock", "Stock"],
  ["production", "Production"],
];
const typeLabel = (code: string) => TYPES.find(([c]) => c === code)?.[1] ?? code;
const usedLabel = (code: string) => USED_FOR.find(([c]) => c === code)?.[1] ?? code;
const plain = (v: string | null) => (v === null || v === "" ? "" : String(Number(v)));

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
        actions={canEdit && <button onClick={() => setEditing("new")}>Add item</button>}
      />
      {error && <p className="error">{error}</p>}
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
            ["Type", typeLabel(i.item_type)],
            ["Stock unit", i.stock_unit_name],
            ["HSN", i.hsn],
          ]}
        />
      </Section>
      <Section title="Stock and quality">
        <Facts
          rows={[
            ["Shelf life", i.shelf_life_days === null ? "" : `${i.shelf_life_days} days`],
            ["Batches tracked", i.batch_tracked ? "Yes" : "No"],
            ["Quality check on receipt", i.qc_required ? "Yes" : "No"],
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
  const { units } = useUnits();
  const [name, setName] = useState(props.copyOf ? `${props.copyOf.name} (copy)` : (it?.name ?? ""));
  const [type, setType] = useState(from?.item_type ?? "goods");
  const [stock, setStock] = useState(from ? String(from.stock_unit) : "");
  const [hsn, setHsn] = useState(from?.hsn ?? "");
  const [shelf, setShelf] = useState(from?.shelf_life_days == null ? "" : String(from.shelf_life_days));
  const [batches, setBatches] = useState(from?.batch_tracked ?? false);
  const [qc, setQc] = useState(from?.qc_required ?? false);
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [rows, setRows] = useState<Row[]>(
    (from?.units ?? []).map((u) => {
      const r = rowOf(u);
      return props.copyOf ? { ...r, barcode: "" } : r; // barcodes belong to one item
    }),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"general" | "stock" | "units">("general");

  const used = new Set(rows.map((r) => r.unit));
  const offered = (current: string) =>
    units.filter((u) => (u.is_active || String(u.id) === current) && (!used.has(String(u.id)) || String(u.id) === current));
  const unitName = (id: string) => units.find((u) => String(u.id) === id)?.name ?? "";
  const fac = factors(stock, rows);
  const stockName = unitName(stock);
  const setRow = (i: number, change: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const toggleUsed = (i: number, code: string, on: boolean) =>
    setRow(i, { used_for: on ? [...rows[i].used_for, code] : rows[i].used_for.filter((c) => c !== code) });

  const num = (v: string) => (v.trim() === "" ? null : v.trim());
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = {
      name,
      item_type: type,
      stock_unit: Number(stock),
      hsn,
      shelf_life_days: shelf.trim() === "" ? null : Number(shelf),
      batch_tracked: batches,
      qc_required: qc,
      notes,
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
      setError((err as Error).message);
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
          <label>
            Name
            <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <div className="row">
            <label>
              Type
              <Combobox
                value={type}
                onChange={setType}
                options={TYPES.map(([value, label]) => ({ value, label }))}
              />
            </label>
            <label>
              Stock unit
              <Combobox
                required
                value={stock}
                placeholder="Type to search units…"
                options={units
                  .filter((u: Unit) => u.is_active || String(u.id) === stock)
                  .map((u) => ({ value: String(u.id), label: u.name }))}
                onChange={setStock}
              />
            </label>
            <label>
              HSN
              <HsnPicker value={hsn} onChange={setHsn} />
            </label>
          </div>
        </Section>
        )}
        {tab === "general" && (
        <Section title="Notes">
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </Section>
        )}
        {tab === "stock" && (
        <Section title="Stock and quality">
          <div className="row">
            <label>
              Shelf life (days)
              <input value={shelf} inputMode="numeric" onChange={(e) => setShelf(e.target.value)} />
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
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button disabled={busy}>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {it && (
          <ActiveButton url={`v1/items/${it.id}/`} active={it.is_active} what={`the item ${it.name}`} onDone={() => props.onDone(it.id)} onError={setError} />
        )}
      </div>
    </form>
  );
}
