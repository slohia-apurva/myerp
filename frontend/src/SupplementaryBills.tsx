import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { DocSide, keptDraft } from "./Attachments";
import { PageHeader } from "./Brand";
import { longDate, money } from "./Companies";
import { announceSaved, closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { ActionsMenu } from "./Exchange";
import { Fold } from "./Master";
import { EntriesBox, Totals, type Entry } from "./PurchaseInvoices";
import { TdsBox, type TdsInfo } from "./Tds";
import { rateCalc, RateLinesTable, type RateLine } from "./RateLines";

/** Purchase Invoice of type "Supplementary" (Sidharth, 2026-11-16, preview 79): the supplier
 * charges more for goods already billed. Opened from a submitted invoice's "Create ▾"; saved
 * through buying/supplementary.py and shown with the purchase invoices. */

export type SupplementaryBill = {
  id: number;
  number: string;
  original: number;
  original_number: string;
  original_bill_no: string;
  original_bill_date: string | null;
  supplier_name: string;
  credit_term_name: string;
  interstate: boolean;
  bill_no: string;
  bill_date: string | null;
  posting_date: string | null;
  bill_total: string | null;
  notes: string;
  rate_lines?: RateLine[];
  entries?: Entry[];
  dues?: { due_date: string; amount: string }[];
  total: string;
  tds?: TdsInfo;
};
type DraftFrom = {
  original: number;
  original_number: string;
  original_bill_no: string;
  original_bill_date: string | null;
  supplier_name: string;
  credit_term_name: string;
  interstate: boolean;
  lines: RateLine[];
};

const base = (companyId: number) => `#/companies/${companyId}/purchase-invoices`;
const num = (v: string | null | undefined) => Number(v) || 0;
const r2 = (n: number) => Math.round(n * 100) / 100;
const printItems = [
  { label: "Supplementary Bill", onClick: () => window.print() },
  { label: "Download PDF", onClick: () => window.print() },
];

/** A new bill from ?form=new&supplementary=<original>, or a draft to finish. */
export function SupplementaryFormTab(props: { companyId: number; original?: number; bill?: SupplementaryBill; canSubmit: boolean }) {
  const [from, setFrom] = useState<DraftFrom | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    if (props.bill || !props.original) return;
    api<DraftFrom>(`v1/companies/${props.companyId}/supplementary-bills/draft-from/?invoice=${props.original}`).then(setFrom, setError);
  }, [props.companyId, props.original, props.bill]);
  if (props.bill) {
    const b = props.bill;
    // A draft's own lines; lines of the original it left out are not offered again.
    const draft: DraftFrom = { ...b, lines: b.rate_lines ?? [] };
    return <SupplementaryForm companyId={props.companyId} from={draft} bill={b} canSubmit={props.canSubmit} />;
  }
  if (error || !from)
    return (
      <section className="page">
        <PageHeader
          title="New Supplementary Bill"
          crumbs={[
            {
              label: "Entry › Purchase › Purchase Invoice",
              href: base(props.companyId),
            },
          ]}
        />
        <ErrorNote error={error} />
      </section>
    );
  return <SupplementaryForm companyId={props.companyId} from={from} canSubmit={props.canSubmit} />;
}

function SupplementaryForm(props: { companyId: number; from: DraftFrom; bill?: SupplementaryBill; canSubmit: boolean }) {
  const { companyId, from, bill } = props;
  const [billNo, setBillNo] = useState(bill?.bill_no ?? "");
  const [billDate, setBillDate] = useState(bill?.bill_date ?? "");
  const [postingDate, setPostingDate] = useState(bill?.posting_date ?? "");
  const [postingTouched, setPostingTouched] = useState(!!bill?.posting_date && bill.posting_date !== bill.bill_date);
  const [billTotal, setBillTotal] = useState(bill?.bill_total ?? "");
  const [notes, setNotes] = useState(bill?.notes ?? "");
  const [lines, setLines] = useState<RateLine[]>(from.lines);
  const [saved, setSaved] = useState<SupplementaryBill | null>(bill ?? null);
  const [draftId, setDraftId] = useState<number | null>(bill?.id ?? null);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState("");

  const calc = rateCalc(lines, "up", from.interstate);
  const ours = billTotal && Math.abs(num(billTotal) - calc.exact) < 1 ? num(billTotal) : Math.round(calc.exact);
  const matches = billTotal !== "" && Math.abs(num(billTotal) - ours) < 0.005;
  const changeBillDate = (v: string) => {
    setBillDate(v);
    if (!postingTouched) setPostingDate(v);
  };
  const changeLine = (i: number, patch: Partial<RateLine>) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, ...patch } : l)));
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const save = async (submit: boolean) => {
    setError("");
    setBusy(true);
    const body = {
      original: from.original,
      bill_no: billNo,
      bill_date: billDate || null,
      posting_date: postingDate || billDate || null,
      bill_total: billTotal === "" ? null : billTotal,
      notes,
      lines: lines
        .filter((_, i) => calc.rows[i].taxable > 0)
        .map((l) => ({
          invoice_line: l.invoice_line,
          qty: l.qty,
          new_rate: l.new_rate,
        })),
      submit,
    };
    try {
      const done = draftId ? await api<SupplementaryBill>(`v1/supplementary-bills/${draftId}/`, body, "PATCH") : await api<SupplementaryBill>(`v1/companies/${companyId}/supplementary-bills/`, body);
      announceSaved("purchase_invoice_saved", {
        id: done.id,
        name: done.number || "Draft",
      });
      if (submit) {
        window.location.hash = `${base(companyId)}?view=${done.id}`;
        return;
      }
      if (!draftId) {
        setDraftId(done.id);
        window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${done.id}`);
      }
      setSaved(done);
      setSavedAt(
        new Date().toLocaleTimeString("en-IN", {
          hour: "numeric",
          minute: "2-digit",
        }),
      );
    } catch (err) {
      const kept = keptDraft(err);
      if (kept && !draftId) {
        setDraftId(kept);
        window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${base(companyId)}?form=${kept}`);
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
  const against = `${from.original_number} · Bill ${from.original_bill_no}${from.original_bill_date ? ` of ${longDate(from.original_bill_date)}` : ""}`;

  return (
    <section className="page item-edit">
      <PageHeader
        title={draftId ? "Edit Supplementary Bill" : "New Supplementary Bill"}
        sub={
          savedAt
            ? `Saved as a draft at ${savedAt}. Carry on, or click "Close" and finish it later.`
            : `Rate charged lower · against purchase invoice ${from.original_number} (Bill ${from.original_bill_no})`
        }
        crumbs={[
          {
            label: "Entry › Purchase › Purchase Invoice",
            href: base(companyId),
          },
        ]}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <ActionsMenu label="Print" items={printItems} />
            <button type="submit" form="supp-form" className={props.canSubmit ? "secondary" : undefined} disabled={busy}>
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
      <form id="supp-form" className="doc-page" onSubmit={onSubmit}>
        <div className="side-main">
          <div className="item-head doc-head">
            <p className="doc-title">{from.supplier_name}</p>
            <p className="item-sub">
              <b>{bill?.number || "Number given on Submit"}</b>
              <span className="tag">Draft</span>
              <span className="tag">Supplementary</span>
              <span className="tag">Against Bill {from.original_bill_no}</span>
            </p>
          </div>
          <ErrorNote error={error} />
          <Fold title="Supplier's Bill" open>
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <label>
                <span className="req">Supplier</span>
                <input value={from.supplier_name} readOnly />
              </label>
              <label>
                <span className="req">Against Invoice</span>
                <input value={against} readOnly />
              </label>
              <label>
                <span className="req">Supplier Invoice No</span>
                <input value={billNo} maxLength={40} onChange={(e) => setBillNo(e.target.value)} />
                <span className="small">The supplier's supplementary invoice (or debit note) number</span>
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
                Credit Term
                <input value={from.credit_term_name || "Due on the bill date"} readOnly />
                <span className="small">From the original bill; due dates count from this bill's date</span>
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
          <Fold title="Items" open>
            <RateLinesTable lines={lines} way="up" interstate={from.interstate} onChange={changeLine} />
            <p className="small">Every line of the original bill is listed. Type the "Revised Rate" on the lines whose price went up; lines left at the bill rate are not on this bill.</p>
          </Fold>
          <Fold title="Totals" open summary={`₹${money(String(ours))}`}>
            <Totals taxable={calc.taxable} cgst={calc.cgst} sgst={calc.sgst} igst={calc.igst} roundOff={r2(ours - calc.exact)} total={ours} />
          </Fold>
          {saved && <TdsBox<SupplementaryBill> billId={saved.id} tds={saved.tds} total={saved.total} draft onChanged={setSaved} />}
          {saved && (
            <EntriesBox entries={saved.entries ?? []} dues={[]} draft>
              <p className="small">No quantity moves. Due dates count from this bill's own date on the credit term.</p>
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
