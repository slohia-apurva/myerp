import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { Attachments, keptDraft } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { longDate, money } from "./Companies";
import { announceSaved, closeThisTab, creatable, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu, usePrintMenu } from "./Exchange";
import { GrnPrint, type PrintKind } from "./GrnPrint";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";

/** Entry > Purchase > Goods Receipt: what arrived against a supplier's purchase orders, and
 * which bins and batches it went into. Submit posts the stock (Dr Stock, Cr Goods Received
 * but Bills not Received) at the order rates plus the order's charges to stock. */

export type Putaway = {
  location: number;
  location_name: string;
  batch: number | null;
  batch_number: string;
  new_batch: boolean;
  mfg_date: string | null;
  expiry_date: string | null;
  qty: string;
  packages: number | null;
  package_type: string;
  package_type_label: string;
  package_qty: string | null;
};
export type PackageRow = {
  id: number;
  seq: number;
  number: string;
  kind_label: string;
  item_name: string;
  item_number: string;
  batch: string;
  expiry_date: string | null;
  location: number;
  location_name: string;
  qty: string;
  left_qty: string;
  unit_name: string;
  status: string;
  status_label: string;
  position: number;
  of_count: number;
};
export type LineInfo = {
  order_line: number;
  order: number;
  order_number: string;
  order_position: number;
  item: number;
  item_name: string;
  item_number: string;
  batch_tracked: boolean;
  qc_required: boolean;
  unit: number;
  unit_name: string;
  rate: string;
  ordered: string;
  earlier: string;
};
export type ReceiptLine = LineInfo & {
  received_qty: string;
  rejected_qty: string;
  accepted_qty: string;
  value: string;
  charges_value: string;
  putaways: Putaway[];
};
export type GoodsReceipt = {
  id: number;
  number: string;
  status: string;
  status_label: string;
  supplier: number;
  supplier_name: string;
  branch: number;
  branch_name: string;
  receipt_date: string;
  orders: number[];
  order_numbers: string[];
  challan_no: string;
  challan_date: string | null;
  transporter: number | null;
  transporter_name: string;
  lr_no: string;
  vehicle_no: string;
  eway_bill_no: string;
  received_by: number | null;
  received_by_name: string;
  currency: string;
  exchange_rate: string | null;
  qc_cartons: string;
  qc_batch_print: string;
  qc_by: number | null;
  qc_by_name: string;
  notes: string;
  stock_value: string;
  accepted_total: string;
  cancel_reason: string;
  submitted_at: string | null;
  submitted_by_name: string;
  lines?: ReceiptLine[];
  packages?: PackageRow[];
};
type PendingLine = LineInfo & { pending: string };
type PendingOrder = {
  id: number;
  number: string;
  order_date: string;
  supplier: number;
  branch: number;
  branch_name: string;
  currency: string;
  transporter: number | null;
  lines: PendingLine[];
};
type Place = { id: number; branch: number; kind: string; name: string; is_default: boolean; purpose: string };
type Setup = {
  branches: { id: number; name: string }[];
  locations: Place[];
  transporters: { id: number; name: string }[];
  /** Masters › People ticked "Stores": for Received By and QC By. */
  stores_people: { id: number; name: string; is_active: boolean }[];
  suppliers: { id: number; name: string }[];
  package_types: [string, string][];
  can_submit: boolean;
  can_cancel: boolean;
  can_create: boolean;
  today: string;
};
type BatchRow = { id: number; number: string; mfg_date: string | null; expiry_date: string | null; status_label: string };
type Postings = {
  gl: { ledger_name: string; debit: string; credit: string; is_reversal: boolean }[];
  stock: { item_name: string; location: string; batch: string; qty: string; value: string; is_reversal: boolean }[];
};

const base = (companyId: number) => `#/companies/${companyId}/goods-receipts`;
const showDate = (iso: string | null) => (iso ? longDate(iso) : "");
const shortDate = (iso: string | null) => (iso ? iso.split("-").reverse().join("-") : "");
/** 600.000000 -> 600, 12.500000 -> 12.5 */
const qty = (v: string | number) => String(Number(v));
const CARTONS = [
  { value: "ok", label: "OK" },
  { value: "damaged", label: "Damaged" },
];
const PRINTS = [
  { value: "matches", label: "Matches" },
  { value: "wrong", label: "Wrong / Missing" },
];
const pillClass = (status: string) => (status === "submitted" ? "pill on" : "pill");

/** "Create ▾" on a submitted receipt: the documents that follow from it. */
const createFromReceipt = (companyId: number, id: number) => [
  { label: "Purchase Invoice (supplier's bill)", onClick: () => openTab(`#/companies/${companyId}/purchase-invoices?form=new&receipt=${id}`) },
  { label: "Purchase Return (goods sent back)", onClick: () => openTab(`#/companies/${companyId}/purchase-returns?form=new&receipt=${id}`) },
];

function useSetup(companyId: number) {
  const [setup, setSetup] = useState<Setup | null>(null);
  // refresh returns the request, so "Create …" can wait for the new person.
  const refresh = useCallback(
    () => api<Setup>(`v1/companies/${companyId}/goods-receipts/setup/`).then(setSetup, () => setSetup(null)),
    [companyId],
  );
  useEffect(() => {
    refresh();
  }, [refresh]);
  return { setup, refresh };
}

/** Each item's batches, fetched once per item. */
function useBatches(itemIds: number[]) {
  const [batches, setBatches] = useState<Record<number, BatchRow[]>>({});
  const key = [...new Set(itemIds)].sort().join(",");
  useEffect(() => {
    key
      .split(",")
      .filter(Boolean)
      .map(Number)
      .filter((id) => !(id in batches))
      .forEach((id) =>
        api<BatchRow[]>(`v1/batches/?item=${id}`).then(
          (rows) => setBatches((b) => ({ ...b, [id]: rows })),
          () => setBatches((b) => ({ ...b, [id]: [] })),
        ),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return batches;
}

export function GoodsReceiptsPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const form = hashParam("form");
  const view = Number(hashParam("view"));
  const can = (p: string) => session.permissions.includes(`purchase.${p}`) || session.permissions.includes(`stock.${p}`);
  if (form && can("create"))
    return <ReceiptFormTab companyId={companyId} form={form} mayAddPeople={session.permissions.includes("masters.edit")} />;
  const print = Number(hashParam("print"));
  if (print > 0) {
    const layout = (hashParam("layout") ?? "note") as PrintKind;
    const only = (hashParam("only") ?? "").split(",").map(Number).filter(Boolean);
    return <GrnPrint id={print} kind={["note", "bins", "labels", "sheet"].includes(layout) ? layout : "note"} only={only} />;
  }
  if (view > 0) return <ReceiptView companyId={companyId} id={view} />;
  return <ReceiptList companyId={companyId} canCreate={can("create")} />;
}

/** "Print ▾": the receipt's layouts (Sidharth, 2026-11-15). Labels print the ticked bags,
 * else all of them. */
function printMenu(companyId: number, id: number | null, opts: { submitted?: boolean; bags?: number[] } = {}) {
  const open = (layout: PrintKind) => () => {
    if (!id) return;
    const only = layout === "labels" || layout === "sheet" ? (opts.bags ?? []) : [];
    openTab(`${base(companyId)}?print=${id}&layout=${layout}${only.length ? `&only=${only.join(",")}` : ""}`);
  };
  const noBags = opts.submitted ? undefined : "Bags get their numbers on Submit";
  return [
    { label: "Goods Receipt Note", onClick: open("note") },
    { label: "Bin Sheets (A4)", onClick: open("bins") },
    { label: "Bag Labels (label printer, 100 × 50 mm)", onClick: open("labels"), disabled: !opts.submitted, title: noBags },
    { label: "Bag Labels (A4 sheet, 24 per page)", onClick: open("sheet"), disabled: !opts.submitted, title: noBags },
    { label: "Download PDF", onClick: open("note") },
  ];
}

// The list ----------------------------------------------------------------------

const VIEWS = [
  { value: "all", label: "All" },
  { value: "draft", label: "Drafts" },
  { value: "submitted", label: "Submitted" },
  { value: "cancelled", label: "Cancelled" },
];
const COLUMNS: [key: string, label: string, text: (r: GoodsReceipt) => string, num?: boolean][] = [
  ["number", "GRN No", (r) => r.number || "Draft"],
  ["date", "Date", (r) => `${shortDate(r.receipt_date)} ${showDate(r.receipt_date)}`],
  ["supplier", "Supplier", (r) => r.supplier_name],
  ["branch", "Warehouse", (r) => r.branch_name],
  ["orders", "Purchase Orders", (r) => r.order_numbers.join(" ")],
  ["challan", "Challan No", (r) => r.challan_no],
  ["value", "Stock Value ₹", (r) => `${r.stock_value} ${money(r.stock_value)}`, true],
  ["status", "Status", (r) => r.status_label],
];

function ReceiptList({ companyId, canCreate }: { companyId: number; canCreate: boolean }) {
  const [view, setView] = useState("all");
  const [rows, setRows] = useState<GoodsReceipt[]>([]);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<unknown>("");
  const reload = useCallback(() => {
    api<GoodsReceipt[]>(`v1/companies/${companyId}/goods-receipts/?view=${view}`).then(setRows, setError);
  }, [companyId, view]);
  useEffect(reload, [reload]);
  useCreated("goods_receipt_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
  useEffect(() => {
    const open = Number(hashParam("open"));
    if (open && rows.some((r) => r.id === open)) setSelectedId(open);
  }, [rows]);
  const shown = useMemo(
    () =>
      rows.filter((r) =>
        COLUMNS.every(([key, , text]) => {
          const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
          const value = text(r).toLowerCase();
          return words.every((w) => value.includes(w));
        }),
      ),
    [rows, search],
  );
  const selected = rows.find((r) => r.id === selectedId) ?? null;
  const printing = usePrintMenu({ title: `Goods receipts: ${VIEWS.find((v) => v.value === view)?.label ?? ""}`, scope: "" });
  const total = shown.reduce((sum, r) => sum + Number(r.stock_value), 0);
  return (
    <section className="page">
      <PageHeader
        title="Goods Receipt"
        crumbs={[{ label: "Entry › Purchase", href: base(companyId) }]}
        sub={`${shown.length} ${shown.length === 1 ? "receipt" : "receipts"}`}
        actions={
          <>
            {canCreate && (
              <button
                type="button"
                className="secondary"
                disabled={selected?.status !== "draft"}
                title={selected ? (selected.status === "draft" ? "" : "Only a draft can be changed") : "Click a draft receipt first"}
                onClick={() => selected && openTab(`${base(companyId)}?form=${selected.id}`)}
              >
                Edit
              </button>
            )}
            {canCreate && <button onClick={() => openTab(`${base(companyId)}?form=new`)}>New goods receipt</button>}
            {printing.buttons}
          </>
        }
      />
      <ErrorNote error={error} />
      {printing.panel}
      <div className={selected ? "side-layout" : "full-list"}>
        <div className="side-main">
          <div className="row filters no-print">
            <span className="po-view">
              <Combobox value={view} onChange={setView} ariaLabel="Show" options={VIEWS} />
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
                    No goods receipts match.
                  </td>
                </tr>
              )}
              {shown.map((r) => (
                <tr
                  key={r.id}
                  tabIndex={0}
                  className={selected?.id === r.id ? "selected" : ""}
                  onClick={() => setSelectedId(selected?.id === r.id ? null : r.id)}
                  onDoubleClick={() => openTab(`${base(companyId)}?view=${r.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") openTab(`${base(companyId)}?view=${r.id}`);
                  }}
                >
                  <td>{r.number ? <b>{r.number}</b> : <span className="small">Draft</span>}</td>
                  <td className="nowrap">{shortDate(r.receipt_date)}</td>
                  <td>{r.supplier_name}</td>
                  <td>{r.branch_name}</td>
                  <td>{r.order_numbers.join(", ")}</td>
                  <td>{r.challan_no}</td>
                  <td className="num">{r.status === "submitted" ? money(r.stock_value) : ""}</td>
                  <td>
                    <span className={pillClass(r.status)}>{r.status_label}</span>
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
            <p className="small no-print">Click a receipt to see it at the right (click it again to close the panel); double-click or press Enter to open it in a new tab.</p>
          )}
        </div>
        {selected && (
          <div className="side-col" aria-label="Receipt details">
            <SidePanel title={selected.number || "Draft receipt"} tag={selected.status_label}>
              <SideRows
                rows={[
                  ["Supplier", selected.supplier_name],
                  ["Receipt Date", showDate(selected.receipt_date)],
                  ["Warehouse", selected.branch_name],
                  ["Purchase Orders", selected.order_numbers.join(", ")],
                  ["Challan No", selected.challan_no],
                  ["Vehicle No", selected.vehicle_no],
                  ["Received By", selected.received_by_name],
                  ["Stock Value", selected.status === "submitted" ? `₹${money(selected.stock_value)}` : ""],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => openTab(`${base(companyId)}?view=${selected.id}`)}>
                  Open
                </button>
                <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?print=${selected.id}&layout=note`)}>
                  Print
                </button>
              </div>
            </SidePanel>
            <SidePanel title="Activity">
              <ChangeLog company={companyId} type="goods_receipt" id={selected.id} stamp={JSON.stringify(selected)} />
            </SidePanel>
          </div>
        )}
      </div>
    </section>
  );
}

// The form ------------------------------------------------------------------------

/** A part of a line's accepted quantity: its bin or area and batch. `batch` is
 * "b<id>" for a batch in the master, "n<number>" for a new one typed here, "" for none. */
type PutDraft = { key: number; location: string; batch: string; mfg: string; expiry: string; qty: string; pkgs: string; pkgType: string; pkgQty: string };
/** Packages × Qty per Package gives the quantity (5 bags of 20 = 100). */
const packed = (p: PutDraft) => !!(num(p.pkgs) && num(p.pkgQty));
const withPack = (p: PutDraft, patch: Partial<PutDraft>): PutDraft => {
  const next = { ...p, ...patch };
  return packed(next) ? { ...next, qty: qty(round6(num(next.pkgs) * num(next.pkgQty))) } : next;
};
/** A quantity in whole packages of the usual size, else no package count. */
const fitPacks = (p: PutDraft, total: number): PutDraft => {
  const each = num(p.pkgQty);
  const n = each ? total / each : 0;
  return { ...p, qty: total ? qty(round6(total)) : "", pkgs: n && Number.isInteger(round6(n)) ? String(round6(n)) : "" };
};
type LineDraft = { key: number; info: LineInfo; received: string; rejected: string; puts: PutDraft[] };
let nextKey = 1;
const num = (v: string) => Number(v) || 0;
const accepted = (l: LineDraft) => Math.max(num(l.received) - num(l.rejected), 0);
const putTotal = (l: LineDraft) => l.puts.reduce((s, p) => s + num(p.qty), 0);
/** "40 kg short" / "20 kg over" when a line's bins do not add up to its accepted quantity
 * (Sidharth, 2026-11-17: Submit is refused until they do). Empty when they match. */
const putGap = (l: LineDraft) => {
  const gap = round6(accepted(l) - putTotal(l));
  if (Math.abs(gap) < 1e-9) return "";
  return `${qty(Math.abs(gap))} ${l.info.unit_name} ${gap > 0 ? "short" : "over"}`;
};
/** What stops a line from being submitted: bins that do not add up, or a batch-tracked bin with no batch. */
const binProblem = (l: LineDraft) => {
  if (accepted(l) <= 0) return "";
  const gap = putGap(l);
  if (gap) return gap;
  if (l.info.batch_tracked && l.puts.some((p) => num(p.qty) && !p.batch)) return "Batch No missing";
  return "";
};
const overBy = (l: LineDraft) => num(l.info.earlier) + accepted(l) - num(l.info.ordered);
const round6 = (n: number) => Math.round(n * 1e6) / 1e6;

function ReceiptFormTab({ companyId, form, mayAddPeople }: { companyId: number; form: string; mayAddPeople: boolean }) {
  const [receipt, setReceipt] = useState<GoodsReceipt | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    if (form === "new") return;
    api<GoodsReceipt>(`v1/goods-receipts/${Number(form)}/`).then(setReceipt, setError);
  }, [form]);
  const title = form === "new" ? "New Goods Receipt" : "Edit Goods Receipt";
  const shell = (note?: unknown) => (
    <section className="page">
      <PageHeader title={title} crumbs={[{ label: "Entry › Purchase › Goods Receipt", href: base(companyId) }]} />
      <ErrorNote error={note} />
    </section>
  );
  if (error) return shell(error);
  if (form !== "new" && !receipt) return shell();
  if (receipt && receipt.status !== "draft") return shell("A submitted receipt cannot be changed. Cancel it and make a new one.");
  return (
    <ReceiptForm
      companyId={companyId}
      title={title}
      receipt={receipt}
      fromOrder={Number(hashParam("order")) || null}
      mayAddPeople={mayAddPeople}
    />
  );
}

function ReceiptForm(props: {
  companyId: number;
  title: string;
  receipt: GoodsReceipt | null;
  fromOrder: number | null;
  mayAddPeople: boolean;
}) {
  const { companyId, receipt: r } = props;
  const { setup, refresh: refreshSetup } = useSetup(companyId);
  const [supplier, setSupplier] = useState(r ? String(r.supplier) : "");
  const [branch, setBranch] = useState(r ? String(r.branch) : "");
  const [date, setDate] = useState(r?.receipt_date ?? new Date().toISOString().slice(0, 10));
  const [orders, setOrders] = useState<number[]>(r?.orders ?? []);
  const [challanNo, setChallanNo] = useState(r?.challan_no ?? "");
  const [challanDate, setChallanDate] = useState(r?.challan_date ?? "");
  const [transporter, setTransporter] = useState(r?.transporter ? String(r.transporter) : "");
  const [lr, setLr] = useState(r?.lr_no ?? "");
  const [vehicle, setVehicle] = useState(r?.vehicle_no ?? "");
  const [eway, setEway] = useState(r?.eway_bill_no ?? "");
  const [receivedBy, setReceivedBy] = useState(r?.received_by ? String(r.received_by) : "");
  const [rate, setRate] = useState(r?.exchange_rate ?? "");
  const [qcCartons, setQcCartons] = useState(r?.qc_cartons ?? "");
  const [qcPrint, setQcPrint] = useState(r?.qc_batch_print ?? "");
  const [qcBy, setQcBy] = useState(r?.qc_by ? String(r.qc_by) : "");
  const [notes, setNotes] = useState(r?.notes ?? "");
  const [lines, setLines] = useState<LineDraft[]>(() =>
    (r?.lines ?? []).map((l) => ({
      key: nextKey++,
      info: l,
      received: qty(l.received_qty),
      rejected: num(l.rejected_qty) ? qty(l.rejected_qty) : "",
      puts: l.putaways.map((p) => ({
        key: nextKey++,
        location: String(p.location),
        batch: p.batch ? `b${p.batch}` : p.batch_number ? `n${p.batch_number}` : "",
        mfg: p.new_batch ? (p.mfg_date ?? "") : "",
        expiry: p.new_batch ? (p.expiry_date ?? "") : "",
        qty: qty(p.qty),
        pkgs: p.packages ? String(p.packages) : "",
        pkgType: p.package_type,
        pkgQty: p.package_qty ? qty(p.package_qty) : "",
      })),
    })),
  );
  const [pending, setPending] = useState<PendingOrder[]>([]);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [draftId, setDraftId] = useState<number | null>(r?.id ?? null);
  const [savedAt, setSavedAt] = useState("");
  const batches = useBatches(lines.map((l) => l.info.item));
  // Each line's bins fold to one line; "Edit bins" opens just that one (Sidharth, 2026-11-17).
  const [openBins, setOpenBins] = useState<number | null>(null);
  const [binCheck, setBinCheck] = useState<LineDraft[] | null>(null);

  // The supplier's open orders (with what is still to come), once a supplier is picked.
  useEffect(() => {
    if (!supplier) return setPending([]);
    api<PendingOrder[]>(`v1/companies/${companyId}/goods-receipts/pending/?supplier=${supplier}`).then(setPending, () => setPending([]));
  }, [companyId, supplier]);
  // Opened from a purchase order's "Create ▾": that order's supplier, warehouse and items.
  const [fromOrder, setFromOrder] = useState(props.fromOrder);
  useEffect(() => {
    if (!fromOrder || !setup) return;
    api<PendingOrder[]>(`v1/companies/${companyId}/goods-receipts/pending/`).then((all) => {
      const o = all.find((x) => x.id === fromOrder);
      setFromOrder(null);
      if (!o) return;
      setSupplier(String(o.supplier));
      setBranch(String(o.branch));
      setTransporter(o.transporter ? String(o.transporter) : "");
      setOrders([o.id]);
      setLines(o.lines.map((l) => newLine(l)));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromOrder, setup, companyId]);

  const places = (setup?.locations ?? []).filter((p) => String(p.branch) === branch);
  const defaultPlace = places.find((p) => p.purpose === "receiving") ?? places.find((p) => p.is_default);
  const newLine = (l: PendingLine): LineDraft => {
    const open = Math.max(num(l.pending), 0);
    return {
      key: nextKey++,
      info: l,
      received: open ? qty(open) : "",
      rejected: "",
      puts: [
        fitPacks(
          { key: nextKey++, location: defaultPlace ? String(defaultPlace.id) : "", batch: "", mfg: "", expiry: "", qty: "", pkgs: "", pkgType: "", pkgQty: "" },
          open,
        ),
      ],
    };
  };
  const offered = pending.filter((o) => !branch || String(o.branch) === branch);
  const pickSupplier = (v: string) => {
    setSupplier(v);
    setOrders([]);
    setLines([]);
  };
  // One warehouse for all the supplier's open orders: take it.
  useEffect(() => {
    if (branch || !pending.length) return;
    const all = new Set(pending.map((o) => o.branch));
    if (all.size === 1) setBranch(String(pending[0].branch));
  }, [pending, branch]);
  const tickOrder = (id: number, on: boolean) => {
    setOrders((os) => (on ? [...os, id] : os.filter((x) => x !== id)));
    if (!on) setLines((ls) => ls.filter((l) => l.info.order !== id));
    else {
      const o = pending.find((x) => x.id === id);
      if (o && o.transporter && !transporter) setTransporter(String(o.transporter));
    }
  };
  const getItems = () => {
    const have = new Set(lines.map((l) => l.info.order_line));
    const add = pending
      .filter((o) => orders.includes(o.id))
      .flatMap((o) => o.lines)
      .filter((l) => !have.has(l.order_line) && num(l.pending) > 0)
      .map(newLine);
    setLines([...lines, ...add]);
  };
  const changeLine = (key: number, patch: Partial<LineDraft>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  const changePut = (line: LineDraft, key: number, patch: Partial<PutDraft>) =>
    changeLine(line.key, { puts: line.puts.map((p) => (p.key === key ? withPack(p, patch) : p)) });
  const setReceived = (l: LineDraft, received: string) => {
    // A single bin follows the accepted quantity until the person splits it.
    const acc = Math.max(num(received) - num(l.rejected), 0);
    changeLine(l.key, { received, puts: l.puts.length === 1 ? [fitPacks(l.puts[0], round6(acc))] : l.puts });
  };
  const setRejected = (l: LineDraft, rejected: string) => {
    const acc = Math.max(num(l.received) - num(rejected), 0);
    changeLine(l.key, { rejected, puts: l.puts.length === 1 ? [fitPacks(l.puts[0], round6(acc))] : l.puts });
  };
  const addPut = (l: LineDraft) => {
    const rest = round6(accepted(l) - putTotal(l));
    const last = l.puts[l.puts.length - 1];
    changeLine(l.key, {
      puts: [
        ...l.puts,
        fitPacks(
          { key: nextKey++, location: "", batch: last?.batch ?? "", mfg: last?.mfg ?? "", expiry: last?.expiry ?? "", qty: "", pkgs: "", pkgType: last?.pkgType ?? "", pkgQty: last?.pkgQty ?? "" },
          rest > 0 ? rest : 0,
        ),
      ],
    });
  };

  const sup = setup?.suppliers.find((s) => String(s.id) === supplier);
  const br = setup?.branches.find((b) => String(b.id) === branch);
  const currency = pending.find((o) => orders.includes(o.id))?.currency ?? r?.currency ?? "INR";
  const toInr = currency === "INR" ? 1 : num(rate);
  const overs = lines.filter((l) => overBy(l) > 0);
  const anyQc = lines.some((l) => l.info.qc_required);
  const value = lines.reduce((s, l) => s + accepted(l) * num(l.info.rate) * toInr, 0);
  const acceptedTotal = lines.reduce((s, l) => s + accepted(l), 0);
  const allPut = lines.every((l) => Math.abs(putTotal(l) - accepted(l)) < 1e-9);
  const notReady = lines.filter((l) => binProblem(l)).length;

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
      receipt_date: date,
      orders,
      challan_no: challanNo,
      challan_date: challanDate || null,
      transporter: transporter ? Number(transporter) : null,
      lr_no: lr,
      vehicle_no: vehicle,
      eway_bill_no: eway,
      received_by: receivedBy ? Number(receivedBy) : null,
      exchange_rate: currency !== "INR" && rate ? rate : null,
      qc_cartons: qcCartons,
      qc_batch_print: qcPrint,
      qc_by: qcBy ? Number(qcBy) : null,
      notes,
      lines: lines.map((l) => ({
        order_line: l.info.order_line,
        received_qty: l.received || "0",
        rejected_qty: l.rejected || "0",
        putaways: l.puts
          .filter((p) => p.location || num(p.qty))
          .map((p) => ({
            location: Number(p.location) || 0,
            batch: p.batch.startsWith("b") ? Number(p.batch.slice(1)) : null,
            batch_number: p.batch.startsWith("n") ? p.batch.slice(1) : "",
            mfg_date: p.batch.startsWith("n") && p.mfg ? p.mfg : null,
            expiry_date: p.batch.startsWith("n") && p.expiry ? p.expiry : null,
            qty: p.qty || "0",
            packages: packed(p) ? Number(p.pkgs) : null,
            package_type: packed(p) ? p.pkgType : "",
            package_qty: packed(p) ? p.pkgQty : null,
          })),
      })),
      submit,
    };
    try {
      const saved = draftId
        ? await api<GoodsReceipt>(`v1/goods-receipts/${draftId}/`, body, "PATCH")
        : await api<GoodsReceipt>(`v1/companies/${companyId}/goods-receipts/`, body);
      announceSaved("goods_receipt_saved", { id: saved.id, name: saved.number || "Draft" });
      if (submit) {
        window.location.hash = `${base(companyId)}?view=${saved.id}`;
        return;
      }
      if (!draftId) {
        setDraftId(saved.id);
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
  /** Bins must add up to the accepted quantity before Submit; the server refuses it too. */
  const submit = () => {
    const wrong = lines.filter((l) => binProblem(l));
    if (wrong.length) return setBinCheck(wrong);
    save(true);
  };
  // Masters › People ticked "Stores"; a disabled one stays only where already picked.
  const peopleFor = (picked: string) =>
    (setup?.stores_people ?? [])
      .filter((p) => p.is_active || String(p.id) === picked)
      .map((p) => ({ value: String(p.id), label: p.name }));
  const newPerson = props.mayAddPeople ? creatable("sales_person", "sales-people", refreshSetup, "as=stores") : undefined;
  const noPeople = setup !== null && setup.stores_people.length === 0;
  const goToLine = (l: LineDraft) => {
    setBinCheck(null);
    setOpenBins(l.key);
    window.setTimeout(() => document.getElementById(`grn-line-${l.key}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };

  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId && !r ? "Edit Goods Receipt" : props.title}
        sub={savedAt ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.` : undefined}
        crumbs={[{ label: "Entry › Purchase › Goods Receipt", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu label="Print" items={printMenu(companyId, draftId)} disabled={!draftId} title={draftId ? undefined : "Save the receipt first"} />
            <button type="submit" form="grn-form" className={setup?.can_submit ? "secondary" : undefined} disabled={busy}>
              Save
            </button>
            {setup?.can_submit && (
              <button type="button" disabled={busy} onClick={submit}>
                Submit
              </button>
            )}
          </>
        }
      />
      {binCheck && <BinCheckPopup lines={binCheck} all={lines} onGo={goToLine} onClose={() => setBinCheck(null)} />}
      <form id="grn-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{sup?.name ?? "Pick a supplier"}</p>
            <p className="item-sub">
              <b>{r?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              {br && <span className="tag">{br.name}</span>}
              {orders.length > 0 && <span className="tag">Against {pending.filter((o) => orders.includes(o.id)).map((o) => o.number).join(", ") || r?.order_numbers.join(", ")}</span>}
            </p>
          </div>
          <ErrorNote error={error} />
          <Fold title="Supplier and Receipt" open summary={sup ? `${showDate(date)} · ${br?.name ?? ""}` : ""}>
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
                  placeholder="Suppliers with open orders…"
                  options={[...(setup?.suppliers ?? []), ...(r && !setup?.suppliers.some((s) => s.id === r.supplier) ? [{ id: r.supplier, name: r.supplier_name }] : [])].map((s) => ({
                    value: String(s.id),
                    label: s.name,
                  }))}
                />
              </label>
              <label>
                <span className="req">Receipt Date</span>
                <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
              </label>
              <label>
                <span className="req">Receiving Warehouse</span>
                <Combobox required value={branch} onChange={setBranch} options={(setup?.branches ?? []).map((b) => ({ value: String(b.id), label: b.name }))} />
                <span className="small">Our branch the goods came into; bins are chosen on each line</span>
              </label>
              <label>
                Supplier's Challan / Invoice No
                <input value={challanNo} maxLength={40} onChange={(e) => setChallanNo(e.target.value)} />
              </label>
              <label>
                Challan / Invoice Date
                <input type="date" value={challanDate} max={date} onChange={(e) => setChallanDate(e.target.value)} />
              </label>
              <label>
                Transporter
                <Combobox
                  value={transporter}
                  onChange={setTransporter}
                  empty="By Supplier"
                  options={(setup?.transporters ?? []).map((t) => ({ value: String(t.id), label: t.name }))}
                />
              </label>
              <label>
                LR / Docket No
                <input value={lr} maxLength={40} onChange={(e) => setLr(e.target.value)} />
              </label>
              <label>
                Vehicle No
                <input value={vehicle} maxLength={20} onChange={(e) => setVehicle(e.target.value.toUpperCase())} />
              </label>
              <label>
                E-way Bill No
                <input value={eway} maxLength={20} onChange={(e) => setEway(e.target.value)} />
              </label>
              <label>
                Received By
                <Combobox value={receivedBy} onChange={setReceivedBy} empty="Not given" options={peopleFor(receivedBy)} create={newPerson} />
                {noPeople && <span className="small">No Stores people yet. Add them in Masters › People.</span>}
              </label>
              {currency !== "INR" && (
                <label>
                  <span className="req">Exchange Rate</span>
                  <input inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} placeholder={`Rupees per ${currency}`} />
                  <span className="small">The orders are in {currency}; the stock is valued in rupees at this rate</span>
                </label>
              )}
            </div>
            <div className="grn-orders">
              <div className="fact-label">Purchase Orders</div>
              {!supplier && <p className="small">Pick the supplier: its open orders are listed here.</p>}
              {supplier && offered.length === 0 && <p className="small">This supplier has no open orders{br ? ` for ${br.name}` : ""}.</p>}
              {offered.map((o) => {
                const left = o.lines.filter((l) => num(l.pending) > 0).length;
                return (
                  <label key={o.id} className="tick">
                    <input type="checkbox" checked={orders.includes(o.id)} onChange={(e) => tickOrder(o.id, e.target.checked)} />
                    <b>{o.number}</b> <span className="small">{`${shortDate(o.order_date)} · ${left} ${left === 1 ? "item" : "items"} pending · ${o.branch_name}`}</span>
                  </label>
                );
              })}
              {orders.length > 0 && (
                <button type="button" className="secondary" onClick={getItems}>
                  Get items
                </button>
              )}
              <p className="small">"Get items" brings in what is still pending on the ticked orders.</p>
            </div>
          </Fold>
          <Fold
            title="Items"
            open
            summary={
              lines.length
                ? `${lines.length} ${lines.length === 1 ? "item" : "items"} · ${qty(round6(acceptedTotal))} accepted${
                    notReady ? ` · ${notReady} ${notReady === 1 ? "line doesn't" : "lines don't"} add up` : allPut ? " · all put away" : ""
                  }`
                : ""
            }
          >
            {lines.length === 0 && <p className="small">Tick the purchase orders above and click "Get items".</p>}
            {lines.length > 0 && (
              <div className="table-scroll">
                <table className="grid po-lines grn-lines">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item</th>
                      <th className="num">Ordered</th>
                      <th className="num">Earlier</th>
                      <th className="num">Pending</th>
                      <th className="num">Received</th>
                      <th className="num">Rejected</th>
                      <th className="num">Accepted</th>
                      <th>Unit</th>
                      <th />
                    </tr>
                  </thead>
                  {lines.map((l, i) => (
                    <tbody key={l.key} id={`grn-line-${l.key}`} className={overBy(l) > 0 ? "grn-over" : undefined}>
                      <tr>
                        <td>{i + 1}</td>
                        <td className="po-item">
                          <b>{l.info.item_name}</b> <span className="small-inline">{l.info.item_number}</span>
                          <span className="small">
                            {[`${l.info.order_number} line ${l.info.order_position}`, `Rate ${currency === "INR" ? "₹" : `${currency} `}${money(l.info.rate)}`, l.info.batch_tracked && "batch-tracked", l.info.qc_required && "QC required"]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </td>
                        <td className="num">{qty(l.info.ordered)}</td>
                        <td className="num">{qty(l.info.earlier)}</td>
                        <td className="num">{qty(Math.max(num(l.info.ordered) - num(l.info.earlier), 0))}</td>
                        <td className="num">
                          <input inputMode="decimal" aria-label={`Received ${i + 1}`} value={l.received} onChange={(e) => setReceived(l, e.target.value)} />
                        </td>
                        <td className="num">
                          <input inputMode="decimal" aria-label={`Rejected ${i + 1}`} value={l.rejected} placeholder="0" onChange={(e) => setRejected(l, e.target.value)} />
                        </td>
                        <td className="num">
                          <b>{qty(round6(accepted(l)))}</b>
                        </td>
                        <td>{l.info.unit_name}</td>
                        <td>
                          <button type="button" className="link danger" title="Leave this item out" onClick={() => setLines(lines.filter((x) => x.key !== l.key))}>
                            ×
                          </button>
                        </td>
                      </tr>
                      {accepted(l) > 0 && (
                        <tr className="grn-put-row">
                          <td />
                          <td colSpan={9}>
                            {openBins !== l.key ? (
                              <BinsLine line={l} batches={batches[l.info.item] ?? []} packageTypes={setup?.package_types ?? []} onEdit={() => setOpenBins(l.key)} />
                            ) : (
                            <PutawayBox
                              onDone={() => setOpenBins(null)}
                              line={l}
                              places={places}
                              batches={batches[l.info.item] ?? []}
                              packageTypes={setup?.package_types ?? []}
                              onChange={(key, patch) => changePut(l, key, patch)}
                              onAdd={() => addPut(l)}
                              onRemove={(key) => changeLine(l.key, { puts: l.puts.filter((p) => p.key !== key) })}
                            />
                            )}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  ))}
                </table>
              </div>
            )}
            {overs.map((l) => (
              <p key={l.key} className="use-note">
                ⚠ <b>{l.info.item_name}</b>: {qty(round6(overBy(l)))} {l.info.unit_name} more than ordered on {l.info.order_number} ({qty(round6(num(l.info.earlier) + accepted(l)))} against{" "}
                {qty(l.info.ordered)}). It is accepted; on Submit the Purchase team and the Owner get an alert, and the order's activity notes it.
              </p>
            ))}
            <p className="small">
              Put all of each line's accepted quantity away before Submit: click "Edit bins" on a line, then "Done" to fold it again. "Bin" lists the bins and areas of the receiving warehouse (Masters › Warehouses). "Batch No" lists the item's batches; type a
              new number and pick 'New batch "…"' to make it here, with its Mfg Date and Expiry (Expiry fills from the item's best-before when left blank). New batches go into the Batches master on
              Submit.
            </p>
          </Fold>
          <Fold title="Quality Check" open={anyQc || !!(qcCartons || qcPrint)} summary={anyQc ? 'For items marked "QC required"' : "Optional"}>
            <div className="item-fields">
              <label>
                Cartons (CFC) Condition
                <Combobox value={qcCartons} onChange={setQcCartons} empty="Not checked" options={CARTONS} />
              </label>
              <label>
                Batch Code Printed on Packs
                <Combobox value={qcPrint} onChange={setQcPrint} empty="Not checked" options={PRINTS} />
              </label>
              <label>
                Checked By
                <Combobox value={qcBy} onChange={setQcBy} empty="Not given" options={peopleFor(qcBy)} create={newPerson} />
              </label>
            </div>
            <p className="small">New batches of items marked "QC required" go into stock as "Quarantine" and can be released on the Batches screen.</p>
          </Fold>
          <Fold title="Notes" open={!!notes}>
            <label>
              Internal Note
              <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
          </Fold>
          <Attachments type="goods_receipt" id={draftId} />
        </div>
        <div className="doc-foot">
          <SidePanel title="Against Purchase Order">
            {lines.length ? (
              <SideRows rows={lines.map((l) => [l.info.item_name, `${qty(round6(num(l.info.earlier) + accepted(l)))} of ${qty(l.info.ordered)} ${l.info.unit_name}`])} />
            ) : (
              <p className="small">Nothing received yet.</p>
            )}
          </SidePanel>
          <SidePanel title="Stock Value (at order rates)">
            <SideRows rows={[...lines.map((l): [string, string] => [l.info.item_name, money(accepted(l) * num(l.info.rate) * toInr)]), ["Total ₹", money(value)]]} />
            <p className="small">The order's charges marked "Add to Stock Cost" (freight, packing…) are added on Submit, by quantity or value. The supplier's bill (Purchase Invoice) settles the final cost.</p>
          </SidePanel>
          <SidePanel title="On Submit">
            <SideRows
              rows={[
                ["Stock (Inventories)", `Dr ${money(value)}`],
                ["Goods Received but Bills not Received", `Cr ${money(value)}`],
              ]}
            />
            <p className="small">One stock entry per bin and batch, each a FIFO lot. No GST is booked here; it comes with the Purchase Invoice.</p>
          </SidePanel>
        </div>
      </form>
    </section>
  );
}

function PutawayBox(props: {
  onDone: () => void;
  line: LineDraft;
  places: Place[];
  batches: BatchRow[];
  packageTypes: [string, string][];
  onChange: (key: number, patch: Partial<PutDraft>) => void;
  onAdd: () => void;
  onRemove: (key: number) => void;
}) {
  const { line: l } = props;
  const acc = accepted(l);
  const done = putTotal(l);
  const unit = l.info.unit_name;
  const typedNew = [...new Set(l.puts.filter((p) => p.batch.startsWith("n")).map((p) => p.batch.slice(1)))];
  const batchOptions = [
    ...props.batches.map((b) => ({ value: `b${b.id}`, label: b.number, hint: [b.expiry_date && `exp ${shortDate(b.expiry_date)}`, b.status_label].filter(Boolean).join(" · ") })),
    ...typedNew.filter((n) => !props.batches.some((b) => b.number.toLowerCase() === n.toLowerCase())).map((n) => ({ value: `n${n}`, label: n, hint: "New batch" })),
  ];
  const placeOptions = props.places.map((p) => ({ value: String(p.id), label: p.name, hint: p.kind === "area" ? "Area" : "Bin" }));
  const ok = Math.abs(done - acc) < 1e-9;
  const typeOptions = props.packageTypes.map(([value, label]) => ({ value, label }));
  const count = l.puts.reduce((s, p) => s + (packed(p) ? num(p.pkgs) : 0), 0);
  const kinds = new Set(l.puts.filter(packed).map((p) => p.pkgType));
  const kindName = kinds.size === 1 ? (props.packageTypes.find(([v]) => kinds.has(v))?.[1] ?? "package").toLowerCase() : "package";
  return (
    <div className="grn-put">
      <div className="grn-put-head">
        <b>Put away into bins</b> <span className="small-inline">· split the accepted quantity across bins{l.info.batch_tracked ? ", batches" : ""} and packages</span>
      </div>
      <table className="grid">
        <thead>
          <tr>
            <th>Bin</th>
            {l.info.batch_tracked && (
              <>
                <th>Batch No</th>
                <th>Mfg Date</th>
                <th>Expiry</th>
              </>
            )}
            <th className="num">Packages</th>
            <th>Package Type</th>
            <th className="num">Qty per Package</th>
            <th className="num">Qty ({unit})</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {l.puts.map((p, n) => {
            const existing = p.batch.startsWith("b") ? props.batches.find((b) => `b${b.id}` === p.batch) : undefined;
            const isNew = p.batch.startsWith("n");
            return (
              <tr key={p.key}>
                <td className="grn-bin">
                  <Combobox value={p.location} onChange={(v) => props.onChange(p.key, { location: v })} ariaLabel={`Bin ${n + 1}`} placeholder="Bin or area…" options={placeOptions} />
                </td>
                {l.info.batch_tracked && (
                  <>
                    <td className="grn-batch">
                      <Combobox
                        value={p.batch}
                        onChange={(v) => props.onChange(p.key, { batch: v })}
                        ariaLabel={`Batch ${n + 1}`}
                        placeholder="Pick or type a new one…"
                        options={batchOptions}
                        createHere={{ label: "New batch", pick: (typed) => props.onChange(p.key, { batch: `n${typed}` }) }}
                      />
                      {isNew && <span className="tag">New batch</span>}
                    </td>
                    <td>{isNew ? <input type="date" aria-label={`Mfg date ${n + 1}`} value={p.mfg} onChange={(e) => props.onChange(p.key, { mfg: e.target.value })} /> : shortDate(existing?.mfg_date ?? null)}</td>
                    <td>
                      {isNew ? (
                        <input type="date" aria-label={`Expiry ${n + 1}`} value={p.expiry} min={p.mfg || undefined} onChange={(e) => props.onChange(p.key, { expiry: e.target.value })} />
                      ) : (
                        shortDate(existing?.expiry_date ?? null)
                      )}
                    </td>
                  </>
                )}
                <td className="num grn-pk-n">
                  <input inputMode="numeric" aria-label={`Packages ${n + 1}`} value={p.pkgs} placeholder="Loose" onChange={(e) => props.onChange(p.key, { pkgs: e.target.value.replace(/\D/g, "") })} />
                </td>
                <td className="grn-pk-type">
                  <Combobox value={p.pkgType} onChange={(v) => props.onChange(p.key, { pkgType: v })} ariaLabel={`Package type ${n + 1}`} empty="None" options={typeOptions} />
                </td>
                <td className="num">
                  <input inputMode="decimal" aria-label={`Qty per package ${n + 1}`} value={p.pkgQty} onChange={(e) => props.onChange(p.key, { pkgQty: e.target.value })} />
                </td>
                <td className="num">
                  {packed(p) ? (
                    <b>{p.qty}</b>
                  ) : (
                    <input inputMode="decimal" aria-label={`Qty ${n + 1}`} value={p.qty} onChange={(e) => props.onChange(p.key, { qty: e.target.value })} />
                  )}
                </td>
                <td>
                  {l.puts.length > 1 && (
                    <button type="button" className="link danger" title="Remove this bin" onClick={() => props.onRemove(p.key)}>
                      ×
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="grn-put-foot">
        <button type="button" className="link" onClick={props.onAdd}>
          + Add bin
        </button>
        <span className={ok ? "ok-note" : "bad-note"}>
          {ok ? "✓ " : ""}
          {qty(round6(done))} of {qty(round6(acc))} {unit} put away
          {!ok && ` · ${putGap(l)}`}
          {count > 0 && ` · ${count} ${kindName}${count === 1 ? "" : "s"}`}
          <button type="button" className="grn-done" onClick={props.onDone}>
            Done
          </button>
        </span>
      </div>
    </div>
  );
}

/** A line's bins folded to one line: how much is put away, and where (Sidharth, 2026-11-17). */
function BinsLine(props: { line: LineDraft; batches: BatchRow[]; packageTypes: [string, string][]; onEdit: () => void }) {
  const { line: l } = props;
  const unit = l.info.unit_name;
  const puts = l.puts.filter((p) => num(p.qty));
  const problem = binProblem(l);
  const done = putTotal(l);
  const of = `${qty(round6(done))} of ${qty(round6(accepted(l)))} ${unit}`;
  const bins = new Set(puts.map((p) => p.location).filter(Boolean)).size;
  const batchNames = [...new Set(puts.map((p) => (p.batch.startsWith("b") ? props.batches.find((b) => `b${b.id}` === p.batch)?.number : p.batch.slice(1))).filter(Boolean))];
  const packs = puts.filter(packed);
  const count = packs.reduce((s, p) => s + num(p.pkgs), 0);
  const kinds = new Set(packs.map((p) => p.pkgType));
  const kind = kinds.size === 1 ? (props.packageTypes.find(([v]) => kinds.has(v))?.[1] ?? "package").toLowerCase() : "package";
  const sizes = new Set(packs.map((p) => num(p.pkgQty)));
  const facts = [
    bins && `${bins} ${bins === 1 ? "bin" : "bins"}`,
    batchNames.length && (batchNames.length > 2 ? `${batchNames.length} batches` : batchNames.join(", ")),
    count && `${count} ${kind}${count === 1 ? "" : "s"}${sizes.size === 1 ? ` × ${qty([...sizes][0])}` : ""}`,
  ].filter(Boolean);
  const status = !done ? `Bins: none yet · ${qty(round6(accepted(l)))} ${unit} to put away` : problem ? `Bins: ${of} · ${problem}` : `✓ Bins: ${of}`;
  return (
    <div className={problem ? "grn-bins-line bad" : "grn-bins-line"}>
      <span className={problem ? "bad-note" : "ok-note"}>{status}</span>
      <span className="small-inline">
        {facts.join(" · ")}
        <button type="button" className="link" onClick={props.onEdit}>
          Edit bins
        </button>
      </span>
    </div>
  );
}

/** Submit with bins that do not add up: one row per line, with a way to get to it (Sidharth, 2026-11-17). */
function BinCheckPopup(props: { lines: LineDraft[]; all: LineDraft[]; onGo: (l: LineDraft) => void; onClose: () => void }) {
  const noBatch = props.lines.some((l) => binProblem(l) === "Batch No missing");
  return (
    <div className="popup-back" role="presentation">
      <div className="popup grn-check" role="dialog" aria-modal="true" aria-label="The bins don't add up">
        <h3>Can't submit yet: the bins don't add up</h3>
        <p>
          Each line's bins must hold exactly its "Accepted" quantity{noBatch ? ', and each bin of a batch-tracked item needs its "Batch No"' : ""}.
        </p>
        <table className="grid">
          <thead>
            <tr>
              <th>Line</th>
              <th>Item</th>
              <th className="num">Accepted</th>
              <th className="num">In Bins</th>
              <th className="num">Difference</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {props.lines.map((l) => (
              <tr key={l.key}>
                <td>{props.all.indexOf(l) + 1}</td>
                <td>{l.info.item_name}</td>
                <td className="num">
                  {qty(round6(accepted(l)))} {l.info.unit_name}
                </td>
                <td className="num">
                  {qty(round6(putTotal(l)))} {l.info.unit_name}
                </td>
                <td className="num bad-note">{binProblem(l)}</td>
                <td>
                  <button type="button" className="link" onClick={() => props.onGo(l)}>
                    Go to line
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small">Fix the bin quantities, or the "Received" or "Rejected" quantity if that was wrong, then Submit again. Nothing has been submitted; "Save" keeps the draft.</p>
        <div className="popup-actions">
          <button type="button" onClick={props.onClose}>
            OK
          </button>
        </div>
      </div>
    </div>
  );
}

/** After Submit every bag or box has its own number, for stickers and tracing (Sidharth, 2026-11-15). */
function PackagesBox({ rows, ticked, onTick }: { rows: PackageRow[]; ticked: number[]; onTick: (ids: number[]) => void }) {
  const kinds = new Set(rows.map((k) => k.kind_label));
  const name = kinds.size === 1 ? [...kinds][0].toLowerCase() : "package";
  const units = new Set(rows.map((k) => k.unit_name));
  const total = rows.reduce((s, k) => s + Number(k.qty), 0);
  return (
    <Fold title="Packages" open summary={`${rows.length} ${name}${rows.length === 1 ? "" : "s"}${units.size === 1 ? ` · ${qty(round6(total))} ${[...units][0]}` : ""}`}>
      <div className="table-scroll">
        <table className="grid grn-packages">
          <thead>
            <tr>
              <th className="no-print">
                <input type="checkbox" aria-label="Tick all bags" checked={ticked.length === rows.length} onChange={(e) => onTick(e.target.checked ? rows.map((k) => k.id) : [])} />
              </th>
              <th>Package No</th>
              <th>Type</th>
              <th>Item</th>
              <th>Batch</th>
              <th>Bin</th>
              <th className="num">Received</th>
              <th className="num">Left</th>
              <th>Unit</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((k) => (
              <tr key={k.id}>
                <td className="no-print">
                  <input
                    type="checkbox"
                    aria-label={`Tick ${k.number}`}
                    checked={ticked.includes(k.id)}
                    onChange={(e) => onTick(e.target.checked ? [...ticked, k.id] : ticked.filter((x) => x !== k.id))}
                  />
                </td>
                <td>
                  <b>{k.number}</b> <span className="small-inline">{k.position} of {k.of_count}</span>
                </td>
                <td>{k.kind_label}</td>
                <td>{k.item_name}</td>
                <td>{k.batch}</td>
                <td>{k.location_name}</td>
                <td className="num">{qty(k.qty)}</td>
                <td className="num">{qty(k.left_qty)}</td>
                <td>{k.unit_name}</td>
                <td>
                  <span className={k.status === "in_stock" ? "pill on" : "pill"}>{k.status_label}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small">
        Each bag or box has its own number, printed with a barcode on its label ("Print ▾", then "Bag Labels"). Tick bags to print only their labels, for example to replace a torn one{ticked.length ? ` (${ticked.length} ticked)` : ""}. When stock is issued, the bags taken will be picked by these numbers.
      </p>
    </Fold>
  );
}

// The receipt's own page (read only) -------------------------------------------------

function ReceiptView({ companyId, id }: { companyId: number; id: number }) {
  const { setup } = useSetup(companyId);
  const [r, setR] = useState<GoodsReceipt | null>(null);
  const [postings, setPostings] = useState<Postings | null>(null);
  const [error, setError] = useState<unknown>("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState(0); // bumps the Activity after a file is added or removed
  const [ticked, setTicked] = useState<number[]>([]); // bags picked for labels
  const reload = useCallback(() => {
    api<GoodsReceipt>(`v1/goods-receipts/${id}/`).then(setR, setError);
    api<Postings>(`v1/postings/?voucher_type=goods_receipt&voucher_id=${id}`).then(setPostings, () => setPostings(null));
  }, [id]);
  useEffect(reload, [reload]);
  useCreated("goods_receipt_saved", (c) => {
    if (c.id === id) reload();
  });
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const act = async (path: string, body: object = {}) => {
    setError("");
    try {
      const done = await api<GoodsReceipt>(`v1/goods-receipts/${id}/${path}/`, body);
      setR(done);
      setCancelling(false);
      announceSaved("goods_receipt_saved", { id, name: done.number || "Draft" });
      api<Postings>(`v1/postings/?voucher_type=goods_receipt&voucher_id=${id}`).then(setPostings, () => setPostings(null));
    } catch (err) {
      setError(err);
    }
  };
  if (!r)
    return (
      <section className="page">
        <PageHeader title="Goods Receipt" crumbs={[{ label: "Entry › Purchase › Goods Receipt", href: base(companyId) }]} />
        <ErrorNote error={error} />
      </section>
    );
  const draft = r.status === "draft";
  const sym = r.currency === "INR" ? "₹" : `${r.currency} `;
  const gl = postings?.gl.filter((g) => !g.is_reversal) ?? [];
  return (
    <section className="page">
      <PageHeader
        title={r.number ? `Goods Receipt ${r.number}` : "Goods Receipt (draft)"}
        sub={
          r.number && r.submitted_at
            ? `Submitted as ${r.number} on ${showDate(r.submitted_at.slice(0, 10))} at ${new Date(r.submitted_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`
            : undefined
        }
        crumbs={[{ label: "Entry › Purchase › Goods Receipt", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {draft && setup?.can_create && (
              <button type="button" className="link" onClick={() => openTab(`${base(companyId)}?form=${r.id}`)}>
                Edit
              </button>
            )}
            {setup?.can_cancel && r.status !== "cancelled" && !cancelling && (
              <button type="button" className="link danger" onClick={() => setCancelling(true)}>
                Cancel receipt
              </button>
            )}
            <ActionsMenu label="Print" items={printMenu(companyId, r.id, { submitted: r.status === "submitted", bags: ticked })} />
            {draft && setup?.can_submit && (
              <button type="button" onClick={() => act("submit")}>
                Submit
              </button>
            )}
            {r.status === "submitted" && <ActionsMenu label="Create" main items={createFromReceipt(companyId, r.id)} />}
          </>
        }
      />
      <div className="doc-page">
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{r.supplier_name}</p>
            <p className="item-sub">
              <b>{r.number || "Number given on Submit"}</b>
              <span className={pillClass(r.status)}>{r.status_label}</span>
              <span className="tag">{r.branch_name}</span>
              {r.order_numbers.length > 0 && <span className="tag">Against {r.order_numbers.join(", ")}</span>}
            </p>
          </div>
          {r.status === "cancelled" && <p className="use-note">Cancelled: {r.cancel_reason}</p>}
          {cancelling && (
            <div className="use-note no-print">
              <label>
                <b>Why is this receipt cancelled?</b>
                <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Entered against the wrong supplier" />
              </label>
              <p className="small">The stock and the books entries are reversed, and the orders show the goods as pending again.</p>
              <div className="buttons">
                <button type="button" className="link" onClick={() => setCancelling(false)}>
                  Keep the receipt
                </button>
                <button type="button" className="link danger" onClick={() => act("cancel", { reason })}>
                  Cancel receipt
                </button>
              </div>
            </div>
          )}
          <ErrorNote error={error} />
          <Fold title="Supplier and Receipt" open>
            <dl className="kv">
              {(
                [
                  ["Supplier", r.supplier_name],
                  ["Receipt Date", showDate(r.receipt_date)],
                  ["Receiving Warehouse", r.branch_name],
                  ["Purchase Orders", r.order_numbers.join(", ")],
                  ["Supplier's Challan / Invoice No", r.challan_no],
                  ["Challan / Invoice Date", showDate(r.challan_date)],
                  ["Transporter", r.transporter_name],
                  ["LR / Docket No", r.lr_no],
                  ["Vehicle No", r.vehicle_no],
                  ["E-way Bill No", r.eway_bill_no],
                  ["Received By", r.received_by_name],
                  ["Exchange Rate", r.currency !== "INR" && r.exchange_rate ? `₹${Number(r.exchange_rate)} per ${r.currency}` : ""],
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
          <Fold title="Items" open>
            <div className="table-scroll">
              <table className="grid po-lines grn-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item</th>
                    <th className="num">Ordered</th>
                    <th className="num">Earlier</th>
                    <th className="num">Received</th>
                    <th className="num">Rejected</th>
                    <th className="num">Accepted</th>
                    <th>Unit</th>
                    <th className="num">Stock Value ₹</th>
                  </tr>
                </thead>
                {(r.lines ?? []).map((l, i) => (
                  <tbody key={l.order_line}>
                    <tr>
                      <td>{i + 1}</td>
                      <td className="po-item">
                        <b>{l.item_name}</b> <span className="small-inline">{l.item_number}</span>
                        <span className="small">
                          {`${l.order_number} line ${l.order_position} · Rate ${sym}${money(l.rate)}`}
                          {Number(l.charges_value) ? ` · charges ₹${money(l.charges_value)}` : ""}
                        </span>
                      </td>
                      <td className="num">{qty(l.ordered)}</td>
                      <td className="num">{qty(l.earlier)}</td>
                      <td className="num">{qty(l.received_qty)}</td>
                      <td className="num">{qty(l.rejected_qty)}</td>
                      <td className="num">
                        <b>{qty(l.accepted_qty)}</b>
                      </td>
                      <td>{l.unit_name}</td>
                      <td className="num">{r.status === "draft" ? "" : money(l.value)}</td>
                    </tr>
                    {l.putaways.length > 0 && (
                      <tr className="grn-put-row">
                        <td />
                        <td colSpan={8}>
                          <div className="grn-put">
                            <table className="grid">
                              <thead>
                                <tr>
                                  <th>Bin</th>
                                  {l.batch_tracked && (
                                    <>
                                      <th>Batch No</th>
                                      <th>Mfg Date</th>
                                      <th>Expiry</th>
                                    </>
                                  )}
                                  <th>Packages</th>
                                  <th className="num">Qty ({l.unit_name})</th>
                                </tr>
                              </thead>
                              <tbody>
                                {l.putaways.map((p, n) => (
                                  <tr key={n}>
                                    <td>{p.location_name}</td>
                                    {l.batch_tracked && (
                                      <>
                                        <td>
                                          {p.batch_number} {p.new_batch && <span className="tag">New batch</span>}
                                        </td>
                                        <td>{shortDate(p.mfg_date)}</td>
                                        <td>{shortDate(p.expiry_date)}</td>
                                      </>
                                    )}
                                    <td>{p.packages ? `${p.packages} ${p.package_type_label}${p.packages === 1 ? "" : "s"} of ${qty(p.package_qty ?? 0)} ${l.unit_name}` : "Loose"}</td>
                                    <td className="num">{qty(p.qty)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                ))}
                {r.status !== "draft" && (
                  <tfoot>
                    <tr>
                      <td colSpan={8}>Total</td>
                      <td className="num">{money(r.stock_value)}</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </Fold>
          {!!r.packages?.length && <PackagesBox rows={r.packages} ticked={ticked} onTick={setTicked} />}
          {(r.qc_cartons || r.qc_batch_print || r.qc_by_name) && (
            <Fold title="Quality Check" open>
              <dl className="kv">
                {(
                  [
                    ["Cartons (CFC) Condition", CARTONS.find((c) => c.value === r.qc_cartons)?.label ?? ""],
                    ["Batch Code Printed on Packs", PRINTS.find((c) => c.value === r.qc_batch_print)?.label ?? ""],
                    ["Checked By", r.qc_by_name],
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
          )}
          {r.notes && (
            <Fold title="Notes" open>
              <p className="pre">{r.notes}</p>
            </Fold>
          )}
          <Attachments type="goods_receipt" id={r.id} onChange={() => setFiles((n) => n + 1)} />
        </div>
        <div className="doc-foot">
          <SidePanel title="Postings">
            {gl.length ? (
              <SideRows rows={gl.map((g): [string, string] => [g.ledger_name, Number(g.debit) ? `Dr ${money(g.debit)}` : `Cr ${money(g.credit)}`])} />
            ) : (
              <p className="small">{draft ? "Nothing is posted until Submit." : "Nothing posted."}</p>
            )}
            {r.status === "cancelled" && postings?.gl.some((g) => g.is_reversal) && <p className="small">Reversed when the receipt was cancelled.</p>}
            {!!postings?.stock.length && (
              <p className="small">
                Stock:{" "}
                {postings.stock
                  .filter((m) => !m.is_reversal)
                  .map((m) => `${qty(m.qty)} ${m.item_name} in ${m.location}${m.batch ? ` (batch ${m.batch})` : ""}`)
                  .join("; ")}
              </p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="goods_receipt" id={r.id} stamp={JSON.stringify(r) + files} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}
