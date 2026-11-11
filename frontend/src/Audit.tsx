import { Combobox } from "./Combobox";
import { useEffect, useState, type ReactNode } from "react";
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
  ["credit_term", "Credit terms"],
  ["unit", "Units"],
  ["item", "Items"],
  ["ledger_group", "Ledger groups"],
  ["ledger", "Ledgers"],
  ["courier_account", "Courier accounts"],
  ["shipment", "Shipments"],
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
export function ChangeLog(props: { company?: number; type?: string; id?: number; stamp?: string }) {
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
      <ol className="feed">
        {entries.map((e) => (
          <li key={e.id} className={`feed-item action-${e.action}`}>
            <div className="feed-meta">
              <strong>{e.user_name}</strong> · {when(e.at)}
            </div>
            <div className="feed-what">
              <span className={`pill action-${e.action}`}>{e.action_label}</span>
              {!single && (
                <span>
                  {" "}
                  {e.type_label.toLowerCase()} <strong>{e.record_name}</strong>
                </span>
              )}
            </div>
            <ul className="change-list">
              {e.changes.map((c) => (
                <li key={c.field}>
                  <span className="change-label">{c.label}</span>{" "}
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
          </li>
        ))}
      </ol>
      {more && (
        <button className="link" onClick={older}>
          Show older changes
        </button>
      )}
    </>
  );
}

/**
 * The activity column beside a page's content (below it on narrow screens):
 * the change log of what the page shows. `filter` adds a "Show" picker.
 */
export function Activity(props: { company?: number; type?: string; filter?: boolean; stamp?: string }) {
  const [type, setType] = useState(props.type ?? "");
  return (
    <aside className="activity" aria-label="Activity">
      <div className="activity-head">
        <h3>Activity</h3>
        {props.filter && (
          <Combobox
            ariaLabel="Show"
            value={type}
            onChange={setType}
            options={RECORD_TYPES.map(([value, label]) => ({ value, label }))}
          />
        )}
      </div>
      <ChangeLog company={props.company} type={type} stamp={props.stamp} />
    </aside>
  );
}

/** A page's content with the activity column on its right. */
export function WithActivity({ activity, children }: { activity: ReactNode; children: ReactNode }) {
  return (
    <div className="with-activity">
      <div className="main-col">{children}</div>
      {activity}
    </div>
  );
}
