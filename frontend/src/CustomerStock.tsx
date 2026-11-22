import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, type SignedIn } from "./api";
import { DocSide } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { announceSaved, closeThisTab, creatable, useCreated, type Creatable } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import type { PackageRow } from "./GoodsReceipts";
import { BagLabelPrint } from "./GrnPrint";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";

/** Entry > Stock > Stock Receipt and Stock Delivery: a customer's own goods coming in (their tea for
 * job work, their packing material, against their challan) and going back to them unused
 * (Sidharth, 2026-11-22, preview 9c in mockups/planning). Only items marked "Customer Provided";
 * quantity only, nothing in the books; held as that customer's stock and never mixed with ours.
 * Draft → Submit; Cancel moves the stock back. */

export type Kind = "receipt" | "delivery";
type Bin = {
  id: number;
  location_name: string;
  batch_number: string;
  package_number: string;
  qty: string;
  qty_unit: string;
};
type Line = {
  id: number;
  position: number;
  item: number;
  item_name: string;
  item_number: string;
  hsn: string;
  batch_tracked: boolean;
  unit: number;
  unit_name: string;
  stock_unit_name: string;
  qty: string;
  location: number | null;
  location_name: string;
  batch_number: string;
  expiry_date: string | null;
  bags: number;
  package_type: string;
  package_type_label: string;
  picked?: string;
  short_picked?: boolean;
  bins?: Bin[];
};
type Entry = {
  id: number;
  company: number;
  company_name: string;
  kind: Kind;
  kind_label: string;
  number: string;
  status: string;
  status_label: string;
  customer: number;
  customer_name: string;
  branch: number;
  branch_name: string;
  area: number | null;
  place_name: string;
  entry_date: string;
  challan_no: string;
  challan_date: string | null;
  reason: string;
  transporter: number | null;
  transporter_name: string;
  vehicle_no: string;
  eway_bill_no: string;
  stores_person: number | null;
  stores_person_name: string;
  notes: string;
  cancel_reason: string;
  created_by_name: string;
  created_at: string;
  submitted_at: string | null;
  submitted_by_name: string;
  items?: string;
  lines?: Line[];
  packages?: PackageRow[];
};
type FormItem = {
  id: number;
  name: string;
  item_number: string;
  batch_tracked: boolean;
  stock_unit: number;
  units: {
    unit: number;
    name: string;
    whole_numbers: boolean;
    factor: string;
  }[];
  held: string | null;
};
type Setup = {
  customer_group: number | null;
  customers: { id: number; name: string; is_active: boolean }[];
  branches: {
    id: number;
    name: string;
    is_active: boolean;
    areas: { id: number; name: string; is_active: boolean }[];
    places: { id: number; label: string }[];
  }[];
  transporters: { id: number; name: string }[];
  stores_people: { id: number; name: string }[];
  package_types: { id: string; name: string }[];
  items: FormItem[];
};
type Problem = { line: number | null; text: string };

const TEXT = {
  receipt: {
    title: "Stock Receipt",
    one: "receipt",
    many: "receipts",
    page: "stock-receipts",
    person: "Received By",
    place: "Put In",
    sub: "a customer's own goods coming in",
  },
  delivery: {
    title: "Stock Delivery",
    one: "delivery",
    many: "deliveries",
    page: "stock-deliveries",
    person: "Handed Over By",
    place: "Taken From",
    sub: "a customer's own goods going back to them",
  },
};
const VIEWS: [string, string][] = [
  ["all", "All"],
  ["draft", "Draft"],
  ["submitted", "Submitted"],
  ["cancelled", "Cancelled"],
];
export const customerStockBase = (companyId: number, kind: Kind) => `#/companies/${companyId}/${TEXT[kind].page}`;
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const at = (iso: string) => `${shortDate(iso)} at ${new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`;
const pillClass = (s: string) => (s === "submitted" ? "pill on" : s === "draft" ? "pill warn" : "pill");
const plain = (n: number) => String(Number(n.toFixed(3)));
const can = (session: SignedIn, action: string) => session.permissions.includes(`stock.${action}`);
const today = () => new Date().toLocaleDateString("en-CA");
const pdf = (id: number, download = false) => openTab(`/api/v1/customer-stock/${id}/pdf/${download ? "?download=1" : ""}`);
const recordType = (kind: Kind) => (kind === "receipt" ? "stock_receipt" : "stock_delivery");

export function CustomerStockPage({ companyId, session, kind }: { companyId: number; session: SignedIn; kind: Kind }) {
  const view = Number(hashParam("view"));
  const print = hashParam("print");
  if (view > 0 && (print === "labels" || print === "sheet")) return <Labels id={view} sheet={print === "sheet"} />;
  if (view > 0) return <EntryView companyId={companyId} id={view} session={session} kind={kind} />;
  if (hashParam("form") === "new") return <EntryView companyId={companyId} id={0} session={session} kind={kind} />;
  return <EntryList companyId={companyId} session={session} kind={kind} />;
}

function Labels({ id, sheet }: { id: number; sheet: boolean }) {
  const [e, setE] = useState<Entry | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    api<Entry>(`v1/customer-stock/${id}/`).then(setE, setError);
  }, [id]);
  if (!e)
    return (
      <section className="page">
        <ErrorNote error={error} />
      </section>
    );
  return <BagLabelPrint sheet={sheet} co={`${e.customer_name}'s goods · ${e.company_name}`} foot={`${shortDate(e.entry_date)} · ${e.number}`} number={e.number} bags={e.packages ?? []} />;
}

function columns(kind: Kind): [key: string, label: string, text: (e: Entry) => string][] {
  return [
    ["number", kind === "receipt" ? "Receipt No" : "Delivery No", (e) => e.number || "Draft"],
    ["date", "Date", (e) => shortDate(e.entry_date)],
    ["customer", "Customer", (e) => e.customer_name],
    ["place", "Branch", (e) => e.place_name],
    ...(kind === "receipt" ? [["challan", "Customer's Challan", (e: Entry) => e.challan_no] as [string, string, (e: Entry) => string]] : []),
    ["items", "Items", (e) => e.items ?? ""],
    ["status", "Status", (e) => e.status_label],
  ];
}

function EntryList({ companyId, session, kind }: { companyId: number; session: SignedIn; kind: Kind }) {
  const text = TEXT[kind];
  const cols = useMemo(() => columns(kind), [kind]);
  const [view, setView] = useState(hashParam("status") ?? "all");
  const [rows, setRows] = useState<Entry[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Entry[]>(`v1/companies/${companyId}/customer-stock/?kind=${kind}&view=${view}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message));
  }, [companyId, kind, view]);
  useEffect(reload, [reload]);
  useCreated(`${recordType(kind)}_saved`, (c) => {
    reload();
    setSelectedId(c.id);
  });
  const shown = useMemo(
    () =>
      rows.filter((e) =>
        cols.every(([key, , value]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          return words.every((w) => value(e).toLowerCase().includes(w));
        }),
      ),
    [rows, search, cols],
  );
  const selected = rows.find((e) => e.id === selectedId) ?? null;
  const printing = usePrintMenu({
    title: `Stock ${text.many}: ${VIEWS.find(([v]) => v === view)?.[1] ?? ""}`,
    scope: "",
  });
  const base = customerStockBase(companyId, kind);
  const open = (id: number) => openTab(`${base}?view=${id}`);
  return (
    <section className="page">
      <PageHeader
        title={text.title}
        crumbs={[{ label: "Entry › Stock", href: base }]}
        sub={`${shown.length} ${shown.length === 1 ? text.one : text.many} · ${text.sub}`}
        actions={
          <>
            {printing.buttons}
            {can(session, "create") && (
              <button type="button" onClick={() => openTab(`${base}?form=new`)}>
                New {text.title}
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
                {cols.map(([key, label]) => (
                  <th key={key}>{label}</th>
                ))}
              </tr>
              <tr className="col-search no-print">
                {cols.map(([key, label]) => (
                  <th key={key}>
                    <input type="search" aria-label={`Search ${label}`} placeholder="Search" value={search[key] ?? ""} onChange={(ev) => setSearch({ ...search, [key]: ev.target.value })} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && (
                <tr>
                  <td colSpan={cols.length} className="small">
                    No stock {text.many} match.
                  </td>
                </tr>
              )}
              {shown.map((e) => (
                <tr
                  key={e.id}
                  tabIndex={0}
                  className={selected?.id === e.id ? "selected" : ""}
                  onClick={() => setSelectedId(selected?.id === e.id ? null : e.id)}
                  onDoubleClick={() => open(e.id)}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter") open(e.id);
                  }}
                >
                  {cols.map(([key, , value]) =>
                    key === "status" ? (
                      <td key={key}>
                        <span className={pillClass(e.status)}>{e.status_label}</span>
                      </td>
                    ) : key === "number" ? (
                      <td key={key}>
                        <b>{value(e)}</b>
                      </td>
                    ) : (
                      <td key={key} className={key === "date" ? "nowrap" : undefined}>
                        {value(e)}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > 0 && <p className="small no-print">Click an entry to see it at the right; double-click or press Enter to open it in a new tab.</p>}
        </div>
        {selected && (
          <div className="side-col" aria-label={`${text.title} details`}>
            <SidePanel title={selected.number || "Draft"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Customer", selected.customer_name],
                  ["Branch", selected.place_name],
                  ["Date", shortDate(selected.entry_date)],
                  ...(kind === "receipt" ? [["Customer's Challan", [selected.challan_no, shortDate(selected.challan_date)].filter(Boolean).join(" · ")] as [string, string]] : []),
                  ["Transporter", selected.transporter_name],
                  ["Reason", selected.reason],
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
              <ChangeLog company={companyId} type="customer_stock" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// One entry ------------------------------------------------------------------------

type Fields = {
  customer: string;
  branch: string;
  area: string;
  entry_date: string;
  challan_no: string;
  challan_date: string;
  reason: string;
  transporter: string;
  vehicle_no: string;
  eway_bill_no: string;
  stores_person: string;
  notes: string;
};
type DraftLine = {
  key: number;
  item: string;
  unit: string;
  qty: string;
  location: string;
  batch_number: string;
  expiry_date: string;
  bags: string;
  package_type: string;
};
let nextKey = 1;
const emptyLine = (): DraftLine => ({
  key: nextKey++,
  item: "",
  unit: "",
  qty: "",
  location: "",
  batch_number: "",
  expiry_date: "",
  bags: "",
  package_type: "bag",
});
const blank = (): Fields => ({
  customer: hashParam("customer") ?? "",
  branch: "",
  area: "",
  entry_date: today(),
  challan_no: "",
  challan_date: "",
  reason: "",
  transporter: "",
  vehicle_no: "",
  eway_bill_no: "",
  stores_person: "",
  notes: "",
});
const fieldsOf = (e: Entry): Fields => ({
  customer: String(e.customer),
  branch: String(e.branch),
  area: e.area ? String(e.area) : "",
  entry_date: e.entry_date,
  challan_no: e.challan_no,
  challan_date: e.challan_date ?? "",
  reason: e.reason,
  transporter: e.transporter ? String(e.transporter) : "",
  vehicle_no: e.vehicle_no,
  eway_bill_no: e.eway_bill_no,
  stores_person: e.stores_person ? String(e.stores_person) : "",
  notes: e.notes,
});
const linesOf = (e: Entry): DraftLine[] =>
  (e.lines ?? []).map((l) => ({
    key: nextKey++,
    item: String(l.item),
    unit: String(l.unit),
    qty: l.qty,
    location: l.location ? String(l.location) : "",
    batch_number: l.batch_number,
    expiry_date: l.expiry_date ?? "",
    bags: l.bags ? String(l.bags) : "",
    package_type: l.package_type,
  }));
/** "Organic Harvest Foods'", "Ravi's". */
const whose = (name: string) => (name.endsWith("s") ? `${name}'` : `${name}'s`);
const bagWord = (n: number, label: string) => `${n} ${label.toLowerCase()}${n === 1 ? "" : label.toLowerCase().endsWith("x") ? "es" : "s"}`;
/** One part per bin and batch: "Store · OHF-2611-A (250) · 10 bags PK-000001 to PK-000010". */
const binsText = (bins: Bin[]) => {
  const parts: { where: string; qty: number; bags: string[] }[] = [];
  for (const b of bins) {
    const where = [b.location_name, b.batch_number].filter(Boolean).join(" · ");
    let part = parts.find((x) => x.where === where);
    if (!part) parts.push((part = { where, qty: 0, bags: [] }));
    part.qty += Number(b.qty_unit);
    if (b.package_number) part.bags.push(b.package_number);
  }
  return parts
    .map((x) => `${x.where} (${plain(x.qty)})${x.bags.length === 1 ? ` · ${x.bags[0]}` : x.bags.length ? ` · ${x.bags.length} bags ${x.bags[0]} to ${x.bags[x.bags.length - 1]}` : ""}`)
    .join("; ");
};

function EntryView({ companyId, id, session, kind }: { companyId: number; id: number; session: SignedIn; kind: Kind }) {
  const text = TEXT[kind];
  const receipt = kind === "receipt";
  const base = customerStockBase(companyId, kind);
  const crumb = `Entry › Stock › ${text.title}`;
  const [e, setE] = useState<Entry | null>(null);
  const [error, setError] = useState<unknown>("");
  const [fields, setFields] = useState<Fields>(blank);
  const [lines, setLines] = useState<DraftLine[]>(() => [emptyLine()]);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0);
  const [busy, setBusy] = useState(false);
  const take = useCallback((x: Entry) => {
    setE(x);
    setFields(fieldsOf(x));
    setLines(linesOf(x));
  }, []);
  useEffect(() => {
    if (id) api<Entry>(`v1/customer-stock/${id}/`).then(take, (err) => setError(err));
  }, [id, take]);
  const draft = !e || e.status === "draft";
  const mayEdit = draft && can(session, "create");
  const setupUrl = `v1/companies/${companyId}/customer-stock/form/?kind=${kind}&customer=${fields.customer}&branch=${fields.branch}&area=${receipt ? "" : fields.area}`;
  const refreshSetup = useCallback(() => api<Setup>(setupUrl).then(setSetup, (err) => setError(err)), [setupUrl]);
  useEffect(() => {
    if (mayEdit) refreshSetup();
  }, [mayEdit, refreshSetup]);
  const mayAddMasters = session.permissions.includes("masters.edit");
  const newCustomer: Creatable | undefined =
    mayAddMasters && setup?.customer_group
      ? {
          kind: "ledger",
          href: (name) => `${window.location.pathname}${window.location.search}#/companies/${companyId}/ledgers?form=new-in-${setup.customer_group}&new=${encodeURIComponent(name)}`,
          reload: refreshSetup,
        }
      : undefined;
  const newTransporter = mayAddMasters ? creatable("courier_account", `companies/${companyId}/couriers`, refreshSetup) : undefined;
  const newPerson = mayAddMasters ? creatable("sales_person", "sales-people", refreshSetup, "as=stores") : undefined;
  const newItem = mayAddMasters ? creatable("item", "items", refreshSetup) : undefined;
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base;
    });
  const done = (x: Entry) => {
    take(x);
    setCancelling(false);
    announceSaved(`${recordType(kind)}_saved`, {
      id: x.id,
      name: x.number || "Draft",
    });
    if (!id) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base}?view=${x.id}`);
  };
  const refusal = (err: unknown) => {
    const data = err instanceof ApiError ? (err.data as { problems?: Problem[] } | undefined) : undefined;
    if (data?.problems?.length) return setProblems(data.problems);
    setError(err);
  };
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      ...fields,
      kind,
      customer: Number(fields.customer) || null,
      branch: Number(fields.branch) || null,
      area: Number(fields.area) || null,
      challan_date: fields.challan_date || null,
      transporter: Number(fields.transporter) || null,
      stores_person: Number(fields.stores_person) || null,
      lines: lines
        .filter((l) => l.item)
        .map((l) => ({
          item: Number(l.item),
          unit: Number(l.unit),
          qty: l.qty || "0",
          location: Number(l.location) || null,
          batch_number: l.batch_number,
          expiry_date: l.expiry_date || null,
          bags: Number(l.bags) || 0,
          package_type: l.package_type || "bag",
        })),
      submit,
    };
    const current = e?.id ?? 0;
    try {
      done(current ? await api<Entry>(`v1/customer-stock/${current}/`, body, "PATCH") : await api<Entry>(`v1/companies/${companyId}/customer-stock/`, body));
    } catch (err) {
      // A refused Submit still saved the draft: read it again.
      const kept = err instanceof ApiError ? (err.data as { id?: number } | undefined)?.id : undefined;
      if (submit && (kept || current)) api<Entry>(`v1/customer-stock/${kept || current}/`).then(done, () => undefined);
      refusal(err);
    }
    setBusy(false);
  };
  const cancel = async () => {
    if (!e) return;
    setError("");
    setBusy(true);
    try {
      done(await api<Entry>(`v1/customer-stock/${e.id}/cancel/`, { reason }));
    } catch (err) {
      refusal(err);
    }
    setBusy(false);
  };
  const goTo = (position: number | null) => {
    setProblems(null);
    if (position) window.setTimeout(() => document.getElementById(`cs-line-${position}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };
  if (id && !e)
    return (
      <section className="page">
        <PageHeader title={text.title} crumbs={[{ label: crumb, href: base }]} />
        <ErrorNote error={error} />
      </section>
    );
  const set = (patch: Partial<Fields>) => setFields({ ...fields, ...patch });
  const status = e?.status ?? "draft";
  const branches = setup?.branches ?? [];
  const branch = branches.find((b) => String(b.id) === fields.branch);
  const items = setup?.items ?? [];
  const itemOf = (v: string) => items.find((i) => String(i.id) === v);
  const savedLines = e?.lines ?? [];
  const bags = e?.packages ?? [];
  const title = e?.number ? `${text.title} ${e.number}` : e ? `${text.title} (Draft)` : `New ${text.title}`;
  const printItems = e
    ? [
        {
          label: receipt ? "Receipt Slip" : "Delivery Challan",
          onClick: () => pdf(e.id),
        },
        ...(receipt
          ? [
              {
                label: "Bag Labels (label printer, 100 × 50 mm)",
                onClick: () => openTab(`${base}?view=${e.id}&print=labels`),
                disabled: !bags.length,
                title: bags.length ? undefined : "Bags are numbered on Submit",
              },
              {
                label: "Bag Labels (A4 sheet, 24 a page)",
                onClick: () => openTab(`${base}?view=${e.id}&print=sheet`),
                disabled: !bags.length,
                title: bags.length ? undefined : "Bags are numbered on Submit",
              },
            ]
          : []),
        { label: "Download PDF", onClick: () => pdf(e.id, true) },
      ]
    : [];
  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={e?.submitted_at ? `Submitted as ${e.number} on ${at(e.submitted_at)}` : e ? `Draft made ${at(e.created_at)} · nothing posted yet` : "Nothing is saved until you press Save"}
        crumbs={[{ label: crumb, href: base }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {e && status !== "cancelled" && can(session, "cancel") && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel
              </button>
            )}
            {e && <ActionsMenu label="Print" items={printItems} />}
            {mayEdit && (
              <button type="button" className="link" disabled={busy} onClick={() => save(false)}>
                Save
              </button>
            )}
            {mayEdit && can(session, "submit") && (
              <button type="button" disabled={busy} onClick={() => save(true)}>
                Submit
              </button>
            )}
            {status === "submitted" && receipt && (
              <ActionsMenu
                label="Create"
                main
                items={[
                  {
                    label: "Stock Delivery (send goods back)",
                    onClick: () => e && openTab(`${customerStockBase(companyId, "delivery")}?form=new&customer=${e.customer}`),
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
            <p className="doc-title">{e ? `${e.customer_name} · ${e.place_name}` : text.title}</p>
            <p className="item-sub">
              {e?.number && <b>{e.number}</b>}
              <span className={pillClass(status)}>{e?.status_label ?? "New"}</span>
            </p>
          </div>
          {e?.status === "cancelled" && <p className="use-note">Cancelled: {e.cancel_reason}</p>}
          {cancelling && e && (
            <div className="use-note no-print">
              <label>
                <b>Why is this {text.one} cancelled?</b>
                <input autoFocus value={reason} onChange={(ev) => setReason(ev.target.value)} placeholder="e.g. Entered twice" />
              </label>
              <p className="small">
                {status === "submitted"
                  ? receipt
                    ? "The goods come out of the customer's stock again; refused if any of them has been used or sent back since."
                    : "The goods go back into the customer's stock, in the bins they were taken from."
                  : "The draft is set aside."}
              </p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep it
                </button>
                <button type="button" className="link danger" disabled={busy} onClick={cancel}>
                  Cancel {text.title}
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title={receipt ? "Customer and Challan" : "Customer and Despatch"} open summary={e ? `${e.customer_name} · ${shortDate(e.entry_date)}` : ""}>
            {mayEdit ? (
              <div className="item-fields">
                <label>
                  <span className="req">Customer</span>
                  <Combobox
                    value={fields.customer}
                    onChange={(v) => set({ customer: v })}
                    required
                    create={newCustomer}
                    options={(setup?.customers ?? []).filter((c) => c.is_active || String(c.id) === fields.customer).map((c) => ({ value: String(c.id), label: c.name }))}
                  />
                  <span className="small">{receipt ? "Whose goods these are: they are held as that customer's stock" : "Only that customer's own stock is picked"}</span>
                </label>
                <label>
                  <span className="req">Branch</span>
                  <Combobox
                    value={fields.branch}
                    onChange={(v) => set({ branch: v, area: "" })}
                    required
                    options={branches.filter((b) => b.is_active || String(b.id) === fields.branch).map((b) => ({ value: String(b.id), label: b.name }))}
                  />
                </label>
                <label>
                  Area
                  <Combobox
                    value={fields.area}
                    onChange={(v) => set({ area: v })}
                    empty={receipt ? "Receiving area or default store" : "Whole branch"}
                    options={(branch?.areas ?? []).filter((a) => a.is_active || String(a.id) === fields.area).map((a) => ({ value: String(a.id), label: a.name }))}
                  />
                  <span className="small">{receipt ? "Where lines go unless they name a place" : "Bins and batches are picked from here (earliest expiry first)"}</span>
                </label>
                <label>
                  <span className="req">Date</span>
                  <input type="date" required value={fields.entry_date} onChange={(ev) => set({ entry_date: ev.target.value })} />
                </label>
                {receipt && (
                  <>
                    <label>
                      Customer's Challan No
                      <input value={fields.challan_no} maxLength={40} placeholder="e.g. OHF/DC/118" onChange={(ev) => set({ challan_no: ev.target.value })} />
                    </label>
                    <label>
                      Challan Date
                      <input type="date" value={fields.challan_date} onChange={(ev) => set({ challan_date: ev.target.value })} />
                    </label>
                  </>
                )}
                <label>
                  Transporter
                  <Combobox
                    value={fields.transporter}
                    onChange={(v) => set({ transporter: v })}
                    empty="By Customer"
                    create={newTransporter}
                    options={(setup?.transporters ?? []).map((c) => ({
                      value: String(c.id),
                      label: c.name,
                    }))}
                  />
                </label>
                <label>
                  Vehicle No
                  <input value={fields.vehicle_no} maxLength={20} placeholder="e.g. WB11A2290" onChange={(ev) => set({ vehicle_no: ev.target.value })} />
                </label>
                <label>
                  E-way Bill No
                  <input value={fields.eway_bill_no} maxLength={20} onChange={(ev) => set({ eway_bill_no: ev.target.value })} />
                </label>
                <label>
                  {text.person}
                  <Combobox
                    value={fields.stores_person}
                    onChange={(v) => set({ stores_person: v })}
                    create={newPerson}
                    options={(setup?.stores_people ?? []).map((p) => ({
                      value: String(p.id),
                      label: p.name,
                    }))}
                  />
                </label>
                <label className="wide">
                  Reason
                  <input
                    value={fields.reason}
                    maxLength={200}
                    placeholder={receipt ? "e.g. Tea for packing, job work order JW-14" : "e.g. Not needed, sent back"}
                    onChange={(ev) => set({ reason: ev.target.value })}
                  />
                </label>
              </div>
            ) : (
              e && (
                <Facts
                  rows={[
                    ["Customer", e.customer_name],
                    ["Branch", e.place_name],
                    ["Date", shortDate(e.entry_date)],
                    ["Customer's Challan", [e.challan_no, shortDate(e.challan_date)].filter(Boolean).join(" · ")],
                    ["Transporter", e.transporter_name],
                    ["Vehicle No", e.vehicle_no],
                    ["E-way Bill No", e.eway_bill_no],
                    [text.person, e.stores_person_name],
                    ["Reason", e.reason],
                  ]}
                />
              )
            )}
          </Fold>
          <Fold title="Items" open summary={`${mayEdit ? lines.filter((l) => l.item).length : savedLines.length} items`}>
            {mayEdit ? (
              <>
                <div className="table-scroll">
                  <table className="grid po-lines">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th style={{ minWidth: 200 }}>Item</th>
                        <th className="num">Qty</th>
                        <th>Unit</th>
                        {receipt ? (
                          <>
                            <th style={{ minWidth: 150 }}>Put In</th>
                            <th style={{ minWidth: 150 }}>Batch</th>
                            <th className="num">Bags</th>
                            <th style={{ minWidth: 110 }}>Bag Type</th>
                          </>
                        ) : (
                          <>
                            <th className="num">Customer's Stock</th>
                            <th>Taken From (bin · batch)</th>
                          </>
                        )}
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l, k) => {
                        const item = itemOf(l.item);
                        const unit = item?.units.find((u) => String(u.unit) === l.unit);
                        const held = item?.held != null && unit ? Number(item.held) / Number(unit.factor || 1) : null;
                        const saved = savedLines.find((s) => s.position === k + 1 && String(s.item) === l.item);
                        const setLine = (patch: Partial<DraftLine>) => setLines((ls) => ls.map((x) => (x.key === l.key ? { ...x, ...patch } : x)));
                        return (
                          <tr key={l.key} id={`cs-line-${k + 1}`}>
                            <td>{k + 1}</td>
                            <td className="po-item">
                              <Combobox
                                value={l.item}
                                ariaLabel={`Item on line ${k + 1}`}
                                placeholder="Type to search items…"
                                create={newItem}
                                onChange={(v) =>
                                  setLine({
                                    item: v,
                                    unit: String(itemOf(v)?.stock_unit ?? ""),
                                  })
                                }
                                options={items.map((i) => ({
                                  value: String(i.id),
                                  label: i.name,
                                  hint: i.item_number,
                                }))}
                              />
                            </td>
                            <td className="num">
                              <input className="num" inputMode="decimal" aria-label={`Qty on line ${k + 1}`} value={l.qty} onChange={(ev) => setLine({ qty: ev.target.value })} />
                            </td>
                            <td>
                              <Combobox
                                value={l.unit}
                                ariaLabel={`Unit on line ${k + 1}`}
                                onChange={(v) => setLine({ unit: v })}
                                options={(item?.units ?? []).map((u) => ({
                                  value: String(u.unit),
                                  label: u.name,
                                }))}
                              />
                            </td>
                            {receipt ? (
                              <>
                                <td className="po-item">
                                  <Combobox
                                    value={l.location}
                                    ariaLabel={`Put line ${k + 1} in`}
                                    onChange={(v) => setLine({ location: v })}
                                    empty="Area above"
                                    options={(branch?.places ?? []).map((p) => ({
                                      value: String(p.id),
                                      label: p.label,
                                    }))}
                                  />
                                </td>
                                <td>
                                  {item?.batch_tracked ? (
                                    <input
                                      aria-label={`Batch on line ${k + 1}`}
                                      value={l.batch_number}
                                      maxLength={60}
                                      placeholder="Customer's lot no"
                                      onChange={(ev) =>
                                        setLine({
                                          batch_number: ev.target.value,
                                        })
                                      }
                                    />
                                  ) : (
                                    <span className="small">No batches</span>
                                  )}
                                </td>
                                <td className="num">
                                  <input
                                    className="num"
                                    inputMode="numeric"
                                    aria-label={`Bags on line ${k + 1}`}
                                    style={{ width: 70 }}
                                    value={l.bags}
                                    onChange={(ev) =>
                                      setLine({
                                        bags: ev.target.value.replace(/\D/g, ""),
                                      })
                                    }
                                  />
                                </td>
                                <td>
                                  <Combobox
                                    value={l.package_type}
                                    ariaLabel={`Bag type on line ${k + 1}`}
                                    onChange={(v) => setLine({ package_type: v || "bag" })}
                                    options={(setup?.package_types ?? []).map((p) => ({ value: p.id, label: p.name }))}
                                  />
                                </td>
                              </>
                            ) : (
                              <>
                                <td className="num">{held == null ? "" : held < Number(l.qty || 0) ? <b className="error">{plain(held)}</b> : plain(held)}</td>
                                <td className="small">
                                  {saved?.bins ? binsText(saved.bins) || <span className="error">Nothing of theirs here</span> : "Picked on Save"}
                                  {saved?.short_picked && (saved.bins?.length ?? 0) > 0 && <span className="error"> · only {saved.picked} free</span>}
                                </td>
                              </>
                            )}
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
                  <button type="button" className="link" onClick={() => setLines((ls) => [...ls, emptyLine()])}>
                    + Add item
                  </button>
                </div>
                <p className="small">
                  Only items marked "Customer Provided" are listed.{" "}
                  {receipt
                    ? 'Each bag gets its own number (PK-…) on Submit, with the line\'s quantity shared equally; print their labels from "Print ▾".'
                    : "Bins and batches are picked from this customer's own stock each time the draft is saved, and again on Submit."}
                </p>
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
                      <th>{receipt ? "Put In (bin · batch)" : "Taken From (bin · batch)"}</th>
                      {receipt && <th className="num">Bags</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {savedLines.map((l) => (
                      <tr key={l.id} id={`cs-line-${l.position}`}>
                        <td>{l.position}</td>
                        <td>
                          <b>{l.item_name}</b>
                          <div className="small">HSN {l.hsn}</div>
                        </td>
                        <td className="num">{l.qty}</td>
                        <td>{l.unit_name}</td>
                        <td className="small">
                          {receipt ? [l.location_name || "Area above", l.batch_number || "–"].join(" · ") : binsText(l.bins ?? [])}
                        </td>
                        {receipt && <td className="num">{l.bags ? bagWord(l.bags, l.package_type_label) : ""}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Fold>
          <p className="small">
            No Ledger Posting: a customer's goods are quantity only and never in our books.{" "}
            {receipt ? `On Submit they are held as ${e ? whose(e.customer_name) : "the customer's"} stock at ${e?.branch_name ?? "the branch"}.` : "On Submit they leave that customer's stock."}
          </p>
        </div>
        <DocSide type={recordType(kind)} id={e?.id ?? null} onChange={() => setFiles((n) => n + 1)}>
          {e && (
            <>
              <SidePanel title="Details">
                <SideRows
                  rows={[
                    ["Made By", e.created_by_name],
                    ["Submitted By", e.submitted_by_name],
                    ...(receipt && bags.length ? [["Bags", `${bags.length} (${bags[0].number} to ${bags[bags.length - 1].number})`] as [string, string]] : []),
                  ]}
                />
              </SidePanel>
              <SidePanel title="Activity">
                <ChangeLog company={companyId} type="customer_stock" id={e.id} stamp={JSON.stringify(e) + files} />
              </SidePanel>
            </>
          )}
        </DocSide>
      </div>
      {problems && <ProblemsPopup problems={problems} what={text.one} onGo={goTo} onClose={() => setProblems(null)} />}
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

/** Everything that stopped Submit, each with "Go to line". */
function ProblemsPopup(props: { problems: Problem[]; what: string; onGo: (line: number | null) => void; onClose: () => void }) {
  return (
    <div className="popup-back" role="presentation">
      <div className="popup grn-check" role="dialog" aria-modal="true" aria-label={`This ${props.what} cannot be submitted yet`}>
        <h3>
          This {props.what} cannot be submitted yet ({props.problems.length})
        </h3>
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
        <p className="small">Nothing has been submitted; the draft is kept.</p>
        <div className="popup-actions">
          <button type="button" onClick={props.onClose}>
            OK
          </button>
        </div>
      </div>
    </div>
  );
}
