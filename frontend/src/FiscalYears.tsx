import { FormEvent, useState } from "react";
import { api } from "./api";
import { Section } from "./Brand";
import { ActiveButton } from "./RowActions";

/** A company's financial years and their months, on the company's "Fiscal years" tab. */
export type FiscalPeriod = { id: number; label: string; start_date: string; end_date: string; is_locked: boolean };
export type FiscalYear = {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
  periods: FiscalPeriod[];
};

const short = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

/** The day after a date, and the last day of the month a year later: the next year to offer. */
function nextYear(years: FiscalYear[]) {
  const last = years.reduce<FiscalYear | null>((a, y) => (!a || y.end_date > a.end_date ? y : a), null);
  if (!last) return { start: "", end: "" };
  const start = new Date(last.end_date + "T00:00:00");
  start.setDate(start.getDate() + 1);
  const end = new Date(start.getFullYear() + 1, start.getMonth(), 0);
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { start: iso(start), end: iso(end) };
}

export function FiscalYears(props: {
  years: FiscalYear[];
  companyId: number;
  canEdit: boolean;
  isOwner: boolean;
  reload: () => void;
}) {
  const [editing, setEditing] = useState<FiscalYear | "new" | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState("");
  const done = () => {
    setEditing(null);
    props.reload();
  };
  const lock = async (p: FiscalPeriod) => {
    setError("");
    try {
      await api(`v1/fiscal-periods/${p.id}/`, { is_locked: !p.is_locked }, "PATCH");
      props.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <>
      <div className="page-head">
        <p className="small">
          A year runs in whole months and is split into monthly periods. A locked month takes no entries; only an Owner
          can unlock it.
        </p>
        {props.canEdit && !editing && <button onClick={() => setEditing("new")}>Add year</button>}
      </div>
      {editing && (
        <YearForm
          key={editing === "new" ? "new" : editing.id}
          year={editing === "new" ? null : editing}
          suggest={nextYear(props.years)}
          companyId={props.companyId}
          onDone={done}
          onCancel={() => setEditing(null)}
        />
      )}
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Year</th>
            <th>From</th>
            <th>To</th>
            <th className="num">Locked months</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {props.years.flatMap((y) => {
            const locked = y.periods.filter((p) => p.is_locked).length;
            const rows = [
              <tr key={y.id} className={y.is_active ? "" : "off"}>
                <td>
                  {y.name}
                  {!y.is_active && <span className="pill">Inactive</span>}
                </td>
                <td>{short(y.start_date)}</td>
                <td>{short(y.end_date)}</td>
                <td className="num">
                  {locked} of {y.periods.length}
                </td>
                <td className="row-actions">
                  <button className="link" onClick={() => setOpen(open === y.id ? null : y.id)}>
                    {open === y.id ? "Hide months" : "Months"}
                  </button>
                  {props.canEdit && (
                    <button className="link" onClick={() => setEditing(y)}>
                      Edit
                    </button>
                  )}
                </td>
              </tr>,
            ];
            if (open === y.id)
              rows.push(
                <tr key={`m-${y.id}`} className="form-row">
                  <td colSpan={5}>
                    <table>
                      <tbody>
                        {y.periods.map((p) => (
                          <tr key={p.id}>
                            <td>{p.label}</td>
                            <td>{p.is_locked ? "Locked" : "Open"}</td>
                            <td className="row-actions">
                              {props.canEdit && (!p.is_locked || props.isOwner) && (
                                <button className={`link ${p.is_locked ? "" : "danger"}`} onClick={() => lock(p)}>
                                  {p.is_locked ? "Unlock" : "Lock"}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </td>
                </tr>,
              );
            return rows;
          })}
          {props.years.length === 0 && (
            <tr>
              <td colSpan={5} className="small">
                No years yet. Click "Add year".
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}

function YearForm(props: {
  year: FiscalYear | null;
  suggest: { start: string; end: string };
  companyId: number;
  onDone: () => void;
  onCancel: () => void;
}) {
  const y = props.year;
  const [name, setName] = useState(y?.name ?? "");
  const [start, setStart] = useState(y?.start_date ?? props.suggest.start);
  const [end, setEnd] = useState(y?.end_date ?? props.suggest.end);
  const [error, setError] = useState("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = { name, start_date: start, end_date: end };
    try {
      if (y) await api(`v1/fiscal-years/${y.id}/`, body, "PATCH");
      else await api(`v1/companies/${props.companyId}/fiscal-years/`, body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <form className="card" onSubmit={save}>
      <h4>{y ? `Edit ${y.name}` : "Add fiscal year"}</h4>
      <Section title="Fiscal year">
        <div className="row">
          <label>
            Name
            <input value={name} placeholder="Leave empty for 2026-27" onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Starts on (1st of a month)
            <input required type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label>
            Ends on (last day of a month)
            <input required type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
      </Section>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {y && (
          <ActiveButton
            url={`v1/fiscal-years/${y.id}/`}
            active={y.is_active}
            what={`the year ${y.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}
