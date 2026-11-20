import { deliveryBase, makeDeliveryNote } from "./DeliveryNotes";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { Attachments, keptDraft } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { TermsText } from "./Terms";
import { Combobox } from "./Combobox";
import { longDate, money } from "./Companies";
import { announceSaved, closeThisTab, creatable, useCreated, type Creatable } from "./Create";
import { useCreditTerms } from "./CreditTerms";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { AddressBlock, ContactTicks, PaymentPanel, TotalsPanel, type Contact, type Place } from "./PurchaseOrders";
import { OrderMail } from "./SupplierMail";
import { type PickBrief } from "./PickLists";
import { useOnReturn, useReturns } from "./Refresh";

/** Entry > Sales > Sales Order: what a customer asked the company for. A draft can be
 * changed; Submit gives it its number and fixes it. Nothing here posts to the books.
 * Goods go out from a branch, or from one area of it ("Despatch From"); the "In Stock"
 * column counts only there (Sidharth, 2026-11-19). */

type Line = {
  id: number;
  item: number;
  item_name: string;
  item_number: string;
  hsn: string;
  description: string;
  unit: number;
  unit_name: string;
  qty: string;
  rate: string;
  rate_source: string;
  taxable: string;
  gst_rate: string;
  amount: string;
  delivered_qty: string;
  pending_qty: string;
  stock: boolean;
  in_stock?: string;
  customer_code?: string;
  closed_at: string | null;
  closed_by_name: string;
  close_reason: string;
};
type Charge = {
  id: number;
  item: number;
  item_name: string;
  sac: string;
  basis: string;
  basis_label: string;
  rate: string;
  amount: string;
  gst_rate: string;
  cgst: string;
  sgst: string;
  igst: string;
};
type SalesOrder = {
  id: number;
  number: string;
  status: string;
  status_label: string;
  submitted_at: string | null;
  customer: number;
  customer_name: string;
  customer_gstin: string;
  branch: number;
  branch_name: string;
  area: number | null;
  area_name: string;
  despatch_from: string;
  bill_from: number | null;
  bill_from_name: string;
  bill_address: Partial<Place>;
  ship_address: Partial<Place>;
  order_date: string;
  delivery_date: string | null;
  credit_term: number | null;
  credit_term_name: string;
  transporter: number | null;
  transporter_name: string;
  salesman: number | null;
  salesman_name: string;
  mail_to: number[];
  customer_po_no: string;
  customer_po_date: string | null;
  terms_set: number | null;
  terms_set_name: string;
  terms: string;
  notes: string;
  interstate: boolean;
  taxable_total: string;
  cgst_total: string;
  sgst_total: string;
  igst_total: string;
  round_off: string;
  total: string;
  cancel_reason: string;
  created_by_name: string;
  line_count: number;
  lines?: Line[];
  charges?: Charge[];
  mail_contacts?: Contact[];
  addresses?: { bill_from: Place | null; customer: Place & { name: string }; ship_to: (Place & { name: string }) | null };
  credit_warning?: string;
  /** Made on Submit (Sidharth, 2026-11-19): the newest is the one that counts. */
  pick_lists?: PickBrief[];
  delivery_notes?: { id: number; number: string; status: string; status_label: string }[];
};
type Customer = {
  id: number;
  name: string;
  is_active: boolean;
  customer_number: string;
  gstin: string;
  gst_type_label: string;
  state_code: string;
  credit_term: number | null;
  transporter: number | null;
  salesman: number | null;
  credit_limit: string;
  outstanding: string;
  terms_set: number | null;
  charges_gst: boolean;
  contacts: Contact[];
  addresses: (Place & { is_shipping: boolean })[];
};
type Despatch = { value: string; branch: number; area: number | null; label: string; hint: string; is_active: boolean };
type Named = { id: number; name: string; is_active: boolean };
type BranchRow = Named & { state_code: string; no_stock: boolean; address_block: Place };
type Setup = {
  company_name: string;
  customers: Customer[];
  despatch: Despatch[];
  branches: BranchRow[];
  salesmen: Named[];
  transporters: Named[];
  terms_sets: (Named & { text: string })[];
  default_terms: number | null;
  charge_items: { id: number; name: string; sac: string; gst_rate: string | null }[];
  gst_rates: string[];
  customer_group: number | null;
};
type SellItem = {
  id: number;
  name: string;
  item_number: string;
  hsn: string;
  description: string;
  maintain_stock: boolean;
  sales_unit: number;
  units: { unit: number; name: string; whole_numbers: boolean; factor: string }[];
  gst_rate: string | null;
  /** In the item's stock unit, at the "Despatch From" place; null for an item kept out of stock. */
  in_stock: string | null;
  customer_name: string;
  customer_code: string;
};

const VIEWS: [string, string][] = [
  ["open", "Open (drafts and ordered)"],
  ["draft", "Drafts"],
  ["done", "Delivered or closed"],
  ["cancelled", "Cancelled"],
  ["all", "All"],
];
const today = () => new Date().toISOString().slice(0, 10);
const showDate = (iso: string | null) => (iso ? longDate(iso) : "");
const shortDate = (iso: string | null) => (iso ? iso.split("-").reverse().join("-") : "");
const pillClass = (status: string) => (status === "ordered" || status === "part_delivered" ? "pill on" : "pill");
const round2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100;
const plainQty = (n: number) => String(Number(n.toFixed(3)));
const base = (companyId: number) => `#/companies/${companyId}/sales-orders`;
const CRUMB = "Entry › Sales › Sales Order";
/** Who gets the order by mail unless changed: the main contact and sales contacts with an email. */
const mailedFirst = (contacts: Contact[]) => contacts.filter((c) => c.email && (c.is_primary || c.kinds.includes("sales"))).map((c) => c.id);

function useSetup(companyId: number) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const refresh = useCallback(
    () => api<Setup>(`v1/companies/${companyId}/sales-orders/setup/`).then(setSetup, () => setSetup(null)),
    [companyId],
  );
  useEffect(() => {
    refresh();
  }, [refresh]);
  useOnReturn(refresh);
  return { setup, refresh };
}

/** 'Create "<typed>"' in the customer picker: the Add ledger form under Sundry Debtors. */
function newCustomer(companyId: number, setup: Setup | null, refresh: () => unknown): Creatable | undefined {
  if (!setup?.customer_group) return undefined;
  return {
    kind: "ledger",
    href: (name) =>
      `${window.location.pathname}${window.location.search}#/companies/${companyId}/ledgers?form=new-in-${setup.customer_group}&new=${encodeURIComponent(name)}`,
    reload: refresh,
  };
}

export function SalesOrdersPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const form = hashParam("form");
  const view = Number(hashParam("view"));
  const can = (p: string) => session.permissions.includes(`sales.${p}`);
  if (form && can("create")) return <OrderFormTab companyId={companyId} form={form} session={session} />;
  if (view > 0) return <OrderView companyId={companyId} id={view} session={session} />;
  return <OrderList companyId={companyId} session={session} />;
}

/** "Print ▾": the order's layouts (each in its own tab), then the PDF to save. */
const printMenu = (id: number | null) => [
  { label: "Sales order", onClick: () => id && openTab(`/api/v1/sales-orders/${id}/pdf/`) },
  { label: "Download PDF", onClick: () => id && openTab(`/api/v1/sales-orders/${id}/pdf/?download=1`) },
];

/** "Create ▾" on a submitted order: the documents that follow from it, built one by one.
 * "Pick List" makes a new one only when the order has no open or picked list. */
const nextDocs = (makePick: (() => void) | null, makeNote: (() => void) | null) => [
  {
    label: "Pick List",
    onClick: () => makePick?.(),
    disabled: !makePick,
    title: makePick ? undefined : "The order already has a pick list (cancel it to make a new one)",
  },
  {
    label: "Delivery Note",
    onClick: () => makeNote?.(),
    disabled: !makeNote,
    title: makeNote ? undefined : "Made from a picked pick list: submit the pick list first",
  },
  { label: "Sales Invoice (coming later)", disabled: true },
];

// The list ----------------------------------------------------------------------

const COLUMNS: [key: string, label: string, text: (o: SalesOrder) => string, num?: boolean][] = [
  ["number", "SO No", (o) => o.number || "Draft"],
  ["date", "Date", (o) => `${shortDate(o.order_date)} ${showDate(o.order_date)}`],
  ["customer", "Customer", (o) => o.customer_name],
  ["salesman", "Salesman", (o) => o.salesman_name],
  ["despatch", "Despatch From", (o) => o.despatch_from],
  ["delivery", "Delivery Date", (o) => `${shortDate(o.delivery_date)} ${showDate(o.delivery_date)}`],
  ["po", "Customer PO", (o) => o.customer_po_no],
  ["total", "Amount ₹", (o) => `${o.total} ${money(o.total)}`, true],
  ["status", "Status", (o) => o.status_label],
];

function OrderList({ companyId, session }: { companyId: number; session: SignedIn }) {
  const canCreate = session.permissions.includes("sales.create");
  const { setup } = useSetup(companyId);
  const [view, setView] = useState("open");
  const [orders, setOrders] = useState<SalesOrder[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<SalesOrder[]>(`v1/companies/${companyId}/sales-orders/?view=${view}`)
      .then(setOrders)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("sales_order_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      orders.filter((o) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          const value = text(o).toLowerCase();
          return words.every((w) => value.includes(w));
        }),
      ),
    [orders, search],
  );
  const selected = orders.find((o) => o.id === selectedId) ?? null;
  const viewLabel = VIEWS.find(([v]) => v === view)?.[1] ?? "";
  const printing = usePrintMenu({ title: `Sales orders: ${viewLabel}`, scope: setup?.company_name ?? "" });
  const total = shown.reduce((sum, o) => sum + Number(o.total), 0);

  return (
    <section className="page">
      <PageHeader
        title="Sales Order"
        crumbs={[{ label: "Entry › Sales", href: base(companyId) }]}
        sub={`${setup?.company_name ?? ""} · ${shown.length} ${shown.length === 1 ? "order" : "orders"}`}
        actions={
          <>
            {canCreate && (
              <button
                type="button"
                className="secondary"
                disabled={selected?.status !== "draft"}
                title={selected ? (selected.status === "draft" ? "" : "Only a draft can be changed") : "Click a draft order first"}
                onClick={() => selected && openTab(`${base(companyId)}?form=${selected.id}`)}
              >
                Edit
              </button>
            )}
            {canCreate && <button onClick={() => openTab(`${base(companyId)}?form=new`)}>New sales order</button>}
            {printing.buttons}
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
                    No sales orders match.
                  </td>
                </tr>
              )}
              {shown.map((o) => (
                <tr
                  key={o.id}
                  tabIndex={0}
                  className={selected?.id === o.id ? "selected" : ""}
                  onClick={() => setSelectedId(selected?.id === o.id ? null : o.id)}
                  onDoubleClick={() => openTab(`${base(companyId)}?view=${o.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") openTab(`${base(companyId)}?view=${o.id}`);
                  }}
                >
                  <td>{o.number ? <b>{o.number}</b> : <span className="small">Draft</span>}</td>
                  <td className="nowrap">{shortDate(o.order_date)}</td>
                  <td>{o.customer_name}</td>
                  <td>{o.salesman_name}</td>
                  <td>{o.despatch_from}</td>
                  <td className="nowrap">{shortDate(o.delivery_date)}</td>
                  <td>{o.customer_po_no}</td>
                  <td className="num">{money(o.total)}</td>
                  <td>
                    <span className={pillClass(o.status)}>{o.status_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
            {shown.length > 1 && (
              <tfoot>
                <tr>
                  <td colSpan={7}>Total</td>
                  <td className="num">{money(total)}</td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
          {shown.length > 0 && (
            <p className="small no-print">Click an order to see it at the right (click it again to close the panel); double-click or press Enter to open it in a new tab.</p>
          )}
        </div>
        {selected && (
          <div className="side-col" aria-label="Order details">
            <SidePanel title={selected.number || "Draft order"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Customer", selected.customer_name],
                  ["Order Date", showDate(selected.order_date)],
                  ["Despatch From", selected.despatch_from],
                  ["Delivery Date", showDate(selected.delivery_date)],
                  ["Salesman", selected.salesman_name],
                  ["Credit Term", selected.credit_term_name],
                  ["Transporter", selected.transporter_name],
                  ["Items", String(selected.line_count)],
                  ["Total", `₹${money(selected.total)}`],
                  ["Made By", selected.created_by_name],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => openTab(`${base(companyId)}?view=${selected.id}`)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => openTab(`/api/v1/sales-orders/${selected.id}/pdf/`)}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="sales_order" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// The form ------------------------------------------------------------------------

type Draft = {
  key: number;
  item: string;
  description: string;
  unit: string;
  qty: string;
  rate: string;
  /** Typed by the person: a new item, unit or quantity no longer fetches a rate. */
  rateTyped: boolean;
  /** Where the rate came from, in words ("Customer's price", "Price list: …", "MRP …"). */
  source: string;
};
type ChargeDraft = { key: number; item: string; basis: string; rate: string; gst: string };
let nextKey = 1;
const blankLine = (): Draft => ({ key: nextKey++, item: "", description: "", unit: "", qty: "", rate: "", rateTyped: false, source: "" });
const blankCharge = (): ChargeDraft => ({ key: nextKey++, item: "", basis: "fixed", rate: "", gst: "" });
const BASES: [string, string][] = [
  ["fixed", "Fixed"],
  ["percent", "% of items"],
  ["per_unit", "Per unit"],
];

function OrderFormTab({ companyId, form, session }: { companyId: number; form: string; session: SignedIn }) {
  const copy = form.startsWith("copy-");
  const id = Number(form.replace("copy-", ""));
  const [order, setOrder] = useState<SalesOrder | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (form === "new") return;
    api<SalesOrder>(`v1/sales-orders/${id}/`)
      .then(setOrder)
      .catch((err: Error) => setError(err.message));
  }, [form, id]);
  const title = form === "new" ? "New Sales Order" : copy ? "Duplicate Sales Order" : "Edit Sales Order";
  const shell = (msg?: string) => (
    <section className="page">
      <PageHeader title={title} crumbs={[{ label: CRUMB, href: base(companyId) }]} />
      {msg && <p className="error">{msg}</p>}
    </section>
  );
  if (error) return shell(error);
  if (form !== "new" && !order) return shell();
  if (order && !copy && order.status !== "draft") return shell("A submitted order cannot be changed. Cancel it and make a new one (Duplicate).");
  return <OrderForm companyId={companyId} title={title} order={copy ? null : order} copyOf={copy ? order : null} session={session} />;
}

function OrderForm(props: { companyId: number; title: string; order: SalesOrder | null; copyOf: SalesOrder | null; session: SignedIn }) {
  const { companyId, order } = props;
  const from = order ?? props.copyOf;
  const canSubmit = props.session.permissions.includes("sales.submit");
  const { setup, refresh: refreshSetup } = useSetup(companyId);
  const { terms, refresh: refreshTerms } = useCreditTerms();
  const mayAddMasters = props.session.permissions.includes("masters.edit");
  const addCustomer = mayAddMasters ? newCustomer(companyId, setup, refreshSetup) : undefined;
  const newTerm = mayAddMasters ? creatable("credit_term", "credit-terms", refreshTerms) : undefined;
  const newTransporter = mayAddMasters ? creatable("courier_account", `companies/${companyId}/couriers`, refreshSetup) : undefined;
  const newTerms = mayAddMasters ? creatable("terms", "terms", refreshSetup) : undefined;
  const newSalesman = mayAddMasters ? creatable("sales_person", "sales-people", refreshSetup, "as=salesman") : undefined;
  const newCharge = mayAddMasters ? creatable("item", "items", refreshSetup) : undefined;

  const [customer, setCustomerId] = useState(from ? String(from.customer) : "");
  const [despatch, setDespatch] = useState(from ? (from.area ? `a${from.area}` : `b${from.branch}`) : "");
  const [orderDate, setOrderDate] = useState(order?.order_date ?? today());
  const [delivery, setDelivery] = useState(order?.delivery_date ?? "");
  const [term, setTerm] = useState(from?.credit_term ? String(from.credit_term) : "");
  const [transporter, setTransporter] = useState(from?.transporter ? String(from.transporter) : "");
  const [salesman, setSalesman] = useState(from?.salesman ? String(from.salesman) : "");
  const [billFrom, setBillFrom] = useState(from?.bill_from ? String(from.bill_from) : "");
  const [billAddr, setBillAddr] = useState(from?.bill_address?.label ?? "");
  const [shipAddr, setShipAddr] = useState(from?.ship_address?.label ?? "");
  const [mailTo, setMailTo] = useState<number[]>(from?.mail_to ?? []);
  const [poNo, setPoNo] = useState(order?.customer_po_no ?? "");
  const [poDate, setPoDate] = useState(order?.customer_po_date ?? "");
  const [termsSet, setTermsSet] = useState(from?.terms_set ? String(from.terms_set) : "");
  const [termsText, setTermsText] = useState(from?.terms ?? "");
  const [termsEdited, setTermsEdited] = useState(!!from);
  const [fillTerms, setFillTerms] = useState(!from);
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [lines, setLines] = useState<Draft[]>(() => [
    ...(from?.lines ?? []).map((l) => ({
      key: nextKey++,
      item: String(l.item),
      description: l.description ?? "",
      unit: String(l.unit),
      qty: l.qty,
      rate: l.rate,
      rateTyped: true,
      source: l.rate_source,
    })),
    blankLine(),
  ]);
  const [charges, setCharges] = useState<ChargeDraft[]>(() =>
    (from?.charges ?? []).map((c) => ({ key: nextKey++, item: String(c.item), basis: c.basis, rate: c.rate, gst: c.gst_rate })),
  );
  const [items, setItems] = useState<SellItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>("");
  const [warning, setWarning] = useState("");

  const place = setup?.despatch.find((d) => d.value === despatch);
  const br = setup?.branches.find((b) => b.id === place?.branch);
  const cust = setup?.customers.find((c) => String(c.id) === customer);

  // The first branch that keeps stock is where goods go out from unless changed.
  useEffect(() => {
    if (despatch || !setup) return;
    const first = setup.branches.find((b) => b.is_active && !b.no_stock);
    if (first) setDespatch(`b${first.id}`);
  }, [setup, despatch]);
  // Bill From starts as the despatch branch.
  useEffect(() => {
    if (!billFrom && br) setBillFrom(String(br.id));
  }, [br, billFrom]);
  useEffect(() => {
    if (!fillTerms || !setup) return;
    const id = termsSet || (from ? "" : String(setup.default_terms ?? ""));
    const set = setup.terms_sets.find((t) => String(t.id) === id);
    if (id && !set) return;
    setTermsSet(id);
    if (set) setTermsText(set.text);
    setFillTerms(false);
  }, [fillTerms, setup, termsSet, from]);
  const pickTerms = (value: string) => {
    setTermsSet(value);
    setTermsEdited(false);
    if (value) setFillTerms(true);
  };

  const visits = useReturns();
  useEffect(() => {
    if (!customer || !place) return setItems([]);
    const q = new URLSearchParams({ customer, date: orderDate, branch: String(place.branch), ...(place.area ? { area: String(place.area) } : {}) });
    api<SellItem[]>(`v1/companies/${companyId}/sales-orders/items/?${q}`).then(setItems, () => setItems([]));
  }, [companyId, customer, orderDate, place, visits]);

  // A customer just made with 'Create "…"' is filled in once the list has it.
  const [pending, setPending] = useState("");
  useEffect(() => {
    if (pending && setup?.customers.some((x) => String(x.id) === pending)) {
      setPending("");
      takeCustomer(pending);
    }
  });
  const pickCustomer = (value: string) => {
    if (value && !setup?.customers.some((x) => String(x.id) === value)) {
      setCustomerId(value);
      setPending(value);
      return;
    }
    takeCustomer(value);
  };
  const takeCustomer = (value: string) => {
    setCustomerId(value);
    const c = setup?.customers.find((x) => String(x.id) === value);
    if (!c) return;
    // The customer's credit term, transporter and salesman come with it; all can be changed here.
    setTerm(c.credit_term ? String(c.credit_term) : "");
    setTransporter(c.transporter ? String(c.transporter) : "");
    setSalesman(c.salesman ? String(c.salesman) : "");
    setBillAddr((c.addresses.find((a) => a.is_billing) ?? c.addresses[0])?.label ?? "");
    setShipAddr((c.addresses.find((a) => a.is_shipping) ?? c.addresses[0])?.label ?? "");
    setMailTo(mailedFirst(c.contacts));
    const sets = String(c.terms_set ?? setup?.default_terms ?? "");
    if (!termsEdited && sets !== termsSet) {
      setTermsSet(sets);
      if (sets) setFillTerms(true);
      else setTermsText("");
    }
    setLines((ls) => ls.map((l) => (l.rateTyped ? l : { ...l, rate: "", source: "" })));
  };

  const fetchRate = (line: Draft) => {
    if (!customer || !line.item || !line.unit || line.rateTyped) return;
    const q = new URLSearchParams({ customer, item: line.item, unit: line.unit, qty: line.qty || "1", date: orderDate });
    api<{ rate: string | null; source_label: string }>(`v1/companies/${companyId}/sales-orders/rate/?${q}`).then((r) =>
      setLines((ls) => ls.map((l) => (l.key === line.key && !l.rateTyped ? { ...l, rate: r.rate ?? l.rate, source: r.rate ? r.source_label : "" } : l))),
    );
  };
  const change = (key: number, patch: Partial<Draft>) => {
    setLines((ls) => {
      let next = ls.map((l) => (l.key === key ? { ...l, ...patch } : l));
      if ("item" in patch) {
        const it = items.find((i) => String(i.id) === patch.item);
        // The line starts in the item's Sales Unit; only the item's own units are offered.
        const unit = it ? String(it.units.some((u) => u.unit === it.sales_unit) ? it.sales_unit : (it.units[0]?.unit ?? "")) : "";
        next = next.map((l) => (l.key === key ? { ...l, unit, description: it?.description ?? "", rateTyped: false, source: "" } : l));
      }
      if (next[next.length - 1].item) next = [...next, blankLine()];
      const now = next.find((l) => l.key === key)!;
      if ("item" in patch || "unit" in patch || "qty" in patch) setTimeout(() => fetchRate(now), 0);
      return next;
    });
  };
  const remove = (key: number) => setLines((ls) => (ls.length > 1 ? ls.filter((l) => l.key !== key) : ls));

  const withGst = !!cust?.charges_gst;
  const gstOf = (line: Draft) => (withGst ? Number(items.find((i) => String(i.id) === line.item)?.gst_rate ?? 0) : 0);
  const filled = lines.filter((l) => l.item);
  const worked = filled.map((l) => {
    const taxable = round2((Number(l.qty) || 0) * (Number(l.rate) || 0));
    const tax = round2((taxable * gstOf(l)) / 100);
    return { line: l, taxable, tax };
  });
  const itemsValue = worked.reduce((s, w) => s + w.taxable, 0);
  const itemsTax = worked.reduce((s, w) => s + w.tax, 0);
  const lineUnits = new Set(filled.map((l) => l.unit));
  const totalQty = filled.reduce((s, l) => s + (Number(l.qty) || 0), 0);
  const chargeItem = (c: ChargeDraft) => setup?.charge_items.find((x) => String(x.id) === c.item);
  const chargeRows = charges
    .filter((c) => c.item)
    .map((c) => {
      const r = Number(c.rate) || 0;
      const amount = c.basis === "fixed" ? round2(r) : c.basis === "percent" ? round2((itemsValue * r) / 100) : lineUnits.size > 1 ? 0 : round2(totalQty * r);
      const tax = withGst ? round2((amount * Number(c.gst || chargeItem(c)?.gst_rate || 0)) / 100) : 0;
      return { c, amount, tax };
    });
  const chargesValue = chargeRows.reduce((s, r) => s + r.amount, 0);
  const taxable = itemsValue + chargesValue;
  const tax = itemsTax + chargeRows.reduce((s, r) => s + r.tax, 0);
  const exact = round2(taxable + tax);
  const rounded = Math.round(exact);
  const billBranch = setup?.branches.find((b) => String(b.id) === billFrom);
  const billPlace = cust?.addresses.find((a) => a.label === billAddr);
  const supplyState = billPlace?.state_code || cust?.state_code || "";
  const interstate = withGst && !!billBranch && supplyState !== billBranch.state_code;
  const half = worked.reduce((s, w) => s + round2(w.tax / 2), 0) + chargeRows.reduce((s, r) => s + round2(r.tax / 2), 0);
  const chosenTerm = terms.find((t) => String(t.id) === term);

  // The credit limit warning, for this order's total (Sidharth, 2026-11-19: a warning only).
  useEffect(() => {
    if (!customer || !cust) return setWarning("");
    const t = setTimeout(() => {
      api<{ warning: string }>(`v1/companies/${companyId}/sales-orders/credit/?customer=${customer}&total=${rounded}`).then(
        (r) => setWarning(r.warning),
        () => setWarning(""),
      );
    }, 400);
    return () => clearTimeout(t);
  }, [companyId, customer, cust, rounded]);

  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const [draftId, setDraftId] = useState<number | null>(order?.id ?? null);
  const [savedAt, setSavedAt] = useState("");
  const keepAt = (id: number) => window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${id}`);
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      customer: Number(customer) || null,
      branch: place?.branch ?? null,
      area: place?.area ?? null,
      order_date: orderDate,
      delivery_date: delivery || null,
      credit_term: term ? Number(term) : null,
      transporter: transporter ? Number(transporter) : null,
      salesman: salesman ? Number(salesman) : null,
      bill_from: billFrom ? Number(billFrom) : null,
      bill_address: billAddr,
      ship_address: shipAddr,
      mail_to: mailTo,
      customer_po_no: poNo,
      customer_po_date: poDate || null,
      terms_set: termsSet ? Number(termsSet) : null,
      terms: termsText,
      notes,
      lines: filled.map((l) => ({
        item: Number(l.item),
        description: l.description,
        unit: Number(l.unit),
        qty: l.qty || "0",
        rate: l.rate || "0",
        rate_source: l.rateTyped && !l.source ? "Typed" : l.source,
      })),
      charges: chargeRows.map(({ c }) => ({ item: Number(c.item), basis: c.basis, rate: c.rate || "0", ...(withGst && c.gst !== "" ? { gst_rate: c.gst } : {}) })),
      submit,
    };
    try {
      const saved = draftId
        ? await api<SalesOrder>(`v1/sales-orders/${draftId}/`, body, "PATCH")
        : await api<SalesOrder>(`v1/companies/${companyId}/sales-orders/`, body);
      announceSaved("sales_order_saved", { id: saved.id, name: saved.number || "Draft" });
      if (submit) {
        window.location.hash = `${base(companyId)}?view=${saved.id}`;
        return;
      }
      if (!draftId) {
        setDraftId(saved.id);
        keepAt(saved.id);
      }
      setSavedAt(new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }));
      setBusy(false);
    } catch (err) {
      const kept = keptDraft(err);
      if (kept && !draftId) {
        setDraftId(kept);
        keepAt(kept);
      }
      setError(err);
      window.scrollTo({ top: 0, behavior: "smooth" });
      setBusy(false);
    }
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    save(false);
  };
  const itemOptions = items.map((i) => ({ value: String(i.id), label: i.name, hint: i.item_number }));
  const owing = cust ? Number(cust.outstanding) : 0;

  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId && !order ? "Edit Sales Order" : props.title}
        sub={savedAt ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.` : undefined}
        crumbs={[{ label: CRUMB, href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu label="Print" items={printMenu(draftId)} disabled={!draftId} title={draftId ? undefined : "Save the order first; a draft prints with the DRAFT mark"} />
            <button type="submit" form="so-form" className={canSubmit ? "secondary" : undefined} disabled={busy}>
              Save
            </button>
            {canSubmit && (
              <button type="button" disabled={busy} onClick={() => save(true)}>
                Submit
              </button>
            )}
          </>
        }
      />
      <form id="so-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{cust?.name ?? "Pick a customer"}</p>
            <p className="item-sub">
              <b>{order?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              {place && <span className="tag">{place.label}</span>}
            </p>
          </div>
          <ErrorNote error={error} />
          {warning && <p className="use-note">{warning}</p>}
          <Fold title="Customer and Dates" open summary={cust ? `${cust.name} · ${showDate(orderDate)}` : ""}>
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <label>
                <span className="req">Customer</span>
                <Combobox
                  required
                  value={customer}
                  onChange={pickCustomer}
                  create={addCustomer}
                  placeholder="Type to search customers…"
                  options={(setup?.customers ?? [])
                    .filter((c) => c.is_active || String(c.id) === customer)
                    .map((c) => ({ value: String(c.id), label: c.name, hint: c.customer_number }))}
                />
                {cust && (
                  <span className="small">
                    {[
                      cust.gstin ? `GSTIN ${cust.gstin}` : cust.gst_type_label,
                      `Outstanding ₹${money(owing)}`,
                      Number(cust.credit_limit) ? `limit ₹${money(cust.credit_limit)}` : "no credit limit",
                    ].join(" · ")}
                  </span>
                )}
              </label>
              <label>
                <span className="req">Order Date</span>
                <input type="date" required value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
              </label>
              <label>
                <span className="req">Delivery Date</span>
                <input type="date" required value={delivery} min={orderDate} onChange={(e) => setDelivery(e.target.value)} />
              </label>
              <label>
                <span className="req">Despatch From</span>
                <Combobox
                  required
                  value={despatch}
                  onChange={setDespatch}
                  options={(setup?.despatch ?? [])
                    .filter((d) => d.is_active || d.value === despatch)
                    .filter((d) => !setup?.branches.find((b) => b.id === d.branch)?.no_stock)
                    .map((d) => ({ value: d.value, label: d.label, hint: d.hint }))}
                />
                <span className="small">A branch, or one area of it. "In Stock" counts only there.</span>
              </label>
              <label>
                Salesman
                <Combobox
                  value={salesman}
                  onChange={setSalesman}
                  empty="None"
                  create={newSalesman}
                  options={(setup?.salesmen ?? []).filter((s) => s.is_active || String(s.id) === salesman).map((s) => ({ value: String(s.id), label: s.name }))}
                />
                <span className="small">From the customer; you can change it here</span>
              </label>
              <label>
                Credit Term
                <Combobox
                  value={term}
                  onChange={setTerm}
                  empty="None"
                  create={newTerm}
                  options={terms.filter((t) => t.is_active || String(t.id) === term).map((t) => ({ value: String(t.id), label: t.name }))}
                />
                <span className="small">From the customer; you can change it here</span>
              </label>
              <label>
                Transporter
                <Combobox
                  value={transporter}
                  onChange={setTransporter}
                  empty="By Customer"
                  create={newTransporter}
                  options={(setup?.transporters ?? [])
                    .filter((t) => t.is_active || String(t.id) === transporter)
                    .map((t) => ({ value: String(t.id), label: t.name }))}
                />
                <span className="small">From the customer; "By Customer" if the customer collects</span>
              </label>
              <label>
                Customer's PO No
                <input value={poNo} maxLength={60} onChange={(e) => setPoNo(e.target.value)} />
              </label>
              <label>
                Customer's PO Date
                <input type="date" value={poDate} onChange={(e) => setPoDate(e.target.value)} />
              </label>
            </div>
          </Fold>
          <Fold title="Addresses" open summary={[billBranch && `Bill from ${billBranch.name}`, shipAddr && `ship to ${shipAddr}`].filter(Boolean).join(" · ")}>
            <div className="address-cols">
              <div>
                <label>
                  Bill From
                  <Combobox
                    value={billFrom}
                    onChange={setBillFrom}
                    options={(setup?.branches ?? []).filter((b) => b.is_active || String(b.id) === billFrom).map((b) => ({ value: String(b.id), label: b.name }))}
                  />
                </label>
                <AddressBlock place={billBranch?.address_block} title={billBranch?.address_block?.title ?? setup?.company_name} />
              </div>
              <div>
                <label>
                  Customer Billing Address
                  <Combobox
                    value={billAddr}
                    onChange={setBillAddr}
                    empty={cust && cust.addresses.length ? undefined : "No address on the customer"}
                    options={(cust?.addresses ?? []).map((a) => ({ value: a.label, label: a.label }))}
                  />
                </label>
                {cust && <AddressBlock place={billPlace} title={cust.name} />}
              </div>
              <div>
                <label>
                  Ship To
                  <Combobox
                    value={shipAddr}
                    onChange={setShipAddr}
                    empty={cust && cust.addresses.length ? undefined : "No address on the customer"}
                    options={(cust?.addresses ?? []).map((a) => ({ value: a.label, label: a.label }))}
                  />
                </label>
                {cust && <AddressBlock place={cust.addresses.find((a) => a.label === shipAddr)} title={cust.name} />}
              </div>
            </div>
          </Fold>
          <Fold title="Customer Contacts" open summary={`${mailTo.length} to mail`}>
            <p className="small">Tick who gets the order confirmation by mail ("Email Customer" after Submit). Contacts are kept on the customer.</p>
            <ContactTicks
              title="Customer Contacts"
              contacts={cust?.contacts ?? []}
              ticked={mailTo}
              onTick={(id, on) => setMailTo((m) => (on ? [...m, id] : m.filter((x) => x !== id)))}
              empty={cust ? "This customer has no contacts yet." : "Pick the customer first."}
            />
          </Fold>
          <Fold title="Items" open summary={`${filled.length} ${filled.length === 1 ? "item" : "items"}`}>
            {!customer && <p className="small">Pick the customer first: the items sold to it are offered here.</p>}
            <div className="table-scroll">
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th className="num">Qty</th>
                    <th>Unit</th>
                    <th className="num">Rate ₹</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th className="num">Amount ₹</th>
                    <th className="num">In Stock</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l, i) => {
                    const it = items.find((x) => String(x.id) === l.item);
                    const w = worked.find((x) => x.line.key === l.key);
                    const u = it?.units.find((x) => String(x.unit) === l.unit);
                    const have = it && it.in_stock !== null && u ? Number(it.in_stock) / (Number(u.factor) || 1) : null;
                    const short = have !== null && Number(l.qty) > have;
                    const theirs = [it?.customer_name && `Customer calls it "${it.customer_name}"`, it?.customer_code && `code ${it.customer_code}`, it?.hsn && `HSN ${it.hsn}`]
                      .filter(Boolean)
                      .join(" · ");
                    return (
                      <tr key={l.key}>
                        <td>{i + 1}</td>
                        <td className="po-item">
                          <Combobox value={l.item} onChange={(v) => change(l.key, { item: v })} placeholder="Type to search items…" ariaLabel={`Item ${i + 1}`} options={itemOptions} />
                          {theirs && <span className="small">{theirs}</span>}
                          {l.item && (
                            <textarea
                              className="po-desc"
                              rows={Math.min(4, Math.max(1, l.description.split("\n").length))}
                              maxLength={5000}
                              aria-label={`Description ${i + 1}`}
                              placeholder="Description for the customer"
                              value={l.description}
                              onChange={(e) => change(l.key, { description: e.target.value })}
                            />
                          )}
                        </td>
                        <td className="num">
                          <input className="num" inputMode="decimal" aria-label={`Qty ${i + 1}`} value={l.qty} onChange={(e) => change(l.key, { qty: e.target.value })} />
                        </td>
                        <td className="po-unit">
                          {it && (
                            <Combobox
                              value={l.unit}
                              onChange={(v) => change(l.key, { unit: v })}
                              ariaLabel={`Unit ${i + 1}`}
                              options={it.units.map((x) => ({ value: String(x.unit), label: x.name }))}
                            />
                          )}
                        </td>
                        <td className="num">
                          <input
                            className="num"
                            inputMode="decimal"
                            aria-label={`Rate ${i + 1}`}
                            value={l.rate}
                            onChange={(e) => change(l.key, { rate: e.target.value, rateTyped: true, source: "" })}
                          />
                          {l.source && <span className="small">{l.source}</span>}
                        </td>
                        <td className="num">{l.item ? money(w?.taxable ?? 0) : ""}</td>
                        <td className="num">{l.item ? gstOf(l) : ""}</td>
                        <td className="num">{l.item ? money((w?.taxable ?? 0) + (w?.tax ?? 0)) : ""}</td>
                        <td className={short ? "num error" : "num"} title={short ? "Not enough in stock at the Despatch From place" : undefined}>
                          {have === null ? (l.item && it && !it.maintain_stock ? "–" : "") : `${plainQty(have)} ${u?.name ?? ""}`}
                        </td>
                        <td>
                          {l.item && (
                            <button type="button" className="link danger" aria-label={`Remove line ${i + 1}`} onClick={() => remove(l.key)}>
                              ✕
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                {filled.length > 0 && (
                  <tfoot>
                    <tr>
                      <td />
                      <td>
                        <b>Total</b>
                      </td>
                      <td colSpan={3} />
                      <td className="num">
                        <b>{money(itemsValue)}</b>
                      </td>
                      <td />
                      <td className="num">
                        <b>{money(round2(itemsValue + itemsTax))}</b>
                      </td>
                      <td colSpan={2} />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </Fold>
          <Fold title="Charges" open={charges.length > 0} summary={chargeRows.length ? `${chargeRows.length} · ₹${money(chargesValue)}${withGst ? " + GST" : ""}` : "None"}>
            <p className="small">Freight, packing and other charges billed to the customer: service items ticked "Use as Sales Charge" in the Items master.</p>
            {charges.length > 0 && (
              <div className="table-scroll">
                <table className="grid po-lines po-charges">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Charge</th>
                      <th>Basis</th>
                      <th className="num">Rate</th>
                      <th className="num">Amount ₹</th>
                      {withGst && <th>GST %</th>}
                      {withGst && <th className="num">GST ₹</th>}
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {charges.map((c, i) => {
                      const row = chargeRows.find((r) => r.c.key === c.key);
                      const set = (patch: Partial<ChargeDraft>) =>
                        setCharges((cs) =>
                          cs.map((x) => {
                            if (x.key !== c.key) return x;
                            const next = { ...x, ...patch };
                            if ("item" in patch) next.gst = setup?.charge_items.find((k) => String(k.id) === patch.item)?.gst_rate ?? "";
                            return next;
                          }),
                        );
                      return (
                        <tr key={c.key}>
                          <td>{i + 1}</td>
                          <td className="po-item">
                            <Combobox
                              value={c.item}
                              onChange={(v) => set({ item: v })}
                              placeholder="Type to search charges…"
                              ariaLabel={`Charge ${i + 1}`}
                              create={newCharge}
                              options={(setup?.charge_items ?? []).map((k) => ({ value: String(k.id), label: k.name, hint: k.sac }))}
                            />
                          </td>
                          <td className="po-basis">
                            <Combobox value={c.basis} onChange={(v) => set({ basis: v })} ariaLabel={`Basis ${i + 1}`} options={BASES.map(([value, label]) => ({ value, label }))} />
                            {c.basis === "per_unit" && lineUnits.size > 1 && <span className="small error">Items are in different units.</span>}
                          </td>
                          <td className="num">
                            {c.basis === "fixed" ? (
                              "–"
                            ) : (
                              <input className="num" inputMode="decimal" aria-label={`Rate ${i + 1}`} value={c.rate} onChange={(e) => set({ rate: e.target.value })} />
                            )}
                          </td>
                          <td className="num">
                            {c.basis === "fixed" ? (
                              <input className="num" inputMode="decimal" aria-label={`Amount ${i + 1}`} value={c.rate} onChange={(e) => set({ rate: e.target.value })} />
                            ) : (
                              money(row?.amount ?? 0)
                            )}
                          </td>
                          {withGst && (
                            <td className="po-gst">
                              <Combobox
                                value={c.gst}
                                onChange={(v) => set({ gst: v })}
                                ariaLabel={`GST rate ${i + 1}`}
                                options={(setup?.gst_rates ?? []).map((r) => ({ value: r, label: r }))}
                              />
                            </td>
                          )}
                          {withGst && <td className="num">{money(row?.tax ?? 0)}</td>}
                          <td>
                            <button type="button" className="link danger" aria-label={`Remove charge ${i + 1}`} onClick={() => setCharges((cs) => cs.filter((x) => x.key !== c.key))}>
                              ✕
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p>
              <button type="button" className="link" onClick={() => setCharges((cs) => [...cs, blankCharge()])}>
                + Add charge
              </button>
            </p>
          </Fold>
          <Fold title="Terms and Notes" summary="Terms for the customer, internal note" open={!!(termsText || notes)}>
            <div className="item-fields">
              <label>
                Terms and Conditions
                <Combobox
                  value={termsSet}
                  onChange={pickTerms}
                  empty="None"
                  placeholder="Type to search…"
                  create={newTerms}
                  options={(setup?.terms_sets ?? []).filter((t) => t.is_active || String(t.id) === termsSet).map((t) => ({ value: String(t.id), label: t.name }))}
                />
                <span className="small">From the customer (its own set), else the company's default. Picking a set brings its text.</span>
              </label>
              <label className="wide">
                Terms for the Customer
                <textarea
                  rows={8}
                  value={termsText}
                  onChange={(e) => {
                    setTermsText(e.target.value);
                    setTermsEdited(true);
                  }}
                  placeholder="Delivery, payment and other terms printed on the order"
                />
                <span className="small">Change it for this order if needed; a line ending in ":" prints as a heading.</span>
              </label>
              <label>
                Internal Note
                <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="For your own people; not printed" />
              </label>
            </div>
          </Fold>
          <Attachments type="sales_order" id={draftId} />
        </div>
        <div className="doc-foot">
          <TotalsPanel
            items={chargeRows.length ? itemsValue : undefined}
            charges={chargeRows.length ? chargesValue : undefined}
            taxable={taxable}
            cgst={interstate ? 0 : half}
            sgst={interstate ? 0 : tax - half}
            igst={interstate ? tax : 0}
            roundOff={rounded - exact}
            total={rounded}
            note={!cust ? "" : !withGst ? "No GST: an export." : interstate ? "Customer in another state, so IGST." : "Same state as the customer, so CGST + SGST."}
          />
          <PaymentPanel term={chosenTerm} on="sales invoice" />
          {order && (
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="sales_order" id={order.id} stamp={JSON.stringify(order)} />
            </SidePanel>
          )}
        </div>
      </form>
    </section>
  );
}

// The order's own page (read only) ------------------------------------------------------

function OrderView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const can = (p: string) => session.permissions.includes(`sales.${p}`);
  const [order, setOrder] = useState<SalesOrder | null>(null);
  const [error, setError] = useState<unknown>("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const [mailing, setMailing] = useState(false);
  const [mailed, setMailed] = useState("");
  const { terms } = useCreditTerms();
  const reload = useCallback(() => {
    api<SalesOrder>(`v1/sales-orders/${id}/`)
      .then(setOrder)
      .catch((err) => setError(err));
  }, [id]);
  useEffect(reload, [reload]);
  useCreated("sales_order_saved", (c) => {
    if (c.id === id) reload();
  });
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const act = async (path: string, body: object = {}) => {
    setError("");
    try {
      const done = await api<SalesOrder>(`v1/sales-orders/${id}/${path}/`, body);
      setOrder(done);
      setCancelling(false);
      announceSaved("sales_order_saved", { id, name: done.number || "Draft" });
    } catch (err) {
      setError(err);
    }
  };
  if (!order)
    return (
      <section className="page">
        <PageHeader title="Sales Order" crumbs={[{ label: CRUMB, href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const draft = order.status === "draft";
  const open = order.status === "ordered" || order.status === "part_delivered";
  const picks = order.pick_lists ?? [];
  // The list still holding stock for the order (open or picked); a delivered one is done.
  const livePick = [...picks].reverse().find((p) => p.status === "open" || p.status === "picked");
  const notes = (order.delivery_notes ?? []).filter((n) => n.status !== "cancelled");
  const lastNote = notes[notes.length - 1];
  const makeNote =
    livePick?.status === "picked" && can("create")
      ? () => makeDeliveryNote(companyId, livePick.id).catch((err) => setError(err))
      : null;
  const pickHref = (pid: number) => `#/companies/${companyId}/pick-lists?view=${pid}`;
  const makePick = async () => {
    setError("");
    try {
      const made = await api<PickBrief>(`v1/sales-orders/${order.id}/pick-list/`, {});
      openTab(pickHref(made.id));
      reload();
    } catch (err) {
      setError(err);
    }
  };
  const canCancel = can("cancel") && (draft || order.status === "ordered");
  const sumOf = (rows: { taxable?: string; amount: string }[] | undefined, key: "taxable" | "amount") =>
    round2((rows ?? []).reduce((s, r) => s + Number(r[key] ?? 0), 0));
  const facts: [string, string][] = [
    ["Customer", order.customer_name],
    ["Customer GSTIN", order.customer_gstin],
    ["Order Date", showDate(order.order_date)],
    ["Delivery Date", showDate(order.delivery_date)],
    ["Despatch From", order.despatch_from],
    ["Salesman", order.salesman_name],
    ["Credit Term", order.credit_term_name],
    ["Transporter", order.transporter_name],
    ["Customer's PO No", order.customer_po_no],
    ["Customer's PO Date", showDate(order.customer_po_date)],
    ["Made By", order.created_by_name],
  ];
  return (
    <section className="page">
      <PageHeader
        title={order.number ? `Sales Order ${order.number}` : "Sales Order (draft)"}
        sub={
          order.number && order.submitted_at
            ? `Submitted as ${order.number} on ${showDate(order.submitted_at.slice(0, 10))} at ${new Date(order.submitted_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`
            : undefined
        }
        crumbs={[{ label: CRUMB, href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {draft && can("create") && (
              <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?form=${order.id}`)}>
                Edit
              </button>
            )}
            {can("create") && (
              <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?form=copy-${order.id}`)}>
                Duplicate
              </button>
            )}
            {canCancel && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel order
              </button>
            )}
            {can("submit") && open && !mailing && (
              <button type="button" className="link" onClick={() => setMailing(true)}>
                Email Customer
              </button>
            )}
            <ActionsMenu label="Print" items={printMenu(order.id)} />
            {draft && can("submit") && (
              <button type="button" onClick={() => act("submit")}>
                Submit
              </button>
            )}
            {open && <ActionsMenu label="Create" main items={nextDocs(livePick || !can("create") ? null : makePick, makeNote)} />}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{order.customer_name}</p>
            <p className="item-sub">
              <b>{order.number || "Number given on Submit"}</b>
              <span className={pillClass(order.status)}>{order.status_label}</span>
              <span className="tag">{order.despatch_from}</span>
            </p>
          </div>
          {order.status === "cancelled" && <p className="use-note">Cancelled: {order.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this order cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Customer withdrew the order" />
              </label>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep the order
                </button>
                <button type="button" className="link danger" onClick={() => act("cancel", { reason })}>
                  Cancel order
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          {livePick && (
            <div className={livePick.all_in ? "use-note pick-note all-in" : "use-note pick-note"}>
              <span>
                <b>
                  Pick List{" "}
                  <a href={pickHref(livePick.id)} target="_blank" rel="noreferrer">
                    {livePick.number}
                  </a>{" "}
                  {livePick.status === "picked" ? "picked." : "made on Submit."}
                </b>{" "}
                {livePick.all_in ? "All items in stock." : livePick.text.replace(/^Not all in stock: /, "")}
              </span>
              <button type="button" className="link" onClick={() => openTab(pickHref(livePick.id))}>
                Open Pick List
              </button>
            </div>
          )}
          {!draft && order.status !== "cancelled" && (
            <div className="doc-counts no-print" aria-label="Documents made from this order">
              <a className={picks.length ? "" : "none"} href={livePick ? pickHref(livePick.id) : `#/companies/${companyId}/pick-lists`} target="_blank" rel="noreferrer">
                <b>{picks.filter((p) => p.status !== "cancelled").length}</b> Pick List
              </a>
              <a
                className={notes.length ? "" : "none"}
                href={notes.length === 1 && lastNote ? `${deliveryBase(companyId)}?view=${lastNote.id}` : deliveryBase(companyId)}
                target="_blank"
                rel="noreferrer"
              >
                <b>{notes.length}</b> {notes.length === 1 ? "Delivery Note" : "Delivery Notes"}
              </a>
              <span className="none">
                <b>0</b> Invoices
              </span>
            </div>
          )}
          {order.credit_warning && <p className="use-note">{order.credit_warning}</p>}
          {mailed && <p className="use-note">{mailed}</p>}
          {mailing && (
            <OrderMail
              orderId={order.id}
              path="sales-orders"
              title="Email Customer"
              onClose={() => setMailing(false)}
              onSent={(to) => {
                setMailing(false);
                setMailed(`Order mailed to ${to.join(", ")}. A copy is in the order's Activity.`);
                setFiles((n) => n + 1);
              }}
            />
          )}
          <Fold title="Customer and Dates" open>
            <dl className="kv">
              {facts
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
            </dl>
          </Fold>
          <Fold title="Addresses" open>
            <div className="address-cols">
              <div>
                <div className="fact-label">Bill From</div>
                <AddressBlock place={order.addresses?.bill_from} title={order.addresses?.bill_from?.title ?? order.addresses?.bill_from?.name} />
              </div>
              <div>
                <div className="fact-label">Customer Billing Address</div>
                <AddressBlock place={order.addresses?.customer.address ? order.addresses.customer : null} title={order.customer_name} />
              </div>
              <div>
                <div className="fact-label">Ship To</div>
                <AddressBlock place={order.addresses?.ship_to} title={order.customer_name} />
              </div>
            </div>
          </Fold>
          <Fold title="Customer Contacts" open>
            {(order.mail_contacts ?? []).length === 0 ? (
              <p className="small">Nobody is ticked to get this order by mail.</p>
            ) : (
              <table className="grid">
                <thead>
                  <tr>
                    <th>Send To</th>
                    <th>Designation</th>
                    <th>Email</th>
                    <th>Phone</th>
                  </tr>
                </thead>
                <tbody>
                  {(order.mail_contacts ?? []).map((c) => (
                    <tr key={c.id}>
                      <td>{c.name}</td>
                      <td>{c.designation}</td>
                      <td>{c.email}</td>
                      <td>{c.phone}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Fold>
          <Fold title="Items" open>
            <div className="table-scroll">
              <table className="grid">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th>HSN</th>
                    <th className="num">Qty</th>
                    <th>Unit</th>
                    <th className="num">Rate ₹</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th className="num">Amount ₹</th>
                    {order.status !== "cancelled" && <th className="num">In Stock</th>}
                  </tr>
                </thead>
                <tbody>
                  {(order.lines ?? []).map((l, i) => {
                    const short = l.in_stock !== undefined && l.stock && Number(l.pending_qty) > Number(l.in_stock);
                    return (
                      <tr key={l.id}>
                        <td>{i + 1}</td>
                        <td>
                          <b>{l.item_name}</b>
                          {l.customer_code && <span className="small"> · code {l.customer_code}</span>}
                          {l.description && <div className="line-desc">{l.description}</div>}
                        </td>
                        <td>{l.hsn}</td>
                        <td className="num">{l.qty}</td>
                        <td>{l.unit_name}</td>
                        <td className="num">
                          {money(l.rate)}
                          {l.rate_source && <div className="small">{l.rate_source}</div>}
                        </td>
                        <td className="num">{money(l.taxable)}</td>
                        <td className="num">{l.gst_rate}</td>
                        <td className="num">{money(l.amount)}</td>
                        {order.status !== "cancelled" && <td className={short ? "num error" : "num"}>{l.stock ? `${l.in_stock ?? ""} ${l.unit_name}` : "–"}</td>}
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr>
                    <td />
                    <td>
                      <b>Total</b>
                    </td>
                    <td colSpan={4} />
                    <td className="num">
                      <b>{money(sumOf(order.lines, "taxable"))}</b>
                    </td>
                    <td />
                    <td className="num">
                      <b>{money(sumOf(order.lines, "amount"))}</b>
                    </td>
                    {order.status !== "cancelled" && <td />}
                  </tr>
                </tfoot>
              </table>
            </div>
          </Fold>
          {!draft && order.status !== "cancelled" && (order.lines ?? []).some((l) => l.stock) && (
            <DeliveredBox order={order} canClose={can("submit")} onDone={setOrder} />
          )}
          {!!order.charges?.length && (
            <Fold title="Charges" open>
              <div className="table-scroll">
                <table className="grid">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Charge</th>
                      <th>SAC</th>
                      <th>Basis</th>
                      <th className="num">Rate</th>
                      <th className="num">Amount ₹</th>
                      <th className="num">GST %</th>
                      <th className="num">GST ₹</th>
                    </tr>
                  </thead>
                  <tbody>
                    {order.charges.map((c, i) => (
                      <tr key={c.id}>
                        <td>{i + 1}</td>
                        <td>
                          <b>{c.item_name}</b>
                        </td>
                        <td>{c.sac}</td>
                        <td>{c.basis_label}</td>
                        <td className="num">{c.basis === "fixed" ? "" : c.basis === "percent" ? `${c.rate}%` : c.rate}</td>
                        <td className="num">{money(c.amount)}</td>
                        <td className="num">{c.gst_rate}</td>
                        <td className="num">{money(Number(c.cgst) + Number(c.sgst) + Number(c.igst))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Fold>
          )}
          {(order.terms || order.notes) && (
            <Fold title="Terms and Notes" open>
              {order.terms && (
                <div>
                  <b className="fact-label">Terms for the Customer{order.terms_set_name ? ` (from "${order.terms_set_name}")` : ""}</b>
                  <TermsText text={order.terms} />
                </div>
              )}
              {order.notes && (
                <div className="no-print">
                  <b className="fact-label">Internal Note</b>
                  <p className="pre">{order.notes}</p>
                </div>
              )}
            </Fold>
          )}
          <Attachments type="sales_order" id={order.id} onChange={() => setFiles((n) => n + 1)} />
        </div>
        <div className="doc-foot">
          <TotalsPanel
            items={order.charges?.length ? sumOf(order.lines, "taxable") : undefined}
            charges={order.charges?.length ? sumOf(order.charges, "amount") : undefined}
            taxable={Number(order.taxable_total)}
            cgst={Number(order.cgst_total)}
            sgst={Number(order.sgst_total)}
            igst={Number(order.igst_total)}
            roundOff={Number(order.round_off)}
            total={Number(order.total)}
            note=""
          />
          <PaymentPanel term={terms.find((t) => t.id === order.credit_term)} on="sales invoice" />
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="sales_order" id={order.id} stamp={JSON.stringify(order) + files} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** "Delivered" box on a submitted order: ordered, delivered and pending per stock
 * line, with "Close Line" for a balance that will not be sent (with a reason) and
 * "Reopen Line". Deliveries come with the Delivery Note. */
function DeliveredBox({ order, canClose, onDone }: { order: SalesOrder; canClose: boolean; onDone: (o: SalesOrder) => void }) {
  const [closing, setClosing] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>("");
  const lines = (order.lines ?? []).filter((l) => l.stock);
  const act = async (line: number, body: object) => {
    setError("");
    try {
      const done = await api<SalesOrder>(`v1/sales-orders/${order.id}/lines/${line}/close/`, body);
      setClosing(null);
      setReason("");
      onDone(done);
      announceSaved("sales_order_saved", { id: order.id, name: done.number });
    } catch (err) {
      setError(err);
    }
  };
  const state = (l: Line): [string, string] => {
    const sent = Number(l.delivered_qty);
    const want = Number(l.qty);
    if (l.closed_at) return [`Closed · ${plainQty(Math.max(want - sent, 0))} ${l.unit_name} not going`, "pill"];
    if (sent >= want) return ["Delivered", "pill on"];
    if (sent === 0) return ["Not delivered", "pill bad"];
    return [`${plainQty(want - sent)} ${l.unit_name} to go`, "pill warn"];
  };
  const pending = lines.filter((l) => Number(l.pending_qty) > 0).length;
  return (
    <Fold title="Delivered" open summary={pending ? `${pending} line${pending > 1 ? "s" : ""} still to go` : "Nothing pending"}>
      <ErrorNote error={error} />
      <div className="table-scroll">
        <table className="grid">
          <thead>
            <tr>
              <th>#</th>
              <th>Item</th>
              <th className="num">Ordered</th>
              <th className="num">Delivered</th>
              <th className="num">Pending</th>
              <th>Status</th>
              <th className="no-print" />
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => {
              const [label, look] = state(l);
              return (
                <tr key={l.id}>
                  <td>{order.lines!.indexOf(l) + 1}</td>
                  <td>
                    <b>{l.item_name}</b>
                    {l.closed_at && (
                      <div className="line-desc">
                        Closed by {l.closed_by_name} on {shortDate(l.closed_at.slice(0, 10))}: {l.close_reason}
                      </div>
                    )}
                    {closing === l.id && (
                      <div className="close-line no-print">
                        <label>
                          <b>Why will the rest not be sent?</b>
                          <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Customer wants only part" />
                        </label>
                        <div className="buttons">
                          <button type="button" className="link" onClick={() => setClosing(null)}>
                            Keep it open
                          </button>
                          <button type="button" className="link danger" onClick={() => act(l.id, { reason })}>
                            Close Line
                          </button>
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="num">
                    {l.qty} {l.unit_name}
                  </td>
                  <td className="num">
                    {l.delivered_qty} {l.unit_name}
                  </td>
                  <td className="num">{l.pending_qty === "0" ? "0" : `${l.pending_qty} ${l.unit_name}`}</td>
                  <td>
                    <span className={look}>{label}</span>
                  </td>
                  <td className="num no-print">
                    {canClose && Number(l.pending_qty) > 0 && closing !== l.id && (
                      <button type="button" className="link danger" onClick={() => setClosing(l.id)}>
                        Close Line
                      </button>
                    )}
                    {canClose && l.closed_at && (
                      <button type="button" className="link" onClick={() => act(l.id, { reopen: true })}>
                        Reopen Line
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Fold>
  );
}
