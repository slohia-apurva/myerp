import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, SignedIn } from "./api";

export type Company = {
  id: number;
  name: string;
  abbr: string;
  gstin: string;
  pan: string;
  state_code: string;
  state: string;
  address: string;
  pincode: string;
  fiscal_year_start_month: number;
  books_start: string;
  multi_currency: boolean;
  base_currency: string;
};
type Branch = {
  id: number;
  name: string;
  state_code: string;
  gstin: string;
  address: string;
  is_head_office: boolean;
  is_active: boolean;
};
export type Group = {
  id: number;
  name: string;
  parent: number | null;
  nature: "asset" | "liability" | "income" | "expense";
  affects_gross_profit: boolean;
  code: string;
  is_standard: boolean;
  ledger_count: number;
  is_bank: boolean;
  bill_wise_default: boolean;
};
type State = { code: string; name: string };
type Opening = { dr: string; cr: string; difference: string };
type Detail = { company: Company; branches: Branch[]; ledger_groups: Group[]; opening: Opening };

export const money = (v: string | number) =>
  Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const longDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const NATURE = { asset: "Asset", liability: "Liability", income: "Income", expense: "Expense" };

function useStates() {
  const [states, setStates] = useState<State[]>([]);
  useEffect(() => {
    api<State[]>("v1/states/").then(setStates);
  }, []);
  return states;
}

function StateSelect(props: { states: State[]; value: string; onChange: (code: string) => void }) {
  return (
    <select required value={props.value} onChange={(e) => props.onChange(e.target.value)}>
      <option value="">Choose…</option>
      {props.states.map((s) => (
        <option key={s.code} value={s.code}>
          {s.name} ({s.code})
        </option>
      ))}
    </select>
  );
}

export function CompaniesPage({ session }: { session: SignedIn }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const states = useStates();
  const reload = useCallback(() => {
    api<Company[]>("v1/companies/")
      .then(setCompanies)
      .catch((err: Error) => setError(err.message));
  }, []);
  useEffect(reload, [reload]);

  return (
    <section className="page">
      <div className="page-head">
        <h2>Companies</h2>
        {session.user.is_owner && <button onClick={() => setAdding(true)}>Add company</button>}
      </div>
      <p className="small">
        Each company keeps its own books, GST registration and document numbers. A new company starts with a Head
        office branch and the standard ledger groups.
      </p>
      {error && <p className="error">{error}</p>}
      {adding && (
        <CompanyForm
          company={null}
          states={states}
          onDone={(c) => {
            setAdding(false);
            window.location.hash = `#/companies/${c.id}`;
          }}
          onCancel={() => setAdding(false)}
        />
      )}
      <table>
        <thead>
          <tr>
            <th>Company</th>
            <th>Short code</th>
            <th>GSTIN</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {companies.map((c) => (
            <tr key={c.id}>
              <td>
                <a href={`#/companies/${c.id}`}>{c.name}</a>
              </td>
              <td>{c.abbr}</td>
              <td>{c.gstin || <span className="small">Unregistered</span>}</td>
              <td>{c.state}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function CompanyForm(props: {
  company: Company | null;
  states: State[];
  onDone: (c: Company) => void;
  onCancel: () => void;
}) {
  const c = props.company;
  const [name, setName] = useState(c?.name ?? "");
  const [abbr, setAbbr] = useState(c?.abbr ?? "");
  const [gstin, setGstin] = useState(c?.gstin ?? "");
  const [pan, setPan] = useState(c?.pan ?? "");
  const [stateCode, setStateCode] = useState(c?.state_code ?? "");
  const [address, setAddress] = useState(c?.address ?? "");
  const [pincode, setPincode] = useState(c?.pincode ?? "");
  const [fyMonth, setFyMonth] = useState(c?.fiscal_year_start_month ?? 4);
  const [booksStart, setBooksStart] = useState(c?.books_start ?? "");
  const [multiCurrency, setMultiCurrency] = useState(c?.multi_currency ?? false);
  const [error, setError] = useState("");

  // A GSTIN starts with the state code and contains the PAN.
  const onGstin = (value: string) => {
    const v = value.toUpperCase();
    setGstin(v);
    if (v.length >= 2 && props.states.some((s) => s.code === v.slice(0, 2))) setStateCode(v.slice(0, 2));
    if (v.length >= 12) setPan(v.slice(2, 12));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = {
      name,
      gstin,
      pan,
      state_code: stateCode,
      address,
      pincode,
      fiscal_year_start_month: fyMonth,
      ...(booksStart ? { books_start: booksStart } : {}),
      multi_currency: multiCurrency,
      ...(c ? {} : abbr ? { abbr } : {}),
    };
    try {
      props.onDone(c ? await api<Company>(`v1/companies/${c.id}/`, body, "PATCH") : await api<Company>("v1/companies/", body));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h3>{c ? `Edit ${c.name}` : "Add company"}</h3>
      <label>
        Legal name
        <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {!c && (
        <label>
          Short code for document numbers (leave blank to use initials)
          <input value={abbr} maxLength={10} placeholder="e.g. AOL" onChange={(e) => setAbbr(e.target.value.toUpperCase())} />
        </label>
      )}
      <div className="row">
        <label>
          GSTIN (blank if unregistered)
          <input value={gstin} maxLength={15} onChange={(e) => onGstin(e.target.value)} />
        </label>
        <label>
          PAN
          <input value={pan} maxLength={10} onChange={(e) => setPan(e.target.value.toUpperCase())} />
        </label>
      </div>
      <div className="row">
        <label>
          State
          <StateSelect states={props.states} value={stateCode} onChange={setStateCode} />
        </label>
        <label>
          PIN code
          <input value={pincode} maxLength={6} inputMode="numeric" onChange={(e) => setPincode(e.target.value)} />
        </label>
      </div>
      <label>
        Address
        <textarea rows={2} value={address} onChange={(e) => setAddress(e.target.value)} />
      </label>
      <label>
        Financial year starts in
        <select value={fyMonth} onChange={(e) => setFyMonth(Number(e.target.value))}>
          {MONTHS.map((m, i) => (
            <option key={m} value={i + 1}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label>
        Books beginning from (opening balances are as at this date; blank = start of this financial year)
        <input type="date" value={booksStart} onChange={(e) => setBooksStart(e.target.value)} />
      </label>
      <label className="check">
        <input type="checkbox" checked={multiCurrency} onChange={(e) => setMultiCurrency(e.target.checked)} />
        Use foreign currencies (exports, imports, EEFC accounts). Books stay in INR.
      </label>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button>{c ? "Save" : "Add company"}</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function CompanyPage({ id, session }: { id: number; session: SignedIn }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const states = useStates();
  const canEdit = session.permissions.includes("masters.edit");
  const reload = useCallback(() => {
    api<Detail>(`v1/companies/${id}/`)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [id]);
  useEffect(reload, [reload]);

  if (!detail) return <section className="page">{error ? <p className="error">{error}</p> : <p>Loading…</p>}</section>;
  const c = detail.company;
  return (
    <section className="page">
      <p className="small">
        <a href="#/companies">Companies</a>
      </p>
      <div className="page-head">
        <h2>{c.name}</h2>
        <div className="buttons">
          <a className="button" href={`#/companies/${c.id}/groups`}>
            Ledger groups
          </a>
          <a className="button" href={`#/companies/${c.id}/ledgers`}>
            Ledgers
          </a>
          {canEdit && !editing && <button onClick={() => setEditing(true)}>Edit details</button>}
        </div>
      </div>
      {editing ? (
        <CompanyForm
          company={c}
          states={states}
          onDone={() => {
            setEditing(false);
            reload();
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <dl className="facts">
          <dt>Short code</dt>
          <dd>{c.abbr}</dd>
          <dt>GSTIN</dt>
          <dd>{c.gstin || "Unregistered"}</dd>
          <dt>PAN</dt>
          <dd>{c.pan || "—"}</dd>
          <dt>State</dt>
          <dd>{c.state}</dd>
          <dt>Address</dt>
          <dd>{[c.address, c.pincode].filter(Boolean).join(" ") || "—"}</dd>
          <dt>Financial year</dt>
          <dd>
            {MONTHS[c.fiscal_year_start_month - 1]} to {MONTHS[(c.fiscal_year_start_month + 10) % 12]}, {c.base_currency}
          </dd>
          <dt>Currencies</dt>
          <dd>{c.multi_currency ? "INR, plus foreign currencies on ledgers" : "INR only"}</dd>
          <dt>Books beginning from</dt>
          <dd>{longDate(c.books_start)}</dd>
          <dt>Opening balances</dt>
          <dd>
            Dr {money(detail.opening.dr)} · Cr {money(detail.opening.cr)}
            {Number(detail.opening.difference) !== 0 && (
              <span className="error">
                {" "}
                · difference {money(Math.abs(Number(detail.opening.difference)))}{" "}
                {Number(detail.opening.difference) > 0 ? "Dr" : "Cr"}
              </span>
            )}
          </dd>
        </dl>
      )}
      <Branches company={c} branches={detail.branches} states={states} canEdit={canEdit} reload={reload} />
    </section>
  );
}

function Branches(props: { company: Company; branches: Branch[]; states: State[]; canEdit: boolean; reload: () => void }) {
  const [editing, setEditing] = useState<Branch | "new" | null>(null);
  const stateName = (code: string) => props.states.find((s) => s.code === code)?.name ?? code;
  return (
    <>
      <div className="page-head">
        <h3>Branches</h3>
        {props.canEdit && (
          <button className="link" onClick={() => setEditing("new")}>
            Add branch
          </button>
        )}
      </div>
      {editing && (
        <BranchForm
          company={props.company}
          branch={editing === "new" ? null : editing}
          states={props.states}
          onDone={() => {
            setEditing(null);
            props.reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      <table>
        <thead>
          <tr>
            <th>Branch</th>
            <th>State</th>
            <th>GSTIN</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {props.branches.map((b) => (
            <tr key={b.id} className={b.is_active ? "" : "inactive"}>
              <td>
                {b.name}
                {b.is_head_office && <span className="small"> · head office</span>}
                {!b.is_active && <span className="small"> · closed</span>}
              </td>
              <td>{stateName(b.state_code)}</td>
              <td>{b.gstin || <span className="small">Company's</span>}</td>
              <td>
                {props.canEdit && (
                  <button className="link" onClick={() => setEditing(b)}>
                    Edit
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function BranchForm(props: { company: Company; branch: Branch | null; states: State[]; onDone: () => void; onCancel: () => void }) {
  const b = props.branch;
  const [name, setName] = useState(b?.name ?? "");
  const [stateCode, setStateCode] = useState(b?.state_code ?? props.company.state_code);
  const [gstin, setGstin] = useState(b?.gstin ?? "");
  const [address, setAddress] = useState(b?.address ?? "");
  const [active, setActive] = useState(b?.is_active ?? true);
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = { name, state_code: stateCode, gstin, address, is_active: active };
    try {
      if (b) await api(`v1/branches/${b.id}/`, body, "PATCH");
      else await api(`v1/companies/${props.company.id}/branches/`, body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h4>{b ? `Edit ${b.name}` : "Add branch"}</h4>
      <label>
        Name
        <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Bhiwandi warehouse" />
      </label>
      <div className="row">
        <label>
          State
          <StateSelect states={props.states} value={stateCode} onChange={setStateCode} />
        </label>
        <label>
          GSTIN (only if registered separately in that state)
          <input value={gstin} maxLength={15} onChange={(e) => setGstin(e.target.value.toUpperCase())} />
        </label>
      </div>
      <label>
        Address
        <textarea rows={2} value={address} onChange={(e) => setAddress(e.target.value)} />
      </label>
      {b && !b.is_head_office && (
        <label className="check">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          Open (untick when the branch closes)
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

export function LedgerGroupsPage({ id, session }: { id: number; session: SignedIn }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Detail>(`v1/companies/${id}/`)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [id]);
  useEffect(reload, [reload]);
  if (!detail) return <section className="page">{error ? <p className="error">{error}</p> : <p>Loading…</p>}</section>;
  return (
    <section className="page">
      <p className="small">
        <a href="#/companies">Companies</a> › <a href={`#/companies/${id}`}>{detail.company.name}</a>
      </p>
      <div className="page-head">
        <h2>Ledger groups</h2>
        <a className="button" href={`#/companies/${id}/ledgers`}>
          Ledgers
        </a>
      </div>
      <LedgerGroups
        company={detail.company}
        groups={detail.ledger_groups}
        canEdit={session.permissions.includes("masters.edit")}
        reload={reload}
      />
    </section>
  );
}

function LedgerGroups(props: { company: Company; groups: Group[]; canEdit: boolean; reload: () => void }) {
  const [editing, setEditing] = useState<{ group: Group | null; parent: number | null } | null>(null);
  const children = useMemo(() => {
    const map = new Map<number | null, Group[]>();
    for (const g of props.groups) map.set(g.parent, [...(map.get(g.parent) ?? []), g]);
    return map;
  }, [props.groups]);

  const node = (g: Group, depth: number): JSX.Element => (
    <li key={g.id}>
      <div className="tree-row" style={{ paddingLeft: 12 + depth * 20 }}>
        <span className={depth === 0 ? "primary" : ""}>{g.name}</span>
        {depth === 0 && (
          <span className="small">
            {NATURE[g.nature]}
            {g.affects_gross_profit ? " · trading account" : ""}
          </span>
        )}
        {!g.is_standard && <span className="tag">added</span>}
        {g.ledger_count > 0 && (
          <a className="small" href={`#/companies/${props.company.id}/ledgers/${g.id}`}>
            {g.ledger_count} {g.ledger_count === 1 ? "ledger" : "ledgers"}
          </a>
        )}
        {props.canEdit && (
          <span className="tree-actions">
            <button className="link" onClick={() => setEditing({ group: null, parent: g.id })}>
              Add under
            </button>
            {!g.is_standard && (
              <button className="link" onClick={() => setEditing({ group: g, parent: g.parent })}>
                Edit
              </button>
            )}
          </span>
        )}
      </div>
      {editing && editing.parent === g.id && editing.group === null && (
        <GroupForm company={props.company} groups={props.groups} group={null} parent={g.id} onDone={done} onCancel={() => setEditing(null)} />
      )}
      {editing?.group?.id === g.id && (
        <GroupForm company={props.company} groups={props.groups} group={g} parent={g.parent} onDone={done} onCancel={() => setEditing(null)} />
      )}
      {(children.get(g.id) ?? []).length > 0 && <ul>{children.get(g.id)!.map((c) => node(c, depth + 1))}</ul>}
    </li>
  );
  function done() {
    setEditing(null);
    props.reload();
  }

  return (
    <>
      <p className="small">
        The 15 primary groups and their standard sub-groups come with every company and cannot be changed. Add your
        own groups under them, for example Export debtors under Sundry Debtors.
      </p>
      <ul className="tree">{(children.get(null) ?? []).map((g) => node(g, 0))}</ul>
    </>
  );
}

function GroupForm(props: {
  company: Company;
  groups: Group[];
  group: Group | null;
  parent: number | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const g = props.group;
  const [name, setName] = useState(g?.name ?? "");
  const [parent, setParent] = useState<number | null>(props.parent);
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (g) await api(`v1/ledger-groups/${g.id}/`, { name, parent }, "PATCH");
      else await api(`v1/companies/${props.company.id}/ledger-groups/`, { name, parent });
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const remove = async () => {
    if (!g || !window.confirm(`Delete the group ${g.name}?`)) return;
    try {
      await api(`v1/ledger-groups/${g.id}/`, undefined, "DELETE");
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card inline" onSubmit={save}>
      <div className="row">
        <label>
          {g ? "Name" : "New group name"}
          <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        {g && (
          <label>
            Under
            <select value={parent ?? ""} onChange={(e) => setParent(Number(e.target.value))}>
              {props.groups
                .filter((o) => o.id !== g.id)
                .map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
            </select>
          </label>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button>{g ? "Save" : "Add group"}</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {g && (
          <button type="button" className="link danger" onClick={remove}>
            Delete group
          </button>
        )}
      </div>
    </form>
  );
}
