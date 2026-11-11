import { Combobox } from "./Combobox";
import { creatable, type Creatable } from "./Create";
import { ErrorNote, useOpenParam } from "./ErrorNote";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { blankParty, GstinField, PartyFields, PartyNumber, PartySummary, PartyTabBar, type Party, type PartyTab } from "./Parties";
import { longDate, money, useStates, type Company, type Group } from "./Companies";
import { Chevron, LevelPicker, PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { ActiveButton } from "./RowActions";

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
const SIDES = [
  { value: "dr", label: "Dr" },
  { value: "cr", label: "Cr" },
];
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

function GroupSelect(props: {
  groups: { group: Group; depth: number }[];
  value: string;
  onChange: (v: string) => void;
  all?: string;
  create?: Creatable;
}) {
  return (
    <Combobox
      value={props.value}
      required={!props.all}
      empty={props.all}
      placeholder="Type to search groups…"
      options={props.groups.map(({ group, depth }) => ({ value: String(group.id), label: group.name, indent: depth }))}
      onChange={props.onChange}
      create={props.create}
    />
  );
}

export function LedgersPage(props: { companyId: number; groupId?: number; session: SignedIn }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [ledgers, setLedgers] = useState<Ledger[]>([]);
  const [query, setQuery] = useState("");
  const [groupFilter, setGroupFilter] = useState(props.groupId ? String(props.groupId) : "");
  const [editing, setEditingNow] = useState<Ledger | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<Ledger | null>(null);
  const setEditing = (value: Ledger | "new" | null) => {
    setCopyOf(null); // only the Duplicate button below sets it again
    setEditingNow(value);
  };
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const canEdit = props.session.permissions.includes("masters.edit");
  const ordered = useMemo(() => treeOrder(detail?.ledger_groups ?? []), [detail]);

  const loadDetail = useCallback(
    () =>
      api<Detail>(`v1/companies/${props.companyId}/`)
        .then(setDetail)
        .catch((err: Error) => setError(err.message)),
    [props.companyId],
  );
  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

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
  const io = useExchange({
    master: "ledgers",
    noun: "ledgers",
    session: props.session,
    company: props.companyId,
    onImported: reload,
  });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (!openId) return;
    if (ledgers.some((l) => l.id === openId)) {
      setSelectedId(openId);
      setEditing(null);
      opened();
    } else if (query || groupFilter) {
      // Show the whole list so the ledger asked for is in it.
      setQuery("");
      setGroupFilter("");
    }
  }, [openId, ledgers, query, groupFilter, opened]);

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
            {io.buttons}
            {canEdit && <button onClick={() => setEditing("new")}>Add ledger</button>}
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {io.panel}
      <div className={`split${editing ? " editing" : ""}`}>
        <div className="split-list">
          <div className="row filters">
            <input
              type="search"
              placeholder="Search by name, account number or customer or vendor number"
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
              key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
              companyId={props.companyId}
              ledger={editing === "new" ? null : editing}
              copyOf={copyOf}
              groups={ordered}
              createGroup={creatable("ledger_group", `companies/${props.companyId}/groups`, loadDetail)}
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
              onDuplicate={() => {
                setEditingNow("new");
                setCopyOf(selected);
              }}
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

function LedgerPanel(props: {
  ledger: Ledger;
  companyId: number;
  canEdit: boolean;
  onEdit: () => void;
  onDuplicate: () => void;
}) {
  const { ledger: l, canEdit, onEdit, onDuplicate } = props;
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
        {canEdit && (
          <div className="buttons">
            <button onClick={onEdit}>Edit</button>
            <button type="button" className="link" onClick={onDuplicate}>
              Duplicate
            </button>
          </div>
        )}
      </div>
      <Section title="Balance">
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
      </Section>
      {l.party && <PartySummary party={l.party} states={states} supplier={l.nature === "liability"} />}
      {l.bill_wise && l.opening_bills.length > 0 && (
        <Section title="Opening bills">
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
        </Section>
      )}
      {l.notes && (
        <Section title="Notes">
          <p className="pre">{l.notes}</p>
        </Section>
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
  /** Duplicate: start as a copy of this ledger, saved as a new one. */
  copyOf?: Ledger | null;
  groups: { group: Group; depth: number }[];
  createGroup?: Creatable;
  defaultGroup: string;
  booksStart: string;
  multiCurrency: boolean;
  companyState: string;
  onDone: (savedId?: number) => void;
  onCancel: () => void;
}) {
  const l = props.ledger;
  // A duplicate copies the setup, not the name, account number, party numbers or balances.
  const c = props.copyOf;
  const from = l ?? c;
  const [name, setName] = useState(l?.name ?? (c ? `${c.name} (copy)` : ""));
  const [group, setGroup] = useState(from ? String(from.group) : props.defaultGroup);
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [tab, setTab] = useState<PartyTab>("general");
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    // A required field left empty on a hidden tab: open that tab and point at it.
    const el = formRef.current;
    if (!el) return;
    const onInvalid = (e: Event) => {
      const target = e.target as HTMLInputElement;
      const panel = target.closest<HTMLElement>("[data-tab]");
      if (panel?.hidden) {
        setTab(panel.dataset.tab as PartyTab);
        requestAnimationFrame(() => target.reportValidity());
      }
    };
    el.addEventListener("invalid", onInvalid, true);
    return () => el.removeEventListener("invalid", onInvalid, true);
  }, []);
  const [bankName, setBankName] = useState(from?.bank_name ?? "");
  const [accountNumber, setAccountNumber] = useState(l?.account_number ?? "");
  const [ifsc, setIfsc] = useState(from?.ifsc ?? "");
  const [bankBranch, setBankBranch] = useState(from?.bank_branch ?? "");
  const [openingAmount, setOpeningAmount] = useState(l && Number(l.opening_amount) ? l.opening_amount : "");
  const [openingSide, setOpeningSide] = useState<Side>(l?.opening_side ?? "dr");
  const groupOf = (id: string) => props.groups.find((g) => String(g.group.id) === id)?.group;
  const [billWise, setBillWise] = useState(
    l ? l.bill_wise : (groupOf(from ? String(from.group) : props.defaultGroup)?.bill_wise_default ?? false),
  );
  const [bills, setBills] = useState<Bill[]>(l?.opening_bills ?? []);
  const [currency, setCurrency] = useState(from?.currency ?? "");
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [fcAmount, setFcAmount] = useState(l && Number(l.opening_fc_amount) ? l.opening_fc_amount : "");
  const [rate, setRate] = useState(l?.opening_rate ?? "");
  const [party, setParty] = useState<Party>(
    l?.party ??
      (c?.party
        ? { ...c.party, id: undefined, name: undefined, companies: undefined, customer_number: "", vendor_number: "" }
        : blankParty(props.companyState)),
  );
  // A customer or supplier another company already has (decision 0020).
  const [partyId, setPartyId] = useState<number | null>(null);
  const [alsoIn, setAlsoIn] = useState<number[]>([]);
  const [existing, setExisting] = useState<Party[]>([]);
  useEffect(() => {
    if (!l) api<Party[]>(`v1/parties/?not_in=${props.companyId}`).then(setExisting);
  }, [l, props.companyId]);
  useEffect(() => {
    if (props.multiCurrency) api<Currency[]>("v1/currencies/").then(setCurrencies);
  }, [props.multiCurrency]);
  const foreign = currency !== "" && currency !== "INR";
  const inr = (fc: string | null | undefined, r: string | null | undefined) =>
    Math.round((Number(fc) || 0) * (Number(r) || 0) * 100) / 100;
  const [error, setError] = useState<unknown>("");
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
      bank_name: bankName,
      account_number: accountNumber,
      ifsc,
      bank_branch: bankBranch,
      bill_wise: billWise,
      currency: foreign ? currency : null,
      ...(isParty
        ? {
            party: { ...party, credit_limit: party.credit_limit || "0" },
            also_in: alsoIn,
            ...(partyId ? { party_id: partyId } : {}),
          }
        : {}),
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
      setError(err);
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
                      <Combobox
                        value={b.side}
                        onChange={(v) => setBill(i, { side: v as Side })}
                        options={SIDES}
                      />
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
              <Combobox value={openingSide} onChange={(v) => setOpeningSide(v as Side)} options={SIDES} />
            </label>
          </div>
        )}
    </>
  );
  return (
    <form className="card" onSubmit={save} ref={formRef}>
      <h3>{l ? `Edit ${l.name}` : c ? `Duplicate ${c.name}` : "Add ledger"}</h3>
      {isParty && <PartyTabBar tab={tab} onTab={setTab} party={party} extraLabel="Opening balance" />}
      <div className="tab-general" data-tab="general" hidden={isParty && tab !== "general"}>
      <Section title="Ledger">
      <div className="row">
        <label>
          Under group
          <GroupSelect groups={props.groups} value={group} onChange={pickGroup} create={props.createGroup} />
        </label>
        {isParty && <PartyNumber party={party} supplier={chosen?.nature === "liability"} onChange={setParty} />}
      </div>
      {isParty && (
        <GstinField party={party} onChange={setParty} onName={(found) => name.trim() === "" && setName(found)} />
      )}
      <label>
        Name
        <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {props.multiCurrency && (
        <label>
          Currency
          <Combobox
            required
            value={currency || "INR"}
            placeholder="Type a currency code or name…"
            options={currencies.map((c) => ({ value: c.code, label: `${c.code} · ${c.name}${c.code === "INR" ? " (base)" : ""}` }))}
            onChange={(v) => setCurrency(v === "INR" ? "" : v)}
          />
        </label>
      )}
      {isParty && !l && existing.length > 0 && (
        <label>
          Existing customer or supplier (from another company)
          <Combobox
            value={partyId === null ? "" : String(partyId)}
            empty="None: a new customer or supplier"
            placeholder="Type a name, number or GSTIN…"
            options={existing.map((x) => ({
              value: String(x.id),
              label: `${[x.customer_number, x.vendor_number].filter(Boolean).join(" ")} ${x.name}`.trim(),
              hint: `${x.gstin ? `· ${x.gstin}` : ""}${x.companies?.length ? ` (in ${x.companies.map((c) => c.name).join(", ")})` : ""}`,
            }))}
            onChange={(v) => {
              const picked = existing.find((x) => x.id === Number(v));
              setPartyId(picked?.id ?? null);
              if (picked) {
                setName(picked.name ?? "");
                setParty({ ...picked, credit_limit: "", salesman: null });
              } else setParty(blankParty(props.companyState));
            }}
          />
        </label>
      )}
      </Section>
      </div>
      {isParty && (
        <PartyFields
          tab={tab}
          supplier={chosen?.nature === "liability"}
          alsoIn={alsoIn}
          onAlsoIn={setAlsoIn}
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
      <label hidden={isParty && tab !== "general"}>
        Notes
        <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <ErrorNote error={error} />
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {l && (
          <ActiveButton
            url={`v1/ledgers/${l.id}/`}
            active={l.is_active}
            what={`the ledger ${l.name}`}
            onDone={() => props.onDone(l.id)}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}
