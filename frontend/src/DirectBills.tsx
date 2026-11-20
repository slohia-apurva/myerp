import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { DocSide, keptDraft } from "./Attachments";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { Locked } from "./Lock";
import { money } from "./Companies";
import { announceSaved, closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu } from "./Exchange";
import { Fold } from "./Master";
import { EntriesBox, Totals, type Entry } from "./PurchaseInvoices";
import { TdsBox, type TdsInfo } from "./Tds";
import { useReturns } from "./Refresh";

/** Purchase Invoice of type "Without goods receipt" (Sidharth, 2026-11-16, preview 82): services
 * and goods not kept in stock. Each line picks an item, booked to the item's "Expense Account"
 * (Masters › Items), or an expense ledger, booked to itself. No stock moves; fixed assets are not
 * bought here. Saved through buying/direct_bills.py and listed with the purchase invoices. */

export type DirectLine = {
  id?: number;
  item: number | null;
  ledger: number | null;
  name: string;
  what: string;
  description: string;
  hsn: string;
  unit: number | null;
  unit_name: string;
  qty: string;
  rate: string;
  taxable: string;
  gst_rate: string;
  cgst: string;
  sgst: string;
  igst: string;
  amount: string;
  booked_to_name: string;
};
export type DirectBill = {
  id: number;
  number: string;
  supplier: number;
  supplier_name: string;
  branch: number;
  bill_no: string;
  bill_date: string | null;
  posting_date: string | null;
  credit_term: number | null;
  bill_total: string | null;
  notes: string;
  interstate: boolean;
  expense_lines?: DirectLine[];
  entries?: Entry[];
  dues?: { due_date: string; amount: string }[];
  total: string;
  tds?: TdsInfo;
};
type Setup = {
  suppliers: { id: number; name: string; credit_term: number | null; state_code: string; is_active: boolean }[];
  branches: { id: number; name: string; state_code: string; is_active: boolean }[];
};
type Lists = {
  items: { id: number; name: string; service: boolean; hsn: string; unit: number; unit_name: string; gst_rate: string | null; booked_to_name: string }[];
  ledgers: { id: number; name: string }[];
  units: { id: number; name: string }[];
};
type Row = { key: number; pick: string; description: string; hsn: string; unit: string; qty: string; rate: string; gst_rate: string };

const base = (companyId: number) => `#/companies/${companyId}/purchase-invoices`;
const num = (v: string | null | undefined) => Number(v) || 0;
const r2 = (n: number) => Math.round(n * 100) / 100;
let nextKey = 1;
const blank = (): Row => ({ key: nextKey++, pick: "", description: "", hsn: "", unit: "", qty: "1", rate: "", gst_rate: "" });
const printItems = [
  { label: "Purchase Invoice", onClick: () => window.print() },
  { label: "Download PDF", onClick: () => window.print() },
];

/** The "Bill Type" picker at the top of a new purchase invoice: switching opens the other form. */
export function BillTypePicker(props: { companyId: number; direct: boolean; locked: boolean }) {
  return (
    <label>
      <span className="req">Bill Type</span>
      {/* Once saved the type is fixed, but it still reads as a dropdown: arrow faded, tagged "Locked" (as other locked pickers). */}
      <Locked on={props.locked}>
        <Combobox
          value={props.direct ? "direct" : "regular"}
          options={[
            { value: "regular", label: "Against goods receipts" },
            { value: "direct", label: "Without goods receipt (services, goods not kept in stock)" },
          ]}
          onChange={(v) => {
            if (props.locked || v === (props.direct ? "direct" : "regular")) return;
            window.location.hash = `${base(props.companyId)}?form=new${v === "direct" ? "&type=direct" : ""}`;
          }}
        />
      </Locked>
      <span className="small">{props.locked ? "Fixed once saved" : "Against goods receipts, Without goods receipt"}</span>
    </label>
  );
}

export function DirectFormTab(props: { companyId: number; bill?: DirectBill; canSubmit: boolean }) {
  const { companyId, bill } = props;
  const [setup, setSetup] = useState<Setup | null>(null);
  const [lists, setLists] = useState<Lists | null>(null);
  const [terms, setTerms] = useState<{ id: number; name: string }[]>([]);
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  useEffect(() => {
    api<Setup>(`v1/companies/${companyId}/purchase-orders/setup/`).then(setSetup, () => setSetup(null));
    api<Lists>(`v1/companies/${companyId}/direct-bills/setup/`).then(setLists, () => setLists(null));
    api<{ id: number; name: string }[]>("v1/credit-terms/").then(setTerms, () => setTerms([]));
  }, [companyId, visits]);
  const [supplier, setSupplier] = useState(String(bill?.supplier ?? ""));
  const [branch, setBranch] = useState(String(bill?.branch ?? ""));
  const [billNo, setBillNo] = useState(bill?.bill_no ?? "");
  const [billDate, setBillDate] = useState(bill?.bill_date ?? "");
  const [postingDate, setPostingDate] = useState(bill?.posting_date ?? "");
  const [postingTouched, setPostingTouched] = useState(!!bill?.posting_date && bill.posting_date !== bill.bill_date);
  const [term, setTerm] = useState(String(bill?.credit_term ?? ""));
  const [billTotal, setBillTotal] = useState(bill?.bill_total ?? "");
  const [notes, setNotes] = useState(bill?.notes ?? "");
  const [rows, setRows] = useState<Row[]>(() =>
    bill?.expense_lines?.length
      ? bill.expense_lines.map((l) => ({
          key: nextKey++,
          pick: l.item ? `item:${l.item}` : `ledger:${l.ledger}`,
          description: l.description,
          hsn: l.hsn,
          unit: l.unit ? String(l.unit) : "",
          qty: l.qty,
          rate: l.rate,
          gst_rate: l.gst_rate,
        }))
      : [blank()],
  );
  const [saved, setSaved] = useState<DirectBill | null>(bill ?? null);
  const [draftId, setDraftId] = useState<number | null>(bill?.id ?? null);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState("");

  useEffect(() => {
    // One branch: pick it.
    if (!branch && setup?.branches.length === 1) setBranch(String(setup.branches[0].id));
  }, [setup, branch]);
  const sup = setup?.suppliers.find((s) => String(s.id) === supplier);
  const br = setup?.branches.find((b) => String(b.id) === branch);
  const interstate = sup && br ? !!sup.state_code && sup.state_code !== br.state_code : (bill?.interstate ?? false);
  const changeBillDate = (v: string) => {
    setBillDate(v);
    if (!postingTouched) setPostingDate(v);
  };
  const pickSupplier = (v: string) => {
    setSupplier(v);
    const s = setup?.suppliers.find((x) => String(x.id) === v);
    if (s?.credit_term) setTerm(String(s.credit_term));
  };
  const change = (key: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const pickLine = (key: number, v: string) => {
    const [kind, id] = v.split(":");
    if (kind === "item") {
      const it = lists?.items.find((x) => String(x.id) === id);
      change(key, { pick: v, hsn: it?.hsn ?? "", unit: it ? String(it.unit) : "", gst_rate: it?.gst_rate ?? "" });
    } else change(key, { pick: v });
  };
  const bookedTo = (r: Row) => {
    const [kind, id] = r.pick.split(":");
    if (kind === "ledger") return lists?.ledgers.find((l) => String(l.id) === id)?.name ?? "";
    if (kind === "item") return lists?.items.find((x) => String(x.id) === id)?.booked_to_name || "Set its Expense Account";
    return "";
  };

  const tax = (taxable: number, rate: number) => {
    const t = r2((taxable * rate) / 100);
    return interstate ? { c: 0, s: 0, i: t } : { c: r2(t / 2), s: r2(t - r2(t / 2)), i: 0 };
  };
  const calc = rows.map((r) => {
    const taxable = r.pick ? r2(num(r.qty) * num(r.rate)) : 0;
    const t = tax(taxable, num(r.gst_rate));
    return { taxable, ...t, amount: r2(taxable + t.c + t.s + t.i) };
  });
  const taxable = r2(calc.reduce((s, x) => s + x.taxable, 0));
  const cgst = r2(calc.reduce((s, x) => s + x.c, 0));
  const sgst = r2(calc.reduce((s, x) => s + x.s, 0));
  const igst = r2(calc.reduce((s, x) => s + x.i, 0));
  const exact = r2(taxable + cgst + sgst + igst);
  const ours = billTotal && Math.abs(num(billTotal) - exact) < 1 ? num(billTotal) : Math.round(exact);
  const matches = billTotal !== "" && Math.abs(num(billTotal) - ours) < 0.005;

  const options = [
    ...(lists?.items ?? []).map((x) => ({ value: `item:${x.id}`, label: x.name, hint: x.service ? "· service" : "· not kept in stock" })),
    ...(lists?.ledgers ?? []).map((l) => ({ value: `ledger:${l.id}`, label: l.name, hint: "· ledger" })),
  ];
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      supplier: Number(supplier) || 0,
      branch: Number(branch) || 0,
      bill_no: billNo,
      bill_date: billDate || null,
      posting_date: postingDate || billDate || null,
      credit_term: term ? Number(term) : null,
      bill_total: billTotal === "" ? null : billTotal,
      notes,
      lines: rows
        .filter((r) => r.pick)
        .map((r) => {
          const [kind, id] = r.pick.split(":");
          return {
            item: kind === "item" ? Number(id) : null,
            ledger: kind === "ledger" ? Number(id) : null,
            description: r.description,
            hsn: r.hsn,
            unit: r.unit ? Number(r.unit) : null,
            qty: r.qty || "0",
            rate: r.rate || "0",
            gst_rate: r.gst_rate || "0",
          };
        }),
      submit,
    };
    try {
      const done = draftId ? await api<DirectBill>(`v1/direct-bills/${draftId}/`, body, "PATCH") : await api<DirectBill>(`v1/companies/${companyId}/direct-bills/`, body);
      announceSaved("purchase_invoice_saved", { id: done.id, name: done.number || "Draft" });
      if (submit) {
        window.location.hash = `${base(companyId)}?view=${done.id}`;
        return;
      }
      if (!draftId) {
        setDraftId(done.id);
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${done.id}`);
      }
      setSaved(done);
      setSavedAt(new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }));
    } catch (err) {
      const kept = keptDraft(err);
      if (kept && !draftId) {
        setDraftId(kept);
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${kept}`);
      }
      setError(err);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    setBusy(false);
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    save(false);
  };

  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId ? "Edit Purchase Invoice" : "New Purchase Invoice"}
        sub={savedAt ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.` : "Without goods receipt · services and goods not kept in stock"}
        crumbs={[{ label: "Entry › Purchase › Purchase Invoice", href: base(companyId) }]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu label="Print" items={printItems} />
            <button type="submit" form="direct-form" className={props.canSubmit ? "secondary" : undefined} disabled={busy}>
              Save
            </button>
            {props.canSubmit && (
              <button type="button" disabled={busy} onClick={() => save(true)}>
                Submit
              </button>
            )}
          </>
        }
      />
      <form id="direct-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{sup?.name ?? bill?.supplier_name ?? "Pick a supplier"}</p>
            <p className="item-sub">
              <b>{bill?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              <span className="tag">Without goods receipt</span>
            </p>
          </div>
          <ErrorNote error={error} />
          <Fold title="Supplier's Bill" open>
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <BillTypePicker companyId={companyId} direct locked={!!draftId} />
              <label>
                <span className="req">Supplier</span>
                <Combobox
                  required
                  value={supplier}
                  onChange={pickSupplier}
                  options={[
                    ...(setup?.suppliers ?? []).filter((s) => s.is_active || String(s.id) === supplier),
                    ...(bill && !setup?.suppliers.some((s) => s.id === bill.supplier) ? [{ id: bill.supplier, name: bill.supplier_name }] : []),
                  ].map((s) => ({ value: String(s.id), label: s.name }))}
                />
              </label>
              <label>
                <span className="req">Supplier Invoice No</span>
                <input value={billNo} maxLength={40} onChange={(e) => setBillNo(e.target.value)} />
              </label>
              <label>
                <span className="req">Supplier Invoice Date</span>
                <input type="date" value={billDate} onChange={(e) => changeBillDate(e.target.value)} />
              </label>
              <label>
                <span className="req">Posting Date</span>
                <input
                  type="date"
                  value={postingDate}
                  onChange={(e) => {
                    setPostingDate(e.target.value);
                    setPostingTouched(true);
                  }}
                />
              </label>
              <label>
                <span className="req">Branch</span>
                <Combobox
                  required
                  value={branch}
                  onChange={setBranch}
                  options={(setup?.branches ?? []).filter((b) => b.is_active || String(b.id) === branch).map((b) => ({ value: String(b.id), label: b.name }))}
                />
              </label>
              <label>
                Credit Term
                <Combobox value={term} onChange={setTerm} empty="Due on the bill date" options={terms.map((t) => ({ value: String(t.id), label: t.name }))} />
                <span className="small">From the supplier; due dates count from the bill date</span>
              </label>
              <label>
                <span className="req">Supplier's Bill Total ₹</span>
                <input inputMode="decimal" value={billTotal} onChange={(e) => setBillTotal(e.target.value)} placeholder="The grand total printed on the bill" />
                {billTotal !== "" && (
                  <span className={matches ? "small ok-note" : "small bad-note"}>
                    {matches ? "✓ Matches our total" : `Our total is ₹${money(String(ours))}; difference ₹${money(String(r2(num(billTotal) - ours)))}`}
                  </span>
                )}
              </label>
            </div>
          </Fold>
          <Fold title="Items and Services" open summary={`${rows.filter((r) => r.pick).length} lines`}>
            <div className="table-scroll">
              <table className="grid po-lines">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Item or Ledger</th>
                    <th>Description</th>
                    <th>HSN / SAC</th>
                    <th className="num">Qty</th>
                    <th>Unit</th>
                    <th className="num">Rate</th>
                    <th className="num">Taxable ₹</th>
                    <th className="num">GST %</th>
                    <th className="num">GST ₹</th>
                    <th>Booked To</th>
                    <th className="no-print" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => {
                    const isItem = r.pick.startsWith("item:");
                    return (
                      <tr key={r.key}>
                        <td>{i + 1}</td>
                        <td className="po-item">
                          <Combobox value={r.pick} onChange={(v) => pickLine(r.key, v)} options={options} ariaLabel="Item or ledger" placeholder="Type an item or ledger…" />
                        </td>
                        <td style={{ minWidth: 170 }}>
                          <input value={r.description} maxLength={200} onChange={(e) => change(r.key, { description: e.target.value })} aria-label="Description" />
                        </td>
                        <td>
                          {isItem ? (
                            r.hsn
                          ) : (
                            <input className="num-in" value={r.hsn} maxLength={8} onChange={(e) => change(r.key, { hsn: e.target.value })} aria-label="HSN or SAC" />
                          )}
                        </td>
                        <td className="num">
                          <input className="num-in" inputMode="decimal" value={r.qty} onChange={(e) => change(r.key, { qty: e.target.value })} aria-label="Quantity" />
                        </td>
                        <td style={{ minWidth: 100 }}>
                          <Combobox
                            value={r.unit}
                            empty="—"
                            onChange={(v) => change(r.key, { unit: v })}
                            options={(lists?.units ?? []).map((u) => ({ value: String(u.id), label: u.name }))}
                            ariaLabel="Unit"
                          />
                        </td>
                        <td className="num">
                          <input className="num-in" inputMode="decimal" value={r.rate} onChange={(e) => change(r.key, { rate: e.target.value })} aria-label="Rate" />
                        </td>
                        <td className="num">{money(String(calc[i].taxable))}</td>
                        <td className="num">
                          <input className="num-in small-in" inputMode="decimal" value={r.gst_rate} onChange={(e) => change(r.key, { gst_rate: e.target.value })} aria-label="GST %" />
                        </td>
                        <td className="num">{money(String(r2(calc[i].c + calc[i].s + calc[i].i)))}</td>
                        <td>{bookedTo(r)}</td>
                        <td className="no-print">
                          <button type="button" className="link danger" onClick={() => setRows(rows.length > 1 ? rows.filter((x) => x.key !== r.key) : [blank()])}>
                            Remove
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="small">
              Pick an item (service, or goods not kept in stock) or a ledger. An item books to the "Expense Account" on its item master (shown in "Booked To", not
              changed here); a ledger books to itself. Only expense ledgers are offered: fixed assets are not bought on this bill. No stock entry is made. Items
              kept in stock need a goods receipt first.
            </p>
            <p>
              <button type="button" className="link" onClick={() => setRows([...rows, blank()])}>
                Add line
              </button>
            </p>
          </Fold>
          <Fold title="Totals" open summary={`₹${money(String(ours))}`}>
            <Totals taxable={taxable} cgst={cgst} sgst={sgst} igst={igst} roundOff={r2(ours - exact)} total={ours} />
          </Fold>
          {saved && <TdsBox<DirectBill> billId={saved.id} tds={saved.tds} total={saved.total} draft onChanged={setSaved} />}
          {saved && (
            <EntriesBox entries={saved.entries ?? []} dues={saved.dues ?? []} draft>
              <p className="small">No stock moves and "Goods Received but Bills not Received" is not touched.</p>
            </EntriesBox>
          )}
          <Fold title="Notes" open={!!notes}>
            <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Notes" />
          </Fold>
        </div>
        <DocSide type="purchase_invoice" id={draftId} />
      </form>
    </section>
  );
}
