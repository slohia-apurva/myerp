import { useEffect, useState } from "react";
import { api } from "./api";

type Change = { field: string; label: string; old: string | null; new: string | null };
type Entry = {
  id: number;
  at: string;
  user_name: string;
  type: string;
  type_label: string;
  record_id: number;
  record_name: string;
  action: "create" | "update" | "delete";
  action_label: string;
  changes: Change[];
};

export const RECORD_TYPES: [string, string][] = [
  ["", "Everything"],
  ["company", "Company details"],
  ["branch", "Branches"],
  ["certificate", "Licences and certificates"],
  ["ledger_group", "Ledger groups"],
  ["ledger", "Ledgers"],
];

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

function Value({ v }: { v: string | null }) {
  return v === null ? <span className="small">blank</span> : <span>{v}</span>;
}

/**
 * The change log: who changed what, when, with old and new values.
 * Give `company` for a company's masters (and `type`/`id` to narrow it to
 * one record); leave it out for users and roles. `stamp` reloads it when the
 * record it shows has just been saved.
 */
export function ChangeLog(props: { company?: number; type?: string; id?: number; stamp?: string; compact?: boolean }) {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");
  const single = props.id !== undefined;

  const query = (before?: number) => {
    const q = new URLSearchParams();
    if (props.company !== undefined) q.set("company", String(props.company));
    if (props.type) q.set("type", props.type);
    if (props.id !== undefined) q.set("id", String(props.id));
    if (before) q.set("before", String(before));
    return `v1/audit/?${q}`;
  };
  useEffect(() => {
    setError("");
    api<{ entries: Entry[]; more: boolean }>(query())
      .then((r) => {
        setEntries(r.entries);
        setMore(r.more);
      })
      .catch((err: Error) => setError(err.message));
  }, [props.company, props.type, props.id, props.stamp]);

  const older = () => {
    if (!entries?.length) return;
    api<{ entries: Entry[]; more: boolean }>(query(entries[entries.length - 1].id)).then((r) => {
      setEntries([...entries, ...r.entries]);
      setMore(r.more);
    });
  };

  if (error) return <p className="error">{error}</p>;
  if (!entries) return <p className="small">Loading…</p>;
  if (entries.length === 0) return <p className="small">No changes recorded yet.</p>;
  return (
    <>
      <table className={`changes${props.compact ? " compact" : ""}`}>
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            {!single && <th>What</th>}
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id}>
              <td className="nowrap">{when(e.at)}</td>
              <td>{e.user_name}</td>
              {!single && (
                <td>
                  <span className="small">{e.type_label}</span>
                  <br />
                  {e.record_name}
                </td>
              )}
              <td>
                <span className={`pill action-${e.action}`}>{e.action_label}</span>
                <ul className="change-list">
                  {e.changes.map((c) => (
                    <li key={c.field}>
                      <strong>{c.label}</strong>
                      {": "}
                      {e.action === "update" ? (
                        <>
                          <del>
                            <Value v={c.old} />
                          </del>
                          {" → "}
                          <Value v={c.new} />
                        </>
                      ) : (
                        <Value v={e.action === "delete" ? c.old : c.new} />
                      )}
                    </li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {more && (
        <button className="link" onClick={older}>
          Show older changes
        </button>
      )}
    </>
  );
}

/** A company's "Change log" tab: everything, or one kind of record. */
export function CompanyChangeLog({ company }: { company: number }) {
  const [type, setType] = useState("");
  return (
    <>
      <div className="page-head">
        <h3>Change log</h3>
        <label className="inline-filter">
          Show
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {RECORD_TYPES.map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="small">
        Every change to this company's masters: who made it, when, and what each value was before and after. The log
        cannot be edited.
      </p>
      <ChangeLog company={company} type={type} />
    </>
  );
}
