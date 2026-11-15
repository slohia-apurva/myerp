import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import type { Charge, Place, PurchaseOrder } from "./PurchaseOrders";

/** The purchase order as printed for the supplier: the three print designs Sidharth
 * approved on 2026-11-14 (domestic, domestic with charges, import with charges),
 * with lighter fonts (2026-11-15). Page 1 has the letterhead, the Supplier / Bill To /
 * Ship To boxes and the order's details; every later page a short heading. When the
 * items run over, the page ends "Carried to page n" with the total so far and the next
 * begins "Brought from page n-1". The pages are laid out here, A4 each, so the browser
 * prints them as they are; its print window also saves a PDF. */

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
  submitted_by_name: string;
  submitted_by_signature?: string;
  created_by_phone?: string;
};

const dmy = (iso: string | null | undefined) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const plain = (v: string | number) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: 6 });

export function PoPrint({ id, pdf }: { id: number; pdf: boolean }) {
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<unknown>("");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    api<Order>(`v1/purchase-orders/${id}/`).then(setOrder, setError);
  }, [id]);
  // Only the pages print.
  useEffect(() => {
    document.body.classList.add("printing-doc");
    return () => document.body.classList.remove("printing-doc");
  }, []);
  useEffect(() => {
    if (!order || !ready) return;
    document.title = `${order.number || "Draft purchase order"} - ${order.supplier_name}`;
    const t = setTimeout(() => window.print(), 300);
    return () => clearTimeout(t);
  }, [order, ready]);
  if (!order)
    return (
      <section className="page">
        <ErrorNote error={error} />
      </section>
    );
  return (
    <>
      <style>{"@page { size: A4; margin: 0; }"}</style>
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
      <PoPages order={order} onReady={() => setReady(true)} />
    </>
  );
}

// The parts of the order -------------------------------------------------------------

type Row = { key: string; node: ReactNode; amount: number };

function useParts(order: Order) {
  const lh = order.letterhead;
  const inr = order.currency === "INR";
  const sym = order.currency_symbol;
  const fmt = (v: string | number) =>
    Number(v).toLocaleString(inr ? "en-IN" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  // Rates: 2 decimals (4 when they need it) in rupees, 4 in a foreign currency.
  const rateFmt = (v: string | number) =>
    Number(v).toLocaleString(inr ? "en-IN" : "en-US", { minimumFractionDigits: inr ? 2 : 4, maximumFractionDigits: 4 });
  const lines = order.lines ?? [];
  const charges = order.charges ?? [];
  const imp = order.import_details ?? {};
  const isImport = !inr || Object.keys(imp).length > 0;
  const gst = !isImport && (lines.some((l) => Number(l.gst_rate)) || charges.some((c) => Number(c.gst_rate)));
  const igst = Number(order.igst_total) > 0;
  const units = new Set(lines.map((l) => l.unit_name));
  const unit = units.size === 1 ? [...units][0] : "";
  const qtyTotal = lines.reduce((s, l) => s + Number(l.qty), 0);
  const itemsValue = lines.reduce((s, l) => s + Number(l.taxable), 0);
  const chargesValue = charges.reduce((s, c) => s + Number(c.amount), 0);
  const hsnHead = charges.length ? "HSN / SAC" : "HSN";
  const cols = gst ? 7 : 6; // columns before the amount
  const basis = (c: Charge) =>
    c.basis === "fixed"
      ? "Fixed"
      : c.basis === "percent"
        ? `${Number(c.rate).toFixed(2).replace(/\.00$/, "")}% of items`
        : `${sym}${fmt(c.rate)} per ${unit || "unit"} × ${plain(qtyTotal)} ${unit}`;

  const head = (
    <thead>
      <tr>
        <th>#</th>
        <th>Item and Description</th>
        <th>{hsnHead}</th>
        <th className="po-r">Qty</th>
        <th>Unit</th>
        <th className="po-r">Rate {sym}</th>
        {gst && <th className="po-r">GST %</th>}
        <th className="po-r">{gst ? "Taxable Amount" : "Amount"} {sym}</th>
      </tr>
    </thead>
  );
  const carried = (page: number, sum: number) => (
    <tr className="po-carry">
      <td />
      <td colSpan={cols - 1}>Carried to page {page}</td>
      <td className="po-r">{fmt(sum)}</td>
    </tr>
  );
  const brought = (page: number, sum: number) => (
    <tr className="po-brought">
      <td />
      <td colSpan={cols - 1}>Brought from page {page}</td>
      <td className="po-r">{fmt(sum)}</td>
    </tr>
  );

  const rows: Row[] = [];
  lines.forEach((l, i) =>
    rows.push({
      key: `l${l.id}`,
      amount: Number(l.taxable),
      node: (
        <tr className={i % 2 ? "alt" : ""}>
          <td>{i + 1}</td>
          <td>
            <b>
              {l.item_name} · {l.item_number}
            </b>
            {l.supplier_code && <div className="po-desc">Your code {l.supplier_code}</div>}
            {l.description && <div className="po-desc">{l.description}</div>}
          </td>
          <td>{l.hsn}</td>
          <td className="po-r">{plain(l.qty)}</td>
          <td>{l.unit_name}</td>
          <td className="po-r">
            {rateFmt(l.rate)}
            {Number(l.discount_pct) > 0 && <div className="po-desc">less {plain(l.discount_pct)}%</div>}
          </td>
          {gst && <td className="po-r">{plain(l.gst_rate)}</td>}
          <td className="po-r">{fmt(l.taxable)}</td>
        </tr>
      ),
    }),
  );
  rows.push({
    key: "items-total",
    amount: 0,
    node: (
      <tr className="po-total">
        <td className="po-blank" />
        <td colSpan={2}>{charges.length ? "Items Total" : "Total"}</td>
        <td className="po-r">{charges.length && unit ? plain(qtyTotal) : ""}</td>
        <td>{charges.length ? unit : ""}</td>
        <td colSpan={cols - 5} />
        <td className="po-r">{fmt(itemsValue)}</td>
      </tr>
    ),
  });
  if (charges.length) {
    rows.push({
      key: "charges",
      amount: 0,
      node: (
        <tr className="po-sub">
          <td colSpan={cols + 1}>Charges</td>
        </tr>
      ),
    });
    charges.forEach((c, i) =>
      rows.push({
        key: `c${c.id}`,
        amount: Number(c.amount),
        node: (
          <tr className={i % 2 ? "alt" : ""}>
            <td>{lines.length + i + 1}</td>
            <td>
              <b>{c.item_name}</b>
            </td>
            <td>{c.sac}</td>
            <td colSpan={gst ? 3 : 3} className="po-r po-mut">
              {basis(c)}
            </td>
            {gst && <td className="po-r">{plain(c.gst_rate)}</td>}
            <td className="po-r">{fmt(c.amount)}</td>
          </tr>
        ),
      }),
    );
    rows.push({
      key: "charges-total",
      amount: 0,
      node: (
        <tr className="po-total">
          <td className="po-blank" />
          <td colSpan={cols - 1}>Charges Total</td>
          <td className="po-r">{fmt(chargesValue)}</td>
        </tr>
      ),
    });
  }

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
  // One rate for everything: it goes in the headings ("CGST 2.5%"); else a GST % column.
  const rates = new Set(taxRows.map((t) => Number(t.rate)));
  const oneRate = rates.size === 1 ? [...rates][0] : null;
  const half = oneRate !== null ? ` ${plain(oneRate / 2)}%` : "";
  const whole = oneRate !== null ? ` ${plain(oneRate)}%` : "";
  const cs = (label: string) => (oneRate !== null ? `${label}${label === "IGST" ? whole : half}` : `${label} ₹`);

  const sums = (
    <div className="po-sums">
      <div className="po-grow">
        {gst && (
          <>
            <div className="po-lab">Tax Summary</div>
            <table className="po-tax">
              <thead>
                <tr>
                  <td>{hsnHead}</td>
                  <td className="po-r">Taxable ₹</td>
                  {oneRate === null && <td className="po-r">GST %</td>}
                  {igst ? (
                    <td className="po-r">{cs("IGST")}</td>
                  ) : (
                    <>
                      <td className="po-r">{cs("CGST")}</td>
                      <td className="po-r">{cs("SGST")}</td>
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
                    {oneRate === null && <td className="po-r">{plain(t.rate)}</td>}
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
                {oneRate === null && (
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
                )}
              </tbody>
            </table>
          </>
        )}
        <div className={`po-lab${gst ? " po-gap" : ""}`}>Amount in Words</div>
        <div>{order.amount_words}</div>
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
                <tr className={charges.length ? "b" : ""}>
                  <td>Taxable</td>
                  <td className="po-r">{fmt(order.taxable_total)}</td>
                </tr>
                {igst ? (
                  <tr>
                    <td>{oneRate !== null ? `IGST${whole}` : "IGST"}</td>
                    <td className="po-r">{fmt(order.igst_total)}</td>
                  </tr>
                ) : (
                  <>
                    <tr>
                      <td>{oneRate !== null ? `CGST${half}` : "CGST"}</td>
                      <td className="po-r">{fmt(order.cgst_total)}</td>
                    </tr>
                    <tr>
                      <td>{oneRate !== null ? `SGST${half}` : "SGST"}</td>
                      <td className="po-r">{fmt(order.sgst_total)}</td>
                    </tr>
                  </>
                )}
              </>
            )}
            {inr && (
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
  );

  const docs = (imp.documents_labels as string[] | undefined) ?? [];
  const importBlock =
    isImport && (docs.length > 0 || imp.packing) ? (
      <div className="po-sums">
        <div className="po-grow">
          {docs.length > 0 && (
            <>
              <div className="po-lab">Documents Required</div>
              <ol className="po-docs">
                {docs.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ol>
            </>
          )}
        </div>
        <div className="po-grow">
          {imp.packing && (
            <>
              <div className="po-lab">Packing and Marking</div>
              <div className="po-pre">{imp.packing as string}</div>
            </>
          )}
        </div>
      </div>
    ) : null;

  const approved =
    order.status === "draft" || !order.submitted_at
      ? "Not yet approved"
      : `Approved${order.submitted_by_name ? ` by ${order.submitted_by_name}` : ""} on ${dmy(order.submitted_at)} ${new Date(
          order.submitted_at,
        ).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
  const end = (
    <div className="po-sums po-end">
      <div className="po-grow">{order.terms.trim() && <PrintTerms text={order.terms} />}</div>
      <div className="po-sign">
        For {lh.name}
        <div className="po-sign-img">
          {order.submitted_by_signature && <img src={order.submitted_by_signature} alt="" />}
        </div>
        <div className="po-sign-line">
          Authorised Signatory
          <div className="po-mut">{approved}</div>
        </div>
      </div>
    </div>
  );

  const tail = [
    { key: "sums", node: sums },
    ...(importBlock ? [{ key: "import", node: importBlock }] : []),
    { key: "end", node: end },
  ];
  return { head, rows, carried, brought, tail, isImport, cols };
}

// The pages ---------------------------------------------------------------------------

type Page = { rows: Row[]; tail: { key: string; node: ReactNode }[]; broughtSum?: number; carriedSum?: number; cont?: boolean };

function PoPages({ order, onReady }: { order: Order; onReady: () => void }) {
  const parts = useParts(order);
  const measure = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<Page[] | null>(null);

  // Lay the parts out on A4 pages from their measured heights.
  useLayoutEffect(() => {
    let gone = false;
    const run = () => {
      const box = measure.current;
      if (!box || gone) return;
      const h = (sel: string) => (box.querySelector(sel) as HTMLElement | null)?.getBoundingClientRect().height ?? 0;
      const all = (sel: string) => [...box.querySelectorAll(sel)].map((e) => (e as HTMLElement).getBoundingClientRect().height);
      const body = h(".po-measure-body"); // the room for content on a page
      const firstRoom = body - h(".po-measure-first");
      const nextRoom = body - h(".po-measure-short");
      const thead = h(".po-measure-table thead");
      const rowH = all(".po-measure-table tbody tr.po-row");
      const carry = h(".po-measure-table tr.po-carry");
      const bring = h(".po-measure-table tr.po-brought");
      const cont = h(".po-measure-cont");
      const tailH = all(".po-measure-tail");
      const out: Page[] = [];
      let page: Page = { rows: [], tail: [] };
      let room = firstRoom;
      let used = thead;
      let sum = 0;
      parts.rows.forEach((r, i) => {
        const more = i < parts.rows.length - 1;
        const need = rowH[i] + (more ? carry : 0);
        if (used + need > room && page.rows.length) {
          page.carriedSum = sum;
          out.push(page);
          page = { rows: [], tail: [], broughtSum: sum };
          room = nextRoom;
          used = thead + bring;
        }
        page.rows.push(r);
        used += rowH[i];
        sum += r.amount;
      });
      parts.tail.forEach((t, i) => {
        if (used + tailH[i] > room - cont && (page.rows.length || page.tail.length)) {
          page.cont = true;
          out.push(page);
          page = { rows: [], tail: [] };
          room = nextRoom;
          used = 0;
        }
        page.tail.push(t);
        used += tailH[i];
      });
      out.push(page);
      setPages(out);
    };
    // Measure once the fonts are in, so the heights are the printed ones.
    document.fonts.ready.then(run);
    return () => {
      gone = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order]);
  useEffect(() => {
    if (pages) onReady();
  }, [pages, onReady]);

  const marks = order.status === "draft" ? "DRAFT" : order.status === "cancelled" ? "CANCELLED" : "";
  const foot =
    order.status === "draft"
      ? "Draft purchase order · not valid until submitted"
      : `${order.number} · Computer-generated purchase order`;
  if (!pages)
    return (
      <div className="po-measure" ref={measure} aria-hidden="true">
        <div className="po-page">
          <div className="po-measure-body" />
        </div>
        <div className="po-page">
          <div className="po-measure-first">
            <FullHead order={order} />
          </div>
          <div className="po-measure-short">
            <ShortHead order={order} />
          </div>
          <table className="po-items po-measure-table">
            {parts.head}
            <tbody>
              {parts.brought(1, 0)}
              {parts.rows.map((r) => (
                <RowWrap key={r.key} node={r.node} />
              ))}
              {parts.carried(2, 0)}
            </tbody>
          </table>
          <p className="po-cont po-measure-cont">Continued on page 2</p>
          {parts.tail.map((t) => (
            <div key={t.key} className="po-measure-tail">
              {t.node}
            </div>
          ))}
        </div>
      </div>
    );
  return (
    <div className="po-pages">
      {pages.map((p, n) => (
        <div key={n} className="po-page">
          {marks && <div className={`po-mark${marks === "CANCELLED" ? " long" : ""}`}>{marks}</div>}
          {n === 0 ? <FullHead order={order} /> : <ShortHead order={order} />}
          {p.rows.length > 0 && (
            <table className="po-items">
              {parts.head}
              <tbody>
                {p.broughtSum !== undefined && parts.brought(n, p.broughtSum)}
                {p.rows.map((r) => (
                  <RowWrap key={r.key} node={r.node} />
                ))}
                {p.carriedSum !== undefined && parts.carried(n + 2, p.carriedSum)}
              </tbody>
            </table>
          )}
          {p.tail.map((t) => (
            <div key={t.key}>{t.node}</div>
          ))}
          {p.cont && <p className="po-cont">Continued on page {n + 2}</p>}
          <div className="po-foot">
            <span>{foot}</span>
            <b>
              Page {n + 1} of {pages.length}
            </b>
          </div>
        </div>
      ))}
    </div>
  );
}

/** A table row, marked so its height can be measured. */
function RowWrap({ node }: { node: ReactNode }) {
  const el = node as React.ReactElement<{ className?: string }>;
  return <el.type {...el.props} className={`${el.props.className ?? ""} po-row`.trim()} />;
}

function Logo({ name }: { name: string }) {
  return <span className="po-logo">{name.slice(0, 1)}</span>;
}

function FullHead({ order }: { order: Order }) {
  const lh = order.letterhead;
  const imp = order.import_details ?? {};
  const isImport = order.currency !== "INR" || Object.keys(imp).length > 0;
  const ab = order.addresses;
  const ourContact = (
    <>
      {order.created_by_name}
      {order.created_by_phone && (
        <>
          <br />
          {order.created_by_phone}
        </>
      )}
    </>
  );
  const label = (k: string) => (imp[`${k}_label`] as string) ?? "";
  const meta: [string, ReactNode][] = isImport
    ? [
        ["Currency", `${order.currency} (${order.currency_symbol})`],
        ["Incoterms", [imp.incoterm, imp.named_place].filter(Boolean).join(" ")],
        ["Mode of Shipment", label("mode")],
        ["Country of Origin", (imp.origin as string) ?? ""],
        ["Port of Loading", (imp.port_loading as string) ?? ""],
        ["Port of Discharge", (imp.port_discharge as string) ?? ""],
        ["Latest Shipment", dmy(imp.latest_shipment as string)],
        ["Payment", [label("payment"), order.credit_term_name].filter(Boolean).join(" · ")],
        ["Partial Shipment", label("partial")],
        ["Transhipment", label("transhipment")],
        ["Insurance By", label("insurance_by")],
        ["Our Contact", ourContact],
      ]
    : [
        ["Expected", dmy(order.expected_date)],
        ["Credit Term", order.credit_term_name],
        ["Transporter", order.transporter_name],
        ["Your Quote", order.supplier_ref],
        ["Our Contact", ourContact],
      ];
  const facts = (...keys: string[]) => keys;
  return (
    <div>
      <div className="po-band">
        <div>
          <div className="po-brand">
            <Logo name={lh.name} />
            <b className="po-company">{lh.name}</b>
          </div>
          <div className="po-mut po-lh">
            {lh.address && <RegdOffice lh={lh} />}
            {(lh.phone || lh.email) && <div>{[lh.phone && `Ph ${lh.phone}`, lh.email].filter(Boolean).join(" · ")}</div>}
            <Facts
              items={[
                ["GSTIN", lh.gstin],
                ["PAN", lh.pan],
              ]}
            />
            <Facts
              items={[
                ["CIN", lh.cin],
                ["FSSAI", lh.fssai],
                ["IEC", isImport ? lh.iec : ""],
              ]}
            />
          </div>
        </div>
        <div className="po-r">
          <h1>PURCHASE ORDER</h1>
          <div className="po-no">{order.number || "Draft · number on Submit"}</div>
          <div className="po-date">Date {dmy(order.order_date)}</div>
        </div>
      </div>
      <div className="po-cards">
        <PrintPlace
          title="Supplier"
          name={order.supplier_name}
          place={(ab?.supplier as Place) ?? null}
          facts={isImport ? facts("taxid", "contact", "phone", "email") : facts("gstin", "fssai", "contact", "phone", "email")}
        />
        <PrintPlace
          title="Bill To"
          name={lh.name}
          place={ab?.bill_to ?? null}
          iec={lh.iec}
          facts={isImport ? facts("gstin", "iec", "contact", "phone") : facts("gstin", "fssai", "contact", "phone", "email")}
        />
        <PrintPlace
          title="Ship To"
          name={ab?.ship_to?.name ?? lh.name}
          place={ab?.ship_to ?? null}
          label
          facts={isImport ? facts("gstin", "contact", "phone") : facts("gstin", "fssai", "contact", "phone", "email")}
        />
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
    </div>
  );
}

function ShortHead({ order }: { order: Order }) {
  const lh = order.letterhead;
  return (
    <div className="po-band po-band-short">
      <div className="po-brand">
        <Logo name={lh.name} />
        <b className="po-company">{lh.name}</b>
      </div>
      <div className="po-r">
        <div className="po-short-title">PURCHASE ORDER</div>
        <div className="po-short-no">
          {order.number || "Draft"} · {dmy(order.order_date)}
        </div>
        <div className="po-mut">{order.supplier_name} · continued</div>
      </div>
    </div>
  );
}

function Facts({ items }: { items: [string, string][] }) {
  const shown = items.filter(([, v]) => v);
  if (!shown.length) return null;
  return (
    <div>
      {shown.map(([k, v], i) => (
        <span key={k}>
          {i > 0 && " · "}
          <b>{k}</b> {v}
        </span>
      ))}
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

const FACT_LABELS: Record<string, string> = {
  gstin: "GSTIN",
  taxid: "Tax ID",
  fssai: "FSSAI",
  iec: "IEC",
  contact: "Contact",
  phone: "Phone",
  email: "Email",
};

function PrintPlace(props: { title: string; name: string; place: Place | null; facts: string[]; iec?: string; label?: boolean }) {
  const p = props.place;
  if (!p)
    return (
      <div className="po-addr">
        <div className="po-lab">{props.title}</div>
        <b>{props.name}</b>
      </div>
    );
  const india = !p.country || p.country === "India";
  const value = (k: string): string | undefined =>
    k === "taxid" ? p.gstin : k === "iec" ? props.iec : k === "email" ? p.email?.split(", ").join(",\n") : (p as unknown as Record<string, string | undefined>)[k];
  return (
    <div className="po-addr">
      <div className="po-lab">{props.title}</div>
      <b>
        {props.name}
        {props.label && p.label ? ` (${p.label})` : ""}
      </b>
      {(p.address ?? "")
        .split("\n")
        .filter(Boolean)
        .map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      {(p.city || p.pincode) && <div>{[p.city, p.pincode].filter(Boolean).join(" - ")}</div>}
      <div>{india ? [p.state && `${p.state} (${p.state_code})`, "India"].filter(Boolean).join(" - ") : p.country}</div>
      <dl>
        {props.facts
          .map((k) => [k, value(k)] as const)
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k}>
              <dt>{FACT_LABELS[k]}</dt>
              <dd className="po-pre">{v}</dd>
            </div>
          ))}
      </dl>
    </div>
  );
}

/** Terms as approved: the first group under "Terms and Conditions", each line ending
 * in ":" starting a group of its own under that heading; terms are numbered. */
function PrintTerms({ text }: { text: string }) {
  const groups: { title: string; lines: string[] }[] = [{ title: "Terms and Conditions", lines: [] }];
  for (const raw of text.split("\n")) {
    const t = raw.trim();
    if (!t) continue;
    if (t.endsWith(":")) {
      const title = t.slice(0, -1);
      if (groups.length === 1 && !groups[0].lines.length) groups[0].title = title;
      else groups.push({ title, lines: [] });
    } else groups[groups.length - 1].lines.push(t);
  }
  const shown = groups.filter((g) => g.lines.length);
  return (
    <div className={shown.length > 1 ? "po-terms two" : "po-terms"}>
      {shown.map((g) => (
        <div key={g.title} className="po-term-group">
          <div className="po-lab">{g.title}</div>
          {g.lines.map((l, i) => (
            <div key={i}>{`${i + 1}. ${l}`}</div>
          ))}
        </div>
      ))}
    </div>
  );
}
