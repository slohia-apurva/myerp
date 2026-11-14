import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { longDate, money } from "./Companies";
import { announceSaved, closeThisTab, creatable, useCreated, type Creatable } from "./Create";
import { useCreditTerms, type CreditTerm } from "./CreditTerms";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";

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
};
export type PurchaseOrder = {
  id: number;
  company: number;
  number: string;
  status: string;
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
  agent: number | null;
  agent_name: string;
  agent_user: number | null;
  agent_user_name: string;
  mail_agent_user: boolean;
  mail_to: number[];
  mail_contacts: (Omit<Contact, "id"> & { id: number | null; of: string })[];
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
  lines?: Line[];
};
type Contact = { id: number; name: string; designation: string; phone: string; email: string; is_primary: boolean; kinds: string[] };
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
  charges_gst: boolean;
  contacts: Contact[];
};
type BranchRow = { id: number; name: string; state_code: string; is_active: boolean; no_stock: boolean; store: string; receiving: string };
type Employee = { id: number; name: string; email: string };
type Transporter = { id: number; name: string; is_active: boolean };
type Setup = {
  company_name: string;
  suppliers: Supplier[];
  branches: BranchRow[];
  employees: Employee[];
  transporters: Transporter[];
  supplier_group: number | null;
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
    () => api<Setup>(`v1/companies/${companyId}/purchase-orders/setup/`).then(setSetup, () => setSetup(null)),
    [companyId],
  );
  useEffect(() => {
    refresh();
  }, [refresh]);
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
  const can = (p: string) => session.permissions.includes(`purchase.${p}`);
  if (form && can("create")) return <OrderFormTab companyId={companyId} form={form} session={session} />;
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
];

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
                  <td colSpan={6}>Total</td>
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
                  ["Supplier", selected.supplier_name],
                  ["Order Date", showDate(selected.order_date)],
                  ["Deliver To", selected.branch_name],
                  ["Expected", showDate(selected.expected_date)],
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
  const [supplier, setSupplierId] = useState(from ? String(from.supplier) : "");
  const [branch, setBranch] = useState(from ? String(from.branch) : "");
  const [orderDate, setOrderDate] = useState(order?.order_date ?? today());
  const [expected, setExpected] = useState(order?.expected_date ?? "");
  const [term, setTerm] = useState(from?.credit_term ? String(from.credit_term) : "");
  // "" is "By Supplier": the supplier sends the goods.
  const [transporter, setTransporter] = useState(from?.transporter ? String(from.transporter) : "");
  const [ref, setRef] = useState(order?.supplier_ref ?? "");
  // The agent picker holds "l<ledger id>" for a supplier firm or "u<user id>" for an employee.
  const [agent, setAgentId] = useState(from?.agent ? `l${from.agent}` : from?.agent_user ? `u${from.agent_user}` : "");
  const [mailAgentUser, setMailAgentUser] = useState(from?.mail_agent_user ?? false);
  const [mailTo, setMailTo] = useState<number[]>(from?.mail_to ?? []);
  const [termsText, setTermsText] = useState(from?.terms ?? "");
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
  const [items, setItems] = useState<BuyItem[]>([]);
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
  const sup = setup?.suppliers.find((s) => String(s.id) === supplier);
  const br = setup?.branches.find((b) => String(b.id) === branch);
  useEffect(() => {
    if (!supplier) return setItems([]);
    api<BuyItem[]>(`v1/companies/${companyId}/purchase-orders/items/?supplier=${supplier}&date=${orderDate}`).then(setItems, () => setItems([]));
  }, [companyId, supplier, orderDate]);
  // A supplier just made with 'Create "…"' is not in the list until it reloads: its
  // credit term and contacts are filled in once it is there.
  const [pending, setPending] = useState("");
  useEffect(() => {
    if (pending && setup?.suppliers.some((x) => String(x.id) === pending)) {
      setPending("");
      takeSupplier(pending);
    }
  });
  const pickSupplier = (value: string) => {
    if (value && !setup?.suppliers.some((x) => String(x.id) === value)) {
      setSupplierId(value);
      setPending(value);
      return;
    }
    takeSupplier(value);
  };
  const takeSupplier = (value: string) => {
    setSupplierId(value);
    const s = setup?.suppliers.find((x) => String(x.id) === value);
    // The supplier's credit term comes with it; it can still be changed here.
    if (s) setTerm(s.credit_term ? String(s.credit_term) : "");
    // So does its preferred transporter (none: "By Supplier").
    if (s) setTransporter(s.transporter ? String(s.transporter) : "");
    // The new supplier's purchase contacts replace the old one's; the agent's stay.
    const agentIds = setup?.suppliers.find((x) => `l${x.id}` === agent)?.contacts.map((c) => c.id) ?? [];
    setMailTo((m) => [...(s ? mailedFirst(s.contacts) : []), ...m.filter((id) => agentIds.includes(id))]);
    if (`l${value}` === agent) setAgentId("");
    setLines((ls) => ls.map((l) => (l.rateTyped ? l : { ...l, rate: "", source: "" })));
  };

  const ag = setup?.suppliers.find((s) => `l${s.id}` === agent);
  const agUser = setup?.employees.find((u) => `u${u.id}` === agent);
  const pickAgent = (value: string) => {
    const old = ag?.contacts.map((c) => c.id) ?? [];
    const next = setup?.suppliers.find((s) => `l${s.id}` === value);
    setAgentId(value);
    setMailAgentUser(value.startsWith("u"));
    setMailTo((m) => [...m.filter((id) => !old.includes(id)), ...(next ? mailedFirst(next.contacts) : [])]);
  };
  const tick = (id: number, on: boolean) => setMailTo((m) => (on ? [...m, id] : m.filter((x) => x !== id)));

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
  const taxable = worked.reduce((s, w) => s + w.taxable, 0);
  const tax = worked.reduce((s, w) => s + w.tax, 0);
  const exact = round2(taxable + tax);
  const rounded = Math.round(exact);
  const interstate = !!sup?.charges_gst && !!br && sup.state_code !== br.state_code;
  const half = worked.reduce((s, w) => s + round2(w.tax / 2), 0);
  const chosenTerm = terms.find((t) => String(t.id) === term);

  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
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
      supplier_ref: ref,
      agent: agent.startsWith("l") ? Number(agent.slice(1)) : null,
      agent_user: agent.startsWith("u") ? Number(agent.slice(1)) : null,
      mail_to: mailTo,
      mail_agent_user: mailAgentUser,
      terms: termsText,
      notes,
      lines: filled.map((l) => ({ item: Number(l.item), description: l.description, unit: Number(l.unit), qty: l.qty || "0", rate: l.rate || "0", discount_pct: l.discount || "0" })),
      submit,
    };
    try {
      const saved = order
        ? await api<PurchaseOrder>(`v1/purchase-orders/${order.id}/`, body, "PATCH")
        : await api<PurchaseOrder>(`v1/companies/${companyId}/purchase-orders/`, body);
      announceSaved("purchase_order_saved", { id: saved.id, name: saved.number || "Draft" });
      if (submit) window.location.hash = `${base(companyId)}?view=${saved.id}`;
      else close();
    } catch (err) {
      setError(err);
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
        title={props.title}
        crumbs={[{ label: "Entry › Purchase › Purchase Order", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Cancel
            </button>
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
                  options={(setup?.suppliers ?? [])
                    .filter((s) => s.is_active || String(s.id) === supplier)
                    .map((s) => ({ value: String(s.id), label: s.name, hint: s.vendor_number }))}
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
                Expected Delivery
                <input type="date" value={expected} min={orderDate} onChange={(e) => setExpected(e.target.value)} />
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
                  options={(setup?.transporters ?? [])
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
          <Fold title="Supplier Contacts and Agent" open summary={`${mailTo.length + (agUser && mailAgentUser ? 1 : 0)} to mail${ag || agUser ? ` · agent ${ag?.name ?? agUser?.name}` : ""}`}>
            <p className="small">Tick who gets this order by mail. Contacts are kept on the supplier's (and the agent's) ledger.</p>
            <ContactTicks title="Supplier Contacts" contacts={sup?.contacts ?? []} ticked={mailTo} onTick={tick} empty={sup ? "This supplier has no contacts yet." : "Pick the supplier first."} />
            <div className="item-fields">
              <label>
                Buying Agent
                <Combobox
                  value={agent}
                  onChange={pickAgent}
                  empty="None"
                  placeholder="Type to search…"
                  options={[
                    ...(setup?.suppliers ?? [])
                      .filter((s) => (s.is_active && String(s.id) !== supplier) || `l${s.id}` === agent)
                      .map((s) => ({ value: `l${s.id}`, label: s.name, hint: "Supplier" })),
                    ...(setup?.employees ?? []).map((u) => ({ value: `u${u.id}`, label: u.name, hint: "Employee" })),
                  ]}
                />
                <span className="small">A broker or firm from the suppliers, or one of your own employees.</span>
              </label>
            </div>
            {ag && <ContactTicks title="Agent Contacts" contacts={ag.contacts} ticked={mailTo} onTick={tick} empty="This agent has no contacts yet." />}
            {agUser && (
              <ContactTicks
                title="Agent Contact"
                contacts={[{ id: -1, name: agUser.name, designation: "Employee", phone: "", email: agUser.email, is_primary: false, kinds: [] }]}
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
                    <th className="num">Rate ₹</th>
                    <th className="num">Disc %</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th className="num">Amount ₹</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l, i) => {
                    const it = items.find((x) => String(x.id) === l.item);
                    const w = work(l, gstOf(l));
                    const theirs = [it?.supplier_name && `Supplier calls it "${it.supplier_name}"`, it?.supplier_code && `code ${it.supplier_code}`, it?.hsn && `HSN ${it.hsn}`]
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
                        <b>{money(taxable)}</b>
                      </td>
                      <td />
                      <td className="num">
                        <b>{money(exact)}</b>
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </Fold>
          <Fold title="Terms and Notes" summary="Terms for the supplier, internal note" open={!!(termsText || notes)}>
            <div className="item-fields">
              <label>
                Terms for the Supplier
                <textarea rows={4} value={termsText} onChange={(e) => setTermsText(e.target.value)} placeholder="Delivery, packing, payment and other terms printed on the order" />
              </label>
              <label>
                Internal Note
                <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="For your own people; not printed" />
              </label>
            </div>
          </Fold>
          <ErrorNote error={error} />
        </div>
        <div className="doc-foot">
          <TotalsPanel
            taxable={taxable}
            cgst={interstate ? 0 : half}
            sgst={interstate ? 0 : tax - half}
            igst={interstate ? tax : 0}
            roundOff={rounded - exact}
            total={rounded}
            note={
              !sup
                ? ""
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
        </div>
      </form>
    </section>
  );
}

function ContactTicks(props: { title: string; contacts: Contact[]; ticked: number[]; onTick: (id: number, on: boolean) => void; empty: string }) {
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

function TotalsPanel(p: { taxable: number; cgst: number; sgst: number; igst: number; roundOff: number; total: number; note: string }) {
  return (
    <SidePanel title="Totals">
      <SideRows
        rows={[
          ["Taxable Value", money(p.taxable)],
          ...(p.cgst ? ([["CGST", money(p.cgst)]] as [string, string][]) : []),
          ...(p.sgst ? ([["SGST", money(p.sgst)]] as [string, string][]) : []),
          ...(p.igst ? ([["IGST", money(p.igst)]] as [string, string][]) : []),
          ["Round Off", money(p.roundOff)],
          ["Total", `₹${money(p.total)}`],
        ]}
      />
      {p.note && <p className="small">{p.note}</p>}
    </SidePanel>
  );
}

function PaymentPanel({ term }: { term: CreditTerm | undefined }) {
  const parts = termParts(term);
  return (
    <SidePanel title="Payment Due">
      {parts.length ? parts.map((p) => <p key={p}>{p}</p>) : <p className="small">No credit term.</p>}
      <p className="small">The exact dates are set on the purchase invoice.</p>
    </SidePanel>
  );
}

// The order's own page (read only) ------------------------------------------------------

function OrderView({ companyId, id, session }: { companyId: number; id: number; session: SignedIn }) {
  const can = (p: string) => session.permissions.includes(`purchase.${p}`);
  const [order, setOrder] = useState<PurchaseOrder | null>(null);
  const [error, setError] = useState<unknown>("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
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
  const printing = usePrintMenu({ title: `Purchase order ${order?.number ?? ""}`, scope: order ? `${order.supplier_name} · ${showDate(order.order_date)}` : "" });
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
            {draft && can("submit") && (
              <button type="button" onClick={() => act("submit")}>
                Submit
              </button>
            )}
            <ActionsMenu items={printing.items} />
          </>
        }
      />
      {printing.panel}
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
          <Fold title="Supplier Contacts and Agent" open>
            <dl className="kv">
              <div>
                <dt>Buying Agent</dt>
                <dd>{order.agent_name || (order.agent_user_name ? `${order.agent_user_name} (employee)` : "None")}</dd>
              </div>
            </dl>
            {order.mail_contacts.length === 0 ? (
              <p className="small">Nobody is ticked to get this order by mail.</p>
            ) : (
              <table className="grid">
                <thead>
                  <tr>
                    <th>Mail To</th>
                    <th>Of</th>
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
                    <th className="num">Disc %</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th className="num">Amount ₹</th>
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
                      <b>{money(order.taxable_total)}</b>
                    </td>
                    <td />
                    <td className="num">
                      <b>{money(order.total)}</b>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Fold>
          {(order.terms || order.notes) && (
            <Fold title="Terms and Notes" open>
              {order.terms && (
                <div>
                  <b className="fact-label">Terms for the Supplier</b>
                  <p className="pre">{order.terms}</p>
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
        <div className="doc-foot">
          <TotalsPanel
            taxable={Number(order.taxable_total)}
            cgst={Number(order.cgst_total)}
            sgst={Number(order.sgst_total)}
            igst={Number(order.igst_total)}
            roundOff={Number(order.round_off)}
            total={Number(order.total)}
            note=""
          />
          <PaymentPanel term={terms.find((t) => t.id === order.credit_term)} />
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="purchase_order" id={order.id} stamp={JSON.stringify(order)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}
