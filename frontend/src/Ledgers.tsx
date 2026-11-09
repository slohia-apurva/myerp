import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { blankParty, PartyFields, PartySummary, type Party } from "./Parties";
import { longDate, money, useStates, type Company, type Group } from "./Companies";
import { Chevron, LevelPicker, PageHeader } from "./Brand";

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
  party: Party | null;
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
  const [selectedId, setSelectedId] = useState<number | null>(null);
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

  // The list follows the group tree: each group with ledgers (directly or below it)
  // gets a heading row, its own ledgers come next, then its sub-groups.
  const [folded, setFolded] = useState<Set<number>>(new Set());
  const [level, setLevel] = useState<number | null>(Infinity);
  const tree = useMemo(() => {
    const own = new Map<number, Ledger[]>();
    for (const l of ledgers) own.set(l.group, [...(own.get(l.group) ?? []), l]);
    const groups = detail?.ledger_groups ?? [];
    const count = new Map<number, number>();
    const net = new Map<number, number>();
    const signed = (l: Ledger) => Number(l.opening_amount) * (l.opening_side === "dr" ? 1 : -1);
    const fill = (g: Group): [number, number] => {
      let c = own.get(g.id)?.length ?? 0;
      let n = (own.get(g.id) ?? []).reduce((t, l) => t + signed(l), 0);
      for (const k of groups.filter((x) => x.parent === g.id)) {
        const [kc, kn] = fill(k);
        c += kc;
        n += kn;
      }
      count.set(g.id, c);
      net.set(g.id, n);
      return [c, n];
    };
    groups.filter((g) => g.parent === null).forEach(fill);
    const rows: ({ kind: "group"; group: Group; depth: number } | { kind: "ledger"; ledger: Ledger; depth: number })[] = [];
    let hideBelow: number | null = null;
    for (const { group, depth } of ordered) {
      if (hideBelow !== null && depth > hideBelow) continue;
      hideBelow = null;
      if (!count.get(group.id)) continue;
      rows.push({ kind: "group", group, depth });
      if (folded.has(group.id)) {
        hideBelow = depth;
        continue;
      }
      for (const l of own.get(group.id) ?? []) rows.push({ kind: "ledger", ledger: l, depth: depth + 1 });
    }
    return { rows, count, net };
  }, [ledgers, detail, ordered, folded]);
  const visible = tree.rows.flatMap((r) => (r.kind === "ledger" ? [r.ledger] : []));
  const deepest = Math.max(0, ...ordered.map((o) => o.depth));
  const showLevels = (n: number) => {
    setLevel(n);
    setFolded(new Set(ordered.filter((o) => o.depth >= n - 1).map((o) => o.group.id)));
  };
  const toggle = (id: number) =>
    setFolded((f) => {
      setLevel(null);
      const next = new Set(f);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Keep a ledger selected: the first in the list until the person picks one.
  const selected = ledgers.find((l) => l.id === selectedId) ?? visible[0] ?? null;
  const pick = (l: Ledger) => {
    setSelectedId(l.id);
    setEditing(null);
  };
  const onListKey = (e: KeyboardEvent<HTMLTableSectionElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const at = selected ? visible.findIndex((l) => l.id === selected.id) : -1;
    const next = visible[Math.min(visible.length - 1, Math.max(0, at + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) {
      pick(next);
      document.getElementById(`ledger-${next.id}`)?.focus();
    }
  };
  const dc = (n: number) => (n === 0 ? "" : `${money(Math.abs(n))} ${n > 0 ? "Dr" : "Cr"}`);

  if (!detail) return <section className="page">{error ? <p className="error">{error}</p> : <p>Loading…</p>}</section>;
  return (
    <section className="page">
      <PageHeader
        title="Ledgers"
        crumbs={[
          { label: "Companies", href: "#/companies" },
          { label: detail.company.name, href: `#/companies/${props.companyId}` },
        ]}
        sub={`${ledgers.length} ${ledgers.length === 1 ? "ledger" : "ledgers"}${query || groupFilter ? " match" : ""}`}
        actions={
          <>
            <a className="button" href={`#/companies/${props.companyId}/groups`}>
              Ledger groups
            </a>
            {canEdit && <button onClick={() => setEditing("new")}>Add ledger</button>}
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      <div className={`split${editing ? " editing" : ""}`}>
        <div className="split-list">
          <div className="row filters">
            <input
              type="search"
              placeholder="Search by name or account number"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <GroupSelect groups={ordered} value={groupFilter} onChange={setGroupFilter} all="All groups" />
          </div>
          <div className="list-tools">
            <LevelPicker levels={deepest + 1} value={level} onPick={showLevels} />
          </div>
          <table className="pick by-group">
            <thead>
              <tr>
                <th>Group / ledger</th>
                <th className="num">Opening</th>
              </tr>
            </thead>
            <tbody onKeyDown={onListKey}>
              {tree.rows.length === 0 && (
                <tr>
                  <td colSpan={2} className="small">
                    No ledgers match.
                  </td>
                </tr>
              )}
              {tree.rows.map((r) =>
                r.kind === "group" ? (
                  <tr
                    key={`g${r.group.id}`}
                    className={`group-row depth-${Math.min(r.depth, 2)}`}
                    onClick={() => toggle(r.group.id)}
                  >
                    <td>
                      <span className="group-name" style={{ paddingLeft: r.depth * 18 }}>
                        <button
                          className="fold"
                          aria-expanded={!folded.has(r.group.id)}
                          aria-label={`${folded.has(r.group.id) ? "Show" : "Hide"} ledgers under ${r.group.name}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggle(r.group.id);
                          }}
                        >
                          <Chevron open={!folded.has(r.group.id)} />
                        </button>
                        {r.group.name}
                        <span className="small">({tree.count.get(r.group.id)})</span>
                      </span>
                    </td>
                    <td className="num">{dc(tree.net.get(r.group.id) ?? 0)}</td>
                  </tr>
                ) : (
                  <tr
                    key={r.ledger.id}
                    id={`ledger-${r.ledger.id}`}
                    tabIndex={0}
                    aria-selected={selected?.id === r.ledger.id}
                    className={["ledger-row", r.ledger.is_active ? "" : "inactive", selected?.id === r.ledger.id ? "selected" : ""].join(" ")}
                    onClick={() => pick(r.ledger)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") pick(r.ledger);
                    }}
                  >
                    <td>
                      <span style={{ paddingLeft: r.depth * 18 + 26, display: "inline-block" }}>
                        {r.ledger.name}
                        {!r.ledger.is_active && <span className="small"> · inactive</span>}
                      </span>
                    </td>
                    <td className="num">
                      {Number(r.ledger.opening_amount) === 0 ? <span className="small">—</span> : dc(Number(r.ledger.opening_amount) * (r.ledger.opening_side === "dr" ? 1 : -1))}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
          {visible.length > 1 && <p className="small">Tip: click a ledger, then use ↑ and ↓ to move through the list.</p>}
        </div>
        <aside className="split-panel" aria-label="Ledger details">
          {editing ? (
            <LedgerForm
              key={editing === "new" ? "new" : editing.id}
              companyId={props.companyId}
              ledger={editing === "new" ? null : editing}
              groups={ordered}
              defaultGroup={groupFilter}
              booksStart={detail.company.books_start}
              multiCurrency={detail.company.multi_currency}
              companyState={detail.company.state_code}
              onDone={(saved) => {
                setEditing(null);
                if (saved) setSelectedId(saved);
                reload();
              }}
              onCancel={() => setEditing(null)}
            />
          ) : selected ? (
            <LedgerPanel
              ledger={selected}
              companyId={props.companyId}
              canEdit={canEdit}
              onEdit={() => setEditing(selected)}
            />
          ) : (
            <div className="card">
              <p className="small">Pick a ledger to see its details here.</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

function LedgerPanel(props: { ledger: Ledger; companyId: number; canEdit: boolean; onEdit: () => void }) {
  const { ledger: l, canEdit, onEdit } = props;
  const states = useStates();
  const opening = Number(l.opening_amount);
  const bank = [
    ["Bank", l.bank_name],
    ["Account number", l.account_number],
    ["IFSC", l.ifsc],
    ["Branch", l.bank_branch],
  ].filter(([, v]) => v);
  return (
    <div className="card panel">
      <div className="panel-head">
        <div>
          <h2>{l.name}</h2>
          <p className="small">
            {l.group_name} · {NATURE[l.nature]}
            {!l.is_active && " · inactive"}
          </p>
        </div>
        {canEdit && <button onClick={onEdit}>Edit</button>}
      </div>
      <div className="stat">
        <span className="stat-label">Opening balance</span>
        <span className="stat-value">
          {opening === 0 ? "Nil" : `${money(l.opening_amount)} ${l.opening_side === "dr" ? "Dr" : "Cr"}`}
        </span>
        {l.currency && opening !== 0 && (
          <span className="stat-note">
            {l.currency} {money(l.opening_fc_amount)}
            {l.opening_rate && ` at ${Number(l.opening_rate)}`}
          </span>
        )}
      </div>
      <dl className="kv">
        <div>
          <dt>Currency</dt>
          <dd>{l.currency || "INR"}</dd>
        </div>
        <div>
          <dt>Bill-wise</dt>
          <dd>{l.bill_wise ? "Yes" : "No"}</dd>
        </div>
        {bank.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {l.party && <PartySummary party={l.party} states={states} />}
      {l.bill_wise && l.opening_bills.length > 0 && (
        <>
          <h3>Opening bills</h3>
          <table>
            <thead>
              <tr>
                <th>Bill</th>
                <th>Date</th>
                <th>Due</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {l.opening_bills.map((b, i) => (
                <tr key={i}>
                  <td>{b.ref}</td>
                  <td>{longDate(b.bill_date)}</td>
                  <td>{b.due_date ? longDate(b.due_date) : "—"}</td>
                  <td className="num">
                    {money(b.amount)} {b.side === "dr" ? "Dr" : "Cr"}
                    {b.fc_amount && Number(b.fc_amount) !== 0 && (
                      <>
                        <br />
                        <span className="small">
                          {l.currency} {money(b.fc_amount)}
                        </span>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {l.notes && (
        <>
          <h3>Notes</h3>
          <p className="pre">{l.notes}</p>
        </>
      )}
      <div className="panel-activity">
        <h3>Activity</h3>
        <ChangeLog company={props.companyId} type="ledger" id={l.id} stamp={JSON.stringify(l)} />
      </div>
    </div>
  );
}

function LedgerForm(props: {
  companyId: number;
  ledger: Ledger | null;
  groups: { group: Group; depth: number }[];
  defaultGroup: string;
  booksStart: string;
  multiCurrency: boolean;
  companyState: string;
  onDone: (savedId?: number) => void;
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
  const [party, setParty] = useState<Party>(l?.party ?? blankParty(props.companyState));
  useEffect(() => {
    if (props.multiCurrency) api<Currency[]>("v1/currencies/").then(setCurrencies);
  }, [props.multiCurrency]);
  const foreign = currency !== "" && currency !== "INR";
  const inr = (fc: string | null | undefined, r: string | null | undefined) =>
    Math.round((Number(fc) || 0) * (Number(r) || 0) * 100) / 100;
  const [error, setError] = useState("");
  const chosen = groupOf(group);
  const isBank = chosen?.is_bank ?? false;
  // Ledgers under Sundry Debtors or Creditors are customers and suppliers.
  const isParty = chosen?.bill_wise_default ?? false;
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
      ...(isParty ? { party: { ...party, credit_limit: party.credit_limit || "0" } } : {}),
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
      const saved = l
        ? await api<Ledger>(`v1/ledgers/${l.id}/`, body, "PATCH")
        : await api<Ledger>(`v1/companies/${props.companyId}/ledgers/`, body);
      props.onDone(saved?.id);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const openingFields = (
    <>
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
    </>
  );
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
      {isParty && (
        <PartyFields
          value={party}
          onChange={setParty}
          companyId={props.companyId}
          extraTab={{
            label: "Opening balance",
            content: (
              <>
                <p className="small">As at {longDate(props.booksStart)}, the day the books begin.</p>
                {openingFields}
              </>
            ),
          }}
        />
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
      {!isParty && (
        <fieldset>
          <legend>Opening balance as at {longDate(props.booksStart)}</legend>
          {openingFields}
        </fieldset>
      )}
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
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
