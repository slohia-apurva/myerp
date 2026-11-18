import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Chevron, LevelPicker, PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu } from "./Exchange";
import { openTab } from "./Master";
import { dmy, EntryLink, rupees } from "./Reports";

/** Accounts reports, read straight from the general ledger (Sidharth, 2026-11-18,
 * preview mockups/reports/1-reports-preview.png): the Trial Balance under the
 * ledger groups, and the Ledger Statement of one ledger. */

type TbRow = {
  kind: "group" | "ledger";
  id: number;
  name: string;
  depth: number;
  parent: number | null;
  opening: string;
  debit: string;
  credit: string;
  closing: string;
};
type TrialBalance = {
  company_name: string;
  from: string;
  to: string;
  rows: TbRow[];
  total: { opening: string; debit: string; credit: string; closing: string };
};
type Entry = { type: string; type_label: string; id: number; number: string; page: string };
type StatementRow = {
  date: string;
  entry: Entry;
  cancel: boolean;
  particulars: string;
  remarks: string;
  debit: string;
  credit: string;
  balance: string;
};
type Statement = {
  company_name: string;
  ledger: number;
  ledger_name: string;
  group_name: string;
  from: string;
  to: string;
  opening: string;
  rows: StatementRow[];
  total_debit: string;
  total_credit: string;
  closing: string;
};

const today = () => new Date().toISOString().slice(0, 10);

/** A signed balance (debit positive) as "1,000.00 Dr" or "1,000.00 Cr"; nothing for zero. */
export function drCr(v: string) {
  const n = Number(v || 0);
  if (n === 0) return "";
  return `${rupees(String(Math.abs(n)))} ${n > 0 ? "Dr" : "Cr"}`;
}
const amount = (v: string) => (Number(v || 0) === 0 ? "" : rupees(v));

function hashParam(key: string): string {
  const query = window.location.hash.split("?")[1] ?? "";
  return new URLSearchParams(query).get(key) ?? "";
}

/** Reports › Trial Balance: every ledger's opening, debits, credits and closing in a period. */
export function TrialBalancePage({ companyId }: { companyId: number }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState(today());
  const [data, setData] = useState<TrialBalance | null>(null);
  const [error, setError] = useState<unknown>("");
  const [folded, setFolded] = useState<Set<number>>(new Set());
  const [level, setLevel] = useState<number | null>(Infinity);
  useEffect(() => {
    const params = new URLSearchParams({ to });
    if (from) params.set("from", from);
    setError("");
    api<TrialBalance>(`v1/companies/${companyId}/trial-balance/?${params}`).then((d) => {
      setData(d);
      if (!from) setFrom(d.from);
    }, setError);
  }, [companyId, from, to]);
  const printing = usePrintMenu({
    title: "Trial Balance",
    scope: [data?.company_name, data && `${dmy(data.from)} to ${dmy(data.to)}`].filter(Boolean).join(" · "),
  });
  const groups = useMemo(() => (data?.rows ?? []).filter((r) => r.kind === "group"), [data]);
  const deepest = Math.max(0, ...groups.map((g) => g.depth));
  const showLevels = (n: number) => {
    setLevel(n);
    setFolded(new Set(groups.filter((g) => g.depth >= n - 1).map((g) => g.id)));
  };
  const toggle = (id: number) =>
    setFolded((f) => {
      setLevel(null);
      const next = new Set(f);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  // A row shows when no group above it is folded.
  const visible = useMemo(() => {
    const parentOf = new Map(groups.map((g) => [g.id, g.parent]));
    const hidden = (r: TbRow) => {
      for (let p = r.parent; p != null; p = parentOf.get(p) ?? null) if (folded.has(p)) return true;
      return false;
    };
    return (data?.rows ?? []).filter((r) => !hidden(r));
  }, [data, groups, folded]);
  const openLedger = (id: number) =>
    openTab(`#/companies/${companyId}/ledger-statement?${new URLSearchParams({ ledger: String(id), from, to })}`);
  const diff = data ? Number(data.total.debit) - Number(data.total.credit) : 0;

  return (
    <section className="page">
      <PageHeader
        title="Trial Balance"
        sub={`${data?.company_name ?? ""}: each ledger's opening, debits, credits and closing, under its groups.`}
        actions={printing.buttons}
      />
      {printing.panel}
      <Section title="Show">
        <div className="row report-filters">
          <label>
            From
            <input type="date" value={from} max="9999-12-31" onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label>
            To
            <input type="date" value={to} max="9999-12-31" onChange={(e) => setTo(e.target.value || today())} />
          </label>
        </div>
        <LevelPicker levels={deepest + 1} value={level} onPick={showLevels} />
      </Section>
      <ErrorNote error={error} />
      {data && data.rows.length === 0 && <p className="small">No balances or entries in this period.</p>}
      {data && data.rows.length > 0 && (
        <table className="report" data-title="Trial Balance">
          <thead>
            <tr>
              <th>Ledger Group / Ledger</th>
              <th className="num">Opening ₹</th>
              <th className="num">Debit ₹</th>
              <th className="num">Credit ₹</th>
              <th className="num">Closing ₹</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={`${r.kind}${r.id}`} className={r.kind === "group" ? "report-l1" : ""}>
                <td style={{ paddingLeft: 10 + r.depth * 22 }}>
                  {r.kind === "group" ? (
                    <>
                      <button
                        className="fold no-print"
                        aria-expanded={!folded.has(r.id)}
                        aria-label={`${folded.has(r.id) ? "Show" : "Hide"} what is under ${r.name}`}
                        onClick={() => toggle(r.id)}
                      >
                        <Chevron open={!folded.has(r.id)} />
                      </button>{" "}
                      {r.name}
                    </>
                  ) : (
                    <a
                      href={`#/companies/${companyId}/ledger-statement?ledger=${r.id}`}
                      title="Open the Ledger Statement"
                      onClick={(e) => {
                        e.preventDefault();
                        openLedger(r.id);
                      }}
                    >
                      {r.name}
                    </a>
                  )}
                </td>
                <td className="num">{drCr(r.opening)}</td>
                <td className="num">{amount(r.debit)}</td>
                <td className="num">{amount(r.credit)}</td>
                <td className="num">{drCr(r.closing)}</td>
              </tr>
            ))}
            <tr className="report-total">
              <td>Total</td>
              <td className="num">{drCr(data.total.opening)}</td>
              <td className="num">{rupees(data.total.debit)}</td>
              <td className="num">{rupees(data.total.credit)}</td>
              <td className="num">{drCr(data.total.closing)}</td>
            </tr>
          </tbody>
        </table>
      )}
      {data && data.rows.length > 0 && (
        <p className={`small no-print${diff ? " error" : ""}`}>
          {diff
            ? `Debits and credits differ by ${rupees(String(Math.abs(diff)))}. The opening balances entered on the ledgers do not add up.`
            : "Debits equal credits. Click a ledger to open its Ledger Statement."}
        </p>
      )}
    </section>
  );
}

type LedgerPick = { id: number; name: string; group_name?: string };

/** Reports › Ledger Statement: every entry to one ledger, with the balance after each. */
export function LedgerStatementPage({ companyId }: { companyId: number }) {
  const [ledgers, setLedgers] = useState<LedgerPick[]>([]);
  const [ledger, setLedger] = useState(hashParam("ledger"));
  const [from, setFrom] = useState(hashParam("from"));
  const [to, setTo] = useState(hashParam("to") || today());
  const [data, setData] = useState<Statement | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    api<LedgerPick[]>(`v1/companies/${companyId}/ledgers/`).then(setLedgers);
  }, [companyId]);
  useEffect(() => {
    if (!ledger) {
      setData(null);
      return;
    }
    const params = new URLSearchParams({ ledger, to });
    if (from) params.set("from", from);
    setError("");
    api<Statement>(`v1/companies/${companyId}/ledger-statement/?${params}`).then((d) => {
      setData(d);
      if (!from) setFrom(d.from);
    }, setError);
  }, [companyId, ledger, from, to]);
  const title = data ? `Ledger Statement: ${data.ledger_name}` : "Ledger Statement";
  const printing = usePrintMenu({
    title,
    scope: [data?.company_name, data?.group_name, data && `${dmy(data.from)} to ${dmy(data.to)}`].filter(Boolean).join(" · "),
  });

  return (
    <section className="page">
      <PageHeader
        title={title}
        sub={data ? `${data.group_name}: every entry, with the balance after each.` : "Pick a ledger to see every entry to it."}
        actions={printing.buttons}
      />
      {printing.panel}
      <Section title="Show">
        <div className="row report-filters">
          <label>
            Ledger
            <Combobox
              options={ledgers.map((l) => ({ value: String(l.id), label: l.name, hint: l.group_name }))}
              value={ledger}
              onChange={setLedger}
              placeholder="Pick a ledger"
              ariaLabel="Ledger"
            />
          </label>
          <label>
            From
            <input type="date" value={from} max="9999-12-31" onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label>
            To
            <input type="date" value={to} max="9999-12-31" onChange={(e) => setTo(e.target.value || today())} />
          </label>
        </div>
      </Section>
      <ErrorNote error={error} />
      {data && (
        <table className="report" data-title={title}>
          <thead>
            <tr>
              <th>Date</th>
              <th>Entry</th>
              <th>Particulars</th>
              <th className="num">Debit ₹</th>
              <th className="num">Credit ₹</th>
              <th className="num">Balance ₹</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{dmy(data.from)}</td>
              <td>
                <i>Opening</i>
              </td>
              <td />
              <td />
              <td />
              <td className="num">{drCr(data.opening) || "0.00"}</td>
            </tr>
            {data.rows.map((r, n) => (
              <tr key={n} className={r.cancel ? "inactive" : ""}>
                <td>{dmy(r.date)}</td>
                <td>
                  <EntryLink companyId={companyId} entry={r.entry} />
                  <span className="small">
                    {" "}
                    {r.entry.type_label}
                    {r.cancel ? " (cancelled)" : ""}
                  </span>
                </td>
                <td>
                  {r.particulars}
                  {r.remarks && <div className="small">{r.remarks}</div>}
                </td>
                <td className="num">{amount(r.debit)}</td>
                <td className="num">{amount(r.credit)}</td>
                <td className="num">{drCr(r.balance) || "0.00"}</td>
              </tr>
            ))}
            <tr className="report-total">
              <td>{dmy(data.to)}</td>
              <td>Closing</td>
              <td />
              <td className="num">{rupees(data.total_debit)}</td>
              <td className="num">{rupees(data.total_credit)}</td>
              <td className="num">{drCr(data.closing) || "0.00"}</td>
            </tr>
          </tbody>
        </table>
      )}
      {data && data.rows.length === 0 && <p className="small">No entries in this period.</p>}
    </section>
  );
}
