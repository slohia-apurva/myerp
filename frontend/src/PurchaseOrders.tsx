import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useTransporterSearch } from "./Shipments";
import { api, type SignedIn } from "./api";
import { DocSide, keptDraft } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { TermsText } from "./Terms";
import { CountryPicker } from "./Pin";
import { useItemSearch } from "./ItemSearch";
import { usePeopleSearch } from "./SalesPeople";
import { Combobox } from "./Combobox";
import { longDate, money } from "./Companies";
import { announceSaved, closeThisTab, creatable, useCreated, type Creatable } from "./Create";
import { useCreditTerms, type CreditTerm } from "./CreditTerms";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { STOCK_COST } from "./Items";
import { defaultPolicy, TransitInsuranceFold, TransitInsuranceView, type OrderInsurance, type PolicyPick } from "./Insurance";
import { PoPrint } from "./PoPrint";
import { OrderMail, SupplierMail } from "./SupplierMail";
import { useOnReturn, useReturns } from "./Refresh";

/** Entry > Purchase > Purchase Order: what the company asked a supplier for. A draft can
 * be changed; Submit gives it its number and fixes it. Nothing here posts to the books. */

type Line = {
  id?: number;
  item: number;
  item_name: string;
  item_number: string;
  hsn: string;
  description?: string;
  unit: number;
  unit_name: string;
  qty: string;
  rate: string;
  discount_pct: string;
  taxable: string;
  gst_rate: string;
  cgst: string;
  sgst: string;
  igst: string;
  amount: string;
  supplier_code?: string;
  // On a saved order: what has come and what is still to come (goods receipts).
  received_qty?: string;
  pending_qty?: string;
  stock?: boolean;
  closed_at?: string | null;
  closed_by_name?: string;
  close_reason?: string;
};
export type Charge = {
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
  add_to_stock: string;
};
export type PurchaseOrder = OrderInsurance & {
  id: number;
  company: number;
  number: string;
  status: string;
  submitted_at?: string | null;
  status_label: string;
  supplier: number;
  supplier_name: string;
  supplier_gstin: string;
  branch: number;
  branch_name: string;
  order_date: string;
  expected_date: string | null;
  credit_term: number | null;
  credit_term_name: string;
  transporter: number | null;
  transporter_name: string;
  terms_set: number | null;
  terms_set_name: string;
  currency: string;
  currency_symbol: string;
  import_details: ImportDetails;
  bill_to: number | null;
  bill_to_name: string;
  supplier_address: Partial<Place>;
  addresses?: { bill_to: Place | null; ship_to: Place; supplier: Place };
  agent: number | null;
  agent_name: string;
  purchaser: number | null;
  purchaser_name: string;
  mail_agent_user: boolean;
  mail_to: number[];
  whatsapp_to: number[];
  mail_contacts: (Omit<Contact, "id"> & { id: number | null; of: string; mail: boolean; whatsapp: boolean })[];
  supplier_ref: string;
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
  supplier_status: string;
  supplier_status_label: string;
  supplier_response?: SupplierResponse;
  lines?: Line[];
  charges?: Charge[];
};
/** What the supplier said through the link in the mailed order. */
type SupplierResponse = {
  status: string;
  status_label: string;
  dispatch_date: string | null;
  rows: { kind: string; at: string; to?: string; by?: string; opened_at?: string | null; name?: string; dispatch_date?: string | null; comment?: string }[];
};
/** An address as the order shows and prints it. */
export type Place = {
  /** Our branches only: "Company (Branch)", or the branch's name alone when it already holds the company's. */
  title?: string;
  name?: string;
  label: string;
  address: string;
  city: string;
  pincode: string;
  state_code: string;
  state: string;
  country: string;
  gstin: string;
  fssai?: string;
  contact?: string;
  phone?: string;
  email?: string;
  is_billing?: boolean;
};
export type Contact = { id: number; name: string; designation: string; phone: string; email: string; is_primary: boolean; kinds: string[] };
/** Who gets the order by mail unless changed: purchase contacts and the main contact, if they have an email. */
const mailedFirst = (contacts: Contact[]) => contacts.filter((c) => c.email && (c.is_primary || c.kinds.includes("purchase"))).map((c) => c.id);
type Supplier = {
  id: number;
  name: string;
  is_active: boolean;
  vendor_number: string;
  gstin: string;
  gst_type_label: string;
  state_code: string;
  credit_term: number | null;
  transporter: number | null;
  /** The supplier's Purchaser in this company (Masters › People). */
  purchaser: number | null;
  terms_set: number | null;
  currency: string;
  currency_symbol: string;
  overseas: boolean;
  last_import: ImportDetails;
  charges_gst: boolean;
  contacts: Contact[];
  addresses: Place[];
};
type BranchRow = {
  id: number;
  name: string;
  state_code: string;
  is_active: boolean;
  no_stock: boolean;
  store: string;
  receiving: string;
  default_billing: boolean;
  is_head_office: boolean;
  address_block: Place;
};
type Setup = {
  company_name: string;
  suppliers: Supplier[];
  branches: BranchRow[];
  insurance_policies: PolicyPick[];
  terms_sets: { id: number; name: string; is_active: boolean; text: string }[];
  default_terms: number | null;
  import_choices: Record<string, [string, string][]>;
  default_documents: string[];
  charge_items: { id: number; name: string; sac: string; add_to_stock: string; gst_rate: string | null }[];
  gst_rates: string[];
  supplier_group: number | null;
};
/** Shipment and payment terms of an import; `<key>_label` and `documents_labels` come
 * back from the server beside the codes. */
type ImportDetails = Record<string, string | string[] | undefined> & { documents?: string[] };
const IMPORT_KEYS = [
  "incoterm", "named_place", "mode", "port_loading", "port_discharge", "origin",
  "latest_shipment", "payment", "partial", "transhipment", "insurance_by", "packing",
] as const;
/** The editable part: codes only, as sent back on Save. */
const importDraft = (d: ImportDetails | undefined): ImportDetails => {
  const out: ImportDetails = { documents: [...(d?.documents ?? [])] };
  for (const k of IMPORT_KEYS) out[k] = (d?.[k] as string) ?? "";
  return out;
};
type BuyItem = {
  id: number;
  name: string;
  item_number: string;
  hsn: string;
  description: string;
  purchase_unit: number;
  units: { unit: number; name: string; whole_numbers: boolean }[];
  gst_rate: string | null;
  supplier_name: string;
  supplier_code: string;
};

const VIEWS: [string, string][] = [
  ["open", "Open (drafts and ordered)"],
  ["draft", "Drafts"],
  ["done", "Received or closed"],
  ["cancelled", "Cancelled"],
  ["all", "All"],
];
const today = () => new Date().toISOString().slice(0, 10);
const showDate = (iso: string | null) => (iso ? longDate(iso) : "");
/** 14-11-2026: short enough for a list column. */
const shortDate = (iso: string | null) => (iso ? iso.split("-").reverse().join("-") : "");
const pillClass = (status: string) =>
  status === "ordered" || status === "part_received" ? "pill on" : "pill";

function useSetup(companyId: number) {
  const [setup, setSetup] = useState<Setup | null>(null);
  // refresh returns the request, so "Create …" can wait for the new supplier.
  const refresh = useCallback(
    () => api<Setup>(`v1/companies/${companyId}/purchase-orders/setup/?search=1`).then(setSetup, () => setSetup(null)),
    [companyId],
  );
  useEffect(() => {
    refresh();
  }, [refresh]);
  useOnReturn(refresh);
  return { setup, refresh };
}

/** 'Create "<typed>"' in the supplier picker: the company's Add ledger form in a new tab, under
 * Sundry Creditors with the name filled in; the picker takes the supplier once it is saved. */
function newSupplier(companyId: number, setup: Setup | null, refresh: () => unknown): Creatable | undefined {
  if (!setup?.supplier_group) return undefined;
  return {
    kind: "ledger",
    href: (name) =>
      `${window.location.pathname}${window.location.search}#/companies/${companyId}/ledgers?form=new-in-${setup.supplier_group}&new=${encodeURIComponent(name)}`,
    reload: refresh,
  };
}

const base = (companyId: number) => `#/companies/${companyId}/purchase-orders`;

export function PurchaseOrdersPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const form = hashParam("form");
  const view = Number(hashParam("view"));
  const print = Number(hashParam("print"));
  const can = (p: string) => session.permissions.includes(`purchase.${p}`);
  if (form && can("create")) return <OrderFormTab companyId={companyId} form={form} session={session} />;
  if (print > 0) return <PoPrint id={print} pdf={hashParam("pdf") === "1"} />;
  if (view > 0) return <OrderView companyId={companyId} id={view} session={session} />;
  return <OrderList companyId={companyId} session={session} />;
}

// The list ----------------------------------------------------------------------

/** What each column's search box looks in. */
const COLUMNS: [key: string, label: string, text: (o: PurchaseOrder) => string, num?: boolean][] = [
  ["number", "PO No", (o) => o.number || "Draft"],
  ["date", "Date", (o) => `${shortDate(o.order_date)} ${showDate(o.order_date)}`],
  ["supplier", "Supplier", (o) => o.supplier_name],
  ["branch", "Deliver To", (o) => o.branch_name],
  ["expected", "Expected", (o) => `${shortDate(o.expected_date)} ${showDate(o.expected_date)}`],
  ["ref", "Supplier Ref", (o) => o.supplier_ref],
  ["total", "Amount ₹", (o) => `${o.total} ${money(o.total)}`, true],
  ["status", "Status", (o) => o.status_label],
  ["reply", "Supplier Reply", (o) => o.supplier_status_label],
];
const replyClass = (s: string) => (s === "accepted" ? "pill on" : s === "issue" ? "pill warn" : "pill");

function OrderList({ companyId, session }: { companyId: number; session: SignedIn }) {
  const canCreate = session.permissions.includes("purchase.create");
  const { setup } = useSetup(companyId);
  const [view, setView] = useState("open");
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<PurchaseOrder[]>(`v1/companies/${companyId}/purchase-orders/?view=${view}`)
      .then(setOrders)
      .catch((err: Error) => setError(err.message));
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("purchase_order_saved", (c) => {
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
  const printing = usePrintMenu({ title: `Purchase orders: ${viewLabel}`, scope: setup?.company_name ?? "" });
  const total = shown.reduce((sum, o) => sum + Number(o.total), 0);

  return (
    <section className="page">
      <PageHeader
        title="Purchase Order"
        crumbs={[{ label: "Entry › Purchase", href: base(companyId) }]}
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
            {canCreate && <button onClick={() => openTab(`${base(companyId)}?form=new`)}>New purchase order</button>}
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
                    No purchase orders match.
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
                  <td>{o.supplier_name}</td>
                  <td>{o.branch_name}</td>
                  <td className="nowrap">{shortDate(o.expected_date)}</td>
                  <td>{o.supplier_ref}</td>
                  <td className="num">{o.currency !== "INR" ? `${o.currency_symbol}${money(o.total)}` : money(o.total)}</td>
                  <td>
                    <span className={pillClass(o.status)}>{o.status_label}</span>
                  </td>
                  <td>{o.number && o.status !== "cancelled" && <span className={replyClass(o.supplier_status)}>{o.supplier_status_label}</span>}</td>
                </tr>
              ))}
            </tbody>
            {shown.length > 1 && (
              <tfoot>
                <tr>
                  <td colSpan={6}>Total</td>
                  <td className="num">{money(total)}</td>
                  <td />
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
                  ["Supplier", selected.supplier_name],
                  ["Order Date", showDate(selected.order_date)],
                  ["Deliver To", selected.branch_name],
                  ["Expected", showDate(selected.expected_date)],
                  ["Credit Term", selected.credit_term_name],
                  ["Transporter", selected.transporter_name],
                  ["Items", String(selected.line_count)],
                  ["Total", `${selected.currency_symbol}${money(selected.total)}`],
                  ["Made By", selected.created_by_name],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => openTab(`${base(companyId)}?view=${selected.id}`)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?print=${selected.id}`)}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="purchase_order" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// Working out a line, as the server does -----------------------------------------

type Draft = {
  key: number;
  item: string;
  description: string;
  unit: string;
  qty: string;
  rate: string;
  discount: string;
  /** Typed by the person: a new item, unit or quantity no longer fetches a rate. */
  rateTyped: boolean;
  source: string;
};
let nextKey = 1;
const blankLine = (): Draft => ({ key: nextKey++, item: "", description: "", unit: "", qty: "", rate: "", discount: "", rateTyped: false, source: "" });
const round2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100;

function work(line: Draft, gst: number) {
  const gross = (Number(line.qty) || 0) * (Number(line.rate) || 0);
  const taxable = round2(gross - (gross * (Number(line.discount) || 0)) / 100);
  const tax = round2((taxable * gst) / 100);
  return { taxable, tax, amount: taxable + tax };
}

/** A charge on the order (freight, packing, insurance…): a service item marked
 * "Use as Purchase Charge". "rate" is the amount (Fixed), the percent (% of items) or
 * the rate per unit (Per unit); "gst" is "" for the item's own rate. */
type ChargeDraft = { key: number; item: string; basis: string; rate: string; gst: string; stock: string };
const BASES: [string, string][] = [
  ["fixed", "Fixed"],
  ["percent", "% of items"],
  ["per_unit", "Per unit"],
];
const blankCharge = (): ChargeDraft => ({ key: nextKey++, item: "", basis: "fixed", rate: "", gst: "", stock: "value" });
const stockWord = (code: string) => STOCK_COST.find(([c]) => c === code)?.[1] ?? code;

/** A credit term in words, part by part: "100% 30 days after the bill". */
function termParts(term: CreditTerm | undefined): string[] {
  if (!term) return [];
  const when = (event: string, days: number) => {
    if (event === "bill") return days ? `${days} days after the bill` : "on the bill date";
    const label = { order: "advance with the order", dispatch: "before dispatch", delivery: "on delivery" }[event] ?? event;
    return days ? `${label} + ${days} days` : label;
  };
  return term.parts.map((p) => `${Number(p.percent)}% ${when(p.event, p.days)}`);
}

// The form ------------------------------------------------------------------------

function OrderFormTab({ companyId, form, session }: { companyId: number; form: string; session: SignedIn }) {
  const copy = form.startsWith("copy-");
  const id = Number(form.replace("copy-", ""));
  const [order, setOrder] = useState<PurchaseOrder | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (form === "new") return;
    api<PurchaseOrder>(`v1/purchase-orders/${id}/`)
      .then(setOrder)
      .catch((err: Error) => setError(err.message));
  }, [form, id]);
  const title = form === "new" ? "New Purchase Order" : copy ? "Duplicate Purchase Order" : "Edit Purchase Order";
  if (error) return <Shell title={title} companyId={companyId} error={error} />;
  if (form !== "new" && !order) return <Shell title={title} companyId={companyId} />;
  if (order && !copy && order.status !== "draft")
    return <Shell title={title} companyId={companyId} error="A submitted order cannot be changed. Cancel it and make a new one (Duplicate)." />;
  return <OrderForm companyId={companyId} title={title} order={copy ? null : order} copyOf={copy ? order : null} session={session} />;
}

function Shell({ title, companyId, error }: { title: string; companyId: number; error?: string }) {
  return (
    <section className="page">
      <PageHeader title={title} crumbs={[{ label: "Entry › Purchase › Purchase Order", href: base(companyId) }]} />
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function OrderForm(props: { companyId: number; title: string; order: PurchaseOrder | null; copyOf: PurchaseOrder | null; session: SignedIn }) {
  const { companyId, order } = props;
  const from = order ?? props.copyOf;
  const canSubmit = props.session.permissions.includes("purchase.submit");
  const { setup, refresh: refreshSetup } = useSetup(companyId);
  const { terms, refresh: refreshTerms } = useCreditTerms();
  const mayAddMasters = props.session.permissions.includes("masters.edit");
  const newTerm = mayAddMasters ? creatable("credit_term", "credit-terms", refreshTerms) : undefined;
  const addSupplier = mayAddMasters ? newSupplier(companyId, setup, refreshSetup) : undefined;
  const newTransporter = mayAddMasters ? creatable("courier_account", `companies/${companyId}/couriers`, refreshSetup) : undefined;
  const newTerms = mayAddMasters ? creatable("terms", "terms", refreshSetup) : undefined;
  const newPurchaser = mayAddMasters ? creatable("sales_person", "sales-people", refreshSetup, "as=purchaser") : undefined;
  const [supplier, setSupplierId] = useState(from ? String(from.supplier) : "");
  const [branch, setBranch] = useState(from ? String(from.branch) : "");
  const [orderDate, setOrderDate] = useState(order?.order_date ?? today());
  const [expected, setExpected] = useState(order?.expected_date ?? "");
  const [term, setTerm] = useState(from?.credit_term ? String(from.credit_term) : "");
  // The company's billing branch ("" until the branches load: then the default one) and
  // the name of the supplier's address on the order.
  const [billTo, setBillTo] = useState(from?.bill_to ? String(from.bill_to) : "");
  const [supAddr, setSupAddr] = useState(from?.supplier_address?.label ?? "");
  // "" is "By Supplier": the supplier sends the goods.
  const [transporter, setTransporter] = useState(from?.transporter ? String(from.transporter) : "");
  // Transporters come from the server as the person types (useTransporterSearch), never all at once.
  const { transporters, onType: findTransporters } = useTransporterSearch(companyId, [transporter]);
  const [ref, setRef] = useState(order?.supplier_ref ?? "");
  // Transit insurance (preview 93b): a new order starts with the default policy, if any.
  const [insuredBy, setInsuredBy] = useState(from?.insured_by ?? "");
  const [policy, setPolicy] = useState(from?.insurance_policy ? String(from.insurance_policy) : "");
  // The agent picker holds "l<ledger id>" for a supplier firm or "u<user id>" for an employee.
  // The agent picker holds "l<ledger id>" for a supplier firm or "p<id>" for a purchaser.
  const [agent, setAgentId] = useState(from?.agent ? `l${from.agent}` : from?.purchaser ? `p${from.purchaser}` : "");
  const [mailAgentUser, setMailAgentUser] = useState(from?.mail_agent_user ?? false);
  const [mailTo, setMailTo] = useState<number[]>(from?.mail_to ?? []);
  const [waTo, setWaTo] = useState<number[]>(from?.whatsapp_to ?? []);
  const [termsText, setTermsText] = useState(from?.terms ?? "");
  const [imp, setImp] = useState<ImportDetails>(() => importDraft(from?.import_details));
  const setImpField = (key: string, value: string | string[]) => setImp((d) => ({ ...d, [key]: value }));
  // The set of terms the text came from; picking a set (or a supplier) brings its text
  // unless the text was changed by hand on this order.
  const [termsSet, setTermsSet] = useState(from?.terms_set ? String(from.terms_set) : "");
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
      discount: l.discount_pct === "0" ? "" : l.discount_pct,
      rateTyped: true,
      source: "",
    })),
    blankLine(),
  ]);
  const [charges, setCharges] = useState<ChargeDraft[]>(() =>
    (from?.charges ?? []).map((c) => ({ key: nextKey++, item: String(c.item), basis: c.basis, rate: c.rate, gst: c.gst_rate, stock: c.add_to_stock })),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>("");

  // The head office (or the only branch) is where goods come unless changed.
  useEffect(() => {
    if (!branch && setup) {
      const open = setup.branches.filter((b) => b.is_active);
      const first = open.find((b) => !b.no_stock) ?? open[0];
      if (first) setBranch(String(first.id));
    }
  }, [setup, branch]);
  useEffect(() => {
    if (insuredBy || !setup) return;
    const start = defaultPolicy(setup.insurance_policies, orderDate);
    setInsuredBy(start ? "us" : "none");
    if (start) setPolicy(String(start.id));
  }, [setup, insuredBy, orderDate]);
  // Bill To starts as the default billing branch (else the head office).
  useEffect(() => {
    if (!billTo && setup) {
      const open = setup.branches.filter((b) => b.is_active);
      const first = open.find((b) => b.default_billing) ?? open.find((b) => b.is_head_office) ?? open[0];
      if (first) setBillTo(String(first.id));
    }
  }, [setup, billTo]);
  // A new order starts with the company's default terms; picking a set brings its text
  // (once the set is in the list, as after "Create …").
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
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  // Suppliers come from the server as the person types (ItemSearch.ts), never all at once:
  // the setup is read without them, and the order's supplier and agent are always fetched.
  const { items: suppliers, onType: findSuppliers } = useItemSearch<Supplier>(
    `v1/companies/${companyId}/purchase-orders/setup/`,
    [supplier, agent.startsWith("l") ? agent.slice(1) : ""],
    visits,
    (a) => (a as Setup).suppliers,
  );
  // Purchasers for the Buying Agent likewise (usePeopleSearch).
  const { people: purchasers, onType: findPurchasers } = usePeopleSearch("purchaser", [agent.startsWith("p") ? agent.slice(1) : ""], visits);
  const findAgents = (text: string) => {
    findSuppliers(text);
    findPurchasers(text);
  };
  const sup = suppliers.find((s) => String(s.id) === supplier);
  const br = setup?.branches.find((b) => String(b.id) === branch);
  // Items come from the server as the person types (ItemSearch.ts), never all at once.
  const { items, onType: findItems } = useItemSearch<BuyItem>(
    supplier ? `v1/companies/${companyId}/purchase-orders/items/?supplier=${supplier}&date=${orderDate}` : null,
    lines.map((l) => l.item),
    visits,
  );
  // A supplier just made with 'Create "…"' is not in the list until it reloads: its
  // credit term and contacts are filled in once it is there.
  const [pending, setPending] = useState("");
  useEffect(() => {
    if (pending && suppliers.some((x) => String(x.id) === pending)) {
      setPending("");
      takeSupplier(pending);
    }
  });
  const pickSupplier = (value: string) => {
    if (value && !suppliers.some((x) => String(x.id) === value)) {
      setSupplierId(value);
      setPending(value);
      return;
    }
    takeSupplier(value);
  };
  const takeSupplier = (value: string) => {
    setSupplierId(value);
    const s = suppliers.find((x) => String(x.id) === value);
    // An import starts with the supplier's last order's details, else the usual documents.
    if (s?.overseas)
      setImp(Object.keys(s.last_import).length ? importDraft(s.last_import) : { ...importDraft(undefined), documents: [...(setup?.default_documents ?? [])] });
    // The supplier's credit term comes with it; it can still be changed here.
    if (s) setTerm(s.credit_term ? String(s.credit_term) : "");
    // Its billing address is the one on the order unless another is picked.
    if (s) setSupAddr((s.addresses.find((a) => a.is_billing) ?? s.addresses[0])?.label ?? "");
    // So does its preferred transporter (none: "By Supplier").
    if (s) setTransporter(s.transporter ? String(s.transporter) : "");
    // Its own terms, else the company's default, unless the text was changed by hand.
    const sets = s ? String(s.terms_set ?? setup?.default_terms ?? "") : "";
    if (s && !termsEdited && sets !== termsSet) {
      setTermsSet(sets);
      if (sets) setFillTerms(true);
      else setTermsText("");
    }
    // The new supplier's purchase contacts replace the old one's; the agent's stay.
    const agentIds = suppliers.find((x) => `l${x.id}` === agent)?.contacts.map((c) => c.id) ?? [];
    setMailTo((m) => [...(s ? mailedFirst(s.contacts) : []), ...m.filter((id) => agentIds.includes(id))]);
    setWaTo((w) => w.filter((id) => agentIds.includes(id)));
    // The supplier's own Purchaser becomes the agent, unless a broker firm or another person was picked.
    const before = suppliers.find((x) => String(x.id) === supplier);
    const usual = before?.purchaser ? `p${before.purchaser}` : "";
    if (`l${value}` === agent || agent === "" || agent === usual) {
      const next = s?.purchaser ? `p${s.purchaser}` : "";
      setAgentId(next);
      setMailAgentUser(false);
    }
    setLines((ls) => ls.map((l) => (l.rateTyped ? l : { ...l, rate: "", source: "" })));
  };

  const ag = suppliers.find((s) => `l${s.id}` === agent);
  const agUser = purchasers.find((u) => `p${u.id}` === agent);
  const pickAgent = (picked: string) => {
    // A purchaser made with "Create …" comes back as its bare id.
    const value = /^\d+$/.test(picked) ? `p${picked}` : picked;
    const old = ag?.contacts.map((c) => c.id) ?? [];
    const next = suppliers.find((s) => `l${s.id}` === value);
    setAgentId(value);
    setMailAgentUser(false);
    setMailTo((m) => [...m.filter((id) => !old.includes(id)), ...(next ? mailedFirst(next.contacts) : [])]);
    setWaTo((w) => w.filter((id) => !old.includes(id)));
  };
  const tick = (id: number, on: boolean) => setMailTo((m) => (on ? [...m, id] : m.filter((x) => x !== id)));
  const tickWa = (id: number, on: boolean) => setWaTo((w) => (on ? [...w, id] : w.filter((x) => x !== id)));

  const fetchRate = (line: Draft) => {
    if (!supplier || !line.item || !line.unit || line.rateTyped) return;
    const q = new URLSearchParams({ supplier, item: line.item, unit: line.unit, qty: line.qty || "1", date: orderDate });
    api<{ rate: string | null; source: string }>(`v1/companies/${companyId}/purchase-orders/rate/?${q}`).then((r) =>
      setLines((ls) =>
        ls.map((l) => (l.key === line.key && !l.rateTyped ? { ...l, rate: r.rate ?? l.rate, source: r.rate ? r.source : "" } : l)),
      ),
    );
  };
  const change = (key: number, patch: Partial<Draft>) => {
    setLines((ls) => {
      let next = ls.map((l) => (l.key === key ? { ...l, ...patch } : l));
      const changed = next.find((l) => l.key === key)!;
      if ("item" in patch) {
        const it = items.find((i) => String(i.id) === patch.item);
        const unit = it ? String(it.units.some((u) => u.unit === it.purchase_unit) ? it.purchase_unit : (it.units[0]?.unit ?? "")) : "";
        // The item's purchase description comes with it; it can be changed for this order.
        next = next.map((l) => (l.key === key ? { ...l, unit, description: it?.description ?? "", rateTyped: false, source: "" } : l));
      }
      if (next[next.length - 1].item) next = [...next, blankLine()];
      const now = next.find((l) => l.key === key)!;
      if ("item" in patch || "unit" in patch || "qty" in patch) setTimeout(() => fetchRate(now), 0);
      return changed ? next : ls;
    });
  };
  const remove = (key: number) => setLines((ls) => (ls.length > 1 ? ls.filter((l) => l.key !== key) : ls));

  const gstOf = (line: Draft) => {
    if (!sup?.charges_gst) return 0;
    return Number(items.find((i) => String(i.id) === line.item)?.gst_rate ?? 0);
  };
  const filled = lines.filter((l) => l.item);
  const worked = filled.map((l) => ({ line: l, ...work(l, gstOf(l)) }));
  const itemsValue = worked.reduce((s, w) => s + w.taxable, 0);
  const itemsTax = worked.reduce((s, w) => s + w.tax, 0);
  const itemsExact = round2(itemsValue + itemsTax);
  // Charges, worked out as the server does: "Per unit" needs every line in one unit.
  const lineUnits = new Set(filled.map((l) => l.unit));
  const totalQty = filled.reduce((s, l) => s + (Number(l.qty) || 0), 0);
  const unitName = (() => {
    const l = filled[0];
    const it = l && items.find((x) => String(x.id) === l.item);
    return lineUnits.size === 1 ? (it?.units.find((u) => String(u.unit) === l.unit)?.name ?? "") : "";
  })();
  const chargeGst = !!sup?.charges_gst;
  const chargeItem = (c: ChargeDraft) => setup?.charge_items.find((x) => String(x.id) === c.item);
  const chargeRate = (c: ChargeDraft) => (chargeGst ? Number(c.gst || chargeItem(c)?.gst_rate || 0) : 0);
  const chargeAmount = (c: ChargeDraft) => {
    const r = Number(c.rate) || 0;
    if (c.basis === "fixed") return round2(r);
    if (c.basis === "percent") return round2((itemsValue * r) / 100);
    return lineUnits.size > 1 ? 0 : round2(totalQty * r);
  };
  const chargesOn = charges.filter((c) => c.item);
  const chargeRows = chargesOn.map((c) => {
    const amount = chargeAmount(c);
    const tax = round2((amount * chargeRate(c)) / 100);
    return { c, amount, tax };
  });
  const chargesValue = chargeRows.reduce((s, r) => s + r.amount, 0);
  const chargesTax = chargeRows.reduce((s, r) => s + r.tax, 0);
  const taxable = itemsValue + chargesValue;
  const tax = itemsTax + chargesTax;
  const exact = round2(taxable + tax);
  // A rupee order rounds to the rupee; a foreign currency order is not rounded.
  const sym = sup?.currency_symbol ?? "₹";
  const rounded = sup && sup.currency !== "INR" ? exact : Math.round(exact);
  const interstate = !!sup?.charges_gst && !!br && sup.state_code !== br.state_code;
  const half = worked.reduce((s, w) => s + round2(w.tax / 2), 0) + chargeRows.reduce((s, r) => s + round2(r.tax / 2), 0);
  const changeCharge = (key: number, patch: Partial<ChargeDraft>) =>
    setCharges((cs) =>
      cs.map((c) => {
        if (c.key !== key) return c;
        const next = { ...c, ...patch };
        // A charge brings its own GST rate and stock cost choice; both can be changed here.
        if ("item" in patch) {
          const it = setup?.charge_items.find((x) => String(x.id) === patch.item);
          next.gst = it?.gst_rate ?? "";
          next.stock = it?.add_to_stock ?? "value";
        }
        return next;
      }),
    );
  const newCharge = mayAddMasters ? creatable("item", "items", refreshSetup) : undefined;
  const chosenTerm = terms.find((t) => String(t.id) === term);

  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  // "Save" keeps the draft and the form open, to carry on adding (Sidharth, 2026-11-14);
  // after the first save of a new order the form edits that draft.
  const [draftId, setDraftId] = useState<number | null>(order?.id ?? null);
  const [savedAt, setSavedAt] = useState("");
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      supplier: Number(supplier) || null,
      branch: Number(branch) || null,
      order_date: orderDate,
      expected_date: expected || null,
      credit_term: term ? Number(term) : null,
      transporter: transporter ? Number(transporter) : null,
      insured_by: insuredBy || "none",
      insurance_policy: insuredBy === "us" && policy ? Number(policy) : null,
      bill_to: billTo ? Number(billTo) : null,
      supplier_address: supAddr,
      supplier_ref: ref,
      agent: agent.startsWith("l") ? Number(agent.slice(1)) : null,
      purchaser: agent.startsWith("p") ? Number(agent.slice(1)) : null,
      mail_to: mailTo,
      whatsapp_to: waTo,
      mail_agent_user: mailAgentUser,
      terms_set: termsSet ? Number(termsSet) : null,
      terms: termsText,
      ...(sup?.overseas ? { import_details: { ...imp, latest_shipment: imp.latest_shipment || null } } : {}),
      notes,
      lines: filled.map((l) => ({ item: Number(l.item), description: l.description, unit: Number(l.unit), qty: l.qty || "0", rate: l.rate || "0", discount_pct: l.discount || "0" })),
      charges: chargesOn.map((c) => ({
        item: Number(c.item),
        basis: c.basis,
        rate: c.rate || "0",
        ...(chargeGst && c.gst !== "" ? { gst_rate: c.gst } : {}),
        add_to_stock: c.stock,
      })),
      submit,
    };
    try {
      const saved = draftId
        ? await api<PurchaseOrder>(`v1/purchase-orders/${draftId}/`, body, "PATCH")
        : await api<PurchaseOrder>(`v1/companies/${companyId}/purchase-orders/`, body);
      announceSaved("purchase_order_saved", { id: saved.id, name: saved.number || "Draft" });
      if (submit) {
        window.location.hash = `${base(companyId)}?view=${saved.id}`;
        return;
      }
      if (!draftId) {
        setDraftId(saved.id);
        // Reloading this tab now opens the saved draft (no new form, no reload now).
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${saved.id}`);
      }
      setSavedAt(new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }));
      setBusy(false);
    } catch (err) {
      const kept = keptDraft(err);
      if (kept && !draftId) {
        setDraftId(kept);
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${kept}`);
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

  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId && !order ? "Edit Purchase Order" : props.title}
        sub={savedAt ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.` : undefined}
        crumbs={[{ label: "Entry › Purchase › Purchase Order", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu
              label="Print"
              items={printMenu(companyId, draftId)}
              disabled={!draftId}
              title={draftId ? undefined : "Save the order first; a draft prints with the DRAFT mark"}
            />
            <button type="submit" form="po-form" className={canSubmit ? "secondary" : undefined} disabled={busy}>
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
      <form id="po-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{sup?.name ?? "Pick a supplier"}</p>
            <p className="item-sub">
              <b>{order?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              {br && <span className="tag">{br.name}</span>}
            </p>
          </div>
          <ErrorNote error={error} />
          <Fold title="Supplier and Dates" open summary={sup ? `${sup.name} · ${showDate(orderDate)}` : ""}>
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <label>
                <span className="req">Supplier</span>
                <Combobox
                  required
                  value={supplier}
                  onChange={pickSupplier}
                  create={addSupplier}
                  placeholder="Type to search suppliers…"
                  options={suppliers
                    .filter((s) => s.is_active || String(s.id) === supplier)
                    .map((s) => ({ value: String(s.id), label: s.name, hint: s.vendor_number }))}
                  onType={findSuppliers}
                />
                {sup && <span className="small">{[sup.gstin ? `GSTIN ${sup.gstin}` : sup.gst_type_label, !sup.charges_gst && "no GST on its bills"].filter(Boolean).join(" · ")}</span>}
              </label>
              <label>
                <span className="req">Order Date</span>
                <input type="date" required value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
              </label>
              <label>
                <span className="req">Deliver To</span>
                <Combobox
                  required
                  value={branch}
                  onChange={setBranch}
                  options={(setup?.branches ?? [])
                    .filter((b) => b.is_active || String(b.id) === branch)
                    .map((b) => ({ value: String(b.id), label: b.name }))}
                />
                {br && (
                  <span className="small">
                    {br.no_stock ? "This branch keeps no stock" : `Goods go to ${br.receiving || br.store || "its store"}`}
                  </span>
                )}
              </label>
              <label>
                <span className="req">Expected Delivery</span>
                <input type="date" required value={expected} min={orderDate} onChange={(e) => setExpected(e.target.value)} />
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
                <span className="small">From the supplier; you can change it here</span>
              </label>
              <label>
                Transporter
                <Combobox
                  value={transporter}
                  onChange={setTransporter}
                  empty="By Supplier"
                  create={newTransporter}
                  onType={findTransporters}
                  options={transporters
                    .filter((t) => t.is_active || String(t.id) === transporter)
                    .map((t) => ({ value: String(t.id), label: t.name }))}
                />
                <span className="small">From the supplier; "By Supplier" if the supplier sends the goods</span>
              </label>
              <label>
                Supplier's Quote Ref
                <input value={ref} maxLength={80} onChange={(e) => setRef(e.target.value)} />
              </label>
            </div>
          </Fold>
          {sup?.overseas && setup && (
            <ImportFold
              details={imp}
              set={setImpField}
              choices={setup.import_choices}
              currency={`${sup.currency}${sup.currency_symbol !== sup.currency ? ` (${sup.currency_symbol})` : ""}`}
            />
          )}
          <Fold title="Addresses" open summary={[br && `Ship to ${br.name}`, supAddr && `supplier's ${supAddr}`].filter(Boolean).join(" · ")}>
            <div className="address-cols">
              <div>
                <label>
                  Bill To
                  <Combobox
                    value={billTo}
                    onChange={setBillTo}
                    options={(setup?.branches ?? [])
                      .filter((b) => b.is_active || String(b.id) === billTo)
                      .map((b) => ({ value: String(b.id), label: b.name }))}
                  />
                </label>
                <AddressBlock place={setup?.branches.find((b) => String(b.id) === billTo)?.address_block} title={setup?.company_name} />
              </div>
              <div>
                <div className="fact-label">Ship To</div>
                <div className="small">The "Deliver To" branch: {br?.name ?? "none yet"}</div>
                <AddressBlock place={br?.address_block} title={br ? (br.address_block?.title ?? `${setup?.company_name} (${br.name})`) : undefined} />
              </div>
              <div>
                <label>
                  Supplier Address
                  <Combobox
                    value={supAddr}
                    onChange={setSupAddr}
                    empty={sup && sup.addresses.length ? undefined : "No address on the supplier"}
                    options={(sup?.addresses ?? []).map((a) => ({ value: a.label, label: a.label }))}
                  />
                </label>
                {sup && <AddressBlock place={sup.addresses.find((a) => a.label === supAddr)} title={sup.name} />}
              </div>
            </div>
          </Fold>
          <Fold title="Supplier Contacts and Agent" open summary={`${mailTo.length + (agUser && mailAgentUser ? 1 : 0)} to mail${waTo.length ? ` · ${waTo.length} on WhatsApp` : ""}${ag || agUser ? ` · agent ${ag?.name ?? agUser?.name}` : ""}`}>
            <p className="small">
              Tick who gets this order by mail and who on WhatsApp (WhatsApp sending comes later; the ticks are kept on the order). Contacts are kept on the
              supplier's (and the agent's) ledger.
            </p>
            <ContactTicks title="Supplier Contacts" contacts={sup?.contacts ?? []} ticked={mailTo} onTick={tick} wa={waTo} onWa={tickWa} empty={sup ? "This supplier has no contacts yet." : "Pick the supplier first."} />
            <div className="item-fields">
              <label>
                Buying Agent
                <Combobox
                  value={agent}
                  onChange={pickAgent}
                  onType={findAgents}
                  empty="None"
                  create={newPurchaser}
                  placeholder="Type to search…"
                  options={[
                    ...suppliers
                      .filter((s) => (s.is_active && String(s.id) !== supplier) || `l${s.id}` === agent)
                      .map((s) => ({ value: `l${s.id}`, label: s.name, hint: "Supplier" })),
                    ...purchasers
                      .filter((u) => u.is_active || `p${u.id}` === agent)
                      .map((u) => ({ value: `p${u.id}`, label: u.name, hint: "Purchaser" })),
                  ]}
                />
                <span className="small">Starts as the supplier's Purchaser; or pick a broker firm from the suppliers, or another purchaser.</span>
              </label>
            </div>
            {ag && <ContactTicks title="Agent Contacts" contacts={ag.contacts} ticked={mailTo} onTick={tick} wa={waTo} onWa={tickWa} empty="This agent has no contacts yet." />}
            {agUser && (
              <ContactTicks
                title="Agent Contact"
                contacts={[{ id: -1, name: agUser.name, designation: "Purchaser", phone: "", email: agUser.email, is_primary: false, kinds: [] }]}
                ticked={mailAgentUser ? [-1] : []}
                onTick={(_, on) => setMailAgentUser(on)}
                empty=""
              />
            )}
          </Fold>
          <Fold title="Items" open summary={`${filled.length} ${filled.length === 1 ? "item" : "items"}`}>
            {!supplier && <p className="small">Pick the supplier first: the items it supplies are offered here.</p>}
            <div className="table-scroll">
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th className="num">Qty</th>
                    <th>Unit</th>
                    <th className="num">Rate {sym}</th>
                    <th className="num">Disc %</th>
                    <th className="num">Taxable {sym}</th>
                    <th className="num">GST %</th>
                    <th className="num">Amount {sym}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l, i) => {
                    const it = items.find((x) => String(x.id) === l.item);
                    const w = work(l, gstOf(l));
                    const theirs = [it?.item_number, it?.supplier_name && `Supplier calls it "${it.supplier_name}"`, it?.supplier_code && `code ${it.supplier_code}`, it?.hsn && `HSN ${it.hsn}`]
                      .filter(Boolean)
                      .join(" · ");
                    return (
                      <tr key={l.key}>
                        <td>{i + 1}</td>
                        <td className="po-item">
                          <Combobox
                            value={l.item}
                            onChange={(v) => change(l.key, { item: v })}
                            placeholder="Type to search items…"
                            ariaLabel={`Item ${i + 1}`}
                            options={itemOptions}
                            onType={findItems}
                          />
                          {theirs && <span className="small">{theirs}</span>}
                          {l.item && (
                            <textarea
                              className="po-desc"
                              rows={Math.min(4, Math.max(1, l.description.split("\n").length))}
                              maxLength={5000}
                              aria-label={`Description ${i + 1}`}
                              placeholder="Description for the supplier"
                              value={l.description}
                              onChange={(e) => change(l.key, { description: e.target.value })}
                            />
                          )}
                        </td>
                        <td className="num">
                          <input
                            className="num"
                            inputMode="decimal"
                            aria-label={`Qty ${i + 1}`}
                            value={l.qty}
                            onChange={(e) => change(l.key, { qty: e.target.value })}
                          />
                        </td>
                        <td className="po-unit">
                          {it && (
                            <Combobox
                              value={l.unit}
                              onChange={(v) => change(l.key, { unit: v })}
                              ariaLabel={`Unit ${i + 1}`}
                              options={it.units.map((u) => ({ value: String(u.unit), label: u.name }))}
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
                        <td className="num">
                          <input
                            className="num"
                            inputMode="decimal"
                            aria-label={`Discount ${i + 1}`}
                            placeholder="0"
                            value={l.discount}
                            onChange={(e) => change(l.key, { discount: e.target.value })}
                          />
                        </td>
                        <td className="num">{l.item ? money(w.taxable) : ""}</td>
                        <td className="num">{l.item ? gstOf(l) : ""}</td>
                        <td className="num">{l.item ? money(w.amount) : ""}</td>
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
                      <td colSpan={4} />
                      <td className="num">
                        <b>{money(itemsValue)}</b>
                      </td>
                      <td />
                      <td className="num">
                        <b>{money(itemsExact)}</b>
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </Fold>
          <ChargesFold
            charges={charges}
            setCharges={setCharges}
            change={changeCharge}
            rows={chargeRows}
            setup={setup}
            sym={sym}
            withGst={chargeGst}
            unitName={unitName}
            mixedUnits={lineUnits.size > 1}
            create={newCharge}
            lines={worked.map((w) => {
              const it = items.find((x) => String(x.id) === w.line.item);
              return { name: it?.name ?? "", qty: Number(w.line.qty) || 0, unit: it?.units.find((u) => String(u.unit) === w.line.unit)?.name ?? "", taxable: w.taxable };
            })}
          />
          <TransitInsuranceFold
            companyId={companyId}
            insuredBy={insuredBy || "none"}
            setInsuredBy={setInsuredBy}
            policy={policy}
            setPolicy={setPolicy}
            policies={setup?.insurance_policies ?? []}
            orderDate={orderDate}
            total={rounded}
            rupeeOrder={!sup || sup.currency === "INR"}
            canAdd={mayAddMasters}
            refresh={refreshSetup}
          />
          <Fold title="Terms and Notes" summary="Terms for the supplier, internal note" open={!!(termsText || notes)}>
            <div className="item-fields">
              <label>
                Terms and Conditions
                <Combobox
                  value={termsSet}
                  onChange={pickTerms}
                  empty="None"
                  placeholder="Type to search…"
                  options={(setup?.terms_sets ?? [])
                    .filter((t) => t.is_active || String(t.id) === termsSet)
                    .map((t) => ({ value: String(t.id), label: t.name }))}
                  create={newTerms}
                />
                <span className="small">From the supplier (its own set), else the company's default. Picking a set brings its text.</span>
              </label>
              <label className="wide">
                Terms for the Supplier
                <textarea
                  rows={8}
                  value={termsText}
                  onChange={(e) => {
                    setTermsText(e.target.value);
                    setTermsEdited(true);
                  }}
                  placeholder="Delivery, packing, payment and other terms printed on the order"
                />
                <span className="small">Change it for this order if needed; a line ending in ":" prints as a heading.</span>
              </label>
              <label>
                Internal Note
                <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="For your own people; not printed" />
              </label>
            </div>
          </Fold>
        </div>
        <DocSide type="purchase_order" id={draftId}>
          <TotalsPanel
            items={chargesOn.length ? itemsValue : undefined}
            charges={chargesOn.length ? chargesValue : undefined}
            taxable={taxable}
            cgst={interstate ? 0 : half}
            sgst={interstate ? 0 : tax - half}
            igst={interstate ? tax : 0}
            roundOff={rounded - exact}
            total={rounded}
            symbol={sym}
            note={
              !sup
                ? ""
                : sup.overseas
                  ? `An import: no GST on the order (IGST and duty are paid on the bill of entry). Amounts in ${sup.currency}.`
                  : !sup.charges_gst
                  ? "This supplier does not charge GST on its bills."
                  : interstate
                    ? "Supplier in another state, so IGST."
                    : "Same state as the supplier, so CGST + SGST."
            }
          />
          <PaymentPanel term={chosenTerm} />
          {order && (
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="purchase_order" id={order.id} stamp={JSON.stringify(order)} />
            </SidePanel>
          )}
        </DocSide>
      </form>
    </section>
  );
}

export function ContactTicks(props: {
  title: string;
  contacts: Contact[];
  ticked: number[];
  onTick: (id: number, on: boolean) => void;
  // WhatsApp ticks; left out where WhatsApp does not apply (an employee agent).
  wa?: number[];
  onWa?: (id: number, on: boolean) => void;
  empty: string;
}) {
  return (
    <div>
      <b className="fact-label">{props.title}</b>
      {props.contacts.length === 0 ? (
        <p className="small">{props.empty}</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Send Mail</th>
              {props.wa && <th>WhatsApp</th>}
              <th>Name</th>
              <th>Designation</th>
              <th>Email</th>
              <th>Phone</th>
            </tr>
          </thead>
          <tbody>
            {props.contacts.map((c) => (
              <tr key={c.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Mail ${c.name}`}
                    disabled={!c.email}
                    title={c.email ? "" : "No email for this contact"}
                    checked={props.ticked.includes(c.id)}
                    onChange={(e) => props.onTick(c.id, e.target.checked)}
                  />
                </td>
                {props.wa && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`WhatsApp ${c.name}`}
                      disabled={!c.phone}
                      title={c.phone ? "" : "No phone number for this contact"}
                      checked={props.wa.includes(c.id)}
                      onChange={(e) => props.onWa?.(c.id, e.target.checked)}
                    />
                  </td>
                )}
                <td>
                  {c.name}
                  {c.is_primary && <span className="pill on">Main</span>}
                </td>
                <td>{c.designation}</td>
                <td>{c.email}</td>
                <td>{c.phone}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** "Import Details": shown on the form only for an overseas supplier (Sidharth, 2026-11-14).
 * Amounts are in the supplier's currency; no exchange rate is kept on the order. */
function ImportFold(props: {
  details: ImportDetails;
  set: (key: string, value: string | string[]) => void;
  choices: Record<string, [string, string][]>;
  currency: string;
}) {
  const d = props.details;
  const text = (k: string) => (d[k] as string) ?? "";
  const pick = (k: string, label: string, hint?: string) => (
    <label>
      {label}
      <Combobox
        value={text(k)}
        onChange={(v) => props.set(k, v)}
        empty="Not set"
        options={(props.choices[k] ?? []).map(([value, l]) => ({ value, label: l }))}
      />
      {hint && <span className="small">{hint}</span>}
    </label>
  );
  const docs = d.documents ?? [];
  const summary = [props.currency.split(" ")[0], [text("incoterm"), text("named_place")].filter(Boolean).join(" "), (props.choices.mode ?? []).find(([c]) => c === text("mode"))?.[1]]
    .filter(Boolean)
    .join(" · ");
  return (
    <Fold title="Import Details" open summary={summary}>
      <p className="small">For an overseas supplier: printed on the order. Amounts on this order are in {props.currency}.</p>
      <div className="import-grid">
        <label>
          Currency
          <input value={props.currency} readOnly className="locked-field" />
          <span className="small">From the supplier's ledger</span>
        </label>
        {pick("incoterm", "Incoterms")}
        <label>
          Named Place
          <input value={text("named_place")} maxLength={80} placeholder="e.g. Kolkata" onChange={(e) => props.set("named_place", e.target.value)} />
          <span className="small">Where the Incoterm applies</span>
        </label>
        {pick("mode", "Mode of Shipment")}
        <label>
          Port of Loading
          <input value={text("port_loading")} maxLength={80} placeholder="e.g. Colombo" onChange={(e) => props.set("port_loading", e.target.value)} />
        </label>
        <label>
          Port of Discharge
          <input value={text("port_discharge")} maxLength={80} placeholder="e.g. Kolkata" onChange={(e) => props.set("port_discharge", e.target.value)} />
        </label>
        <label>
          Country of Origin
          <CountryPicker value={text("origin")} onChange={(v) => props.set("origin", v)} />
        </label>
        <label>
          Latest Shipment Date
          <input type="date" value={text("latest_shipment")} onChange={(e) => props.set("latest_shipment", e.target.value)} />
        </label>
        {pick("payment", "Payment Method")}
        {pick("partial", "Partial Shipment")}
        {pick("transhipment", "Transhipment")}
        {pick("insurance_by", "Insurance By")}
      </div>
      <div className="item-fields">
        <div>
          <b className="fact-label">Documents Required</b>
          <div className="checks">
            {(props.choices.documents ?? []).map(([code, label]) => (
              <label key={code} className="check">
                <input
                  type="checkbox"
                  checked={docs.includes(code)}
                  onChange={(e) => props.set("documents", e.target.checked ? [...docs, code] : docs.filter((x) => x !== code))}
                />
                {label}
              </label>
            ))}
          </div>
          <span className="small">The ticks start from the supplier's last order.</span>
        </div>
        <label>
          Packing and Marking
          <textarea rows={3} value={text("packing")} maxLength={1000} onChange={(e) => props.set("packing", e.target.value)} />
        </label>
      </div>
    </Fold>
  );
}

/** The import details of a saved order, as facts. */
function ImportView({ order }: { order: PurchaseOrder }) {
  const d = order.import_details;
  const t = (k: string) => (d[k] as string) || "";
  const rows: [string, string][] = [
    ["Currency", order.currency],
    ["Incoterms", [t("incoterm"), t("named_place")].filter(Boolean).join(" ")],
    ["Mode of Shipment", t("mode_label")],
    ["Port of Loading", t("port_loading")],
    ["Port of Discharge", t("port_discharge")],
    ["Country of Origin", t("origin")],
    ["Latest Shipment Date", showDate(t("latest_shipment") || null)],
    ["Payment Method", t("payment_label")],
    ["Partial Shipment", t("partial_label")],
    ["Transhipment", t("transhipment_label")],
    ["Insurance By", t("insurance_by_label")],
    ["Documents Required", ((d.documents_labels as string[]) ?? []).join(", ")],
    ["Packing and Marking", t("packing")],
  ];
  return (
    <Fold title="Import Details" open>
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
    </Fold>
  );
}

export function TotalsPanel(p: {
  items?: number;
  charges?: number;
  taxable: number;
  cgst: number;
  sgst: number;
  igst: number;
  roundOff: number;
  total: number;
  note: string;
  symbol?: string;
}) {
  return (
    <SidePanel title="Totals">
      <SideRows
        rows={[
          ...(p.charges !== undefined
            ? ([
                ["Items", money(p.items ?? 0)],
                ["Charges", money(p.charges)],
              ] as [string, string][])
            : []),
          ["Taxable Value", money(p.taxable)],
          ...(p.cgst ? ([["CGST", money(p.cgst)]] as [string, string][]) : []),
          ...(p.sgst ? ([["SGST", money(p.sgst)]] as [string, string][]) : []),
          ...(p.igst ? ([["IGST", money(p.igst)]] as [string, string][]) : []),
          ...(!p.symbol || p.symbol === "₹" || p.roundOff ? ([["Round Off", money(p.roundOff)]] as [string, string][]) : []),
          ["Total", `${p.symbol ?? "₹"}${money(p.total)}`],
        ]}
      />
      {p.note && <p className="small">{p.note}</p>}
    </SidePanel>
  );
}

/** An address as lines: name, street, "City - PIN", "State (code) - Country", then
 * GSTIN, FSSAI, contact, phone and email, each on its own line (as printed). */
export function AddressBlock({ place, title }: { place: Place | null | undefined; title?: string }) {
  if (!place) return <p className="small">No address.</p>;
  const india = !place.country || place.country === "India";
  const cityLine = [place.city, place.pincode].filter(Boolean).join(" - ");
  const stateLine = india ? [place.state && `${place.state} (${place.state_code})`, "India"].filter(Boolean).join(" - ") : place.country;
  const facts: [string, string | undefined][] = [
    ["GSTIN", place.gstin],
    ["FSSAI", place.fssai],
    ["Contact", place.contact],
    ["Phone", place.phone],
    ["Email", place.email],
  ];
  return (
    <div className="address-block">
      {title && <b>{title}</b>}
      {place.address.split("\n").map((line, i) => (
        <div key={i}>{line}</div>
      ))}
      {cityLine && <div>{cityLine}</div>}
      {stateLine && <div>{stateLine}</div>}
      <dl>
        {facts
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
      </dl>
    </div>
  );
}

export function PaymentPanel({ term, on = "purchase invoice" }: { term: CreditTerm | undefined; on?: string }) {
  const parts = termParts(term);
  return (
    <SidePanel title="Payment Due">
      {parts.length ? parts.map((p) => <p key={p}>{p}</p>) : <p className="small">No credit term.</p>}
      <p className="small">The exact dates are set on the {on}.</p>
    </SidePanel>
  );
}

/** "Print ▾" on an order: its layouts, each opening in its own tab. More
 * layouts join this list as they are made. */
function printMenu(companyId: number, id: number | null) {
  return [
    { label: "Purchase order", onClick: () => id && openTab(`${base(companyId)}?print=${id}`) },
    { label: "Download PDF", onClick: () => id && openTab(`${base(companyId)}?print=${id}&pdf=1`) },
  ];
}

/** "Create ▾" on a submitted order: the documents that follow from it. */
const createFromOrder = (companyId: number, id: number) => [
  { label: "Goods Receipt (goods received)", onClick: () => openTab(`#/companies/${companyId}/goods-receipts?form=new&order=${id}`) },
  { label: "Purchase Invoice (supplier's bill)", onClick: () => openTab(`#/companies/${companyId}/purchase-invoices?form=new&order=${id}`) },
];

// The order's own page (read only) ------------------------------------------------------

function OrderView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const can = (p: string) => session.permissions.includes(`purchase.${p}`);
  const [order, setOrder] = useState<PurchaseOrder | null>(null);
  const [error, setError] = useState<unknown>("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0); // bumps the Activity after a file is added or removed
  const [mailing, setMailing] = useState(!!hashParam("mail"));
  const [sendingPo, setSendingPo] = useState(false);
  const [mailed, setMailed] = useState("");
  const { terms } = useCreditTerms();
  const reload = useCallback(() => {
    api<PurchaseOrder>(`v1/purchase-orders/${id}/`)
      .then(setOrder)
      .catch((err) => setError(err));
  }, [id]);
  useEffect(reload, [reload]);
  useCreated("purchase_order_saved", (c) => {
    if (c.id === id) reload();
  });
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const act = async (path: string, body: object = {}) => {
    setError("");
    try {
      const done = await api<PurchaseOrder>(`v1/purchase-orders/${id}/${path}/`, body);
      setOrder(done);
      setCancelling(false);
      announceSaved("purchase_order_saved", { id, name: done.number || "Draft" });
    } catch (err) {
      setError(err);
    }
  };
  if (!order)
    return (
      <section className="page">
        <PageHeader title="Purchase Order" crumbs={[{ label: "Entry › Purchase › Purchase Order", href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const draft = order.status === "draft";
  const canCancel = can("cancel") && (draft || order.status === "ordered");
  return (
    <section className="page">
      <PageHeader
        title={order.number ? `Purchase Order ${order.number}` : "Purchase Order (draft)"}
        sub={
          order.number && order.submitted_at
            ? `Submitted as ${order.number} on ${showDate(order.submitted_at.slice(0, 10))} at ${new Date(order.submitted_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`
            : undefined
        }
        crumbs={[{ label: "Entry › Purchase › Purchase Order", href: base(companyId) }]}
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
            {can("submit") && !draft && order.status !== "cancelled" && !sendingPo && (
              <button type="button" className="link" onClick={() => setSendingPo(true)}>
                Email PO
              </button>
            )}
            {can("submit") && !draft && order.status !== "cancelled" && !mailing && (
              <button type="button" className="link" onClick={() => setMailing(true)}>
                Email Supplier
              </button>
            )}
            {/* The order prints in its own tab, laid out for the supplier. */}
            <ActionsMenu label="Print" items={printMenu(companyId, order.id)} />
            {draft && can("submit") && (
              <button type="button" onClick={() => act("submit")}>
                Submit
              </button>
            )}
            {(order.status === "ordered" || order.status === "part_received") && (
              <ActionsMenu label="Create" main items={createFromOrder(companyId, order.id)} />
            )}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{order.supplier_name}</p>
            <p className="item-sub">
              <b>{order.number || "Number given on Submit"}</b>
              <span className={pillClass(order.status)}>{order.status_label}</span>
              <span className="tag">{order.branch_name}</span>
            </p>
          </div>
          {order.status === "cancelled" && <p className="use-note">Cancelled: {order.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this order cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Supplier out of stock" />
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
          {mailed && <p className="use-note">{mailed}</p>}
          {sendingPo && (
            <OrderMail
              orderId={order.id}
              onClose={() => setSendingPo(false)}
              onSent={(to) => {
                setSendingPo(false);
                setMailed(`Order mailed to ${to.join(", ")}. A copy is in the order's Activity.`);
                setFiles((n) => n + 1);
              }}
            />
          )}
          {mailing && (
            <SupplierMail
              orderId={order.id}
              grn={hashParam("grn") ?? ""}
              onClose={() => setMailing(false)}
              onSent={(to) => {
                setMailing(false);
                setMailed(`Mail sent to ${to.join(", ")}. A copy is in the order's Activity.`);
                setFiles((n) => n + 1);
              }}
            />
          )}
          <Fold title="Supplier and Dates" open>
            <dl className="kv">
              {(
                [
                  ["Supplier", order.supplier_name],
                  ["Supplier GSTIN", order.supplier_gstin],
                  ["Order Date", showDate(order.order_date)],
                  ["Deliver To", order.branch_name],
                  ["Expected Delivery", showDate(order.expected_date)],
                  ["Credit Term", order.credit_term_name],
                  ["Transporter", order.transporter_name],
                  ["Supplier's Quote Ref", order.supplier_ref],
                  ["Made By", order.created_by_name],
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
          {order.currency !== "INR" || Object.keys(order.import_details).length > 0 ? <ImportView order={order} /> : null}
          <Fold title="Addresses" open>
            <div className="address-cols">
              <div>
                <div className="fact-label">Bill To</div>
                <AddressBlock place={order.addresses?.bill_to} title={order.addresses?.bill_to?.name} />
              </div>
              <div>
                <div className="fact-label">Ship To</div>
                <AddressBlock place={order.addresses?.ship_to} title={order.addresses ? (order.addresses.ship_to.title ?? `${order.addresses.ship_to.name} (${order.addresses.ship_to.label})`) : undefined} />
              </div>
              <div>
                <div className="fact-label">Supplier Address</div>
                <AddressBlock place={order.addresses?.supplier.address ? order.addresses.supplier : null} title={order.addresses?.supplier.name} />
              </div>
            </div>
          </Fold>
          <Fold title="Supplier Contacts and Agent" open>
            <dl className="kv">
              <div>
                <dt>Buying Agent</dt>
                <dd>{order.agent_name || (order.purchaser_name ? `${order.purchaser_name} (purchaser)` : "None")}</dd>
              </div>
            </dl>
            {order.mail_contacts.length === 0 ? (
              <p className="small">Nobody is ticked to get this order by mail or WhatsApp.</p>
            ) : (
              <table className="grid">
                <thead>
                  <tr>
                    <th>Send To</th>
                    <th>Of</th>
                    <th>Mail</th>
                    <th>WhatsApp</th>
                    <th>Designation</th>
                    <th>Email</th>
                    <th>Phone</th>
                  </tr>
                </thead>
                <tbody>
                  {order.mail_contacts.map((c) => (
                    <tr key={c.id ?? c.email}>
                      <td>{c.name}</td>
                      <td>{c.of}</td>
                      <td>{c.mail ? "✓" : ""}</td>
                      <td>{c.whatsapp ? "✓" : ""}</td>
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
                    <th className="num">Rate {order.currency_symbol}</th>
                    <th className="num">Disc %</th>
                    <th className="num">Taxable {order.currency_symbol}</th>
                    <th className="num">GST %</th>
                    <th className="num">Amount {order.currency_symbol}</th>
                  </tr>
                </thead>
                <tbody>
                  {(order.lines ?? []).map((l, i) => (
                    <tr key={l.id}>
                      <td>{i + 1}</td>
                      <td>
                        <b>{l.item_name}</b>
                        {l.description && <div className="line-desc">{l.description}</div>}
                      </td>
                      <td>{l.hsn}</td>
                      <td className="num">{l.qty}</td>
                      <td>{l.unit_name}</td>
                      <td className="num">{money(l.rate)}</td>
                      <td className="num">{l.discount_pct === "0" ? "" : l.discount_pct}</td>
                      <td className="num">{money(l.taxable)}</td>
                      <td className="num">{l.gst_rate}</td>
                      <td className="num">{money(l.amount)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td />
                    <td>
                      <b>Total</b>
                    </td>
                    <td colSpan={5} />
                    <td className="num">
                      <b>{money(sumOf(order.lines, "taxable"))}</b>
                    </td>
                    <td />
                    <td className="num">
                      <b>{money(sumOf(order.lines, "amount"))}</b>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Fold>
          {!draft && order.status !== "cancelled" && (order.lines ?? []).some((l) => l.stock) && (
            <ReceivedBox order={order} canClose={can("submit")} onDone={(o) => setOrder(o)} />
          )}
          {!!order.supplier_response?.rows.length && <SupplierReplies box={order.supplier_response} />}
          {!!order.charges?.length && <ChargesView order={order} />}
          {order.insured_by !== "none" && <TransitInsuranceView rows={[order]} />}
          {(order.terms || order.notes) && (
            <Fold title="Terms and Notes" open>
              {order.terms && (
                <div>
                  <b className="fact-label">Terms for the Supplier{order.terms_set_name ? ` (from "${order.terms_set_name}")` : ""}</b>
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
        </div>
        <DocSide type="purchase_order" id={order.id} onChange={() => setFiles((n) => n + 1)}>
          <TotalsPanel
            items={order.charges?.length ? sumOf(order.lines, "taxable") : undefined}
            charges={order.charges?.length ? sumOf(order.charges, "amount") : undefined}
            taxable={Number(order.taxable_total)}
            cgst={Number(order.cgst_total)}
            sgst={Number(order.sgst_total)}
            igst={Number(order.igst_total)}
            roundOff={Number(order.round_off)}
            total={Number(order.total)}
            symbol={order.currency_symbol}
            note=""
          />
          <PaymentPanel term={terms.find((t) => t.id === order.credit_term)} />
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="purchase_order" id={order.id} stamp={JSON.stringify(order) + files} />
          </SidePanel>
        </DocSide>
      </div>
    </section>
  );
}

const sumOf = <K extends string>(rows: Record<K, string>[] | undefined, key: K) =>
  round2((rows ?? []).reduce((s, r) => s + Number(r[key]), 0));

/** The order's charges, with how each goes into the cost of the goods, and an estimate
 * of the stock cost per item (the goods receipt works out the real one). */
function ChargesFold(p: {
  charges: ChargeDraft[];
  setCharges: (f: (cs: ChargeDraft[]) => ChargeDraft[]) => void;
  change: (key: number, patch: Partial<ChargeDraft>) => void;
  rows: { c: ChargeDraft; amount: number; tax: number }[];
  setup: Setup | null;
  sym: string;
  withGst: boolean;
  unitName: string;
  mixedUnits: boolean;
  create?: Creatable;
  lines: { name: string; qty: number; unit: string; taxable: number }[];
}) {
  const { rows, sym, withGst } = p;
  const value = rows.reduce((s, r) => s + r.amount, 0);
  const gst = rows.reduce((s, r) => s + r.tax, 0);
  const byQty = rows.filter((r) => r.c.stock === "qty").reduce((s, r) => s + r.amount, 0);
  const byValue = rows.filter((r) => r.c.stock === "value").reduce((s, r) => s + r.amount, 0);
  const notInCost = rows.filter((r) => r.c.stock === "no");
  const qty = p.lines.reduce((s, l) => s + l.qty, 0);
  const items = p.lines.reduce((s, l) => s + l.taxable, 0);
  const options = (p.setup?.charge_items ?? []).map((i) => ({ value: String(i.id), label: i.name, hint: i.sac }));
  const summary = rows.length ? `${rows.length} ${rows.length === 1 ? "charge" : "charges"} · ${sym}${money(value)}${withGst ? " + GST" : ""}` : "None";
  return (
    <Fold title="Charges" open={p.charges.length > 0} summary={summary}>
      <p className="small">
        Extra costs on this order. Each charge is a service item from the Items master (ticked "Use as Purchase Charge");
        {withGst ? " its GST rate and" : " its"} "Add to Stock Cost" come from the item and can be changed here.
      </p>
      {p.charges.length > 0 && (
        <div className="table-scroll">
          <table className="grid po-lines po-charges">
            <thead>
              <tr>
                <th>#</th>
                <th>Charge</th>
                <th>SAC</th>
                <th>Basis</th>
                <th className="num">Rate</th>
                <th className="num">Amount {sym}</th>
                {withGst && <th>GST %</th>}
                {withGst && <th className="num">GST {sym}</th>}
                <th>Add to Stock Cost</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {p.charges.map((c, i) => {
                const it = p.setup?.charge_items.find((x) => String(x.id) === c.item);
                const row = rows.find((r) => r.c.key === c.key);
                return (
                  <tr key={c.key}>
                    <td>{i + 1}</td>
                    <td className="po-item">
                      <Combobox
                        value={c.item}
                        onChange={(v) => p.change(c.key, { item: v })}
                        placeholder="Type to search charges…"
                        ariaLabel={`Charge ${i + 1}`}
                        options={options}
                        create={p.create}
                      />
                    </td>
                    <td>{it?.sac}</td>
                    <td className="po-basis">
                      <Combobox
                        value={c.basis}
                        onChange={(v) => p.change(c.key, { basis: v })}
                        ariaLabel={`Basis ${i + 1}`}
                        options={BASES.map(([value, label]) => ({
                          value,
                          label: value === "per_unit" && p.unitName ? `Per unit (${p.unitName})` : label,
                        }))}
                      />
                      {c.basis === "per_unit" && p.mixedUnits && <span className="small error">Items are in different units.</span>}
                    </td>
                    <td className="num">
                      {c.basis === "fixed" ? (
                        "–"
                      ) : (
                        <input
                          className="num"
                          inputMode="decimal"
                          aria-label={`Rate ${i + 1}`}
                          placeholder={c.basis === "percent" ? "%" : "per unit"}
                          value={c.rate}
                          onChange={(e) => p.change(c.key, { rate: e.target.value })}
                        />
                      )}
                    </td>
                    <td className="num">
                      {c.basis === "fixed" ? (
                        <input
                          className="num"
                          inputMode="decimal"
                          aria-label={`Amount ${i + 1}`}
                          value={c.rate}
                          onChange={(e) => p.change(c.key, { rate: e.target.value })}
                        />
                      ) : (
                        money(row?.amount ?? 0)
                      )}
                    </td>
                    {withGst && (
                      <td className="po-gst">
                        <Combobox
                          value={c.gst}
                          onChange={(v) => p.change(c.key, { gst: v })}
                          ariaLabel={`GST rate ${i + 1}`}
                          options={(p.setup?.gst_rates ?? []).map((r) => ({ value: r, label: r }))}
                        />
                      </td>
                    )}
                    {withGst && <td className="num">{money(row?.tax ?? 0)}</td>}
                    <td className="po-stock">
                      {STOCK_COST.map(([code, label]) => (
                        <label key={code} className="check">
                          <input
                            type="radio"
                            name={`stock-${c.key}`}
                            checked={c.stock === code}
                            onChange={() => p.change(c.key, { stock: code })}
                          />
                          {label}
                        </label>
                      ))}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="link danger"
                        aria-label={`Remove charge ${i + 1}`}
                        onClick={() => p.setCharges((cs) => cs.filter((x) => x.key !== c.key))}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            {rows.length > 0 && (
              <tfoot>
                <tr>
                  <td />
                  <td>
                    <b>Total charges</b>
                  </td>
                  <td colSpan={3} />
                  <td className="num">
                    <b>{money(value)}</b>
                  </td>
                  {withGst && <td />}
                  {withGst && (
                    <td className="num">
                      <b>{money(gst)}</b>
                    </td>
                  )}
                  <td colSpan={2} />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
      <p>
        <button type="button" className="link" onClick={() => p.setCharges((cs) => [...cs, blankCharge()])}>
          + Add charge
        </button>
      </p>
      <p className="small">
        "Fixed" is an amount; "% of items" is worked on the items' taxable value; "Per unit" is a rate on the total
        quantity (only when all lines share a unit).
      </p>
      {rows.length > 0 && p.lines.length > 0 && (
        <>
          <b className="fact-label">Stock Cost per Item</b> <span className="small">(estimate; the goods receipt works out the final cost)</span>
          <div className="table-scroll">
            <table className="grid">
              <thead>
                <tr>
                  <th>Item</th>
                  <th className="num">Taxable {sym}</th>
                  <th className="num">By Quantity {sym}</th>
                  <th className="num">By Value {sym}</th>
                  <th className="num">Stock Cost {sym}</th>
                  <th className="num">Per Unit {sym}</th>
                </tr>
              </thead>
              <tbody>
                {p.lines.map((l, i) => {
                  const q = qty ? round2((byQty * l.qty) / qty) : 0;
                  const v = items ? round2((byValue * l.taxable) / items) : 0;
                  const cost = l.taxable + q + v;
                  return (
                    <tr key={i}>
                      <td>{l.name}</td>
                      <td className="num">{money(l.taxable)}</td>
                      <td className="num">{money(q)}</td>
                      <td className="num">{money(v)}</td>
                      <td className="num">{money(cost)}</td>
                      <td className="num">{l.qty ? `${money(cost / l.qty)}${l.unit ? ` / ${l.unit}` : ""}` : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {notInCost.length > 0 && (
            <p className="small">
              "No" charges are not in the stock cost:{" "}
              {notInCost.map((r) => `${p.setup?.charge_items.find((x) => String(x.id) === r.c.item)?.name ?? ""} (${sym}${money(r.amount)})`).join(", ")} go
              to the expense account.
            </p>
          )}
        </>
      )}
    </Fold>
  );
}

function ChargesView({ order }: { order: PurchaseOrder }) {
  const sym = order.currency_symbol;
  const charges = order.charges ?? [];
  const withGst = charges.some((c) => Number(c.gst_rate));
  const rateText = (c: Charge) => (c.basis === "fixed" ? "" : c.basis === "percent" ? `${c.rate}%` : c.rate);
  return (
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
              <th className="num">Amount {sym}</th>
              {withGst && <th className="num">GST %</th>}
              {withGst && <th className="num">GST {sym}</th>}
              <th>Add to Stock Cost</th>
            </tr>
          </thead>
          <tbody>
            {charges.map((c, i) => (
              <tr key={c.id}>
                <td>{i + 1}</td>
                <td>
                  <b>{c.item_name}</b>
                </td>
                <td>{c.sac}</td>
                <td>{c.basis_label}</td>
                <td className="num">{rateText(c)}</td>
                <td className="num">{money(c.amount)}</td>
                {withGst && <td className="num">{c.gst_rate}</td>}
                {withGst && <td className="num">{money(Number(c.cgst) + Number(c.sgst) + Number(c.igst))}</td>}
                <td>{stockWord(c.add_to_stock)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td />
              <td>
                <b>Total charges</b>
              </td>
              <td colSpan={3} />
              <td className="num">
                <b>{money(sumOf(charges, "amount"))}</b>
              </td>
              {withGst && <td />}
              {withGst && (
                <td className="num">
                  <b>{money(charges.reduce((s, c) => s + Number(c.cgst) + Number(c.sgst) + Number(c.igst), 0))}</b>
                </td>
              )}
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </Fold>
  );
}

/** How a line stands against what came: the words and the pill's look. */
function lineState(l: Line): [string, string] {
  const got = Number(l.received_qty ?? 0);
  const want = Number(l.qty);
  const unit = l.unit_name;
  if (l.closed_at) return [`Closed · ${plainQty(Math.max(want - got, 0))} ${unit} not coming`, "pill"];
  if (got > want) return [`${plainQty(got - want)} ${unit} over`, "pill warn"];
  if (got === want) return ["Received", "pill on"];
  if (got === 0) return ["Not received", "pill bad"];
  return [`${plainQty(want - got)} ${unit} short`, "pill warn"];
}

const plainQty = (n: number) => String(Number(n.toFixed(6)));

/** "Received" box on a submitted order (Sidharth, 2026-11-15): ordered, received
 * and pending per stock line, and "Close Line" for a balance that will not
 * come (with a reason), or "Reopen Line". Opened from a goods receipt's notice
 * (?grn=), the lines that differ are marked. */
function ReceivedBox({ order, canClose, onDone }: { order: PurchaseOrder; canClose: boolean; onDone: (o: PurchaseOrder) => void }) {
  const fromReceipt = !!hashParam("grn");
  const [closing, setClosing] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>("");
  const lines = (order.lines ?? []).filter((l) => l.stock);
  const act = async (line: number, body: object) => {
    setError("");
    try {
      const done = await api<PurchaseOrder>(`v1/purchase-orders/${order.id}/lines/${line}/close/`, body);
      setClosing(null);
      setReason("");
      onDone(done);
      announceSaved("purchase_order_saved", { id: order.id, name: done.number });
    } catch (err) {
      setError(err);
    }
  };
  const pending = lines.filter((l) => Number(l.pending_qty) > 0).length;
  return (
    <Fold title="Received" open summary={pending ? `${pending} line${pending > 1 ? "s" : ""} still to come` : "Nothing pending"}>
      <ErrorNote error={error} />
      <div className="table-scroll">
        <table className="grid">
          <thead>
            <tr>
              <th>#</th>
              <th>Item</th>
              <th className="num">Ordered</th>
              <th className="num">Received</th>
              <th className="num">Pending</th>
              <th>Status</th>
              <th className="no-print" />
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => {
              const [label, look] = lineState(l);
              const differs = fromReceipt && !l.closed_at && Number(l.received_qty) !== Number(l.qty);
              const open = Number(l.pending_qty) > 0;
              return (
                <tr key={l.id} className={differs ? "differs" : undefined}>
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
                          <b>Why will the rest not come?</b>
                          <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Supplier will not send balance" />
                        </label>
                        <div className="buttons">
                          <button type="button" className="link" onClick={() => setClosing(null)}>
                            Keep it open
                          </button>
                          <button type="button" className="link danger" onClick={() => act(l.id!, { reason })}>
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
                    {l.received_qty} {l.unit_name}
                  </td>
                  <td className="num">{l.pending_qty === "0" ? "0" : `${l.pending_qty} ${l.unit_name}`}</td>
                  <td>
                    <span className={look}>{label}</span>
                  </td>
                  <td className="num no-print">
                    {canClose && open && closing !== l.id && (
                      <button type="button" className="link danger" onClick={() => setClosing(l.id!)}>
                        Close Line
                      </button>
                    )}
                    {canClose && l.closed_at && (
                      <button type="button" className="link" onClick={() => act(l.id!, { reopen: true })}>
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

/** "Supplier Response": each mailing of the order and what the supplier said
 * through its link (Accept Order, Report an Issue, comments). */
function SupplierReplies({ box }: { box: SupplierResponse }) {
  const when = (iso: string) => {
    const d = new Date(iso);
    const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true }).toLowerCase();
    return `${shortDate(iso.slice(0, 10))} ${time}`;
  };
  const tag = box.status === "accepted" && box.dispatch_date ? `Accepted · dispatch ${shortDate(box.dispatch_date)}` : box.status_label;
  return (
    <Fold title="Supplier Response" open summary={tag}>
      <div className="replies">
        {box.rows.map((r, i) => (
          <div key={i} className={`reply ${r.kind}`}>
            {r.kind === "mailed" ? (
              <>
                <b>Mailed</b> to {r.to} by {r.by} · {when(r.at)}
                <span className="small"> · {r.opened_at ? `link opened ${when(r.opened_at)}` : "link not opened yet"}</span>
              </>
            ) : (
              <>
                <b>{r.kind === "accepted" ? "Accepted" : r.kind === "issue" ? "Issue" : "Comment"}</b> {r.kind === "accepted" ? "by" : "from"} {r.name} · {when(r.at)}
                {r.dispatch_date && ` · dispatch expected ${shortDate(r.dispatch_date)}`}
                {r.comment && <div className="pre">"{r.comment}"</div>}
              </>
            )}
          </div>
        ))}
      </div>
    </Fold>
  );
}
