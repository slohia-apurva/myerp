import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, SignedIn } from "./api";
import { longDate, money, type Company, type Group } from "./Companies";

type Ledger = {
  id: number;
  name: string;
  group: number;
  group_name: string;
  nature: string;
  is_active: boolean;
  notes: string;
  bank_name: string;
  account_number: string;
  ifsc: string;
  bank_branch: string;
  opening_amount: string;
  opening_side: Side;
  bill_wise: boolean;
  opening_bills: Bill[];
  currency: string | null;
  opening_fc_amount: string;
  opening_rate: string | null;
};
type Currency = { code: string; name: string; symbol: string };
type Side = "dr" | "cr";
type Bill = {
  ref: string;
  bill_date: string;
  due_date: string | null;
  amount: string;
  side: Side;
  fc_amount?: string | null;
  rate?: string | null;
};
type Detail = { company: Company; ledger_groups: Group[] };

const NATURE: Record<string, string> = { asset: "Asset", liability: "Liability", income: "Income", expense: "Expense" };

// Groups in tree order, each with its depth, for indented pickers.
function treeOrder(groups: Group[]): { group: Group; depth: number }[] {
  const children = new Map<number | null, Group[]>();
  for (const g of groups) children.set(g.parent, [...(children.get(g.parent) ?? []), g]);
  const out: { group: Group; depth: number }[] = [];
  const walk = (parent: number | null, depth: number) => {
    for (const g of children.get(parent) ?? []) {
      out.push({ group: g, depth });
      walk(g.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

function GroupSelect(props: { groups: { group: Group; depth: number }[]; value: string; onChange: (v: string) => void; all?: string }) {
  return (
    <select value={props.value} required={!props.all} onChange={(e) => props.onChange(e.target.value)}>
      <option value="">{props.all ?? "Choose a group…"}</option>
      {props.groups.map(({ group, depth }) => (
        <option key={group.id} value={group.id}>
          {"   ".repeat(depth)}
          {group.name}
        </option>
      ))}
    </select>
  );
}

export function LedgersPage(props: { companyId: number; groupId?: number; session: SignedIn }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [ledgers, setLedgers] = useState<Ledger[]>([]);
  const [query, setQuery] = useState("");
  const [groupFilter, setGroupFilter] = useState(props.groupId ? String(props.groupId) : "");
  const [editing, setEditing] = useState<Ledger | "new" | null>(null);
  const [error, setError] = useState("");
  const canEdit = props.session.permissions.includes("masters.edit");
  const ordered = useMemo(() => treeOrder(detail?.ledger_groups ?? []), [detail]);

  useEffect(() => {
    api<Detail>(`v1/companies/${props.companyId}/`)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [props.companyId]);

  const reload = useCallback(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (groupFilter) params.set("group", groupFilter);
    api<Ledger[]>(`v1/companies/${props.companyId}/ledgers/?${params}`)
      .then(setLedgers)
      .catch((err: Error) => setError(err.message));
  }, [props.companyId, query, groupFilter]);
  useEffect(() => {
    const timer = window.setTimeout(reload, 200);
    return () => window.clearTimeout(timer);
  }, [reload]);

  if (!detail) return <section className="page">{error ? <p className="error">{error}</p> : <p>Loading…</p>}</section>;
  return (
    <section className="page">
      <p className="small">
        <a href="#/companies">Companies</a> › <a href={`#/companies/${props.companyId}`}>{detail.company.name}</a>
      </p>
      <div className="page-head">
        <h2>Ledgers</h2>
        {canEdit && <button onClick={() => setEditing("new")}>Add ledger</button>}
      </div>
      {error && <p className="error">{error}</p>}
      {editing && (
        <LedgerForm
          companyId={props.companyId}
          ledger={editing === "new" ? null : editing}
          groups={ordered}
          defaultGroup={groupFilter}
          booksStart={detail.company.books_start}
          multiCurrency={detail.company.multi_currency}
          onDone={() => {
            setEditing(null);
            reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      <div className="row filters">
        <input type="search" placeholder="Search by name or account number" value={query} onChange={(e) => setQuery(e.target.value)} />
        <GroupSelect groups={ordered} value={groupFilter} onChange={setGroupFilter} all="All groups" />
      </div>
      <table>
        <thead>
          <tr>
            <th>Ledger</th>
            <th>Group</th>
            <th>Nature</th>
            <th className="num">Opening</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {ledgers.length === 0 && (
            <tr>
              <td colSpan={5} className="small">
                No ledgers match.
              </td>
            </tr>
          )}
          {ledgers.map((l) => (
            <tr key={l.id} className={l.is_active ? "" : "inactive"}>
              <td>
                {l.name}
                {!l.is_active && <span className="small"> · inactive</span>}
                {l.account_number && (
                  <>
                    <br />
                    <span className="small">
                      {[l.bank_name, l.account_number, l.ifsc].filter(Boolean).join(" · ")}
                    </span>
                  </>
                )}
              </td>
              <td>{l.group_name}</td>
              <td>{NATURE[l.nature]}</td>
              <td className="num">
                {Number(l.opening_amount) === 0 ? (
                  <span className="small">—</span>
                ) : (
                  <>
                    {money(l.opening_amount)} {l.opening_side === "dr" ? "Dr" : "Cr"}
                    {l.currency && (
                      <>
                        <br />
                        <span className="small">
                          {l.currency} {money(l.opening_fc_amount)}
                        </span>
                      </>
                    )}
                  </>
                )}
              </td>
              <td>
                {canEdit && (
                  <button className="link" onClick={() => setEditing(l)}>
                    Edit
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function LedgerForm(props: {
  companyId: number;
  ledger: Ledger | null;
  groups: { group: Group; depth: number }[];
  defaultGroup: string;
  booksStart: string;
  multiCurrency: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const l = props.ledger;
  const [name, setName] = useState(l?.name ?? "");
  const [group, setGroup] = useState(l ? String(l.group) : props.defaultGroup);
  const [notes, setNotes] = useState(l?.notes ?? "");
  const [active, setActive] = useState(l?.is_active ?? true);
  const [bankName, setBankName] = useState(l?.bank_name ?? "");
  const [accountNumber, setAccountNumber] = useState(l?.account_number ?? "");
  const [ifsc, setIfsc] = useState(l?.ifsc ?? "");
  const [bankBranch, setBankBranch] = useState(l?.bank_branch ?? "");
  const [openingAmount, setOpeningAmount] = useState(l && Number(l.opening_amount) ? l.opening_amount : "");
  const [openingSide, setOpeningSide] = useState<Side>(l?.opening_side ?? "dr");
  const groupOf = (id: string) => props.groups.find((g) => String(g.group.id) === id)?.group;
  const [billWise, setBillWise] = useState(l ? l.bill_wise : (groupOf(props.defaultGroup)?.bill_wise_default ?? false));
  const [bills, setBills] = useState<Bill[]>(l?.opening_bills ?? []);
  const [currency, setCurrency] = useState(l?.currency ?? "");
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [fcAmount, setFcAmount] = useState(l && Number(l.opening_fc_amount) ? l.opening_fc_amount : "");
  const [rate, setRate] = useState(l?.opening_rate ?? "");
  useEffect(() => {
    if (props.multiCurrency) api<Currency[]>("v1/currencies/").then(setCurrencies);
  }, [props.multiCurrency]);
  const foreign = currency !== "" && currency !== "INR";
  const inr = (fc: string | null | undefined, r: string | null | undefined) =>
    Math.round((Number(fc) || 0) * (Number(r) || 0) * 100) / 100;
  const [error, setError] = useState("");
  const chosen = groupOf(group);
  const isBank = chosen?.is_bank ?? false;
  const usualSide: Side = chosen?.nature === "asset" || chosen?.nature === "expense" ? "dr" : "cr";

  const pickGroup = (id: string) => {
    setGroup(id);
    // A new ledger under Sundry Debtors or Creditors is bill-wise by default.
    if (!l) {
      const g = groupOf(id);
      setBillWise(g?.bill_wise_default ?? false);
      setOpeningSide(g?.nature === "asset" || g?.nature === "expense" ? "dr" : "cr");
    }
  };
  // For a bill-wise ledger the opening balance is the total of its bills.
  const billInr = (b: Bill) => (foreign ? inr(b.fc_amount, b.rate) : Number(b.amount) || 0);
  const billsTotal = bills.reduce((t, b) => t + billInr(b) * (b.side === "dr" ? 1 : -1), 0);
  const billsFcTotal = bills.reduce((t, b) => t + (Number(b.fc_amount) || 0) * (b.side === "dr" ? 1 : -1), 0);
  const setBill = (i: number, change: Partial<Bill>) => setBills(bills.map((b, j) => (j === i ? { ...b, ...change } : b)));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = {
      name,
      group: Number(group),
      notes,
      is_active: active,
      bank_name: bankName,
      account_number: accountNumber,
      ifsc,
      bank_branch: bankBranch,
      bill_wise: billWise,
      currency: foreign ? currency : null,
      ...(billWise
        ? {
            opening_amount: Math.abs(billsTotal).toFixed(2),
            opening_side: billsTotal < 0 ? "cr" : "dr",
            opening_bills: bills.map((b) =>
              foreign
                ? { ...b, due_date: b.due_date || null, amount: undefined }
                : { ...b, due_date: b.due_date || null, fc_amount: null, rate: null },
            ),
          }
        : foreign
          ? { opening_fc_amount: fcAmount || "0", opening_rate: rate || null, opening_side: openingSide }
          : { opening_amount: openingAmount || "0", opening_side: openingSide }),
    };
    try {
      if (l) await api(`v1/ledgers/${l.id}/`, body, "PATCH");
      else await api(`v1/companies/${props.companyId}/ledgers/`, body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <form className="card" onSubmit={save}>
      <h3>{l ? `Edit ${l.name}` : "Add ledger"}</h3>
      <div className="row">
        <label>
          Name
          <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Under group
          <GroupSelect groups={props.groups} value={group} onChange={pickGroup} />
        </label>
      </div>
      {props.multiCurrency && (
        <label>
          Currency
          <select value={currency || "INR"} onChange={(e) => setCurrency(e.target.value === "INR" ? "" : e.target.value)}>
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code} · {c.name}
                {c.code === "INR" ? " (base)" : ""}
              </option>
            ))}
          </select>
        </label>
      )}
      {isBank && (
        <fieldset>
          <legend>Bank details</legend>
          <div className="row">
            <label>
              Bank
              <input value={bankName} onChange={(e) => setBankName(e.target.value)} placeholder="e.g. HDFC Bank" />
            </label>
            <label>
              Account number
              <input value={accountNumber} onChange={(e) => setAccountNumber(e.target.value)} />
            </label>
          </div>
          <div className="row">
            <label>
              IFSC
              <input value={ifsc} maxLength={11} onChange={(e) => setIfsc(e.target.value.toUpperCase())} />
            </label>
            <label>
              Branch
              <input value={bankBranch} onChange={(e) => setBankBranch(e.target.value)} />
            </label>
          </div>
        </fieldset>
      )}
      <fieldset>
        <legend>Opening balance as at {longDate(props.booksStart)}</legend>
        <label className="check">
          <input type="checkbox" checked={billWise} onChange={(e) => setBillWise(e.target.checked)} />
          Maintain balances bill by bill (customers, suppliers)
        </label>
        {billWise ? (
          <>
            <table className="grid">
              <thead>
                <tr>
                  <th>Bill reference</th>
                  <th>Bill date</th>
                  <th>Due date</th>
                  {foreign && <th className="num">Amount ({currency})</th>}
                  {foreign && <th className="num">Rate</th>}
                  <th className="num">Amount (₹)</th>
                  <th>Dr/Cr</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {bills.map((b, i) => (
                  <tr key={i}>
                    <td>
                      <input required value={b.ref} onChange={(e) => setBill(i, { ref: e.target.value })} />
                    </td>
                    <td>
                      <input required type="date" value={b.bill_date} onChange={(e) => setBill(i, { bill_date: e.target.value })} />
                    </td>
                    <td>
                      <input type="date" value={b.due_date ?? ""} onChange={(e) => setBill(i, { due_date: e.target.value })} />
                    </td>
                    {foreign && (
                      <td>
                        <input
                          required
                          className="num"
                          inputMode="decimal"
                          value={b.fc_amount ?? ""}
                          onChange={(e) => setBill(i, { fc_amount: e.target.value })}
                        />
                      </td>
                    )}
                    {foreign && (
                      <td>
                        <input
                          required
                          className="num"
                          inputMode="decimal"
                          value={b.rate ?? ""}
                          onChange={(e) => setBill(i, { rate: e.target.value })}
                        />
                      </td>
                    )}
                    <td>
                      {foreign ? (
                        <div className="num">{money(billInr(b))}</div>
                      ) : (
                        <input
                          required
                          className="num"
                          inputMode="decimal"
                          value={b.amount}
                          onChange={(e) => setBill(i, { amount: e.target.value })}
                        />
                      )}
                    </td>
                    <td>
                      <select value={b.side} onChange={(e) => setBill(i, { side: e.target.value as Side })}>
                        <option value="dr">Dr</option>
                        <option value="cr">Cr</option>
                      </select>
                    </td>
                    <td>
                      <button type="button" className="link danger" onClick={() => setBills(bills.filter((_, j) => j !== i))}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3}>
                    <button
                      type="button"
                      className="link"
                      onClick={() =>
                        setBills([...bills, { ref: "", bill_date: "", due_date: null, amount: "", side: usualSide, fc_amount: "", rate: "" }])
                      }
                    >
                      Add bill
                    </button>
                  </td>
                  {foreign && (
                    <td className="num">
                      <strong>{money(Math.abs(billsFcTotal))}</strong>
                    </td>
                  )}
                  {foreign && <td />}
                  <td className="num">
                    <strong>{money(Math.abs(billsTotal))}</strong>
                  </td>
                  <td>
                    <strong>{billsTotal < 0 ? "Cr" : "Dr"}</strong>
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
            <p className="small">
              The opening balance is the total of the bills. Bills must be dated before {longDate(props.booksStart)}.
            </p>
          </>
        ) : (
          <div className="row">
            {foreign ? (
              <>
                <label>
                  Amount ({currency})
                  <input className="num" inputMode="decimal" placeholder="0.00" value={fcAmount} onChange={(e) => setFcAmount(e.target.value)} />
                </label>
                <label>
                  Rate (₹ per {currency})
                  <input className="num" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} />
                </label>
                <label>
                  Amount (₹)
                  <input className="num" readOnly value={money(inr(fcAmount, rate))} />
                </label>
              </>
            ) : (
              <label>
                Amount
                <input
                  className="num"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={openingAmount}
                  onChange={(e) => setOpeningAmount(e.target.value)}
                />
              </label>
            )}
            <label>
              Dr/Cr
              <select value={openingSide} onChange={(e) => setOpeningSide(e.target.value as Side)}>
                <option value="dr">Dr</option>
                <option value="cr">Cr</option>
              </select>
            </label>
          </div>
        )}
      </fieldset>
      <label>
        Notes
        <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {l && (
        <label className="check">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          Active (ledgers are never deleted; untick to stop new entries)
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button>{l ? "Save" : "Add ledger"}</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
