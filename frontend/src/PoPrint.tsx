import { useEffect, useState } from "react";
import { api } from "./api";
import { closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import type { Charge, Place, PurchaseOrder } from "./PurchaseOrders";

/** The purchase order as printed for the supplier (layout approved by Sidharth,
 * 2026-11-14): letterhead, Supplier / Bill To / Ship To, the items, the charges, the
 * tax summary, totals, amount in words, terms and the signature. An import adds its
 * shipment and payment terms and is in the order's currency with no GST. A draft
 * prints with "DRAFT" across it. The browser prints it; its print dialog also saves
 * it as a PDF. */

type Order = PurchaseOrder & {
  letterhead: {
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
    cin: string;
    fssai: string;
    iec: string;
  };
  amount_words: string;
  submitted_at: string | null;
};

const dmy = (iso: string | null | undefined) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const plain = (v: string | number) => {
  const n = Number(v);
  return Number.isInteger(n) ? n.toLocaleString("en-IN") : String(Number(n.toFixed(6)));
};

export function PoPrint({ id, pdf }: { id: number; pdf: boolean }) {
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    api<Order>(`v1/purchase-orders/${id}/`).then(setOrder, setError);
  }, [id]);
  // Only the sheet prints; the page's own number goes in the foot of every page.
  useEffect(() => {
    document.body.classList.add("printing-doc");
    return () => document.body.classList.remove("printing-doc");
  }, []);
  useEffect(() => {
    if (!order) return;
    document.title = `${order.number || "Draft purchase order"} - ${order.supplier_name}`;
    const t = setTimeout(() => window.print(), 400);
    return () => clearTimeout(t);
  }, [order]);
  if (!order)
    return (
      <section className="page">
        <ErrorNote error={error} />
      </section>
    );
  const foot = `${order.number || "Draft purchase order"} · ${order.status === "draft" ? "not valid until submitted" : "computer-generated purchase order"}`;
  return (
    <>
      <style>{`@page { size: A4; margin: 32mm 11mm 14mm; @top-left { content: url("${shortHead(order)}"); vertical-align: bottom; padding-bottom: 4mm; } @bottom-left { content: ${JSON.stringify(foot)}; font: 7.5pt Inter, sans-serif; color: #7b8794; } @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 700 8pt Inter, sans-serif; color: #14532d; } } @page :first { margin-top: 12mm; @top-left { content: none; } }`}</style>
      <div className="po-print-bar no-print">
        <p>
          {pdf
            ? 'To keep a PDF, pick "Save as PDF" as the printer in the print window.'
            : "The print window opens by itself; click Print to open it again."}
        </p>
        <button type="button" className="link" onClick={() => closeThisTab(() => history.back())}>
          Close
        </button>
        <button type="button" onClick={() => window.print()}>
          {pdf ? "Save as PDF" : "Print"}
        </button>
      </div>
      <PoSheet order={order} />
    </>
  );
}

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** The short heading at the top of every page after the first (as approved): logo,
 * company, "PURCHASE ORDER", number and date, and the supplier "continued". Page
 * margins take text or an image only, so it is drawn as one small picture. */
function shortHead(order: Order): string {
  const name = order.letterhead.name;
  const no = `${order.number || "Draft"} · ${dmy(order.order_date)}`;
  const font = "Inter, 'DejaVu Sans', Arial, sans-serif";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="188mm" height="16mm" viewBox="0 0 533 46">
<rect x="0" y="6" width="26" height="26" rx="6" fill="#2e9e62"/>
<text x="13" y="25" text-anchor="middle" font-family="${font}" font-size="15" font-weight="800" fill="#fff">${esc(name.slice(0, 1))}</text>
<text x="34" y="24" font-family="${font}" font-size="11" font-weight="600" fill="#1f2933">${esc(name)}</text>
<text x="533" y="12" text-anchor="end" font-family="${font}" font-size="11" font-weight="700" fill="#14532d">PURCHASE ORDER</text>
<text x="533" y="25" text-anchor="end" font-family="${font}" font-size="9" font-weight="600" fill="#1f2933">${esc(no)}</text>
<text x="533" y="36" text-anchor="end" font-family="${font}" font-size="7.5" fill="#616e7c">${esc(order.supplier_name)} · continued</text>
<rect x="0" y="42" width="533" height="2.5" fill="#2e9e62"/></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function PoSheet({ order }: { order: Order }) {
  const lh = order.letterhead;
  const inr = order.currency === "INR";
  const sym = order.currency_symbol;
  const fmt = (v: string | number) =>
    Number(v).toLocaleString(inr ? "en-IN" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const lines = order.lines ?? [];
  const charges = order.charges ?? [];
  const imp = order.import_details ?? {};
  const isImport = !inr || Object.keys(imp).length > 0;
  const gst = lines.some((l) => Number(l.gst_rate)) || charges.some((c) => Number(c.gst_rate));
  const igst = Number(order.igst_total) > 0;
  const disc = lines.some((l) => Number(l.discount_pct));
  const units = new Set(lines.map((l) => l.unit_name));
  const qtyTotal = lines.reduce((s, l) => s + Number(l.qty), 0);
  const itemsValue = lines.reduce((s, l) => s + Number(l.taxable), 0);
  const chargesValue = charges.reduce((s, c) => s + Number(c.amount), 0);
  const cols = 6 + (disc ? 1 : 0) + (gst ? 1 : 0); // columns before the amount
  const basis = (c: Charge) =>
    c.basis === "fixed"
      ? "Fixed"
      : c.basis === "percent"
        ? `${plain(c.rate)}% of items`
        : `${sym}${plain(c.rate)} per ${units.size === 1 ? [...units][0] : "unit"} × ${plain(qtyTotal)} ${units.size === 1 ? [...units][0] : ""}`;
  const supplierContacts = order.mail_contacts.filter((c) => c.of === "Supplier" && (c.mail || c.whatsapp));
  const supplierPlace: Place = {
    ...(order.addresses?.supplier as Place),
    contact: supplierContacts.map((c) => c.name).join(", "),
    phone: supplierContacts.map((c) => c.phone).filter(Boolean).join(", "),
    email: supplierContacts.map((c) => c.email).filter(Boolean).join(", "),
  };
  // Tax by HSN / SAC code and rate, items and charges together.
  const tax = new Map<string, { code: string; rate: string; taxable: number; cgst: number; sgst: number; igst: number }>();
  for (const r of [
    ...lines.map((l) => ({ code: l.hsn, rate: l.gst_rate, taxable: l.taxable, cgst: l.cgst, sgst: l.sgst, igst: l.igst })),
    ...charges.map((c) => ({ code: c.sac, rate: c.gst_rate, taxable: c.amount, cgst: c.cgst, sgst: c.sgst, igst: c.igst })),
  ]) {
    const key = `${r.code}|${r.rate}`;
    const t = tax.get(key) ?? { code: r.code, rate: r.rate, taxable: 0, cgst: 0, sgst: 0, igst: 0 };
    t.taxable += Number(r.taxable);
    t.cgst += Number(r.cgst);
    t.sgst += Number(r.sgst);
    t.igst += Number(r.igst);
    tax.set(key, t);
  }
  const taxRows = [...tax.values()];
  const meta: [string, string][] = isImport
    ? [
        ["Currency", `${order.currency} (${sym})`],
        ["Incoterms", [imp.incoterm, imp.named_place].filter(Boolean).join(" ") as string],
        ["Mode of Shipment", (imp.mode_label as string) ?? ""],
        ["Country of Origin", (imp.origin as string) ?? ""],
        ["Port of Loading", (imp.port_loading as string) ?? ""],
        ["Port of Discharge", (imp.port_discharge as string) ?? ""],
        ["Latest Shipment", dmy(imp.latest_shipment as string)],
        ["Payment", [imp.payment_label, order.credit_term_name].filter(Boolean).join(" · ")],
        ["Partial Shipment", (imp.partial_label as string) ?? ""],
        ["Transhipment", (imp.transhipment_label as string) ?? ""],
        ["Insurance By", (imp.insurance_by_label as string) ?? ""],
        ["Our Contact", order.created_by_name],
      ]
    : [
        ["Expected", dmy(order.expected_date)],
        ["Credit Term", order.credit_term_name],
        ["Transporter", order.transporter_name],
        ["Your Quote", order.supplier_ref],
        ["Our Contact", order.created_by_name],
      ];
  const docs = (imp.documents_labels as string[] | undefined) ?? [];
  return (
    <div className={`po-sheet${order.status === "draft" ? " is-draft" : ""}${order.status === "cancelled" ? " is-cancelled" : ""}`}>
      <div className="po-band">
        <div>
          <span className="po-logo">{lh.name.slice(0, 1)}</span>
          <b className="po-company">{lh.name}</b>
          <div className="po-mut po-lh">
            {lh.address && <RegdOffice lh={lh} />}
            {(lh.phone || lh.email) && <div>{[lh.phone && `Ph ${lh.phone}`, lh.email].filter(Boolean).join(" · ")}</div>}
            <div>
              {(
                [
                  ["GSTIN", lh.gstin],
                  ["PAN", lh.pan],
                ] as [string, string][]
              )
                .filter(([, v]) => v)
                .map(([k, v], i) => (
                  <span key={k}>
                    {i > 0 && " · "}
                    <b>{k}</b> {v}
                  </span>
                ))}
            </div>
            <div>
              {(
                [
                  ["CIN", lh.cin],
                  ["FSSAI", lh.fssai],
                  ["IEC", isImport ? lh.iec : ""],
                ] as [string, string][]
              )
                .filter(([, v]) => v)
                .map(([k, v], i) => (
                  <span key={k}>
                    {i > 0 && " · "}
                    <b>{k}</b> {v}
                  </span>
                ))}
            </div>
          </div>
        </div>
        <div className="po-r">
          <h1>PURCHASE ORDER</h1>
          <div className="po-no">{order.number || "Draft · number on Submit"}</div>
          <div className="po-date">Date {dmy(order.order_date)}</div>
        </div>
      </div>
      <div className="po-cards">
        <PrintPlace title="Supplier" name={order.supplier_name} place={supplierPlace} taxId={isImport} />
        <PrintPlace title="Bill To" name={lh.name} place={order.addresses?.bill_to ?? null} />
        <PrintPlace title="Ship To" name={order.addresses?.ship_to?.name ?? lh.name} place={order.addresses?.ship_to ?? null} label />
      </div>
      <div className={`po-meta${isImport ? " import" : ""}`}>
        {meta
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k}>
              <div className="po-lab">{k}</div>
              {v}
            </div>
          ))}
      </div>
      <table className="po-items">
        <thead>
          <tr>
            <th>#</th>
            <th>Item and Description</th>
            <th>HSN / SAC</th>
            <th className="po-r">Qty</th>
            <th>Unit</th>
            <th className="po-r">Rate {sym}</th>
            {disc && <th className="po-r">Disc %</th>}
            {gst && <th className="po-r">GST %</th>}
            <th className="po-r">{gst ? "Taxable Amount" : "Amount"} {sym}</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={l.id} className={i % 2 ? "alt" : ""}>
              <td>{i + 1}</td>
              <td>
                <b>
                  {l.item_name} · {l.item_number}
                </b>
                {l.description && <div className="po-desc">{l.description}</div>}
              </td>
              <td>{l.hsn}</td>
              <td className="po-r">{plain(l.qty)}</td>
              <td>{l.unit_name}</td>
              <td className="po-r">{fmt(l.rate)}</td>
              {disc && <td className="po-r">{Number(l.discount_pct) ? plain(l.discount_pct) : ""}</td>}
              {gst && <td className="po-r">{plain(l.gst_rate)}</td>}
              <td className="po-r">{fmt(l.taxable)}</td>
            </tr>
          ))}
          <tr className="po-total">
            <td />
            <td colSpan={2}>Items Total</td>
            <td className="po-r">{units.size === 1 ? plain(qtyTotal) : ""}</td>
            <td>{units.size === 1 ? [...units][0] : ""}</td>
            <td colSpan={cols - 5} />
            <td className="po-r">{fmt(itemsValue)}</td>
          </tr>
          {charges.length > 0 && (
            <>
              <tr className="po-sub">
                <td colSpan={cols + 1}>Charges</td>
              </tr>
              {charges.map((c, i) => (
                <tr key={c.id} className={i % 2 ? "alt" : ""}>
                  <td>{lines.length + i + 1}</td>
                  <td>
                    <b>{c.item_name}</b>
                  </td>
                  <td>{c.sac}</td>
                  <td colSpan={cols - (gst ? 4 : 3)} className="po-r po-mut">
                    {basis(c)}
                  </td>
                  {gst && <td className="po-r">{plain(c.gst_rate)}</td>}
                  <td className="po-r">{fmt(c.amount)}</td>
                </tr>
              ))}
              <tr className="po-total">
                <td />
                <td colSpan={cols - 1}>Charges Total</td>
                <td className="po-r">{fmt(chargesValue)}</td>
              </tr>
            </>
          )}
        </tbody>
      </table>
      <div className="po-keep po-sums">
        <div className="po-grow">
          {gst && (
            <>
              <div className="po-lab">Tax Summary</div>
              <table className="po-tax">
                <thead>
                  <tr>
                    <td>HSN / SAC</td>
                    <td className="po-r">Taxable ₹</td>
                    <td className="po-r">GST %</td>
                    {igst ? (
                      <td className="po-r">IGST ₹</td>
                    ) : (
                      <>
                        <td className="po-r">CGST ₹</td>
                        <td className="po-r">SGST ₹</td>
                      </>
                    )}
                    <td className="po-r">Tax ₹</td>
                  </tr>
                </thead>
                <tbody>
                  {taxRows.map((t) => (
                    <tr key={`${t.code}|${t.rate}`}>
                      <td>{t.code}</td>
                      <td className="po-r">{fmt(t.taxable)}</td>
                      <td className="po-r">{plain(t.rate)}</td>
                      {igst ? (
                        <td className="po-r">{fmt(t.igst)}</td>
                      ) : (
                        <>
                          <td className="po-r">{fmt(t.cgst)}</td>
                          <td className="po-r">{fmt(t.sgst)}</td>
                        </>
                      )}
                      <td className="po-r">{fmt(t.cgst + t.sgst + t.igst)}</td>
                    </tr>
                  ))}
                  <tr className="po-total">
                    <td>Total</td>
                    <td className="po-r">{fmt(order.taxable_total)}</td>
                    <td />
                    {igst ? (
                      <td className="po-r">{fmt(order.igst_total)}</td>
                    ) : (
                      <>
                        <td className="po-r">{fmt(order.cgst_total)}</td>
                        <td className="po-r">{fmt(order.sgst_total)}</td>
                      </>
                    )}
                    <td className="po-r">{fmt(Number(order.cgst_total) + Number(order.sgst_total) + Number(order.igst_total))}</td>
                  </tr>
                </tbody>
              </table>
            </>
          )}
          <div className="po-lab po-gap">Amount in Words</div>
          {order.amount_words}
          {isImport && <p className="po-mut">No GST on this order: import IGST and customs duty are paid on the bill of entry.</p>}
        </div>
        <div className="po-totals">
          <table>
            <tbody>
              {charges.length > 0 && (
                <>
                  <tr>
                    <td>Items</td>
                    <td className="po-r">{fmt(itemsValue)}</td>
                  </tr>
                  <tr>
                    <td>Charges</td>
                    <td className="po-r">{fmt(chargesValue)}</td>
                  </tr>
                </>
              )}
              {gst && (
                <>
                  <tr className="b">
                    <td>Taxable</td>
                    <td className="po-r">{fmt(order.taxable_total)}</td>
                  </tr>
                  {Number(order.cgst_total) > 0 && (
                    <tr>
                      <td>CGST</td>
                      <td className="po-r">{fmt(order.cgst_total)}</td>
                    </tr>
                  )}
                  {Number(order.sgst_total) > 0 && (
                    <tr>
                      <td>SGST</td>
                      <td className="po-r">{fmt(order.sgst_total)}</td>
                    </tr>
                  )}
                  {igst && (
                    <tr>
                      <td>IGST</td>
                      <td className="po-r">{fmt(order.igst_total)}</td>
                    </tr>
                  )}
                </>
              )}
              {Number(order.round_off) !== 0 && (
                <tr>
                  <td>Round Off</td>
                  <td className="po-r">{fmt(order.round_off)}</td>
                </tr>
              )}
              <tr className="po-grand">
                <td>Total{inr ? "" : ` (${order.currency})`}</td>
                <td className="po-r">
                  {sym}
                  {fmt(order.total)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      {isImport && (docs.length > 0 || imp.packing) && (
        <div className="po-keep po-sums">
          {docs.length > 0 && (
            <div className="po-grow">
              <div className="po-lab">Documents Required</div>
              <ol className="po-docs">
                {docs.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ol>
            </div>
          )}
          {imp.packing && (
            <div className="po-grow">
              <div className="po-lab">Packing and Marking</div>
              <div className="po-pre">{imp.packing as string}</div>
            </div>
          )}
        </div>
      )}
      <div className="po-keep po-sums po-end">
        <div className="po-grow">
          {order.terms.trim() && (
            <>
              <div className="po-lab">Terms and Conditions</div>
              <PrintTerms text={order.terms} />
            </>
          )}
        </div>
        <div className="po-sign">
          For {lh.name}
          <div className="po-sign-line">
            Authorised Signatory
            <div className="po-mut">
              {order.status === "draft" ? "Not yet approved" : `Submitted on ${dmy(order.submitted_at)}`}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The registered office on two lines, as approved: "Regd Office: <first line>," then
 * the rest of the street with the city and PIN. */
function RegdOffice({ lh }: { lh: Order["letterhead"] }) {
  const [first, ...rest] = lh.address
    .split("\n")
    .map((l) => l.trim().replace(/,$/, ""))
    .filter(Boolean);
  const second = [...rest, lh.city].filter(Boolean).join(", ") + (lh.pincode ? ` - ${lh.pincode}` : "");
  return (
    <>
      <div>
        Regd Office: {first}
        {second ? "," : ""}
      </div>
      {second && <div>{second}</div>}
    </>
  );
}

function PrintPlace(props: { title: string; name: string; place: Place | null; taxId?: boolean; label?: boolean }) {
  const p = props.place;
  if (!p)
    return (
      <div className="po-addr">
        <div className="po-lab">{props.title}</div>
        <b>{props.name}</b>
      </div>
    );
  const india = !p.country || p.country === "India";
  const facts: [string, string | undefined][] = [
    [props.taxId && !india ? "Tax ID" : "GSTIN", p.gstin],
    ["FSSAI", p.fssai],
    ["Contact", p.contact],
    ["Phone", p.phone],
    ["Email", p.email],
  ];
  return (
    <div className="po-addr">
      <div className="po-lab">{props.title}</div>
      <b>
        {props.name}
        {props.label && p.label ? ` (${p.label})` : ""}
      </b>
      {(p.address ?? "").split("\n").filter(Boolean).map((line, i) => (
        <div key={i}>{line}</div>
      ))}
      {(p.city || p.pincode) && <div>{[p.city, p.pincode].filter(Boolean).join(" - ")}</div>}
      <div>{india ? [p.state && `${p.state} (${p.state_code})`, "India"].filter(Boolean).join(" - ") : p.country}</div>
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

/** Terms as printed: a line ending in ":" is a heading; the terms are numbered. */
function PrintTerms({ text }: { text: string }) {
  let n = 0;
  return (
    <div className="po-terms">
      {text
        .split("\n")
        .filter((l) => l.trim())
        .map((l, i) => {
          const t = l.trim();
          if (t.endsWith(":")) {
            n = 0;
            return <b key={i}>{t.slice(0, -1)}</b>;
          }
          n += 1;
          return <div key={i}>{`${n}. ${t}`}</div>;
        })}
    </div>
  );
}
