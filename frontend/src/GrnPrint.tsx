import { useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { Barcode } from "./barcode";
import { closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import type { GoodsReceipt, PackageRow, ReceiptLine } from "./GoodsReceipts";
import type { Place } from "./PurchaseOrders";

/** The goods receipt's prints (Sidharth, 2026-11-15, previews 42 and 44):
 * - "Goods Receipt Note": A4, no rates or values, with a bin-wise storage summary;
 * - "Bin Sheets (A4)": one page per bin the receipt filled, to hang at the bin, with the
 *   bin's barcode and a QR code that opens "Bin contents" on a phone;
 * - "Bag Labels": one label per bag, 100 × 50 mm on a label printer or 24 to an A4 sheet.
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
type Receipt = GoodsReceipt & { letterhead: Letterhead; supplier_place: Place & { name?: string } };
export type PrintKind = "note" | "bins" | "labels" | "sheet";

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
    const what = { note: "Goods receipt note", bins: "Bin sheets", labels: "Bag labels", sheet: "Bag labels" }[kind];
    document.title = `${what} ${r.number || "draft"}`;
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
      {kind === "labels" && <BagLabels r={r} bags={bags} />}
      {kind === "sheet" && <LabelSheets r={r} bags={bags} />}
    </>
  );
}

const PAGE_RULES: Record<PrintKind, string> = {
  note: `@page { size: A4; margin: 12mm 11mm 14mm; @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 600 8pt Inter, sans-serif; color: #14532d; } }`,
  bins: `@page { size: A4; margin: 12mm 12mm 12mm; }`,
  labels: `@page { size: 100mm 50mm; margin: 0; }`,
  sheet: `@page { size: A4; margin: 0; }`,
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

function BagLabels({ r, bags }: { r: Receipt; bags: PackageRow[] }) {
  if (!bags.length) return <p className="page">This receipt has no bags or boxes to label.</p>;
  return (
    <div className="bag-labels">
      {bags.map((k) => (
        <div key={k.id} className="bag-label">
          <div className="bag-label-top">
            <div>
              <div className="bag-label-co">{r.letterhead.name}</div>
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
            Bin {k.location_name} · {dmy(r.receipt_date)} · GRN {r.number}
          </div>
        </div>
      ))}
    </div>
  );
}

function LabelSheets({ r, bags }: { r: Receipt; bags: PackageRow[] }) {
  if (!bags.length) return <p className="page">This receipt has no bags or boxes to label.</p>;
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
                {k.kind_label} {k.position} of {k.of_count} · {r.number}
              </div>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}
