import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader } from "./Brand";
import { Combobox } from "./Combobox";
import { money } from "./Companies";
import { closeThisTab, useCreated } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu } from "./Exchange";
import { Fold, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useReturns } from "./Refresh";

/** Entry › Accounts › TDS Check (Sidharth, 2026-11-19, previews 95a/95b): every supplier's TDS for the year worked
 * out again with today's masters, against what was deducted; a gap is put right by a TDS Adjustment
 * (TdsAdjustments.tsx). A quarter marked "Return Filed" is locked. Served by buying/tds_check.py. */

type Summary = {
  supplier: number;
  supplier_name: string;
  pan: string;
  section: string;
  section_shown: string;
  bills: number;
  taxable: string;
  due: string;
  deducted: string;
  gap: string;
  fixable: string;
  no_section: number;
  to_set: number;
  result: string;
  result_label: string;
};
type Quarter = { quarter_start: string; label: string; id: number | null; filed_on: string | null; ack_no: string };
type Year = { start: string; end: string; label: string };
type Check = { start: string; end: string; years: Year[]; quarters: Quarter[]; rows: Summary[]; checked_at: string };
type Bill = {
  invoice: number;
  number: string;
  posting_date: string;
  bill_no: string;
  taxable: string;
  year_so_far: string;
  on_bill_section: string;
  base: string;
  rate: string;
  due: string;
  on_bill: string;
  adjusted: string;
  deducted: string;
  gap: string;
  filed: boolean;
  needs_section: boolean;
  section_set_by: string;
  why: string;
};
type Adjustment = { id: number; number: string; status: string; status_label: string; adj_date: string; total: string };
type SupplierCheck = {
  start: string;
  end: string;
  summary: Summary;
  section_name: string;
  limits: string;
  above_limit_only: boolean;
  deductee: string;
  balance: string;
  bills: Bill[];
  adjustments: Adjustment[];
};

const base = (companyId: number) => `#/companies/${companyId}/tds-check`;
const dmy = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const today = () => new Date().toISOString().slice(0, 10);
const pill = (result: string) => (result === "short" ? "pill bad" : result === "excess" || result === "missing" ? "pill warn" : result === "matches" ? "pill on" : "pill");
/** Something to put right: TDS short or in excess, or a section missing on a bill. */
const toFix = (r: Summary) => Number(r.gap) !== 0 || r.no_section > 0;
const gapText = (v: string) => (Number(v) < 0 ? `(${money(-Number(v))})` : money(v));
const gapClass = (v: string) => (Number(v) > 0 ? "num bad-note" : "num");
const balanceText = (v: string) => (Number(v) < 0 ? `₹${money(-Number(v))} Cr` : `₹${money(v)} Dr`);

export function TdsCheckPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const ledger = Number(hashParam("ledger"));
  const section = hashParam("section");
  if (ledger > 0 && section) return <SupplierPage companyId={companyId} session={session} ledger={ledger} section={section} year={hashParam("year") ?? ""} />;
  return <CheckList companyId={companyId} session={session} />;
}

// The list: one line per supplier ledger and section ------------------------------------------

const SHOW = [
  { value: "gaps", label: "Only with something to put right" },
  { value: "all", label: "All suppliers" },
];
const COLUMNS: [key: string, label: string, text: (r: Summary) => string, num?: boolean][] = [
  ["supplier", "Supplier Ledger", (r) => r.supplier_name],
  ["pan", "PAN", (r) => r.pan],
  ["section", "Section", (r) => `${r.section} ${r.section_shown}`],
  ["bills", "Bills", (r) => String(r.bills), true],
  ["taxable", "Before GST ₹", (r) => `${r.taxable} ${money(r.taxable)}`, true],
  ["due", "TDS Due ₹", (r) => `${r.due} ${money(r.due)}`, true],
  ["deducted", "TDS Deducted ₹", (r) => `${r.deducted} ${money(r.deducted)}`, true],
  ["gap", "Short (Excess) ₹", (r) => `${r.gap} ${gapText(r.gap)}`, true],
  ["no_section", "No Section On Bill", (r) => String(r.no_section), true],
  ["result", "Result", (r) => r.result_label],
];

function CheckList({ companyId, session }: { companyId: number; session: SignedIn }) {
  const [year, setYear] = useState("");
  const [show, setShow] = useState("gaps");
  const [data, setData] = useState<Check | null>(null);
  const [search, setSearch] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<unknown>("");
  const visits = useReturns();
  const reload = useCallback(() => {
    setError("");
    api<Check>(`v1/companies/${companyId}/tds-check/${year ? `?year=${year}` : ""}`).then(setData, setError);
  }, [companyId, year]);
  useEffect(reload, [reload, visits]);
  useCreated("tds_adjustment_saved", reload);
  const rows = useMemo(
    () =>
      (data?.rows ?? [])
        .filter((r) => show === "all" || toFix(r))
        .filter((r) =>
          COLUMNS.every(([key, , text]) => {
            const words = (search[key] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
            const value = text(r).toLowerCase();
            return words.every((w) => value.includes(w));
          }),
        ),
    [data, show, search],
  );
  const keyOf = (r: Summary) => `${r.supplier}-${r.section}`;
  const chosen = rows.find((r) => keyOf(r) === selected) ?? null;
  const yearLabel = data?.years.find((y) => y.start === data.start)?.label ?? "";
  const printing = usePrintMenu({ title: `TDS Check ${yearLabel}`, scope: "" });
  const open = (r: Summary) => openTab(`${base(companyId)}?ledger=${r.supplier}&section=${encodeURIComponent(r.section)}&year=${data?.start ?? ""}`);
  const all = data?.rows ?? [];
  const count = (key: string) => all.filter((r) => r.result === key);
  const sum = (list: Summary[]) => list.reduce((s, r) => s + Math.abs(Number(r.gap)), 0);
  return (
    <section className="page">
      <PageHeader
        title="TDS Check"
        crumbs={[{ label: "Entry › Accounts", href: base(companyId) }]}
        sub="The TDS each supplier's bills should have had this year, against what they had. Run it before each quarter's TDS return."
        actions={printing.buttons}
      />
      <ErrorNote error={error} />
      {printing.panel}
      <div className="side-layout">
        <div className="side-main">
          <div className="row filters no-print">
            <span className="po-view">
              <Combobox
                value={data?.start ?? year}
                onChange={(v) => {
                  setYear(v);
                  setSelected(null);
                }}
                ariaLabel="Financial Year"
                options={(data?.years ?? []).map((y) => ({ value: y.start, label: y.label }))}
              />
            </span>
            <span className="po-view">
              <Combobox value={show} onChange={(v) => setShow(v || "gaps")} ariaLabel="Show" options={SHOW} />
            </span>
            <button type="button" onClick={reload}>
              Check Again
            </button>
            {Object.values(search).some(Boolean) && (
              <button type="button" className="link" onClick={() => setSearch({})}>
                Clear searches
              </button>
            )}
          </div>
          <table className="pick po-list">
            <thead>
              <tr>
                {COLUMNS.map(([key, label, , isNum]) => (
                  <th key={key} className={isNum ? "num" : undefined}>
                    {label}
                  </th>
                ))}
              </tr>
              <tr className="col-search no-print">
                {COLUMNS.map(([key, label]) => (
                  <th key={key}>
                    <input type="search" aria-label={`Search ${label}`} placeholder="Search" value={search[key] ?? ""} onChange={(e) => setSearch({ ...search, [key]: e.target.value })} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data && rows.length === 0 && (
                <tr>
                  <td colSpan={COLUMNS.length} className="small">
                    {show === "gaps" ? "Nothing to put right this year." : "No bills with TDS sections this year."}
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr
                  key={keyOf(r)}
                  tabIndex={0}
                  className={selected === keyOf(r) ? "selected" : ""}
                  onClick={() => setSelected(selected === keyOf(r) ? null : keyOf(r))}
                  onDoubleClick={() => open(r)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") open(r);
                  }}
                >
                  <td>
                    <b>{r.supplier_name}</b>
                  </td>
                  <td>{r.pan}</td>
                  <td className="nowrap">{r.section}</td>
                  <td className="num">{r.bills}</td>
                  <td className="num">{money(r.taxable)}</td>
                  <td className="num">{money(r.due)}</td>
                  <td className="num">{money(r.deducted)}</td>
                  <td className={gapClass(r.gap)}>{gapText(r.gap)}</td>
                  <td className="num">{r.no_section ? <b>{r.no_section}</b> : 0}</td>
                  <td>
                    <span className={pill(r.result)}>{r.result_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 0 && <p className="small no-print">Click a line to see it at the right; double-click or press Enter to open the supplier's bills in a new tab.</p>}
        </div>
        <div className="side-col">
          {chosen ? (
            <SidePanel title={chosen.supplier_name} tag={chosen.result_label}>
              <SideRows
                rows={[
                  ["Section", chosen.section_shown],
                  ["PAN", chosen.pan],
                  ["Bills", String(chosen.bills)],
                  ["TDS Due", `₹${money(chosen.due)}`],
                  ["TDS Deducted", `₹${money(chosen.deducted)}`],
                  ["Short (Excess)", `₹${gapText(chosen.gap)}`],
                  ["Can Be Put Right", Number(chosen.fixable) ? `₹${gapText(chosen.fixable)}` : "Nothing"],
                  ["No Section On Bill", chosen.no_section ? `${chosen.no_section} ${chosen.no_section === 1 ? "bill" : "bills"}` : "None"],
                ]}
              />
              <div className="side-buttons">
                <button type="button" onClick={() => open(chosen)}>
                  Open
                </button>
              </div>
            </SidePanel>
          ) : (
            data && (
              <SidePanel title="Check Summary">
                <SideRows
                  rows={[
                    ["Year", `${dmy(data.start)} to ${dmy(data.end)}`],
                    ["Suppliers Checked", String(new Set(all.map((r) => r.supplier)).size)],
                    ["Short", count("short").length ? `${count("short").length} · ₹${money(sum(count("short")))}` : "None"],
                    ["Excess", count("excess").length ? `${count("excess").length} · ₹${money(sum(count("excess")))}` : "None"],
                    ["Section Missing", count("missing").length ? String(count("missing").length) : "None"],
                    ["Matches / Below Limit", String(count("matches").length + count("below").length)],
                    ["Checked On", new Date(data.checked_at).toLocaleString("en-IN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit" })],
                  ]}
                />
              </SidePanel>
            )
          )}
          {data && <ReturnsPanel companyId={companyId} session={session} quarters={data.quarters} onChange={reload} />}
          <SidePanel title="How It Checks">
            <p className="small">
              Every submitted bill of the year is worked out again, in date order, with today's masters: the item's or ledger's "TDS Section", the supplier's PAN and type, and the section's rates and
              limits on the bill's date. So a bill entered before an item got its TDS Section shows here as Short, or as "Section missing" when it owes nothing. Submitted TDS
              Adjustments count as deducted, and set the section on the bills they name.
            </p>
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** "TDS Returns": the year's four quarters; a quarter marked filed is locked against adjustments. */
function ReturnsPanel({ companyId, session, quarters, onChange }: { companyId: number; session: SignedIn; quarters: Quarter[]; onChange: () => void }) {
  const canMark = session.permissions.includes("accounts.submit") || session.user.is_owner;
  const [marking, setMarking] = useState<string | null>(null);
  const [filedOn, setFiledOn] = useState(today());
  const [ack, setAck] = useState("");
  const [error, setError] = useState<unknown>("");
  const mark = async () => {
    setError("");
    try {
      await api(`v1/companies/${companyId}/tds-returns/`, { quarter_start: marking, filed_on: filedOn, ack_no: ack });
      setMarking(null);
      setAck("");
      onChange();
    } catch (err) {
      setError(err);
    }
  };
  const unmark = async (id: number) => {
    setError("");
    try {
      await api(`v1/tds-returns/${id}/`, undefined, "DELETE");
      onChange();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <SidePanel title="TDS Returns">
      {quarters.map((q) => (
        <div key={q.quarter_start} className="side-row">
          <span>{q.label}</span>
          <span>
            {q.id ? (
              <>
                Filed {dmy(q.filed_on)}
                {q.ack_no ? ` · ${q.ack_no}` : ""}
                {session.user.is_owner && (
                  <>
                    {" "}
                    <button type="button" className="link danger no-print" onClick={() => q.id && unmark(q.id)}>
                      Remove mark
                    </button>
                  </>
                )}
              </>
            ) : canMark ? (
              <button type="button" className="link no-print" onClick={() => setMarking(q.quarter_start)}>
                Mark Filed
              </button>
            ) : (
              "Not filed"
            )}
          </span>
        </div>
      ))}
      {marking && (
        <div className="use-note no-print">
          <b>{quarters.find((q) => q.quarter_start === marking)?.label}: return filed</b>
          <label>
            Filed On
            <input type="date" value={filedOn} max={today()} onChange={(e) => setFiledOn(e.target.value)} />
          </label>
          <label>
            Acknowledgement No
            <input value={ack} maxLength={30} onChange={(e) => setAck(e.target.value)} />
          </label>
          <ErrorNote error={error} />
          <div className="buttons">
            <button type="button" className="link" onClick={() => setMarking(null)}>
              Cancel
            </button>
            <button type="button" onClick={mark}>
              Save
            </button>
          </div>
        </div>
      )}
      {!marking && <ErrorNote error={error} />}
      <p className="small">Once a quarter is marked filed, its bills cannot be adjusted and its bills with TDS cannot be cancelled.</p>
    </SidePanel>
  );
}

// One supplier: the bills one by one ------------------------------------------------------------

function SupplierPage({ companyId, session, ledger, section, year }: { companyId: number; session: SignedIn; ledger: number; section: string; year: string }) {
  const [data, setData] = useState<SupplierCheck | null>(null);
  const [error, setError] = useState<unknown>("");
  const visits = useReturns();
  const query = `ledger=${ledger}&section=${encodeURIComponent(section)}${year ? `&year=${year}` : ""}`;
  const reload = useCallback(() => {
    api<SupplierCheck>(`v1/companies/${companyId}/tds-check/supplier/?${query}`).then(setData, setError);
  }, [companyId, query]);
  useEffect(reload, [reload, visits]);
  useCreated("tds_adjustment_saved", reload);
  const printing = usePrintMenu({ title: `TDS Check: ${data?.summary.supplier_name ?? ""} ${section}`, scope: "" });
  const close = () =>
    closeThisTab(() => {
      window.location.hash = base(companyId);
    });
  const s = data?.summary;
  const canAdjust = session.permissions.includes("accounts.create") || session.user.is_owner;
  const shortBills = (data?.bills ?? []).filter((b) => Number(b.gap) !== 0 && !b.filed);
  const filedGaps = (data?.bills ?? []).filter((b) => (Number(b.gap) !== 0 || b.needs_section) && b.filed);
  const bills = (n: number) => `${n} ${n === 1 ? "bill" : "bills"}`;
  const total = (key: keyof Bill) => (data?.bills ?? []).reduce((n, b) => n + Number(b[key]), 0);
  return (
    <section className="page">
      <PageHeader
        title={`TDS Check: ${s?.supplier_name ?? ""}`}
        crumbs={[{ label: "Entry › Accounts › TDS Check", href: base(companyId) }]}
        sub={
          data
            ? `${s?.section_shown} ${data.section_name} · ${dmy(data.start)} to ${dmy(data.end)} · ${data.deductee}${data.limits ? ` · limits: ${data.limits}${data.above_limit_only ? " (TDS on what passes the year limit)" : ""}` : ""}`
            : undefined
        }
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            {printing.buttons}
          </>
        }
      />
      <ErrorNote error={error} />
      {printing.panel}
      {data && s && (
        <div className="side-layout">
          <div className="side-main">
            <Fold title="Bills This Year" open summary={`${data.bills.length} ${data.bills.length === 1 ? "bill" : "bills"}`}>
              <div className="table-scroll">
                <table className="grid po-lines">
                  <thead>
                    <tr>
                      <th>Bill No</th>
                      <th>Date</th>
                      <th className="num">Before GST ₹</th>
                      <th className="num">Year So Far ₹</th>
                      <th>Section On Bill</th>
                      <th className="num">TDS Due ₹</th>
                      <th className="num">Deducted ₹</th>
                      <th className="num">Short (Excess) ₹</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {data.bills.map((b) => [
                      <tr key={b.invoice}>
                        <td className="nowrap">
                          {b.number} <span className="small">Bill {b.bill_no}</span>
                        </td>
                        <td className="nowrap">{dmy(b.posting_date)}</td>
                        <td className="num">{money(b.taxable)}</td>
                        <td className="num">{money(b.year_so_far)}</td>
                        <td>{b.on_bill_section}</td>
                        <td className="num">
                          {money(b.due)}
                          {Number(b.rate) > 0 && <span className="small"> at {b.rate}%</span>}
                        </td>
                        <td className="num">
                          {money(b.deducted)}
                          {Number(b.adjusted) !== 0 && <span className="small"> incl. adjusted {gapText(b.adjusted)}</span>}
                        </td>
                        <td className={gapClass(b.gap)}>{gapText(b.gap)}</td>
                        <td className="no-print">
                          <button type="button" className="link" onClick={() => openTab(`#/companies/${companyId}/purchase-invoices?view=${b.invoice}`)}>
                            Open
                          </button>
                        </td>
                      </tr>,
                      b.why ? (
                        <tr key={`${b.invoice}-why`}>
                          <td />
                          <td colSpan={8} className="small">
                            {b.why}
                          </td>
                        </tr>
                      ) : null,
                    ])}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={2}>Total</td>
                      <td className="num">{money(total("taxable"))}</td>
                      <td colSpan={2} />
                      <td className="num">{money(total("due"))}</td>
                      <td className="num">{money(total("deducted"))}</td>
                      <td className={gapClass(s.gap)}>{gapText(s.gap)}</td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            </Fold>
          </div>
          <div className="side-col">
            <SidePanel title="Put It Right" tag={s.result_label}>
              {Number(s.fixable) === 0 && s.to_set === 0 ? (
                <p className="small">{filedGaps.length ? "The bills to put right are in quarters whose TDS return is filed, so they cannot be adjusted." : "Nothing to put right."}</p>
              ) : Number(s.fixable) === 0 ? (
                <>
                  <p className="use-note">
                    <b>
                      {section} missing on {bills(s.to_set)}
                    </b>
                    . No TDS is owed on them, so the TDS Adjustment only records the section ("Set section only", ₹0) and posts nothing. The bills themselves are not changed.
                  </p>
                  {filedGaps.length > 0 && <p className="small">Bills in quarters whose TDS return is filed are left out.</p>}
                  {canAdjust && (
                    <div className="side-buttons">
                      <button type="button" onClick={() => openTab(`#/companies/${companyId}/tds-adjustments?form=new&${query.replace(/(^|&)year=[^&]*/, "")}&year=${data.start}`)}>
                        Set Section
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <p className="use-note">
                    <b>
                      ₹{money(Math.abs(Number(s.fixable)))} {Number(s.fixable) > 0 ? "short" : "in excess"}
                    </b>{" "}
                    on {shortBills.length} {shortBills.length === 1 ? "bill" : "bills"}. A submitted bill is never changed, so it is put right on a TDS Adjustment.
                  </p>
                  <p className="small">
                    {Number(s.fixable) > 0
                      ? `The adjustment, dated the day it is made, debits the supplier and credits "TDS Payable ${section}". The supplier then owes us that much, or is paid that much less. Interest for deducting late is shown on it, to pay with the challan.`
                      : `The adjustment debits "TDS Payable ${section}" and credits the supplier. Use it only while that TDS is not yet paid to the government.`}
                  </p>
                  {s.to_set > 0 && <p className="small">The same adjustment sets {section} on the {bills(s.to_set)} that missed it.</p>}
                  {filedGaps.length > 0 && <p className="small">Bills in quarters whose TDS return is filed are left out.</p>}
                  {canAdjust && (
                    <div className="side-buttons">
                      <button type="button" onClick={() => openTab(`#/companies/${companyId}/tds-adjustments?form=new&${query.replace(/(^|&)year=[^&]*/, "")}&year=${data.start}`)}>
                        Make TDS Adjustment
                      </button>
                    </div>
                  )}
                </>
              )}
            </SidePanel>
            <SidePanel title="Supplier Facts">
              <SideRows
                rows={[
                  ["Ledger Balance", balanceText(data.balance)],
                  ["Deductee Type", data.deductee],
                  ["PAN", s.pan],
                  ["Adjustments So Far", data.adjustments.length ? "" : "None"],
                ]}
              />
              {data.adjustments.map((a) => (
                <div key={a.id} className="side-row">
                  <button type="button" className="link" onClick={() => openTab(`#/companies/${companyId}/tds-adjustments?view=${a.id}`)}>
                    {a.number || "Draft"}
                  </button>
                  <span>
                    {dmy(a.adj_date)} · ₹{gapText(a.total)} · {a.status_label}
                  </span>
                </div>
              ))}
            </SidePanel>
          </div>
        </div>
      )}
    </section>
  );
}
