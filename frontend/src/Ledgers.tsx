import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, SignedIn } from "./api";
import type { Company, Group } from "./Companies";

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
            <th />
          </tr>
        </thead>
        <tbody>
          {ledgers.length === 0 && (
            <tr>
              <td colSpan={4} className="small">
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
  const [error, setError] = useState("");
  const isBank = props.groups.find((g) => String(g.group.id) === group)?.group.is_bank ?? false;

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
    };
    try {
      if (l) await api(`v1/ledgers/${l.id}/`, body, "PATCH");
      else await api(`v1/companies/${props.companyId}/ledgers/`, body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const remove = async () => {
    if (!l || !window.confirm(`Delete the ledger ${l.name}?`)) return;
    try {
      await api(`v1/ledgers/${l.id}/`, undefined, "DELETE");
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
          <GroupSelect groups={props.groups} value={group} onChange={setGroup} />
        </label>
      </div>
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
      <label>
        Notes
        <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {l && (
        <label className="check">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          Active (untick to stop new entries to this ledger)
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button>{l ? "Save" : "Add ledger"}</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {l && (
          <button type="button" className="link danger" onClick={remove}>
            Delete ledger
          </button>
        )}
      </div>
    </form>
  );
}
