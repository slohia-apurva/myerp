import { money } from "./Companies";

/** The lines of a rate change on a bill already entered (Sidharth, 2026-11-16, previews 78/79):
 * a Debit Note "Rate charged higher" (way "down") or a Supplementary Bill (way "up"). Each line
 * is a line of the original bill, at the quantity kept, with the new rate typed in. */

export type RateLine = {
  id?: number;
  invoice_line: number;
  item_name: string;
  item_number?: string;
  hsn: string;
  unit_name: string;
  billed_qty: string;
  left_qty: string;
  in_stock?: string | null;
  qty: string;
  rate: string;
  new_rate: string | null;
  gst_rate: string;
  taxable?: string;
  cgst?: string;
  sgst?: string;
  igst?: string;
  amount?: string;
  stock_difference?: string;
  price_difference?: string;
};

const num = (v: string | null | undefined) => Number(v) || 0;
const r2 = (n: number) => Math.round(n * 100) / 100;

/** Each line's taxable and GST as the server works them out; a line whose rate moved the
 * wrong way (or not at all) counts as nothing. */
export function rateCalc(lines: RateLine[], way: "down" | "up", interstate: boolean) {
  const rows = lines.map((l) => {
    const per = way === "down" ? num(l.rate) - num(l.new_rate) : num(l.new_rate) - num(l.rate);
    const taxable = l.new_rate !== null && l.new_rate !== "" && per > 0 ? r2(num(l.qty) * per) : 0;
    const t = r2((taxable * num(l.gst_rate)) / 100);
    const g = interstate ? { c: 0, s: 0, i: t } : { c: r2(t / 2), s: r2(t - r2(t / 2)), i: 0 };
    return { per: per > 0 ? per : 0, taxable, ...g, amount: r2(taxable + t) };
  });
  const sum = (k: "taxable" | "c" | "s" | "i") => r2(rows.reduce((s, x) => s + x[k], 0));
  const exact = r2(sum("taxable") + sum("c") + sum("s") + sum("i"));
  return {
    rows,
    taxable: sum("taxable"),
    cgst: sum("c"),
    sgst: sum("s"),
    igst: sum("i"),
    exact,
  };
}

/** "80 kg still in stock, 30 kg already used" for a line. */
function stockNote(l: RateLine) {
  if (l.in_stock === null || l.in_stock === undefined) return "";
  const kept = num(l.left_qty);
  const here = Math.min(num(l.in_stock), kept);
  const used = r2(kept - here);
  return ` · ${here} ${l.unit_name} still in stock${used > 0 ? `, ${used} ${l.unit_name} already used` : ""}`;
}

export function RateLinesTable(props: { lines: RateLine[]; way: "down" | "up"; interstate: boolean; onChange?: (i: number, patch: Partial<RateLine>) => void }) {
  const { lines, way, onChange } = props;
  const calc = rateCalc(lines, way, props.interstate);
  return (
    <div className="table-scroll">
      <table className="grid po-lines">
        <thead>
          <tr>
            <th>#</th>
            <th>Item</th>
            <th className="num">Billed Qty</th>
            <th className="num">Bill Rate</th>
            <th className="num">{way === "down" ? "Agreed Rate" : "Revised Rate"}</th>
            <th className="num">{way === "down" ? "Less per Unit" : "More per Unit"}</th>
            <th className="num">Qty</th>
            <th>Unit</th>
            <th className="num">Taxable ₹</th>
            <th className="num">GST %</th>
            <th className="num">GST ₹</th>
            <th className="num">Amount ₹</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => {
            const c = calc.rows[i];
            const moved = !onChange || c.taxable > 0;
            const split = onChange
              ? ""
              : [
                  num(l.stock_difference) ? `₹${money(String(Math.abs(num(l.stock_difference))))} to stock on hand` : "",
                  num(l.price_difference) ? `₹${money(String(Math.abs(num(l.price_difference))))} to Purchase Price Difference` : "",
                ]
                  .filter(Boolean)
                  .map((x) => ` · ${x}`)
                  .join("");
            return (
              <tr key={l.id ?? l.invoice_line} className={onChange && moved ? "differs" : undefined}>
                <td>{i + 1}</td>
                <td className="po-item">
                  <b>{l.item_name}</b>
                  <span className="small">
                    {l.item_number && `${l.item_number} · `}HSN {l.hsn}
                    {onChange ? stockNote(l) : split}
                  </span>
                </td>
                <td className="num">{Number(l.billed_qty)}</td>
                <td className="num">{money(l.rate)}</td>
                <td className="num">
                  {onChange ? (
                    <input
                      className="num-in"
                      inputMode="decimal"
                      value={l.new_rate ?? ""}
                      onChange={(e) => onChange(i, { new_rate: e.target.value })}
                      aria-label={way === "down" ? "Agreed rate" : "Revised rate"}
                    />
                  ) : (
                    money(l.new_rate ?? "0")
                  )}
                </td>
                <td className="num">{c.per ? money(String(r2(c.per))) : ""}</td>
                <td className="num">
                  {onChange ? <input className="num-in" inputMode="decimal" value={l.qty} onChange={(e) => onChange(i, { qty: e.target.value })} aria-label="Quantity" /> : Number(l.qty)}
                </td>
                <td>{l.unit_name}</td>
                <td className="num">{money(String(onChange ? c.taxable : num(l.taxable)))}</td>
                <td className="num">{Number(l.gst_rate)}</td>
                <td className="num">{money(String(onChange ? r2(c.c + c.s + c.i) : r2(num(l.cgst) + num(l.sgst) + num(l.igst))))}</td>
                <td className="num">{money(String(onChange ? c.amount : num(l.amount)))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
