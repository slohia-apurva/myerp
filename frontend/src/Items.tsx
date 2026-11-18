import { TdsSectionPicker } from "./Tds";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, useOpenParam } from "./ErrorNote";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { Combobox } from "./Combobox";
import { HsnDescription, HsnPicker } from "./Hsn";
import { RequestAdditionLink } from "./RequestAddition";
import { useBrands } from "./Brands";
import { announceSaved, closeThisTab, creatable, useCreated } from "./Create";
import { groupPaths, useItemGroups } from "./ItemGroups";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { Fold, hashParam, SidePanel, SideRows } from "./Master";
import { labelFor, unitLabel, useUnits, type Unit } from "./Units";
import { longDate, type Company } from "./Companies";
import { ItemStockBox, openItemStock, qty, useItemStock } from "./Reports";
import { PriceTable, priceBody, rowFromServer, type PriceRow } from "./PriceLines";
import { ColumnSearch } from "./ColumnSearch";
import { accountsSummary, ItemAccountsEditor, saveItemAccounts, useItemAccounts, type ItemAccount } from "./ItemAccounts";
import { useReturns } from "./Refresh";

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
  /** Goods code for the challan and e-way bill, on a service that keeps stock (job work). */
  delivery_hsn?: string;
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
  tds_section?: string;
  safety_stock_qty: string | null;
  min_order_qty: string | null;
  max_stock_qty: string | null;
  batch_tracked: boolean;
  qc_required: boolean;
  default_request_type: string;
  maintain_stock: boolean;
  allow_purchase: boolean;
  purchase_charge: boolean;
  add_to_stock: string;
  allow_sales: boolean;
  offer_to_all: boolean;
  notes: string;
  is_active: boolean;
  units: ItemUnit[];
  gst_rates: GstRate[];
  party_names: PartyName[];
  warnings: string[];
  lock?: LockInfo;
};
export type GstRate = { valid_from: string; rate: string };
/** What one customer or supplier calls the item: their own name and/or code. */
export type PartyName = { party: number; party_name?: string; party_kind?: string; name: string; code: string };
type PartyRow = { id: number; name: string; customer_number: string; vendor_number: string; is_active?: boolean };

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
/** How a purchase charge is spread into the cost of the goods received. */
export const STOCK_COST: [string, string][] = [
  ["no", "No"],
  ["qty", "By Quantity"],
  ["value", "By Value"],
];
const stockCostLabel = (code: string) => STOCK_COST.find(([c]) => c === code)?.[1] ?? code;
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

/** `?form=new`, `?form=<id>` or `?form=copy-<id>` on #/items: this tab was opened to
 * add, change or duplicate one item (Sidharth, 2026-11-13), and shows only that form. */
function formParam(): string | null {
  const query = window.location.hash.split("?")[1] ?? "";
  return new URLSearchParams(query).get("form");
}

/** The name of the top-level group a group sits under. */
function groupTop(groups: { id: number; name: string; parent: number | null }[], id: number): string {
  let g = groups.find((x) => x.id === id);
  while (g && g.parent !== null) g = groups.find((x) => x.id === g!.parent);
  return g?.name ?? "";
}

/** `?view=<id>` on #/items: the item's own page (all its sections, read only). */
function viewParam(): number | null {
  const query = window.location.hash.split("?")[1] ?? "";
  const id = Number(new URLSearchParams(query).get("view"));
  return id > 0 ? id : null;
}

/** Open an item's own page in a new tab, beside the list. */
/** "Customer", "Supplier" or both, from the numbers the party was given. */
const partyKind = (p?: { customer_number: string; vendor_number: string }) =>
  [p?.customer_number && "Customer", p?.vendor_number && "Supplier"].filter(Boolean).join(", ");

function openItemView(id: number) {
  window.open(`${window.location.pathname}${window.location.search}#/items?view=${id}`, "_blank");
}

/** Open the add / change form of an item in a new tab, beside the list. */
function openItemForm(form: string) {
  window.open(`${window.location.pathname}${window.location.search}#/items?form=${form}`, "_blank");
}

/** The form alone, in its own tab: Save and Cancel close the tab and the list refreshes. */
function ItemFormTab({ form }: { form: string }) {
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (form === "new") {
      setItems([]);
      return;
    }
    api<Item[]>("v1/items/")
      .then(setItems)
      .catch((err: Error) => setError(err.message));
  }, [form]);
  const copy = form.startsWith("copy-");
  const target = form === "new" ? null : (items?.find((i) => i.id === Number(form.replace("copy-", ""))) ?? null);
  const toList = () => {
    window.location.hash = "#/items";
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("item_saved", saved);
    closeThisTab(toList);
  };
  const missing = form !== "new" && items !== null && target === null;
  const title = form === "new" ? "Add item" : copy ? "Duplicate item" : "Edit item";
  return (
    <section className="page item-edit">
      {error && <p className="error">{error}</p>}
      {missing && <p className="error">That item was not found.</p>}
      {items !== null && !missing && (
        <ItemForm
          title={title}
          item={copy ? null : target}
          copyOf={copy ? target : null}
          onDone={(id, name) => finish(id ? { id, name: name ?? "" } : undefined)}
          onCancel={() => finish()}
        />
      )}
      {items === null && !error && <PageHeader title={title} />}
    </section>
  );
}

export function ItemsPage({ session, company }: { session: SignedIn; company?: Company }) {
  const form = formParam();
  const view = viewParam();
  if (form && session.permissions.includes("masters.edit")) return <ItemFormTab form={form} />;
  if (view) return <ItemViewPage id={view} session={session} />;
  return <ItemList session={session} company={session.permissions.includes("stock.view") ? company : undefined} />;
}

function ItemList({ session, company }: { session: SignedIn; company?: Company }) {
  const canEdit = session.permissions.includes("masters.edit");
  // Stock of the company picked at the top right, for those who may see stock.
  const stock = useItemStock(company?.id);
  const { units } = useUnits();
  const [items, setItems] = useState<Item[]>([]);
  const [query, setQuery] = useState("");
  // `?group=<id>` (from the Items count on Item groups) shows that group and everything under it.
  const [groupFilter, setGroupFilter] = useState(hashParam("group") ?? "");
  const { groups: allGroups } = useItemGroups();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Item[]>("v1/items/")
      .then(setItems)
      .catch((err: Error) => setError(err.message));
  }, []);
  useEffect(reload, [reload]);
  // The add / change form is its own tab: when it saves, refresh and select the item.
  useCreated("item_saved", (c) => {
    reload();
    setQuery("");
    setSelectedId(c.id);
  });
  const io = useExchange({ master: "items", noun: "items", session, onImported: reload });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && items.some((i) => i.id === openId)) {
      setQuery("");
      setSelectedId(openId);
      opened();
    }
  }, [openId, items, opened]);

  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const inGroup = new Set<number>();
    if (groupFilter) {
      const add = (id: number) => {
        inGroup.add(id);
        allGroups.filter((g) => g.parent === id).forEach((g) => add(g.id));
      };
      add(Number(groupFilter));
    }
    return items.filter((i) => {
      if (groupFilter && (i.item_group === null || !inGroup.has(i.item_group))) return false;
      const text = [i.name, i.item_number, i.hsn, ...i.units.map((u) => u.barcode)].join(" ").toLowerCase();
      return words.every((w) => text.includes(w));
    });
  }, [items, query, groupFilter, allGroups]);
  const groupLabels = groupPaths(allGroups);
  const selected = items.find((i) => i.id === selectedId) ?? shown[0] ?? null;
  const pick = (i: Item) => setSelectedId(i.id);
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
            {canEdit && <button onClick={() => openItemForm("new")}>Add item</button>}
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          <div className="row filters">
            <input
              type="search"
              placeholder="Search by name, item number, HSN or barcode"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Combobox
              value={groupFilter}
              onChange={setGroupFilter}
              empty="All groups"
              ariaLabel="Item group"
              options={allGroups.map((g) => ({ value: String(g.id), label: groupLabels.get(g.id) ?? g.name }))}
            />
          </div>
          <table className="pick">
            <thead>
              <tr>
                <th>Item No</th>
                <th>Item Name</th>
                <th>Item Group</th>
                <th>HSN</th>
                <th>Stock Unit</th>
                <th className="num">GST Rate</th>
                {company && <th className="num">In Stock</th>}
              </tr>
              <ColumnSearch key={company ? "stock" : "plain"} />
            </thead>
            <tbody onKeyDown={onListKey}>
              {shown.length === 0 && (
                <tr>
                  <td colSpan={company ? 7 : 6} className="small">
                    No items match.
                  </td>
                </tr>
              )}
              {shown.map((i) => {
                const rate = rateToday(i.gst_rates);
                return (
                  <tr
                    key={i.id}
                    id={`item-${i.id}`}
                    tabIndex={0}
                    aria-selected={selected?.id === i.id}
                    className={["ledger-row", i.is_active ? "" : "inactive", selected?.id === i.id ? "selected" : ""].join(" ")}
                    onClick={() => pick(i)}
                    onDoubleClick={() => openItemView(i.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") openItemView(i.id);
                    }}
                  >
                    <td>{i.item_number}</td>
                    <td>
                      {i.name}
                      {!i.is_active && <span className="small"> · inactive</span>}
                    </td>
                    <td>{i.item_group_name ?? ""}</td>
                    <td>{i.hsn}</td>
                    <td>{labelFor(units, i.stock_unit, i.stock_unit_name)}</td>
                    <td className="num">{rate ? `${plain(rate.rate)}%` : ""}</td>
                    {company && (
                      <td className="num">
                        {i.maintain_stock && (
                          <a
                            href={`#/companies/${company.id}/stock-summary?item=${i.id}`}
                            title="See this item's stock by batch and bin"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              openItemStock(company.id, i.id);
                            }}
                          >
                            {qty(stock[String(i.id)] ?? "0")}
                          </a>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small">Click an item to see its details at the right; double-click or press Enter to open it.</p>}
        </div>
        <div className="side-col" aria-label="Item details">
          {selected ? (
            <>
              <SidePanel title="Item Details" tag={selected.item_number}>
                <SideRows
                  rows={[
                    ["Goods or service", typeLabel(selected.item_type)],
                    ["Item group", selected.item_group_name ?? ""],
                    ["Brand", selected.brand_name ?? ""],
                    ["HSN code", selected.hsn],
                    ...(selected.delivery_hsn ? ([["Delivery HSN", selected.delivery_hsn]] as [string, string][]) : []),
                    ["Default unit", labelFor(units, selected.stock_unit, selected.stock_unit_name)],
                    ["GST rate today", rateToday(selected.gst_rates) ? `${plain(rateToday(selected.gst_rates)!.rate)}%` : ""],
                  ]}
                />
                <div className="side-buttons">
                  <button type="button" className="link" onClick={() => openItemView(selected.id)}>
                    View
                  </button>
                  {canEdit && (
                    <button type="button" className="link" onClick={() => openItemForm(String(selected.id))}>
                      Edit
                    </button>
                  )}
                  {canEdit && (
                    <button type="button" className="link" onClick={() => openItemForm(`copy-${selected.id}`)}>
                      Duplicate
                    </button>
                  )}
                </div>
              </SidePanel>
              {company && selected.maintain_stock && <ItemStockBox companyId={company.id} itemId={selected.id} />}
              <ItemActivity item={selected} />
            </>
          ) : (
            <SidePanel title="Item Details">
              <p className="small">Pick an item to see its details here.</p>
            </SidePanel>
          )}
        </div>
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

function ItemActivity({ item }: { item: Item }) {
  return (
    <SidePanel title="Activity">
      <ChangeLog type="item" id={item.id} stamp={JSON.stringify(item)} />
    </SidePanel>
  );
}

/** The item's own page: every section, read only; Edit opens the form in a new tab. */
/** The view page's "Customer Prices": what each customer pays for the item (read only). */
function PricesView({ item, side }: { item: Item; side: "customer" | "supplier" }) {
  const [rows, setRows] = useState<(PriceRow & { id: number })[]>([]);
  useEffect(() => {
    api<(PriceRow & { id: number })[]>(`v1/items/${item.id}/${side}-prices/`).then(setRows);
  }, [item.id]);
  return (
    <Fold title={side === "supplier" ? "Supplier Prices" : "Customer Prices"} summary={`${rows.length} ${rows.length === 1 ? "price" : "prices"}`}>
      {rows.length === 0 ? (
        <p className="small">No {side} has its own price for this item.</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>{side === "supplier" ? "Supplier" : "Customer"}</th>
              <th>Unit</th>
              <th className="num">From Qty</th>
              <th className="num">Rate</th>
              <th>From Date</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.party_name}</td>
                <td>{r.unit_label}</td>
                <td className="num">{Number(r.min_qty)}</td>
                <td className="num">{Number(r.rate).toFixed(2)}</td>
                <td>{longDate(r.from_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Fold>
  );
}

/** The item's Expense Account in each company, on the item's own page. */
function AccountsView({ itemId }: { itemId: number }) {
  const [rows] = useItemAccounts(itemId);
  return (
    <Fold title="Accounts" summary={accountsSummary(rows)}>
      <Facts
        rows={(rows ?? []).map((r) => [
          `Expense Account, ${r.company_name}`,
          r.expense_ledger_name || (r.group_ledger_name ? `From item group: ${r.group_ledger_name}` : "From item group (not set)"),
        ])}
      />
    </Fold>
  );
}

function ItemViewPage({ id, session }: { id: number; session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { units } = useUnits();
  const unit = (id: number | null, name: string | null) => labelFor(units, id, name);
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Item[]>("v1/items/")
      .then(setItems)
      .catch((err: Error) => setError(err.message));
  }, []);
  useEffect(reload, [reload]);
  useCreated("item_saved", reload);
  // The page opens in its own tab: Close shuts it (or shows the list if it was opened by hand).
  const close = () =>
    closeThisTab(() => {
      window.location.hash = "#/items";
    });
  const i = items?.find((x) => x.id === id) ?? null;
  const rate = i ? rateToday(i.gst_rates) : undefined;
  return (
    <section className="page">
      <PageHeader
        title={i?.name ?? "Item"}
        sub={i ? `${i.item_number} · ${typeLabel(i.item_type)}${i.maintain_stock ? " · Stock kept" : ""}${i.is_active ? "" : " · inactive"}` : undefined}
        actions={
          <>
            {i && canEdit && (
              <button type="button" className="link" onClick={() => openItemForm(`copy-${i.id}`)}>
                Duplicate
              </button>
            )}
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {i && canEdit && <button onClick={() => openItemForm(String(i.id))}>Edit</button>}
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {items !== null && !i && <p className="error">That item was not found.</p>}
      {i && (
        <div className="side-layout">
          <div className="side-main">
            <Fold
              open
              title="General"
              summary={[typeLabel(i.item_type), i.item_group_name, i.hsn && `HSN ${i.hsn}`].filter(Boolean).join(" · ")}
            >
              <Facts
                rows={[
                  ["Goods or service", typeLabel(i.item_type)],
                  ["Item group", i.item_group_name ?? ""],
                  ["HSN code", i.hsn],
                  ...(i.delivery_hsn ? ([["Delivery HSN code", i.delivery_hsn]] as [string, string][]) : []),
                  ["Default unit of measure", unit(i.stock_unit, i.stock_unit_name)],
                  ["Brand", i.brand_name ?? ""],
                  ["Notes", i.notes],
                ]}
              />
            </Fold>
            <Fold
              title="Sales"
              summary={[i.mrp ? `MRP ₹ ${plain(i.mrp)}` : "MRP not set", i.best_before_value !== null && `Best before ${i.best_before_value} ${i.best_before_unit}`]
                .filter(Boolean)
                .join(" · ")}
            >
              <Facts
                rows={[
                  ["Default sales unit", unit(i.sales_unit, i.sales_unit_name)],
                  ["MRP", i.mrp === null ? "" : `₹ ${plain(i.mrp)}`],
                  ["USP", i.usp],
                  ["Best before", i.best_before_value === null ? "" : `${i.best_before_value} ${i.best_before_unit}`],
                  ["Batch No", i.batch_no],
                ]}
              />
              {i.sales_description && <div className="rich">{i.sales_description}</div>}
            </Fold>
            <Fold
              title="Purchase"
              summary={[i.lead_time_days !== null && `Lead time ${i.lead_time_days} days`, i.safety_stock_qty && `Safety stock ${plain(i.safety_stock_qty)}`]
                .filter(Boolean)
                .join(" · ")}
            >
              <Facts
                rows={[
                  ["Default purchase unit", unit(i.purchase_unit, i.purchase_unit_name)],
                  ["Lead time", i.lead_time_days === null ? "" : `${i.lead_time_days} days`],
                  ["Safety stock qty", i.safety_stock_qty === null ? "" : plain(i.safety_stock_qty)],
                  ["Minimum order qty", i.min_order_qty === null ? "" : plain(i.min_order_qty)],
                  ["Max stock qty", i.max_stock_qty === null ? "" : plain(i.max_stock_qty)],
                  ["TDS Section", i.tds_section || (i.item_type === "goods" ? "None (194Q when the company deducts it)" : "None (the supplier's default)")],
                ]}
              />
              {i.purchase_description && <div className="rich">{i.purchase_description}</div>}
            </Fold>
            <Fold title="GST Rates" summary={rate ? `${plain(rate.rate)}% from ${showDate(rate.valid_from)} (in force)` : "No rate set"}>
              {i.gst_rates.length > 0 && (
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
                          {r === rate && <span className="pill on">In force</span>}
                        </td>
                        <td className="num">{plain(r.rate)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Fold>
            <Fold
              title="Stock And Quality"
              summary={[i.batch_tracked ? "Batches tracked" : "Batches not tracked", i.qc_required ? "Quality check on receipt" : "No quality check"].join(" · ")}
            >
              <Facts
                rows={[
                  ["Batches tracked", i.batch_tracked ? "Yes" : "No"],
                  ["Quality check on receipt", i.qc_required ? "Yes" : "No"],
                  ["Default material request type", requestLabel(i.default_request_type)],
                ]}
              />
            </Fold>
            <Fold
              title="Units Of Measure"
              summary={`${i.units.length} ${i.units.length === 1 ? "unit" : "units"}${i.units.length ? `: ${i.units.map((u) => unit(u.unit, u.unit_name)).join(", ")}` : ""}`}
            >
              <div className="table-scroll">
                <table className="grid unit-lines">
                  <thead>
                    <tr>
                      <th>Unit</th>
                      <th>Contains</th>
                      <th className="num">= {i.stock_unit_name ? unit(i.stock_unit, i.stock_unit_name) : "Stock unit"}</th>
                      <th>Size (Cm)</th>
                      <th className="num">Net Kg</th>
                      <th className="num">Gross Kg</th>
                      <th>Barcode</th>
                      <th>Used For</th>
                    </tr>
                  </thead>
                  <tbody>
                    {i.units.map((u) => (
                      <tr key={u.unit}>
                        <td>
                          <b>{unit(u.unit, u.unit_name)}</b>
                          {!u.contains_unit_name && <span className="pill"> Stock unit</span>}
                        </td>
                        <td>{u.contains_unit_name ? `${plain(u.contains_qty)} ${unit(u.contains_unit, u.contains_unit_name)}` : "—"}</td>
                        <td className="num">{plain(u.factor)}</td>
                        <td>
                          {u.length_cm && u.breadth_cm && u.height_cm
                            ? `${plain(u.length_cm)}×${plain(u.breadth_cm)}×${plain(u.height_cm)}`
                            : "—"}
                        </td>
                        <td className="num">{u.net_kg ? plain(u.net_kg) : "—"}</td>
                        <td className="num">{u.gross_kg ? plain(u.gross_kg) : "—"}</td>
                        <td>{u.barcode || "—"}</td>
                        <td>
                          {u.used_for.map((c) => (
                            <span key={c} className="pill on">
                              {usedLabel(c)}
                            </span>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {i.warnings.map((w) => (
                <p key={w} className="small">
                  {w}
                </p>
              ))}
            </Fold>
            <Fold
              title="Customer And Supplier Names"
              summary={`${i.party_names.length} ${i.party_names.length === 1 ? "name" : "names"}`}
            >
              {i.party_names.length === 0 ? (
                <p className="small">No customer or supplier has its own name or code for this item.</p>
              ) : (
                <table className="grid">
                  <thead>
                    <tr>
                      <th>Customer Or Supplier</th>
                      <th>Their Item Name</th>
                      <th>Their Item Code</th>
                    </tr>
                  </thead>
                  <tbody>
                    {i.party_names.map((r) => (
                      <tr key={r.party}>
                        <td>
                          {r.party_name}
                          {r.party_kind && <span className="small"> · {r.party_kind}</span>}
                        </td>
                        <td>{r.name}</td>
                        <td>{r.code}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Fold>
            <AccountsView itemId={i.id} />
            <PricesView item={i} side="customer" />
            <PricesView item={i} side="supplier" />
            <Fold title="Connections" summary="No documents yet" />
          </div>
          <div className="side-col">
            <SidePanel title="Switches">
              <SideRows
                rows={[
                  ["Disabled", i.is_active ? "No" : "Yes"],
                  ["Allow purchase", i.allow_purchase ? "Yes" : "No"],
                  ...(i.item_type === "service"
                    ? ([
                        ["Use as Purchase Charge", i.purchase_charge ? "Yes" : "No"],
                        ...(i.purchase_charge ? [["Add to Stock Cost", stockCostLabel(i.add_to_stock)]] : []),
                      ] as [string, string][])
                    : []),
                  ["Allow sales", i.allow_sales ? "Yes" : "No"],
                  ["Offer to all", i.offer_to_all ? "Yes" : "No"],
                  ["Maintain stock", i.maintain_stock ? "Yes" : "No"],
                ]}
              />
            </SidePanel>
            <ItemActivity item={i} />
          </div>
        </div>
      )}
    </section>
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

function ItemForm(props: {
  title: string;
  item: Item | null;
  copyOf: Item | null;
  onDone: (savedId?: number, savedName?: string) => void;
  onCancel: () => void;
}) {
  const it = props.item;
  const locked = (field: string) => isLocked(it?.lock, field);
  const from = it ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const { units, refresh: refreshUnits } = useUnits();
  const newUnit = creatable("unit", "units", refreshUnits);
  const [name, setName] = useState(props.copyOf ? `${props.copyOf.name} (copy)` : (it?.name ?? ""));
  const [type, setType] = useState(from?.item_type ?? "goods");
  const [stocked, setStocked] = useState(from?.maintain_stock ?? true); // "Maintain stock", whatever the type
  const [disabled, setDisabled] = useState(it ? !it.is_active : false);
  const [allowPurchase, setAllowPurchase] = useState(from?.allow_purchase ?? true);
  const [purchaseCharge, setPurchaseCharge] = useState(from?.purchase_charge ?? false);
  const [addToStock, setAddToStock] = useState(from?.add_to_stock ?? "value");
  const [allowSales, setAllowSales] = useState(from?.allow_sales ?? true);
  const [offerAll, setOfferAll] = useState(from?.offer_to_all ?? false);
  const [stock, setStock] = useState(from ? String(from.stock_unit) : "");
  const { groups: itemGroups, refresh: refreshGroups } = useItemGroups();
  const newGroup = creatable("item_group", "item-groups", refreshGroups);
  const groupNames = groupPaths(itemGroups);
  const parents = new Set(itemGroups.map((g) => g.parent)); // groups with sub-groups are not offered
  const topGroup = (() => {
    let g = itemGroups.find((x) => String(x.id) === (it?.item_group ? String(it.item_group) : ""));
    while (g && g.parent !== null) g = itemGroups.find((x) => x.id === g!.parent);
    return g?.name ?? "";
  })();
  const [group, setGroup] = useState(from?.item_group == null ? "" : String(from.item_group));
  const { brands, refresh: refreshBrands } = useBrands();
  const newBrand = creatable("brand", "brands", refreshBrands);
  const [brand, setBrand] = useState(from?.brand == null ? "" : String(from.brand));
  const [hsn, setHsn] = useState(from?.hsn ?? "");
  const [deliveryHsn, setDeliveryHsn] = useState(from?.delivery_hsn ?? "");
  const [mrp, setMrp] = useState(from?.mrp == null ? "" : plain(from.mrp));
  const [usp, setUsp] = useState(from?.usp ?? "");
  const [bestBefore, setBestBefore] = useState(from?.best_before_value == null ? "" : String(from.best_before_value));
  const [bestBeforeUnit, setBestBeforeUnit] = useState(from?.best_before_unit ?? "days");
  const [batchNo, setBatchNo] = useState(from?.batch_no ?? "");
  const [tdsSection, setTdsSection] = useState(from?.tds_section ?? "");
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
  // A duplicate starts with no customer or supplier names: a party's code belongs to one item only.
  const [names, setNames] = useState<PartyName[]>(props.copyOf ? [] : (from?.party_names ?? []).map((r) => ({ ...r })));
  const [parties, setParties] = useState<PartyRow[]>([]);
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  useEffect(() => {
    api<PartyRow[]>("v1/parties/").then(setParties);
  }, [visits]);
  // Its own Expense Account per company (bills without goods receipt).
  const [accounts, setAccounts] = useItemAccounts(it && !props.copyOf ? it.id : null);
  // What customers pay for this item: one set of data with each customer's Item Prices.
  const [custPrices, setCustPrices] = useState<PriceRow[] | null>(null);
  useEffect(() => {
    if (!it || props.copyOf) return;
    api<(PriceRow & { min_qty: string; rate: string })[]>(`v1/items/${it.id}/customer-prices/`).then((r) =>
      setCustPrices(r.map(rowFromServer)),
    );
  }, [it, props.copyOf]);
  // What suppliers charge for this item. A duplicate can start with the original's lines.
  const [suppPrices, setSuppPrices] = useState<PriceRow[] | null>(null);
  const [copyPrices, setCopyPrices] = useState(true);
  const [copySource, setCopySource] = useState<PriceRow[]>([]);
  useEffect(() => {
    const source = it ?? props.copyOf;
    if (!source) return;
    api<(PriceRow & { min_qty: string; rate: string })[]>(`v1/items/${source.id}/supplier-prices/`).then((r) => {
      const rows = r.map(rowFromServer);
      if (it) setSuppPrices(rows);
      else setCopySource(rows);
    });
  }, [it, props.copyOf]);
  const [rows, setRows] = useState<Row[]>(
    (from?.units ?? []).map((u) => {
      const r = rowOf(u);
      return props.copyOf ? { ...r, barcode: "" } : r; // barcodes belong to one item
    }),
  );
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"none" | "general" | "sales" | "purchase" | "gst" | "stock" | "units" | "names" | "prices" | "supplier-prices" | "accounts" | "connections">("general");

  const used = new Set(rows.map((r) => r.unit));
  const offered = (current: string) =>
    units.filter((u) => (u.is_active || String(u.id) === current) && (!used.has(String(u.id)) || String(u.id) === current));
  const unitName = (id: string) => labelFor(units, id);
  const fac = factors(stock, rows);
  const stockName = unitName(stock);
  const listed = [stock, ...rows.map((r) => r.unit)].filter((id, k, all) => id && all.indexOf(id) === k);
  const unitChoices = listed.map((id) => ({ value: id, label: unitName(id) }));
  const [centralRates, setCentralRates] = useState<{ rate: string; label: string }[]>([]);
  useEffect(() => {
    api<{ rate: string; label: string }[]>("v1/gst-rates/").then(setCentralRates);
  }, []);
  // The active central rates, plus a rate this item already holds that has since been disabled.
  const rateOptions = (current: string) => {
    const list = centralRates.map((c) => ({ value: plain(c.rate), label: c.label }));
    if (current && !list.some((o) => o.value === current)) list.push({ value: current, label: `GST ${current}%` });
    return list;
  };
  const setRate = (i: number, change: Partial<GstRate>) => setRates(rates.map((r, j) => (j === i ? { ...r, ...change } : r)));
  // One unit at a time is edited in the box under the list; the others show as one line each.
  const [editing, setEditing] = useState<number | null>(null);
  const [editBackup, setEditBackup] = useState<Row | null>(null); // null while adding a new unit
  const [unitError, setUnitError] = useState("");
  const startEdit = (i: number) => {
    setUnitError("");
    setEditBackup({ ...rows[i], used_for: [...rows[i].used_for] });
    setEditing(i);
  };
  const addUnit = () => {
    setUnitError("");
    setEditBackup(null);
    setRows([...rows, blankRow()]);
    setEditing(rows.length);
  };
  const cancelEdit = () => {
    if (editing === null) return;
    setRows(editBackup ? rows.map((r, j) => (j === editing ? editBackup : r)) : rows.filter((_, j) => j !== editing));
    setEditing(null);
    setEditBackup(null);
  };
  const finishEdit = () => {
    const r = editing === null ? undefined : rows[editing];
    if (!r) return;
    const isStock = r.unit !== "" && r.unit === stock;
    if (!r.unit) return setUnitError("Pick the unit.");
    if (!isStock && (!r.contains_qty.trim() || !r.contains_unit)) return setUnitError("Fill in how many of which unit it contains.");
    setUnitError("");
    setEditing(null);
    setEditBackup(null);
  };
  const removeUnit = (i: number) => {
    setRows(rows.filter((_, j) => j !== i));
    if (editing !== null) setEditing(editing === i ? null : editing > i ? editing - 1 : editing);
  };
  const setRow = (i: number, change: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const toggleUsed = (i: number, code: string, on: boolean) =>
    setRow(i, { used_for: on ? [...rows[i].used_for, code] : rows[i].used_for.filter((c) => c !== code) });

  // A service that keeps stock (job work): the invoice uses the service code (HSN code),
  // the delivery challan and e-way bill use the goods code (Delivery HSN code).
  const jobWork = type === "service" && stocked;
  const num = (v: string) => (v.trim() === "" ? null : v.trim());
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    // The General tab's boxes are not on screen while another tab is open, so
    // the browser cannot check them: check here and take the person there.
    if (!name.trim() || !stock || !hsn || !group || (jobWork && !deliveryHsn)) {
      setTab("general");
      setError(
        !name.trim()
          ? "Give the item name at the top."
          : !stock
            ? "Pick the default unit of measure on the General tab."
            : !hsn
              ? "Pick the HSN code on the General tab."
              : !group
                ? "Pick the item group on the General tab."
                : "Pick the delivery HSN code on the General tab.",
      );
      return;
    }
    setBusy(true);
    const body = {
      name,
      item_type: type,
      maintain_stock: stocked,
      allow_purchase: allowPurchase,
      purchase_charge: type === "service" && purchaseCharge,
      add_to_stock: addToStock,
      allow_sales: allowSales,
      offer_to_all: offerAll,
      is_active: !disabled,
      stock_unit: Number(stock),
      hsn,
      delivery_hsn: jobWork ? deliveryHsn : "",
      item_group: group === "" ? null : Number(group),
      brand: brand === "" ? null : Number(brand),
      mrp: num(mrp),
      usp,
      best_before_value: num(bestBefore),
      best_before_unit: bestBeforeUnit,
      batch_no: batchNo,
      lead_time_days: num(leadTime),
      tds_section: tdsSection,
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
      party_names: names.filter((r) => r.party).map((r) => ({ party: r.party, name: r.name.trim(), code: r.code.trim() })),
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
      if (it && custPrices !== null) await api(`v1/items/${saved.id}/customer-prices/`, priceBody(custPrices), "PUT");
      if (it && suppPrices !== null) await api(`v1/items/${saved.id}/supplier-prices/`, priceBody(suppPrices), "PUT");
      if (it && accounts !== null) await saveItemAccounts(saved.id, accounts);
      if (!it && props.copyOf && copyPrices && copySource.length > 0) {
        // The copy keeps every supplier line whose unit the new item also has.
        const has = new Set(saved.units.map((u) => u.unit));
        await api(`v1/items/${saved.id}/supplier-prices/`, priceBody(copySource.filter((r) => r.unit && has.has(r.unit))), "PUT");
      }
      props.onDone(saved.id, saved.name);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  const folds = [
    ["general", "General", [typeLabel(type), hsn && `HSN ${hsn}`].filter(Boolean).join(" · ")],
    ["sales", "Sales", [mrp ? `MRP ₹ ${mrp}` : "", bestBefore ? `Best before ${bestBefore} ${bestBeforeUnit}` : ""].filter(Boolean).join(" · ")],
    ["purchase", "Purchase", [leadTime ? `Lead time ${leadTime} days` : "", safety ? `Safety stock ${safety}` : ""].filter(Boolean).join(" · ")],
    ["gst", "GST Rates", `${rates.length} ${rates.length === 1 ? "rate" : "rates"}`],
    ["stock", "Stock And Quality", [batches ? "Batches tracked" : "", qc ? "Quality check on receipt" : ""].filter(Boolean).join(" · ")],
    ["units", "Units Of Measure", `${rows.length} ${rows.length === 1 ? "unit" : "units"}`],
    ["names", "Customer And Supplier Names", `${names.length} ${names.length === 1 ? "name" : "names"}`],
    ["prices", "Customer Prices", `${(custPrices ?? []).length} ${(custPrices ?? []).length === 1 ? "price" : "prices"}`],
    ["supplier-prices", "Supplier Prices", `${(suppPrices ?? []).length} ${(suppPrices ?? []).length === 1 ? "price" : "prices"}`],
    ["accounts", "Accounts", accountsSummary(accounts)],
    ["connections", "Connections", "No documents yet"],
  ] as const;
  return (
    <>
      <PageHeader
        title={props.title}
        sub={it ? `${it.item_number} · ${typeLabel(type)}${stocked ? " · Stock kept" : ""}${disabled ? " · Disabled" : ""}` : undefined}
        actions={
          <>
            <button type="button" className="link" onClick={props.onCancel}>
              Cancel
            </button>
            <button type="submit" form="item-form" disabled={busy}>
              Save
            </button>
          </>
        }
      />
      <form id="item-form" className="side-layout" onSubmit={save}>
        <div className="side-main">
      <div className="item-head">
        <label className="item-title">
          <span className="req small">Item name</span>
          <input
            required
            autoFocus
            maxLength={120}
            placeholder="Item name"
            aria-label="Item name"
            value={name}
            onChange={(e) => changeName(e.target.value)}
          />
        </label>
        <p className="item-sub">
          <b>{it?.item_number ?? "Number given when you save"}</b>
          <span className="tag">{typeLabel(type)}</span>
          <span className="tag">{stocked ? "Stock kept" : "No stock kept"}</span>
          {disabled && <span className="tag">Disabled</span>}
        </p>
      </div>

        <InUseNote lock={it?.lock} />
        <div className={"fold" + (tab === "general" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "general"} onClick={() => setTab(tab === "general" ? "none" : "general")}>
            <span className="fold-title">{folds[0][1]}</span>
            {tab !== "general" && <span className="fold-summary">{folds[0][2]}</span>}
          </button>
          {tab === "general" && <div className="fold-body">
        {true && (
        <Section>
          <p className="small"><span className="req-star">*</span> Required</p>
          <div className="item-general single">
            <div>
              <label>
                <span className="req">Goods or service</span>
                <Locked on={locked("item_type")}>
                  <Combobox value={type} onChange={setType} options={TYPES.map(([value, label]) => ({ value, label }))} />
                </Locked>
              </label>
              <label>
                <span className="req">Item group</span>
                <Combobox
                  required
                  value={group}
                  placeholder="Type to search groups…"
                  options={itemGroups
                    .filter((g) => (g.is_active && !parents.has(g.id)) || String(g.id) === group)
                    .filter((g) => !(it?.lock?.in_use.length) || !topGroup || groupTop(itemGroups, g.id) === topGroup)
                    .map((g) => ({ value: String(g.id), label: groupNames.get(g.id) ?? g.name }))}
                  onChange={setGroup}
                  create={newGroup}
                />
                {it && it.lock && it.lock.in_use.length > 0 && topGroup && (
                  <span className="small">In use: can move only to another group under {topGroup}.</span>
                )}
              </label>
              <label>
                <span className="req">HSN code</span>
                {jobWork && <span className="small"> (the service code, used on the invoice)</span>}
                <Locked on={locked("hsn")}>
                  <HsnPicker value={hsn} onChange={setHsn} />
                </Locked>
                <RequestAdditionLink kind="hsn" />
              </label>
              <label>
                HSN description
                <HsnDescription code={hsn} />
              </label>
              {jobWork && (
                <>
                  <label>
                    <span className="req">Delivery HSN code</span>
                    <span className="small"> (the goods code, used on the delivery challan and e-way bill)</span>
                    <Locked on={locked("delivery_hsn")}>
                      <HsnPicker value={deliveryHsn} onChange={setDeliveryHsn} />
                    </Locked>
                    <RequestAdditionLink kind="hsn" />
                  </label>
                  <label>
                    Delivery HSN description
                    <HsnDescription code={deliveryHsn} />
                  </label>
                </>
              )}
              <label>
                <span className="req">Default unit of measure</span>
                <Locked on={locked("stock_unit")}>
                <Combobox
                  required
                  value={stock}
                  placeholder="Type to search units…"
                  options={units
                    .filter((u: Unit) => u.is_active || String(u.id) === stock)
                    .map((u) => ({ value: String(u.id), label: unitLabel(u) }))}
                  onChange={setStock}
                  create={newUnit}
                />
                </Locked>
              </label>
                <label>
                  <span className="req">Brand</span>
                  <Combobox
                    required
                    value={brand}
                    placeholder="Type to search brands…"
                    options={brands
                      .filter((b) => b.is_active || String(b.id) === brand)
                      .map((b) => ({ value: String(b.id), label: b.name }))}
                    onChange={setBrand}
                    create={newBrand}
                  />
                </label>
            </div>
          </div>
        </Section>
        )}
        {true && (
        <Section>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </Section>
        )}
          </div>}
        </div>
        <div className={"fold" + (tab === "sales" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "sales"} onClick={() => setTab(tab === "sales" ? "none" : "sales")}>
            <span className="fold-title">{folds[1][1]}</span>
            {tab !== "sales" && <span className="fold-summary">{folds[1][2]}</span>}
          </button>
          {tab === "sales" && <div className="fold-body">
        {true && (
          <Section>
            <div className="item-fields">
              <label>
                Sales description
                <textarea rows={4} maxLength={5000} value={salesText} onChange={(e) => setSalesText(e.target.value)} />
                <span className="small">The wording customers see for this item on quotations, orders and sales bills. Plain text: on print it shows smaller, under the item name.</span>
              </label>
              <div className="item-cols wide">
                <label>
                  Default sales unit
                  <Combobox value={salesUnit} onChange={setSalesUnit} empty="Same as the stock unit" options={unitChoices} />
                </label>
                <label>
                  MRP (₹)
                  <input className="num" inputMode="decimal" value={mrp} onChange={(e) => setMrp(e.target.value)} />
                </label>
                <label>
                  USP
                  <input maxLength={200} value={usp} onChange={(e) => setUsp(e.target.value)} />
                </label>
                <label>
                  Batch No
                  <input maxLength={60} value={batchNo} onChange={(e) => setBatchNo(e.target.value)} />
                </label>
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
              </div>
            </div>
          </Section>
        )}
          </div>}
        </div>
        <div className={"fold" + (tab === "purchase" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "purchase"} onClick={() => setTab(tab === "purchase" ? "none" : "purchase")}>
            <span className="fold-title">{folds[2][1]}</span>
            {tab !== "purchase" && <span className="fold-summary">{folds[2][2]}</span>}
          </button>
          {tab === "purchase" && <div className="fold-body">
        {true && (
          <Section>
            <div className="item-fields">
              <label>
                Purchase description
                <textarea rows={4} maxLength={5000} value={buyText} onChange={(e) => setBuyText(e.target.value)} />
                <span className="small">The wording suppliers see for this item on purchase orders. Plain text: on print it shows smaller, under the item name.</span>
              </label>
              <div className="item-cols wide">
                <label>
                  Default purchase unit
                  <Combobox value={buyUnit} onChange={setBuyUnit} empty="Same as the stock unit" options={unitChoices} />
                </label>
                <label>
                  Lead time in days
                  <input className="num" inputMode="numeric" value={leadTime} onChange={(e) => setLeadTime(e.target.value)} />
                </label>
                <div aria-hidden="true" />
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
                <label>
                  TDS Section
                  <TdsSectionPicker value={tdsSection} onChange={setTdsSection} empty={type === "service" ? "None: the supplier's default" : "None: 194Q when the company deducts it"} />
                  <span className="small">e.g. 194C for an Annual Maintenance (AMC). Goods usually leave it empty.</span>
                </label>
              </div>
              <p className="small wide">The quantities are in the item's default unit.</p>
            </div>
          </Section>
        )}
          </div>}
        </div>
        <div className={"fold" + (tab === "gst" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "gst"} onClick={() => setTab(tab === "gst" ? "none" : "gst")}>
            <span className="fold-title">{folds[3][1]}</span>
            {tab !== "gst" && <span className="fold-summary">{folds[3][2]}</span>}
          </button>
          {tab === "gst" && <div className="fold-body">
        {true && (
          <Section>
            <p className="small">
              When the law changes, click "Add rate" and give the new rate and the date it starts. Keep the old rows: bills
              take the rate in force on the bill date.
            </p>
            {rates.length > 0 && (
              <table className="grid">
                <thead>
                  <tr>
                    <th><span className="req">From</span></th>
                    <th className="num"><span className="req">GST rate (%)</span></th>
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
                        <Combobox
                          required
                          ariaLabel="GST rate (%)"
                          placeholder="Type to search rates…"
                          value={r.rate}
                          options={rateOptions(r.rate)}
                          onChange={(v) => setRate(i, { rate: v })}
                        />
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
              </button>{" "}
              <RequestAdditionLink kind="gst_rate" label="Rate not in the list? Request Addition" />
            </div>
          </Section>
        )}
          </div>}
        </div>
        <div className={"fold" + (tab === "stock" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "stock"} onClick={() => setTab(tab === "stock" ? "none" : "stock")}>
            <span className="fold-title">{folds[4][1]}</span>
            {tab !== "stock" && <span className="fold-summary">{folds[4][2]}</span>}
          </button>
          {tab === "stock" && <div className="fold-body">
        {true && (
        <Section>
          <div className="item-general">
            <div className="item-fields">
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
            <fieldset className="item-checks">
              <legend>Switches</legend>
              <label className="check">
                <Locked on={locked("batch_tracked")}>
                  <input type="checkbox" checked={batches} onChange={(e) => setBatches(e.target.checked)} />
                  Track batches
                </Locked>
              </label>
              <label className="check">
                <input type="checkbox" checked={qc} onChange={(e) => setQc(e.target.checked)} />
                Quality check on receipt
              </label>
              <p className="small">"Track batches" asks for the batch number and expiry on every receipt and issue.</p>
            </fieldset>
          </div>
        </Section>
        )}
          </div>}
        </div>
        <div className={"fold" + (tab === "units" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "units"} onClick={() => setTab(tab === "units" ? "none" : "units")}>
            <span className="fold-title">{folds[5][1]}</span>
            {tab !== "units" && <span className="fold-summary">{folds[5][2]}</span>}
          </button>
          {tab === "units" && <div className="fold-body">
        {true && (
        <Locked on={locked("units")}>
        <Section>
          <p className="small">
            The stock unit is added for you. For every other unit say how many of which unit it contains; "= {stockName || "stock unit"}" is
            worked out from that.
          </p>
          {rows.length > 0 && (
            <div className="table-scroll">
              <table className="grid unit-lines">
                <thead>
                  <tr>
                    <th>Unit</th>
                    <th>Contains</th>
                    <th className="num">= {stockName || "Stock unit"}</th>
                    <th>Size (Cm)</th>
                    <th className="num">Net Kg</th>
                    <th className="num">Gross Kg</th>
                    <th>Barcode</th>
                    <th>Used For</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => {
                    const isStock = r.unit !== "" && r.unit === stock;
                    return (
                      <tr key={i} className={editing === i ? "sel" : ""}>
                        <td>
                          <b>{r.unit ? unitName(r.unit) : "New unit"}</b>
                          {isStock && <span className="pill"> Stock unit</span>}
                        </td>
                        <td>{isStock || !r.contains_unit ? "—" : `${r.contains_qty} ${unitName(r.contains_unit)}`}</td>
                        <td className="num">{r.unit && fac.has(r.unit) ? Number(fac.get(r.unit)!.toFixed(6)) : "—"}</td>
                        <td>{r.length_cm && r.breadth_cm && r.height_cm ? `${r.length_cm}×${r.breadth_cm}×${r.height_cm}` : "—"}</td>
                        <td className="num">{r.net_kg || "—"}</td>
                        <td className="num">{r.gross_kg || "—"}</td>
                        <td>{r.barcode || "—"}</td>
                        <td>
                          {r.used_for.map((c) => (
                            <span key={c} className="pill on">
                              {usedLabel(c)}
                            </span>
                          ))}
                        </td>
                        <td className="row-actions">
                          <button type="button" className="link" onClick={() => startEdit(i)}>
                            Edit
                          </button>
                          {!isStock && (
                            <button type="button" className="link danger" onClick={() => removeUnit(i)}>
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
          )}
          {editing !== null && rows[editing] && (() => {
            const i = editing;
            const r = rows[i];
            const isStock = r.unit !== "" && r.unit === stock;
            return (
              <div className="address-card unit-edit">
                <h4>{editBackup ? `Edit Unit${r.unit ? `: ${unitName(r.unit)}` : ""}` : "Add Unit"}</h4>
                  <div className="row">
                    <label>
                      <span className="req">Unit</span>
                      <Combobox
                        required
                        value={r.unit}
                        placeholder="Type to search units…"
                        options={offered(r.unit).map((u) => ({ value: String(u.id), label: unitLabel(u) }))}
                        create={newUnit}
                        onChange={(v) => {
                          const picked = units.find((u) => String(u.id) === v);
                          setRow(i, { unit: v, whole_numbers: picked ? picked.whole_numbers : true });
                        }}
                      />
                    </label>
                    {!isStock && (
                      <label>
                        <span className="req">Contains how many</span>
                        <input required inputMode="decimal" value={r.contains_qty} onChange={(e) => setRow(i, { contains_qty: e.target.value })} />
                      </label>
                    )}
                    {!isStock && (
                      <label>
                        <span className="req">Of</span>
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
                {unitError && <p className="error">{unitError}</p>}
                <div className="buttons">
                  <button type="button" onClick={finishEdit}>
                    Done
                  </button>
                  <button type="button" className="link" onClick={cancelEdit}>
                    Cancel
                  </button>
                </div>
              </div>
            );
          })()}
          {editing === null && (
            <div>
              <button type="button" className="link" onClick={addUnit}>
                Add unit
              </button>
            </div>
          )}
        </Section>
        </Locked>
        )}
          </div>}
        </div>
        <div className={"fold" + (tab === "names" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "names"} onClick={() => setTab(tab === "names" ? "none" : "names")}>
            <span className="fold-title">{folds[6][1]}</span>
            {tab !== "names" && <span className="fold-summary">{folds[6][2]}</span>}
          </button>
          {tab === "names" && <div className="fold-body">
            <Section>
              <p className="small">
                The name and code a customer or supplier uses for this item. They show on that party's Products tab and
                will print on its documents. A party's code can belong to only one item.
              </p>
              {names.length > 0 && (
                <table className="grid">
                  <thead>
                    <tr>
                      <th>Customer Or Supplier</th>
                      <th>Their Item Name</th>
                      <th>Their Item Code</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {names.map((r, k) => (
                      <tr key={r.party}>
                        <td>
                          {parties.find((x) => x.id === r.party)?.name ?? r.party_name}
                          <span className="small"> · {partyKind(parties.find((x) => x.id === r.party)) || r.party_kind}</span>
                        </td>
                        <td>
                          <input
                            aria-label="Their item name"
                            maxLength={120}
                            value={r.name}
                            onChange={(e) => setNames(names.map((x, j) => (j === k ? { ...x, name: e.target.value } : x)))}
                          />
                        </td>
                        <td>
                          <input
                            aria-label="Their item code"
                            maxLength={40}
                            value={r.code}
                            onChange={(e) => setNames(names.map((x, j) => (j === k ? { ...x, code: e.target.value } : x)))}
                          />
                        </td>
                        <td>
                          <button type="button" className="link danger" onClick={() => setNames(names.filter((_, j) => j !== k))}>
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <label>
                Add Customer Or Supplier
                <Combobox
                  value=""
                  placeholder="Type to search customers and suppliers…"
                  ariaLabel="Add customer or supplier"
                  options={parties
                    .filter((x) => !names.some((n) => n.party === x.id))
                    .map((x) => ({ value: String(x.id), label: `${x.name}${partyKind(x) ? ` · ${partyKind(x)}` : ""}` }))}
                  onChange={(v) => {
                    const id = Number(v);
                    if (id) setNames([...names, { party: id, name: "", code: "" }]);
                  }}
                />
              </label>
            </Section>
          </div>}
        </div>
        <div className={"fold" + (tab === "prices" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "prices"} onClick={() => setTab(tab === "prices" ? "none" : "prices")}>
            <span className="fold-title">{folds[7][1]}</span>
            {tab !== "prices" && <span className="fold-summary">{folds[7][2]}</span>}
          </button>
          {tab === "prices" && <div className="fold-body">
            <Section>
              {!it || custPrices === null ? (
                <p className="small">Save the item first; then add the rates a customer pays for it here.</p>
              ) : (
                <>
                  <p className="small">
                    What a customer pays for this item, from a date and a quantity. Where a customer has any price for this
                    item, only those are used for it; its price list covers the other items. The same lines show under that
                    customer's "Item Prices". Rates are before GST.
                  </p>
                  <PriceTable rows={custPrices} onChange={setCustPrices} by="customer" item={it} />
                </>
              )}
            </Section>
          </div>}
        </div>
        <div className={"fold" + (tab === "supplier-prices" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "supplier-prices"} onClick={() => setTab(tab === "supplier-prices" ? "none" : "supplier-prices")}>
            <span className="fold-title">{folds[8][1]}</span>
            {tab !== "supplier-prices" && <span className="fold-summary">{folds[8][2]}</span>}
          </button>
          {tab === "supplier-prices" && <div className="fold-body">
            <Section>
              {props.copyOf ? (
                <label className="tick">
                  <input type="checkbox" checked={copyPrices} onChange={(e) => setCopyPrices(e.target.checked)} />
                  Copy supplier prices ({copySource.length} {copySource.length === 1 ? "line" : "lines"} from {props.copyOf.name})
                </label>
              ) : !it || suppPrices === null ? (
                <p className="small">Save the item first; then add the rates a supplier charges for it here.</p>
              ) : (
                <>
                  <p className="small">
                    What a supplier charges for this item, from a date and a quantity. Where a supplier has any price for this
                    item, only those are used for it; its price list covers the other items. The same lines show under that
                    supplier's "Item Prices". Rates are before GST.
                  </p>
                  <PriceTable rows={suppPrices} onChange={setSuppPrices} by="supplier" item={it} />
                </>
              )}
            </Section>
          </div>}
        </div>
        <div className={"fold" + (tab === "accounts" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "accounts"} onClick={() => setTab(tab === "accounts" ? "none" : "accounts")}>
            <span className="fold-title">{folds[9][1]}</span>
            {tab !== "accounts" && <span className="fold-summary">{folds[9][2]}</span>}
          </button>
          {tab === "accounts" && <div className="fold-body">
            <Section>
              {!it || accounts === null ? (
                <p className="small">Save the item first; then pick its Expense Account for each company here.</p>
              ) : (
                <ItemAccountsEditor rows={accounts} onChange={(rows: ItemAccount[]) => setAccounts(rows)} />
              )}
            </Section>
          </div>}
        </div>
        <div className={"fold" + (tab === "connections" ? " open" : "")}>
          <button type="button" className="fold-head" aria-expanded={tab === "connections"} onClick={() => setTab(tab === "connections" ? "none" : "connections")}>
            <span className="fold-title">{folds[10][1]}</span>
            {tab !== "connections" && <span className="fold-summary">{folds[10][2]}</span>}
          </button>
          {tab === "connections" && <div className="fold-body">
        {true && (
          <Section>
            <p className="small">
              The documents that use this item, with a count for each, will be listed here once purchase, sales and stock
              entries are built.
            </p>
          </Section>
        )}
          </div>}
        </div>
      <ErrorNote error={error} />
        </div>
        <div className="side-col">
          <SidePanel title="Switches">
            <div className="item-switches">
                            <label className="check">
                <input type="checkbox" checked={disabled} onChange={(e) => setDisabled(e.target.checked)} />
                Disabled
              </label>
              <label className="check">
                <input type="checkbox" checked={allowPurchase} onChange={(e) => setAllowPurchase(e.target.checked)} />
                Allow purchase
              </label>
              {type === "service" && (
                <label className="check">
                  <input type="checkbox" checked={purchaseCharge} onChange={(e) => setPurchaseCharge(e.target.checked)} />
                  Use as Purchase Charge
                </label>
              )}
              {type === "service" && purchaseCharge && (
                <label>
                  Add to Stock Cost
                  <Combobox
                    value={addToStock}
                    onChange={setAddToStock}
                    options={STOCK_COST.map(([value, label]) => ({ value, label }))}
                  />
                </label>
              )}
              <label className="check">
                <input type="checkbox" checked={allowSales} onChange={(e) => setAllowSales(e.target.checked)} />
                Allow sales
              </label>
              <label className="check">
                <input type="checkbox" checked={offerAll} onChange={(e) => setOfferAll(e.target.checked)} />
                Offer to all
              </label>
              <label className="check">
                <Locked on={locked("maintain_stock")}>
                  <input type="checkbox" checked={stocked} onChange={(e) => setStocked(e.target.checked)} />
                  Maintain stock
                </Locked>
              </label>
              <p className="small">"Maintain stock" says whether stock of this item is kept, goods or service.</p>
            </div>
          </SidePanel>
          <SidePanel title="Tips">
            <p className="small">A red * marks a field that must be filled in.</p>
            <p className="small">Pick an item group that has no sub-groups.</p>
          </SidePanel>
          {it && (
            <SidePanel title="Activity">
              <ChangeLog type="item" id={it.id} stamp={JSON.stringify(it)} />
            </SidePanel>
          )}
        </div>
      </form>
    </>
  );
}
