import { useEffect, useState } from "react";
import { api } from "./api";
import { Combobox, type Option } from "./Combobox";
import { money } from "./Companies";
import { ErrorNote } from "./ErrorNote";
import { Fold } from "./Master";

/** TDS (Sidharth, 2026-11-16, previews 86a/86b): the central list of sections,
 * the pickers on suppliers, items and ledgers, and the "TDS" box on every purchase bill. */

export type TdsSection = { code: string; new_code: string; name: string; label: string; for_goods: boolean };

export type TdsRow = {
  line_kind: string;
  line_position: number;
  label: string;
  section: string;
  section_shown: string;
  payment_code: string;
  by_hand: boolean;
  taxable: string;
  base: string;
  rate: string;
  amount: string;
  note: string;
};

export type TdsInfo = {
  deductee: string;
  year_so_far: { section: string; amount: string }[];
  rows: TdsRow[];
  total: string;
  adjusted?: { id: number; number: string; date: string; section: string; section_shown?: string; base?: string; rate?: string; amount: string; by?: string }[];
  with_adjusted?: string;
};

let cached: Promise<TdsSection[]> | null = null;

export function useTdsSections(): TdsSection[] {
  const [rows, setRows] = useState<TdsSection[]>([]);
  useEffect(() => {
    cached = cached ?? api<TdsSection[]>("v1/tds-sections/");
    cached.then(setRows, () => {
      cached = null;
    });
  }, []);
  return rows;
}

export const DEDUCTEE_TYPES: Option[] = [
  { value: "company", label: "Company" },
  { value: "firm", label: "Firm or LLP" },
  { value: "individual", label: "Individual or HUF" },
  { value: "others", label: "Others" },
];

/** A type-to-search picker of the TDS sections; blank means none. */
export function TdsSectionPicker(props: { value: string; onChange: (code: string) => void; empty?: string; ariaLabel?: string }) {
  const sections = useTdsSections();
  const options = sections.map((s) => ({ value: s.code, label: s.label }));
  if (props.value && !sections.some((s) => s.code === props.value)) options.push({ value: props.value, label: props.value });
  return <Combobox options={options} value={props.value} onChange={props.onChange} empty={props.empty ?? "None"} ariaLabel={props.ariaLabel ?? "TDS Section"} />;
}

const n = (v: string | undefined) => Number(v) || 0;

/** The bill's "TDS" box. On a draft each line's section can be changed (saved at once). */
export function TdsBox<T>(props: { billId: number; companyId?: number; tds?: TdsInfo; total: string; draft: boolean; onChanged?: (fresh: T) => void }) {
  const { tds, draft } = props;
  const [error, setError] = useState<unknown>("");
  if (!tds) return null;
  const change = async (row: TdsRow, section: string) => {
    setError("");
    try {
      const fresh = await api<T>(`v1/purchase-invoices/${props.billId}/tds/`, { rows: [{ line_kind: row.line_kind, line_position: row.line_position, section }] }, "PUT");
      props.onChanged?.(fresh);
    } catch (err) {
      setError(err);
    }
  };
  const yearText = tds.year_so_far.some((y) => n(y.amount)) ? tds.year_so_far.map((y) => `${y.section} ₹${money(y.amount)}`).join(" · ") : "Nothing yet";
  return (
    <Fold title="TDS" open summary={n(tds.total) ? `₹${money(tds.total)}` : "None"}>
      <div className="row" style={{ gap: "48px", marginBottom: "12px" }}>
        <div>
          <div className="fact-label">Deductee Type</div>
          <div>{tds.deductee}</div>
        </div>
        <div>
          <div className="fact-label">Supplier's Year So Far</div>
          <div>
            {yearText} <span className="small">(this financial year, before this bill)</span>
          </div>
        </div>
      </div>
      {tds.rows.length === 0 ? (
        <p className="small">Save the bill to see its TDS.</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Line</th>
              <th>Section</th>
              <th className="num">On ₹ (Before GST)</th>
              <th className="num">Rate %</th>
              <th className="num">TDS ₹</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {tds.rows.map((r) => (
              <tr key={r.line_kind + r.line_position}>
                <td>{r.label}</td>
                <td style={{ minWidth: "20em" }}>
                  {draft ? <TdsSectionPicker value={r.section} onChange={(code) => change(r, code)} ariaLabel={`TDS section of ${r.label}`} /> : r.section_shown || "None"}
                </td>
                <td className="num">{n(r.base) ? money(r.base) : ""}</td>
                <td className="num">{n(r.rate) ? r.rate : ""}</td>
                <td className="num">{n(r.amount) ? money(r.amount) : ""}</td>
                <td className="small">{r.note}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={4}>TDS Deducted</td>
              <td className="num">{money(tds.total)}</td>
              <td className="small">{n(tds.total) && !tds.adjusted?.length ? `The supplier is paid ₹${money(String(Math.round((n(props.total) - n(tds.total)) * 100) / 100))}` : ""}</td>
            </tr>
            {(tds.adjusted ?? []).map((a) => (
              <tr key={a.id}>
                <td colSpan={4}>
                  {n(a.amount) ? "TDS adjusted later" : `Section ${a.section_shown || a.section} set later`}:{" "}
                  <a href={`#/companies/${props.companyId ?? ""}/tds-adjustments?view=${a.id}`} target="_blank" rel="noreferrer">
                    {a.number}
                  </a>{" "}
                  <span className="small">
                    {a.date.split("-").reverse().join("-")}
                    {n(a.amount) ? ` · ${a.section}` : ""}
                    {a.by ? ` · ${a.by}` : ""}
                    {!n(a.amount) && n(a.base ?? "0") ? ` · on ₹${money(a.base ?? "0")}` : ""}
                  </span>
                </td>
                <td className="num">{n(a.amount) < 0 ? `(${money(-n(a.amount))})` : money(a.amount)}</td>
                <td />
              </tr>
            ))}
            {(tds.adjusted ?? []).length > 0 && (
              <tr>
                <td colSpan={4}>Total TDS on This Bill</td>
                <td className="num">{money(tds.with_adjusted ?? tds.total)}</td>
                <td className="small">{`The supplier is paid ₹${money(String(Math.round((n(props.total) - n(tds.with_adjusted)) * 100) / 100))}`}</td>
              </tr>
            )}
          </tfoot>
        </table>
      )}
      <ErrorNote error={error} />
      <p className="small">
        From 1 April 2026 a section shows its Income-tax Act 2025 number first, with the old one in brackets, as "393(1) Sl. 6(i) (194C)"; a bill
        dated before that keeps the old number. Each line's section comes from its item or ledger (goods: 194Q when the company deducts it; else the supplier's default) and can be changed or
        cleared here. MyERP checks the section's limits (one bill, and the supplier's year so far) and the rate for the deductee type; no PAN means the
        higher rate. The supplier is credited with the bill total less TDS.
      </p>
    </Fold>
  );
}
