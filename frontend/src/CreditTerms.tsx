import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { Activity, WithActivity } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { ActionCells, ActionHeads, ActiveButton, FormBody } from "./RowActions";

/** Credit terms: how a party's bills are paid, split into parts. */
export type TermPart = { percent: string; event: string; days: number };
export type CreditTerm = {
  id: number;
  name: string;
  is_active: boolean;
  notes: string;
  parts: TermPart[];
  summary: string;
  party_count: number;
};

export const EVENTS: [string, string][] = [
  ["order", "With the order (advance)"],
  ["dispatch", "Before dispatch"],
  ["delivery", "On delivery"],
  ["bill", "After the bill date"],
];

export function useCreditTerms() {
  const [terms, setTerms] = useState<CreditTerm[]>([]);
  const reload = useCallback(() => {
    api<CreditTerm[]>("v1/credit-terms/").then(setTerms);
  }, []);
  useEffect(reload, [reload]);
  return { terms, reload };
}

/** Masters > Credit terms: one list for every company in the group. */
export function CreditTermsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { terms, reload } = useCreditTerms();
  const [editing, setEditing] = useState<CreditTerm | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<CreditTerm | null>(null);
  const done = () => {
    setEditing(null);
    setCopyOf(null);
    reload();
  };
  return (
    <section className="page">
      <PageHeader
        title="Credit terms"
        sub="How customers pay and suppliers are paid. One list for every company in the group."
        actions={
          canEdit && (
            <button
              onClick={() => {
                setCopyOf(null);
                setEditing("new");
              }}
            >
              Add credit terms
            </button>
          )
        }
      />
      <WithActivity activity={<Activity type="credit_term" stamp={JSON.stringify(terms)} />}>
      {editing && (
        <TermForm
          key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
          term={editing === "new" ? null : editing}
          copyOf={copyOf}
          readOnly={!canEdit}
          onDone={done}
          onCancel={() => {
            setEditing(null);
            setCopyOf(null);
          }}
        />
      )}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>When payment is due</th>
            <th className="num">Parties</th>
            <ActionHeads />
          </tr>
        </thead>
        <tbody>
          {terms.map((t) => (
            <tr key={t.id} className={t.is_active ? "" : "off"}>
              <td>
                {t.name}
                {!t.is_active && <span className="pill">Inactive</span>}
                {t.notes && <div className="small">{t.notes}</div>}
              </td>
              <td>{t.summary}</td>
              <td className="num">{t.party_count || ""}</td>
              <ActionCells
                canEdit={canEdit}
                onOpen={() => {
                  setCopyOf(null);
                  setEditing(t);
                }}
                onDuplicate={() => {
                  setCopyOf(t);
                  setEditing("new");
                }}
              />
            </tr>
          ))}
        </tbody>
      </table>
      </WithActivity>
    </section>
  );
}

function TermForm(props: {
  term: CreditTerm | null;
  copyOf?: CreditTerm | null;
  readOnly?: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const t = props.term;
  const from = t ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const [name, setName] = useState(props.copyOf ? `${props.copyOf.name} (copy)` : (t?.name ?? ""));
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [parts, setParts] = useState<TermPart[]>(from?.parts ?? [{ percent: "100", event: "bill", days: 30 }]);
  const [error, setError] = useState("");
  const total = parts.reduce((sum, p) => sum + (Number(p.percent) || 0), 0);
  const setPart = (i: number, change: Partial<TermPart>) =>
    setParts(parts.map((p, j) => (j === i ? { ...p, ...change } : p)));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = { name, notes, parts };
    try {
      if (t) await api(`v1/credit-terms/${t.id}/`, body, "PATCH");
      else await api("v1/credit-terms/", body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h4>{t ? `${props.readOnly ? "View" : "Edit"} ${t.name}` : props.copyOf ? `Duplicate ${props.copyOf.name}` : "Add credit terms"}</h4>
      <FormBody readOnly={props.readOnly}>
      <Section title="Credit terms">
      <label>
        Name
        <input
          required
          autoFocus
          value={name}
          placeholder="e.g. 50% advance, 50% on delivery"
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <table className="grid">
        <thead>
          <tr>
            <th className="num">Share (%)</th>
            <th>Due</th>
            <th className="num">Plus days</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {parts.map((p, i) => (
            <tr key={i}>
              <td>
                <input
                  required
                  className="num"
                  inputMode="decimal"
                  value={p.percent}
                  onChange={(e) => setPart(i, { percent: e.target.value })}
                />
              </td>
              <td>
                <select value={p.event} onChange={(e) => setPart(i, { event: e.target.value })}>
                  {EVENTS.map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  className="num"
                  inputMode="numeric"
                  value={p.days}
                  onChange={(e) => setPart(i, { days: Number(e.target.value) || 0 })}
                />
              </td>
              <td>
                {parts.length > 1 && (
                  <button type="button" className="link danger" onClick={() => setParts(parts.filter((_, j) => j !== i))}>
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="num">
              <strong className={total === 100 ? "" : "error"}>{Number(total.toFixed(2))}%</strong>
            </td>
            <td colSpan={3}>
              <button
                type="button"
                className="link"
                onClick={() =>
                  setParts([...parts, { percent: total < 100 ? String(Number((100 - total).toFixed(2))) : "", event: "bill", days: 0 }])
                }
              >
                Add part
              </button>
            </td>
          </tr>
        </tfoot>
      </table>
      <p className="small">
        The shares must add up to 100%. "Plus days" counts from the event: 30 days after the bill date, or 7 days after
        delivery.
      </p>
      <label>
        Notes
        <input value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      </Section>
      </FormBody>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {!props.readOnly && <button>Save</button>}
        <button type="button" className="link" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
        {t && !props.readOnly && (
          <ActiveButton
            url={`v1/credit-terms/${t.id}/`}
            active={t.is_active}
            what={`the credit terms ${t.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}
