import { useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { Barcode } from "./barcode";
import { closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { Section } from "./Brand";
import type { GoodsReceipt, PackageRow, ReceiptLine } from "./GoodsReceipts";
import type { Place } from "./PurchaseOrders";

/** The goods receipt's prints (Sidharth, 2026-11-15, previews 42 and 44):
 * - "Goods Receipt Note": A4, no rates or values, with a bin-wise storage summary;
 * - "Bin Sheets (A4)": one page per bin the receipt filled, to hang at the bin, with the
 *   bin's barcode and a QR code that opens "Bin contents" on a phone;
 * - "Bag Labels": one label per bag, 100 × 50 mm on a label printer or 24 to an A4 sheet;
 * - "Retention Sample Labels" (Sidharth, 2026-11-25): one label per retained sample of each
 *   batch received, same two sizes, set up in a box on the print page before printing.
 * Each opens in its own tab and brings up the browser's print window, which also saves a PDF. */

type Letterhead = {
  mark?: string;
  name: string;
  address: string;
  city: string;
  pincode: string;
  state: string;
  state_code: string;
  phone: string;
  email: string;
  gstin: string;
  pan: string;
  fssai: string;
};
type Receipt = GoodsReceipt & { letterhead: Letterhead; supplier_place: Place & { name?: string }; branch_title?: string };
export type PrintKind = "note" | "bins" | "labels" | "sheet" | "samples" | "samplesheet";
export const PRINT_KINDS: PrintKind[] = ["note", "bins", "labels", "sheet", "samples", "samplesheet"];

const dmy = (iso: string | null | undefined) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const qty = (v: string | number | null | undefined) => Number(v ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 6 });
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
/** PK-000001 to PK-000005, PK-000009 */
export function ranges(rows: PackageRow[]): string {
  const sorted = [...rows].sort((a, b) => a.seq - b.seq);
  const out: string[] = [];
  for (let i = 0; i < sorted.length; ) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1].seq === sorted[j].seq + 1) j++;
    out.push(i === j ? sorted[i].number : `${sorted[i].number} to ${sorted[j].number}`);
    i = j + 1;
  }
  return out.join(", ");
}
/** The address a QR code on a bin opens. */
export const binLink = (id: number) => `${window.location.origin}${window.location.pathname}#/bins/${id}`;

/** One line per bin, item and batch: what the receipt put where. */
type BinRow = { location: number; bin: string; line: ReceiptLine; batch: string; expiry: string | null; packs: string[]; bags: PackageRow[]; count: number; kind: string; qty: number };
function binRows(r: GoodsReceipt): BinRow[] {
  const rows: BinRow[] = [];
  for (const l of r.lines ?? []) {
    for (const p of l.putaways) {
      let row = rows.find((x) => x.location === p.location && x.line === l && x.batch === p.batch_number);
      if (!row) {
        row = { location: p.location, bin: p.location_name, line: l, batch: p.batch_number, expiry: p.expiry_date, packs: [], bags: [], count: 0, kind: "", qty: 0 };
        rows.push(row);
      }
      row.qty += Number(p.qty);
      if (p.packages) {
        row.packs.push(`${plural(p.packages, p.package_type_label)} × ${qty(p.package_qty)} ${l.unit_name}`);
        row.count += p.packages;
        row.kind = row.kind && row.kind !== p.package_type_label ? "Package" : p.package_type_label;
      }
    }
  }
  for (const row of rows) {
    row.bags = (r.packages ?? []).filter((k) => k.location === row.location && k.item_number === row.line.item_number && k.batch === row.batch);
  }
  return rows;
}

export function GrnPrint({ id, kind, only }: { id: number; kind: PrintKind; only: number[] }) {
  const [r, setR] = useState<Receipt | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    api<Receipt>(`v1/goods-receipts/${id}/?print=1`).then(setR, setError);
  }, [id]);
  useEffect(() => {
    document.body.classList.add("printing-doc");
    return () => document.body.classList.remove("printing-doc");
  }, []);
  useEffect(() => {
    if (!r) return;
    const what = { note: "Goods receipt note", bins: "Bin sheets", labels: "Bag labels", sheet: "Bag labels", samples: "Retention sample labels", samplesheet: "Retention sample labels" }[kind];
    document.title = `${what} ${r.number || "draft"}`;
    // Sample labels are set up first (how many, size, which batches); printed with "Print Labels".
    if (kind === "samples" || kind === "samplesheet") return;
    // Give the QR pictures a moment to load before the print window opens.
    const t = setTimeout(() => window.print(), kind === "bins" ? 900 : 400);
    return () => clearTimeout(t);
  }, [r, kind]);
  if (!r)
    return (
      <section className="page">
        <ErrorNote error={error} />
      </section>
    );
  const bags = (r.packages ?? []).filter((k) => !only.length || only.includes(k.id));
  if (kind === "samples" || kind === "samplesheet") return <SamplePrint r={r} sheet={kind === "samplesheet"} />;
  return (
    <>
      <style>{PAGE_RULES[kind]}</style>
      <div className="po-print-bar no-print">
        <p>
          {kind === "labels"
            ? "Pick the label printer and paper size 100 × 50 mm in the print window."
            : kind === "sheet"
              ? 'Load A4 label sheets (3 across, 8 down, 70 × 37 mm) and print at "Actual size".'
              : 'The print window opens by itself. To keep a PDF, pick "Save as PDF" as the printer.'}
        </p>
        <button type="button" className="link" onClick={() => closeThisTab(() => history.back())}>
          Close
        </button>
        <button type="button" onClick={() => window.print()}>
          Print
        </button>
      </div>
      {kind === "note" && <ReceiptNote r={r} />}
      {kind === "bins" && <BinSheets r={r} />}
      {kind === "labels" && <BagLabels co={r.letterhead.name} foot={`${dmy(r.receipt_date)} · GRN ${r.number}`} bags={bags} />}
      {kind === "sheet" && <LabelSheets number={r.number} bags={bags} />}
    </>
  );
}

const PAGE_RULES: Record<PrintKind, string> = {
  note: `@page { size: A4; margin: 12mm 11mm 14mm; @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 600 8pt Inter, sans-serif; color: #14532d; } }`,
  bins: `@page { size: A4; margin: 12mm 12mm 12mm; }`,
  labels: `@page { size: 100mm 50mm; margin: 0; }`,
  sheet: `@page { size: A4; margin: 0; }`,
  samples: `@page { size: 100mm 50mm; margin: 0; }`,
  samplesheet: `@page { size: A4; margin: 0; }`,
};

// Goods Receipt Note -----------------------------------------------------------------

function ReceiptNote({ r }: { r: Receipt }) {
  const lh = r.letterhead;
  const sp = r.supplier_place ?? {};
  const rows = binRows(r);
  const units = new Set((r.lines ?? []).map((l) => l.unit_name));
  const unit = units.size === 1 ? [...units][0] : "";
  const bagCount = rows.reduce((s, x) => s + x.count, 0);
  const kinds = new Set(rows.filter((x) => x.count).map((x) => x.kind));
  const bagWord = kinds.size === 1 ? [...kinds][0] : "Package";
  const facts: [string, ReactNode][] = [
    ["Received At", `${r.branch_name}`],
    ["Against PO", r.order_numbers.join(", ")],
    ["Challan / Invoice", [r.challan_no, dmy(r.challan_date)].filter(Boolean).join(" · ")],
    ["Transporter", [r.transporter_name, r.lr_no && `LR ${r.lr_no}`].filter(Boolean).join(" · ")],
    ["Vehicle · E-way", [r.vehicle_no, r.eway_bill_no].filter(Boolean).join(" · ")],
  ];
  const qc: [string, string][] = [
    ["Cartons (CFC) Condition", { ok: "OK", damaged: "Damaged" }[r.qc_cartons] ?? ""],
    ["Batch Code Printed on Packs", { matches: "Matches", wrong: "Wrong / Missing" }[r.qc_batch_print] ?? ""],
    ["Checked By", r.qc_by_name],
  ];
  const rejected = (r.lines ?? []).filter((l) => Number(l.rejected_qty));
  return (
    <div className="grn-doc">
      {lh.mark && <img className="po-mark-img" src={lh.mark} alt="" />}
      {r.status === "draft" && <div className="po-mark">DRAFT</div>}
      {r.status === "cancelled" && <div className="po-mark long">CANCELLED</div>}
      <div className="po-band">
        <div>
          <div className="po-brand">
            <span className="po-logo">{lh.name.slice(0, 1)}</span>
            <b className="po-company">{lh.name}</b>
          </div>
          <div className="po-mut po-lh">
            {lh.address && <div>Regd Office: {[lh.address.split("\n").join(", "), lh.city].filter(Boolean).join(", ") + (lh.pincode ? ` - ${lh.pincode}` : "")}</div>}
            <div>{[lh.gstin && `GSTIN ${lh.gstin}`, lh.pan && `PAN ${lh.pan}`, lh.fssai && `FSSAI ${lh.fssai}`].filter(Boolean).join(" · ")}</div>
          </div>
        </div>
        <div className="po-r">
          <h1>GOODS RECEIPT NOTE</h1>
          <div className="po-no">{r.number || "Draft · number on Submit"}</div>
          <div className="po-date">Date {dmy(r.receipt_date)}</div>
        </div>
      </div>
      <div className="grn-doc-cards">
        <div className="po-addr">
          <div className="po-lab">Supplier</div>
          <b>{r.supplier_name}</b>
          {(sp.address ?? "")
            .split("\n")
            .filter(Boolean)
            .map((x, i) => (
              <div key={i}>{x}</div>
            ))}
          {(sp.city || sp.pincode) && <div>{[sp.city, sp.pincode].filter(Boolean).join(" - ")}</div>}
          {sp.gstin && <div>GSTIN {sp.gstin}</div>}
        </div>
        <div className="po-addr">
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
      </div>
      <div className="po-lab grn-doc-h">Items Received</div>
      <table className="po-items">
        <thead>
          <tr>
            <th>#</th>
            <th>Item</th>
            <th>Batch</th>
            <th className="po-r">Ordered</th>
            <th className="po-r">Received</th>
            <th className="po-r">Rejected</th>
            <th className="po-r">Accepted</th>
            <th>Unit</th>
            <th className="po-r">Packages</th>
          </tr>
        </thead>
        <tbody>
          {(r.lines ?? []).map((l, i) => {
            const batches = [...new Set(l.putaways.map((p) => p.batch_number).filter(Boolean))];
            const first = l.putaways.find((p) => p.batch_number);
            const count = l.putaways.reduce((s, p) => s + (p.packages ?? 0), 0);
            const kinds = new Set(l.putaways.filter((p) => p.packages).map((p) => p.package_type_label));
            return (
              <tr key={l.order_line} className={i % 2 ? "alt" : undefined}>
                <td>{i + 1}</td>
                <td>
                  <b>{l.item_name}</b>
                  <div className="po-mut">{l.item_number}</div>
                </td>
                <td>
                  {batches.join(", ") || "–"}
                  {batches.length === 1 && first && (first.mfg_date || first.expiry_date) && (
                    <div className="po-mut">{[first.mfg_date && `Mfg ${dmy(first.mfg_date)}`, first.expiry_date && `Exp ${dmy(first.expiry_date)}`].filter(Boolean).join(" · ")}</div>
                  )}
                </td>
                <td className="po-r">{qty(l.ordered)}</td>
                <td className="po-r">{qty(l.received_qty)}</td>
                <td className="po-r">{qty(l.rejected_qty)}</td>
                <td className="po-r">
                  <b>{qty(l.accepted_qty)}</b>
                </td>
                <td>{l.unit_name}</td>
                <td className="po-r">{count ? plural(count, kinds.size === 1 ? [...kinds][0] : "Package") : "Loose"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="po-lab grn-doc-h">Bin-wise Storage</div>
      <table className="po-items">
        <thead>
          <tr>
            <th>Bin</th>
            <th>Item</th>
            <th>Batch</th>
            <th>Packages</th>
            <th>Package Nos</th>
            <th className="po-r">Qty</th>
            <th>Unit</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((x, i) => (
            <tr key={i} className={i % 2 ? "alt" : undefined}>
              <td>
                <b>{x.bin}</b>
              </td>
              <td>{x.line.item_name}</td>
              <td>{x.batch || "–"}</td>
              <td>{x.packs.join(" + ") || "Loose"}</td>
              <td>{x.bags.length ? ranges(x.bags) : r.status === "draft" && x.count ? "On Submit" : "–"}</td>
              <td className="po-r">{qty(x.qty)}</td>
              <td>{x.line.unit_name}</td>
            </tr>
          ))}
          <tr className="po-total">
            <td colSpan={3}>Total</td>
            <td>{bagCount ? plural(bagCount, bagWord) : ""}</td>
            <td />
            <td className="po-r">{unit ? qty(rows.reduce((s, x) => s + x.qty, 0)) : ""}</td>
            <td>{unit}</td>
          </tr>
        </tbody>
      </table>
      {(qc.some(([, v]) => v) || rejected.length > 0) && (
        <>
          <div className="po-lab grn-doc-h">Quality Check</div>
          <dl className="grn-doc-kv">
            {qc
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            {rejected.length > 0 && (
              <div>
                <dt>Rejected</dt>
                <dd>{rejected.map((l) => `${l.item_name} ${qty(l.rejected_qty)} ${l.unit_name}`).join("; ")}</dd>
              </div>
            )}
          </dl>
        </>
      )}
      {r.notes && (
        <>
          <div className="po-lab grn-doc-h">Notes</div>
          <div className="po-pre">{r.notes}</div>
        </>
      )}
      <div className="grn-doc-sign">
        <div>
          Received By
          {r.received_by_name && <b>{r.received_by_name}</b>}
        </div>
        <div>
          Checked By (QC)
          {r.qc_by_name && <b>{r.qc_by_name}</b>}
        </div>
        <div>Store In-charge</div>
        <div>Authorised Signatory</div>
      </div>
      <div className="grn-doc-foot">{r.number || "Draft"} · Computer-generated goods receipt · No rates or values are printed</div>
    </div>
  );
}

// Bin sheets -------------------------------------------------------------------------

function BinSheets({ r }: { r: Receipt }) {
  const rows = binRows(r);
  const bins = [...new Map(rows.map((x) => [x.location, x.bin])).entries()];
  return (
    <>
      {bins.map(([location, bin], n) => {
        const here = rows.filter((x) => x.location === location);
        const bags = here.flatMap((x) => x.bags).sort((a, b) => a.seq - b.seq);
        const units = new Set(here.map((x) => x.line.unit_name));
        const unit = units.size === 1 ? [...units][0] : "";
        const count = here.reduce((s, x) => s + x.count, 0);
        const kinds = new Set(here.filter((x) => x.count).map((x) => x.kind));
        return (
          <div key={location} className="bin-sheet">
            <div className="bin-sheet-top">
              <div>
                <div className="po-mut">
                  {r.letterhead.name} · {r.branch_name}
                </div>
                <div className="bin-sheet-name">{bin}</div>
                <div className="bin-sheet-code">LOC-{String(location).padStart(6, "0")}</div>
                <Barcode className="bin-sheet-bar" value={`LOC-${String(location).padStart(6, "0")}`} />
              </div>
              <div className="bin-sheet-qr">
                <img src={`/api/v1/qr/?text=${encodeURIComponent(binLink(location))}`} alt={`QR code for ${bin}`} />
                Scan to see what is in this bin now
              </div>
            </div>
            <div className="po-lab grn-doc-h">Received into this bin</div>
            <div className="bin-sheet-sub">
              GRN <b>{r.number || "Draft"}</b> · {dmy(r.receipt_date)} · {r.supplier_name}
              {r.challan_no ? ` · Challan ${r.challan_no}` : ""}
            </div>
            <table className="po-items bin-sheet-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Batch</th>
                  <th>Expiry</th>
                  <th>Bags</th>
                  <th>Bag Nos</th>
                  <th className="po-r">Qty</th>
                </tr>
              </thead>
              <tbody>
                {here.map((x, i) => (
                  <tr key={i}>
                    <td>
                      <b>{x.line.item_name}</b>
                      <div className="po-mut">{x.line.item_number}</div>
                    </td>
                    <td>{x.batch || "–"}</td>
                    <td>{dmy(x.expiry) || "–"}</td>
                    <td>{x.packs.join(" + ") || "Loose"}</td>
                    <td>{x.bags.length ? ranges(x.bags) : "–"}</td>
                    <td className="po-r">
                      <b>
                        {qty(x.qty)} {x.line.unit_name}
                      </b>
                    </td>
                  </tr>
                ))}
                {here.length > 1 && (
                  <tr className="po-total">
                    <td colSpan={3}>Total</td>
                    <td>{count ? plural(count, kinds.size === 1 ? [...kinds][0] : "Package") : ""}</td>
                    <td />
                    <td className="po-r">{unit ? `${qty(here.reduce((s, x) => s + x.qty, 0))} ${unit}` : ""}</td>
                  </tr>
                )}
              </tbody>
            </table>
            {bags.length > 0 && (
              <>
                <div className="po-lab grn-doc-h">Bags</div>
                <table className="po-items bin-sheet-table">
                  <thead>
                    <tr>
                      <th>Bag No</th>
                      <th>Item</th>
                      <th>Batch</th>
                      <th className="po-r">Qty</th>
                      <th className="bin-sheet-write">Taken out (write in)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bags.map((k) => (
                      <tr key={k.id}>
                        <td>
                          <b>{k.number}</b>
                        </td>
                        <td>{k.item_name}</td>
                        <td>{k.batch || "–"}</td>
                        <td className="po-r">
                          {qty(k.qty)} {k.unit_name}
                        </td>
                        <td />
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
            <div className="bin-sheet-foot">
              <span>
                {r.received_by_name ? `Put away by ${r.received_by_name} · ` : ""}Printed {new Date().toLocaleString("en-IN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit" })}
              </span>
              <b>
                Bin {n + 1} of {bins.length}
              </b>
            </div>
          </div>
        );
      })}
    </>
  );
}

// Bag labels -------------------------------------------------------------------------

/** Bag labels printed from another entry (a Stock Receipt of a customer's goods): the same
 * labels, 100 × 50 mm or 24 to an A4 sheet, and the print window opens by itself. */
export function BagLabelPrint({ sheet, co, foot, number, bags }: { sheet: boolean; co: string; foot: string; number: string; bags: PackageRow[] }) {
  useEffect(() => {
    document.body.classList.add("printing-doc");
    document.title = `Bag labels ${number}`;
    const t = setTimeout(() => window.print(), 400);
    return () => {
      clearTimeout(t);
      document.body.classList.remove("printing-doc");
    };
  }, [number]);
  return (
    <>
      <style>{PAGE_RULES[sheet ? "sheet" : "labels"]}</style>
      <div className="po-print-bar no-print">
        <p>{sheet ? 'Load A4 label sheets (3 across, 8 down, 70 × 37 mm) and print at "Actual size".' : "Pick the label printer and paper size 100 × 50 mm in the print window."}</p>
        <button type="button" className="link" onClick={() => closeThisTab(() => history.back())}>
          Close
        </button>
        <button type="button" onClick={() => window.print()}>
          Print
        </button>
      </div>
      {sheet ? <LabelSheets number={number} bags={bags} /> : <BagLabels co={co} foot={foot} bags={bags} />}
    </>
  );
}

function BagLabels({ co, foot, bags }: { co: string; foot: string; bags: PackageRow[] }) {
  if (!bags.length) return <p className="page">This entry has no bags or boxes to label.</p>;
  return (
    <div className="bag-labels">
      {bags.map((k) => (
        <div key={k.id} className="bag-label">
          <div className="bag-label-top">
            <div>
              <div className="bag-label-co">{co}</div>
              <div className="bag-label-no">{k.number}</div>
            </div>
            <div className="bag-label-qty">
              <b>
                {qty(k.qty)} {k.unit_name}
              </b>
              <div>
                {k.kind_label} {k.position} of {k.of_count}
              </div>
            </div>
          </div>
          <Barcode className="bag-label-bar" value={k.number} />
          <div>
            <b>{k.item_name}</b> · {k.item_number}
          </div>
          <div>{[k.batch && `Batch ${k.batch}`, k.expiry_date && `Exp ${dmy(k.expiry_date)}`].filter(Boolean).join(" · ")}</div>
          <div className="bag-label-mut">
            Bin {k.location_name} · {foot}
          </div>
        </div>
      ))}
    </div>
  );
}

function LabelSheets({ number, bags }: { number: string; bags: PackageRow[] }) {
  if (!bags.length) return <p className="page">This entry has no bags or boxes to label.</p>;
  const pages: PackageRow[][] = [];
  for (let i = 0; i < bags.length; i += 24) pages.push(bags.slice(i, i + 24));
  return (
    <>
      {pages.map((page, n) => (
        <div key={n} className="label-sheet">
          {page.map((k) => (
            <div key={k.id} className="label-cell">
              <div className="label-cell-top">
                <b>{k.number}</b>
                <b>
                  {qty(k.qty)} {k.unit_name}
                </b>
              </div>
              <Barcode className="label-cell-bar" value={k.number} />
              <div className="label-cell-item">{k.item_name}</div>
              <div>{[k.batch, k.expiry_date && `Exp ${dmy(k.expiry_date)}`].filter(Boolean).join(" · ")}</div>
              <div className="bag-label-mut">
                {k.kind_label} {k.position} of {k.of_count} · {number}
              </div>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

// Retention sample labels ----------------------------------------------------------------

/** One batch of one item on the receipt, as the sample labels list it. */
type SampleRow = { key: string; item_name: string; item_number: string; batch: number | null; batch_number: string; mfg: string | null; expiry: string | null; order: string; tick: boolean; retain: string };
const todayIso = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
/** A sample is kept until the batch expires; with no expiry, for one year from sampling. */
export function retainUntil(expiry: string | null, sampledOn: string): string {
  if (expiry) return expiry.slice(0, 10);
  const [y, m, d] = sampledOn.split("-");
  return y ? `${Number(y) + 1}-${m}-${m === "02" && d === "29" ? "28" : d}` : "";
}
/** The batches a receipt brought in, one row per item and batch (lines without a batch too,
 * unticked, for items that are not batch-tracked). */
export function sampleRows(r: GoodsReceipt, sampledOn: string): SampleRow[] {
  const rows: SampleRow[] = [];
  for (const l of r.lines ?? []) {
    for (const p of l.putaways) {
      const key = `${l.item_number}|${p.batch_number}`;
      if (rows.some((x) => x.key === key)) continue;
      rows.push({ key, item_name: l.item_name, item_number: l.item_number, batch: p.batch, batch_number: p.batch_number, mfg: p.mfg_date, expiry: p.expiry_date, order: l.order_number, tick: !!p.batch_number, retain: retainUntil(p.expiry_date, sampledOn) });
    }
  }
  return rows;
}
/** The address the QR code on a sample label opens: the batch's trace page (receipts, bins,
 * where it went), the same address on every label printed from now on. */
export const batchLink = (id: number) => `${window.location.origin}${window.location.pathname}#/batches/${id}/trace`;

function SamplePrint({ r, sheet }: { r: Receipt; sheet: boolean }) {
  const [count, setCount] = useState("2");
  const [size, setSize] = useState("");
  const [sampledOn, setSampledOn] = useState(todayIso);
  const [rows, setRows] = useState<SampleRow[]>(() => sampleRows(r, todayIso()));
  const change = (key: string, patch: Partial<SampleRow>) => setRows((all) => all.map((x) => (x.key === key ? { ...x, ...patch } : x)));
  const pickDate = (v: string) => {
    // Rows still on the default follow the new sampling date.
    setRows((all) => all.map((x) => (x.retain === retainUntil(x.expiry, sampledOn) ? { ...x, retain: retainUntil(x.expiry, v) } : x)));
    setSampledOn(v);
  };
  const n = Math.max(0, Math.min(20, Math.floor(Number(count) || 0)));
  const labels = rows.filter((x) => x.tick).flatMap((x) => Array.from({ length: n }, (_, i) => ({ row: x, position: i + 1 })));
  const co = r.branch_title || r.letterhead.name;
  return (
    <>
      <style>{PAGE_RULES[sheet ? "samplesheet" : "samples"]}</style>
      <div className="po-print-bar no-print">
        <p>{sheet ? 'Load A4 label sheets (3 across, 8 down, 70 × 37 mm) and print at "Actual size".' : "Pick the label printer and paper size 100 × 50 mm in the print window."}</p>
      </div>
      <div className="sample-setup no-print">
        <Section title="Retention Sample Labels">
          <div className="item-fields">
            <label>
              <span className="req">Samples Per Batch</span>
              <input type="number" min={1} max={20} step={1} value={count} onChange={(e) => setCount(e.target.value)} />
            </label>
            <label>
              Sample Size
              <input value={size} maxLength={20} placeholder="e.g. 250 g" onChange={(e) => setSize(e.target.value)} />
            </label>
            <label>
              <span className="req">Sampled On</span>
              <input type="date" value={sampledOn} onChange={(e) => e.target.value && pickDate(e.target.value)} />
            </label>
          </div>
          <table className="grid">
            <thead>
              <tr>
                <th style={{ width: 30 }}></th>
                <th>Item</th>
                <th>Batch</th>
                <th>Expiry</th>
                <th>Retain Until</th>
                <th className="num">Labels</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.key}>
                  <td>
                    <input type="checkbox" aria-label={`Print ${x.item_name} ${x.batch_number}`} checked={x.tick} onChange={(e) => change(x.key, { tick: e.target.checked })} />
                  </td>
                  <td>
                    {x.item_name} · {x.item_number}
                  </td>
                  <td className="nowrap">{x.batch_number || "—"}</td>
                  <td className="nowrap">{dmy(x.expiry) || "—"}</td>
                  <td>
                    <input type="date" aria-label={`Retain until ${x.item_name} ${x.batch_number}`} value={x.retain} onChange={(e) => change(x.key, { retain: e.target.value })} />
                  </td>
                  <td className="num">{x.tick ? n : 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small">Untick the batches you do not keep a sample of. "Retain Until" is the batch's expiry date, or one year from "Sampled On" when it has none, and can be changed per line.</p>
          <div className="sample-setup-buttons">
            <button type="button" className="link" onClick={() => closeThisTab(() => history.back())}>
              Close
            </button>
            <button type="button" disabled={!labels.length} onClick={() => window.print()}>
              Print Labels
            </button>
          </div>
        </Section>
      </div>
      {!labels.length ? (
        <p className="page no-print">Tick a batch and give the number of samples to see its labels.</p>
      ) : sheet ? (
        <SampleSheets r={r} size={size} sampledOn={sampledOn} labels={labels} n={n} />
      ) : (
        <div className="bag-labels">
          {labels.map(({ row: x, position }) => (
            <div key={`${x.key}|${position}`} className="bag-label sample-label">
              <div className="sample-label-top">
                <div>
                  <div className="sample-label-title">RETENTION SAMPLE</div>
                  <div className="bag-label-co">{co}</div>
                </div>
                <div className="sample-label-of">
                  Sample {position} of {n}
                  {size && <div>{size}</div>}
                </div>
              </div>
              <div className="sample-label-body">
                {x.batch && <img className="sample-label-qr" src={`/api/v1/qr/?text=${encodeURIComponent(batchLink(x.batch))}`} alt={`QR code for batch ${x.batch_number}`} />}
                <div className="sample-label-facts">
                  <div className="sample-label-item">
                    <span>{x.item_name}</span>
                    <span>&nbsp;· {x.item_number}</span>
                  </div>
                  <div className="sample-label-batch">{x.batch_number ? `Batch ${x.batch_number}` : "No batch"}</div>
                  <dl>
                    {(x.mfg || x.expiry) && (
                      <>
                        <dt>Mfg / Exp</dt>
                        <dd>
                          {dmy(x.mfg) || "—"} / {dmy(x.expiry) || "—"}
                        </dd>
                      </>
                    )}
                    <dt>Supplier</dt>
                    <dd>{r.supplier_name}</dd>
                    <dt>GRN</dt>
                    <dd>{r.number}</dd>
                    {x.order && (
                      <>
                        <dt>PO</dt>
                        <dd>{x.order}</dd>
                      </>
                    )}
                  </dl>
                </div>
              </div>
              <div className="sample-label-foot">
                <span>Sampled {dmy(sampledOn)} · By ____________</span>
                <span>
                  Retain Until <b>{dmy(x.retain)}</b>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function SampleSheets({ r, size, sampledOn, labels, n }: { r: Receipt; size: string; sampledOn: string; labels: { row: SampleRow; position: number }[]; n: number }) {
  const pages: (typeof labels)[] = [];
  for (let i = 0; i < labels.length; i += 24) pages.push(labels.slice(i, i + 24));
  return (
    <>
      {pages.map((page, p) => (
        <div key={p} className="label-sheet">
          {page.map(({ row: x, position }) => (
            <div key={`${x.key}|${position}`} className="label-cell sample-cell">
              <div className="label-cell-top">
                <b>RETENTION SAMPLE</b>
                <b>
                  {position} of {n}
                </b>
              </div>
              <div className="label-cell-item">{x.item_name}</div>
              <div>
                Batch <b>{x.batch_number || "—"}</b>
                {x.expiry && ` · Exp ${dmy(x.expiry)}`}
              </div>
              <div>{r.number}</div>
              <div className="label-cell-item">{[r.supplier_name, size].filter(Boolean).join(" · ")}</div>
              <div>
                Sampled {dmy(sampledOn)} · Retain Until <b>{dmy(x.retain)}</b>
              </div>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}
