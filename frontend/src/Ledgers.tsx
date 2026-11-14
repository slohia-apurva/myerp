import { Combobox } from "./Combobox";
import { announceCreated, announceSaved, closeThisTab, creatable, useCreated, useNewName, type Creatable } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { FormEvent, KeyboardEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { api, SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { priceBody } from "./PriceLines";
import { blankParty, GstinField, PartyFields, PartyNumber, PartySummary, type Party, type PartyTab } from "./Parties";
import { longDate, money, useStates, type Company, type Group } from "./Companies";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { Chevron, LevelPicker, PageHeader } from "./Brand";
import { useExchange } from "./Exchange";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";

export type Ledger = {
  id: number;
  name: string;
  group: number;
  group_name: string;
  nature: string;
  is_active: boolean;
  lock?: LockInfo;
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
      options={props.groups
        .filter(({ group }) => group.is_active || props.all !== undefined || String(group.id) === props.value)
        .map(({ group, depth }) => ({ value: String(group.id), label: group.name, indent: depth }))}
      onChange={props.onChange}
      create={props.create}
    />
  );
}


/** `#/companies/<id>/ledgers?form=new`, `new-in-<group id>`, `<ledger id>` or `copy-<ledger id>`: this tab
 * was opened to add, change, view or duplicate one ledger (Sidharth, 2026-11-14). */
const formParam = () => hashParam("form");
const ledgersHash = (company: number, query = "") => `#/companies/${company}/ledgers${query}`;

/** Masters > Ledgers: the group tree on the left, the selected ledger's panels on the right.
 * Add, Edit, View and Duplicate each open in a new tab. */
export function LedgersPage(props: { companyId: number; groupId?: number; session: SignedIn }) {
  const form = formParam();
  if (form) return <LedgerFormTab companyId={props.companyId} form={form} session={props.session} />;
  return <LedgerList {...props} />;
}

function LedgerList(props: { companyId: number; groupId?: number; session: SignedIn }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [ledgers, setLedgers] = useState<Ledger[]>([]);
  const [query, setQuery] = useState("");
  const [groupFilter, setGroupFilter] = useState(props.groupId ? String(props.groupId) : "");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const canEdit = props.session.permissions.includes("masters.edit");
  const ordered = useMemo(() => treeOrder(detail?.ledger_groups ?? []), [detail]);
  const edit = (what: number | string) => openTab(ledgersHash(props.companyId, `?form=${what}`));

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
  // A ledger saved in the tab that Add, Edit or Duplicate opened: refresh and select it.
  useCreated("ledger_saved", (c) => {
    reload();
    setSelectedId(c.id);
  });
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
      opened();
    } else if (query || groupFilter) {
      // Show the whole list so the ledger asked for is in it.
      setQuery("");
      setGroupFilter("");
    }
  }, [openId, ledgers, query, groupFilter, opened]);

  // The list follows the group tree: each group with ledgers (directly or below it)
  // gets a heading row, its own ledgers come next, then its sub-groups. With a group chosen
  // in the filter, that group and the ones under it show even when empty, so a ledger can be added.
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
    const byId = new Map(groups.map((g) => [g.id, g]));
    const inFilter = (g: Group): boolean => {
      if (!groupFilter) return false;
      for (let x: Group | undefined = g; x; x = x.parent === null ? undefined : byId.get(x.parent)) {
        if (String(x.id) === groupFilter) return true;
      }
      return false;
    };
    const rows: ({ kind: "group"; group: Group; depth: number } | { kind: "ledger"; ledger: Ledger; depth: number })[] = [];
    let hideBelow: number | null = null;
    for (const { group, depth } of ordered) {
      if (hideBelow !== null && depth > hideBelow) continue;
      hideBelow = null;
      if (!count.get(group.id) && !(inFilter(group) && group.is_active)) continue;
      rows.push({ kind: "group", group, depth });
      if (folded.has(group.id)) {
        hideBelow = depth;
        continue;
      }
      for (const l of own.get(group.id) ?? []) rows.push({ kind: "ledger", ledger: l, depth: depth + 1 });
    }
    return { rows, count, net };
  }, [ledgers, detail, ordered, folded, groupFilter]);
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
  const pick = (l: Ledger) => setSelectedId(l.id);
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
  const stop = (fn: () => void) => (e: { stopPropagation: () => void }) => {
    e.stopPropagation();
    fn();
  };

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
        actions={io.buttons}
      />
      {error && <p className="error">{error}</p>}
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
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
                <th />
              </tr>
            </thead>
            <tbody onKeyDown={onListKey}>
              {tree.rows.length === 0 && (
                <tr>
                  <td colSpan={3} className="small">
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
                    <td className="row-actions">
                      {canEdit && r.group.is_active && (
                        <button className="link" onClick={stop(() => edit(`new-in-${r.group.id}`))}>
                          + Ledger
                        </button>
                      )}
                    </td>
                  </tr>
                ) : (
                  <tr
                    key={r.ledger.id}
                    id={`ledger-${r.ledger.id}`}
                    tabIndex={0}
                    aria-selected={selected?.id === r.ledger.id}
                    className={["ledger-row", r.ledger.is_active ? "" : "inactive", selected?.id === r.ledger.id ? "selected" : ""].join(" ")}
                    onClick={() => pick(r.ledger)}
                    onDoubleClick={() => edit(r.ledger.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") pick(r.ledger);
                    }}
                  >
                    <td>
                      <span style={{ paddingLeft: r.depth * 18 + 26, display: "inline-block" }}>
                        {r.ledger.name}
                        {!r.ledger.is_active && <span className="pill">Disabled</span>}
                      </span>
                    </td>
                    <td className="num">
                      {Number(r.ledger.opening_amount) === 0 ? <span className="small">—</span> : dc(Number(r.ledger.opening_amount) * (r.ledger.opening_side === "dr" ? 1 : -1))}
                    </td>
                    <td className="row-actions">
                      <button className="link" onClick={stop(() => edit(r.ledger.id))}>
                        {canEdit ? "Edit" : "View"}
                      </button>
                      {canEdit && (
                        <button className="link quiet" onClick={stop(() => edit(`copy-${r.ledger.id}`))}>
                          Duplicate
                        </button>
                      )}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
          {visible.length > 1 && <p className="small">Tip: click a ledger, then use ↑ and ↓ to move through the list.</p>}
        </div>
        <div className="side-col">
          {selected ? (
            <LedgerPanels ledger={selected} companyId={props.companyId} />
          ) : (
            <SidePanel title="Ledger Details">
              <p className="small">Click a ledger to see its details here.</p>
            </SidePanel>
          )}
        </div>
      </div>
    </section>
  );
}

/** The form of one ledger, alone in its own tab: Save and Cancel close the tab. */
function LedgerFormTab(props: { companyId: number; form: string; session: SignedIn }) {
  const copy = props.form.startsWith("copy-");
  const inGroup = props.form.startsWith("new-in-");
  const key = Number(props.form.replace(/^(copy-|new-in-)/, ""));
  const [detail, setDetail] = useState<Detail | null>(null);
  const [ledgers, setLedgers] = useState<Ledger[] | null>(null);
  const loadDetail = useCallback(() => api<Detail>(`v1/companies/${props.companyId}/`).then(setDetail), [props.companyId]);
  useEffect(() => {
    loadDetail();
    api<Ledger[]>(`v1/companies/${props.companyId}/ledgers/`).then(setLedgers);
  }, [loadDetail, props.companyId]);
  const canEdit = props.session.permissions.includes("masters.edit");
  // `&new=<name>`: opened by "Create …" in a picker (a purchase order's supplier, say).
  const startName = useNewName();
  const adding = props.form === "new" || inGroup;
  const editing = !adding && !copy;
  const target = adding ? null : (ledgers?.find((l) => l.id === key) ?? null);
  const ordered = useMemo(() => treeOrder(detail?.ledger_groups ?? []), [detail]);
  const toList = () => {
    window.location.hash = ledgersHash(props.companyId);
  };
  const title = editing ? (canEdit ? "Edit ledger" : "View ledger") : copy ? "Duplicate ledger" : "Add ledger";
  if (!detail || ledgers === null)
    return (
      <section className="page">
        <PageHeader title={title} />
      </section>
    );
  if (!adding && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That ledger was not found.</p>
      </section>
    );
  if (!canEdit && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view ledgers.</p>
      </section>
    );
  return (
    <LedgerForm
      title={title}
      companyId={props.companyId}
      ledger={editing ? target : null}
      copyOf={copy ? target : null}
      groups={ordered}
      createGroup={creatable("ledger_group", `companies/${props.companyId}/groups`, loadDetail)}
      defaultGroup={inGroup ? String(key) : ""}
      startName={adding ? (startName ?? undefined) : undefined}
      booksStart={detail.company.books_start}
      multiCurrency={detail.company.multi_currency}
      companyState={detail.company.state_code}
      readOnly={!canEdit}
      onDone={(saved) => {
        if (saved) announceSaved("ledger_saved", saved);
        if (saved && adding && startName) announceCreated("ledger", saved);
        closeThisTab(toList);
      }}
      onCancel={() => closeThisTab(toList)}
    />
  );
}


/** The selected ledger's panels at the right of the list: details, party details, opening bills, activity. */
function LedgerPanels(props: { ledger: Ledger; companyId: number }) {
  const { ledger: l } = props;
  const states = useStates();
  const opening = Number(l.opening_amount);
  const openingText = opening === 0 ? "Nil" : `${money(l.opening_amount)} ${l.opening_side === "dr" ? "Dr" : "Cr"}`;
  return (
    <>
      <SidePanel title="Ledger Details">
        <SideRows
          rows={[
            ["Name", l.name],
            ["Group", l.group_name],
            ["Nature", NATURE[l.nature] ?? ""],
            ["Opening Balance", openingText],
            [
              "In Foreign Currency",
              l.currency && opening !== 0
                ? `${l.currency} ${money(l.opening_fc_amount)}${l.opening_rate ? ` at ${Number(l.opening_rate)}` : ""}`
                : "",
            ],
            ["Currency", l.currency || "INR"],
            ["Bill-Wise", l.bill_wise ? "Yes" : "No"],
            ["Bank", l.bank_name],
            ["Account Number", l.account_number],
            ["IFSC", l.ifsc],
            ["Branch", l.bank_branch],
            ["In Use", l.lock?.in_use.join(", ") ?? ""],
            ["Disabled", l.is_active ? "No" : "Yes"],
            ["Notes", l.notes],
          ]}
        />
      </SidePanel>
      {l.party && <PartySummary party={l.party} states={states} supplier={l.nature === "liability"} />}
      {l.bill_wise && l.opening_bills.length > 0 && (
        <SidePanel title="Opening Bills">
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
        </SidePanel>
      )}
      <SidePanel title="Activity">
        <ChangeLog company={props.companyId} type="ledger" id={l.id} stamp={JSON.stringify(l)} />
      </SidePanel>
    </>
  );
}

function LedgerForm(props: {
  companyId: number;
  ledger: Ledger | null;
  /** Duplicate: start as a copy of this ledger, saved as a new one. */
  copyOf?: Ledger | null;
  title: string;
  readOnly?: boolean;
  groups: { group: Group; depth: number }[];
  createGroup?: Creatable;
  defaultGroup: string;
  booksStart: string;
  multiCurrency: boolean;
  companyState: string;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
  startName?: string;
}) {
  const l = props.ledger;
  // A duplicate copies the setup, not the name, account number, party numbers or balances.
  const c = props.copyOf;
  const from = l ?? c;
  const [name, setName] = useState(l?.name ?? (c ? `${c.name} (copy)` : (props.startName ?? "")));
  const [group, setGroup] = useState(from ? String(from.group) : props.defaultGroup);
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [disabled, setDisabled] = useState(l ? !l.is_active : false);
  const locked = (field: string) => isLocked(l?.lock, field);
  const [tab, setTab] = useState<PartyTab>("general");
  useEffect(() => {
    // A required field left empty on a hidden tab: open that tab and point at it.
    const el = document.getElementById("ledger-form");
    if (!el) return;
    const onInvalid = (e: Event) => {
      const target = e.target as HTMLInputElement;
      const panel = target.closest<HTMLElement>("[data-fold]");
      if (panel?.hidden) {
        setTab(panel.dataset.fold as PartyTab);
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
    if (props.multiCurrency) api<Currency[]>("v1/currencies/").then(setCurrencies);
  }, [props.multiCurrency]);
  const foreign = currency !== "" && currency !== "INR";
  const inr = (fc: string | null | undefined, r: string | null | undefined) =>
    Math.round((Number(fc) || 0) * (Number(r) || 0) * 100) / 100;
  const [error, setError] = useState<unknown>("");
  const chosen = groupOf(group);
  // Only customers have the "Labels" tab: leave it if the group is changed to suppliers.
  useEffect(() => {
    if (chosen?.nature === "liability" && tab === "labels") setTab("general");
  }, [chosen?.nature, tab]);
  const isBank = chosen?.is_bank ?? false;
  // Ledgers under Sundry Debtors or Creditors are customers and suppliers.
  const isParty = chosen?.bill_wise_default ?? false;
  // A firm can have one customer ledger and one supplier ledger in a company.
  const side = !isParty ? "" : chosen?.nature === "liability" ? "supplier" : "customer";
  useEffect(() => {
    if (!l && side) api<Party[]>(`v1/parties/?not_in=${props.companyId}&side=${side}`).then(setExisting);
  }, [l, props.companyId, side]);
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
      ...(l ? { is_active: !disabled } : {}),
      notes,
      bank_name: bankName,
      account_number: accountNumber,
      ifsc,
      bank_branch: bankBranch,
      bill_wise: billWise,
      currency: foreign ? currency : null,
      ...(isParty
        ? {
            party: { ...party, item_prices: undefined, credit_limit: party.credit_limit || "0" },
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
      // A customer's own item prices are one set of data kept apart from the party.
      const partyIdNow = saved?.party?.id ?? party.id;
      if (isParty && party.item_prices !== undefined && partyIdNow) {
        const side = chosen?.nature === "liability" ? "buying" : "selling";
        await api(`v1/parties/${partyIdNow}/item-prices/?side=${side}`, priceBody(party.item_prices), "PUT");
      }
      props.onDone(saved ? { id: saved.id, name: saved.name } : undefined);
    } catch (err) {
      setError(err);
    }
  };
  const openingFields = (
    <>
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
          <div className="item-fields">
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
  const dis = props.readOnly;
  // Folding sections, one open at a time, in the order shown (Sidharth, 2026-11-14).
  const ORDER: Record<string, number> = { general: 1, bank: 2, extra: 3, details: 4, addresses: 5, contacts: 6, documents: 7, products: 8, prices: 9, labels: 10 };
  const TITLE: Record<string, string> = {
    general: "Ledger",
    bank: "Bank Details",
    extra: "Opening Balance",
    details: "GST And Credit",
    addresses: "Addresses",
    contacts: "Contacts",
    documents: "Documents",
    products: "Products",
    prices: "Item Prices",
    labels: "Labels",
  };
  const openingText = billWise
    ? Math.abs(billsTotal) === 0
      ? "Nil"
      : `${money(Math.abs(billsTotal))} ${billsTotal < 0 ? "Cr" : "Dr"}`
    : foreign
      ? `${currency} ${money(fcAmount || 0)}`
      : Number(openingAmount) === 0
        ? "Nil"
        : `${money(openingAmount)} ${openingSide === "dr" ? "Dr" : "Cr"}`;
  const SUMMARY: Record<string, string> = {
    general: [name, chosen?.name].filter(Boolean).join(" · "),
    bank: bankName,
    extra: openingText,
    details: party.gstin || "",
    addresses: `${party.addresses.length} ${party.addresses.length === 1 ? "address" : "addresses"}`,
    contacts: `${party.contacts.length} ${party.contacts.length === 1 ? "contact" : "contacts"}`,
    documents: `${party.document_count ?? 0} documents`,
    products: (party.products ?? []).length ? `${(party.products ?? []).length} items` : "Any item",
    prices: (party.item_prices ?? []).length ? `${(party.item_prices ?? []).length} prices` : "",
    labels: "",
  };
  const fold = (code: string, body: ReactNode) => (
    <div key={code} className={"fold" + (tab === code ? " open" : "")} style={{ order: ORDER[code] }}>
      <button type="button" className="fold-head" aria-expanded={tab === code} onClick={() => setTab(tab === code ? "none" : (code as PartyTab))}>
        <span className="fold-title">{TITLE[code]}</span>
        {tab !== code && <span className="fold-summary">{SUMMARY[code]}</span>}
      </button>
      <div className="fold-body" data-fold={code} hidden={tab !== code}>
        {body}
      </div>
    </div>
  );
  const openingBody = (
    <>
      <p className="small">As at {longDate(props.booksStart)}, the day the books begin.</p>
      {openingFields}
    </>
  );
  return (
    <FormPage
      title={props.title}
      sub={l ? l.name : undefined}
      formId="ledger-form"
      onSubmit={save}
      onCancel={props.onCancel}
      error={error}
      readOnly={dis}
      disabled={l ? { value: disabled, set: setDisabled } : undefined}
      switches={
        <label className="check">
          <Locked on={locked("bill_wise")}>
            <input type="checkbox" disabled={dis} checked={billWise} onChange={(e) => setBillWise(e.target.checked)} />
            Bill-Wise
          </Locked>
        </label>
      }
      activity={l ? <ChangeLog company={props.companyId} type="ledger" id={l.id} stamp={JSON.stringify(l)} /> : undefined}
    >
      <InUseNote lock={l?.lock} />
      {fold(
        "general",
        <div className="item-fields">
          <label>
            <span className="req">Under Group</span>
            <Locked on={locked("group")}>
              <GroupSelect groups={props.groups} value={group} onChange={pickGroup} create={props.createGroup} />
            </Locked>
          </label>
          {isParty && <PartyNumber party={party} supplier={chosen?.nature === "liability"} onChange={setParty} />}
          {isParty && (
            <GstinField
              party={party}
              onChange={setParty}
              // The name typed in a 'Create "…"' picker gives way to the GST record's.
              onName={(found) => (name.trim() === "" || name === props.startName) && setName(found)}
            />
          )}
          <label>
            <span className="req">Name</span>
            <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          {props.multiCurrency && (
            <label>
              Currency
              <Locked on={locked("currency")}>
                <Combobox
                  required
                  value={currency || "INR"}
                  placeholder="Type a currency code or name…"
                  options={currencies.map((c) => ({ value: c.code, label: `${c.code} · ${c.name}${c.code === "INR" ? " (base)" : ""}` }))}
                  onChange={(v) => setCurrency(v === "INR" ? "" : v)}
                />
              </Locked>
            </label>
          )}
          {isParty && !l && existing.length > 0 && (
            <label>
              Existing Customer Or Supplier
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
                    // Its ledger on the other side here already has the plain name.
                    const here = picked.companies?.some((c) => c.id === props.companyId);
                    setName(here ? `${picked.name} (${side === "supplier" ? "Supplier" : "Customer"})` : (picked.name ?? ""));
                    setParty({ ...picked, credit_limit: "", salesman: null, preferred_transporter: null });
                  } else setParty(blankParty(props.companyState));
                }}
              />
            </label>
          )}
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>,
      )}
      {isParty && (
        <PartyFields
          tab={tab}
          fold={fold}
          supplier={chosen?.nature === "liability"}
          alsoIn={alsoIn}
          onAlsoIn={setAlsoIn}
          value={party}
          onChange={setParty}
          companyId={props.companyId}
          canEdit={!dis}
          extraTab={{ label: "Opening Balance", content: openingBody }}
        />
      )}
      {isBank &&
        fold(
          "bank",
          <div className="item-fields">
            <label>
              Bank
              <input value={bankName} onChange={(e) => setBankName(e.target.value)} placeholder="e.g. HDFC Bank" />
            </label>
            <label>
              Account Number
              <input value={accountNumber} onChange={(e) => setAccountNumber(e.target.value)} />
            </label>
            <label>
              IFSC
              <input value={ifsc} maxLength={11} onChange={(e) => setIfsc(e.target.value.toUpperCase())} />
            </label>
            <label>
              Branch
              <input value={bankBranch} onChange={(e) => setBankBranch(e.target.value)} />
            </label>
          </div>,
        )}
      {!isParty && fold("extra", openingBody)}
    </FormPage>
  );
}
