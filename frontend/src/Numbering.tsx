import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Section } from "./Brand";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";

/** A company's "Numbering" tab: the group's master numbers and the company's document series. */
type Master = { key: string; label: string; prefix: string; width: number; last: number; next: string };
type SeriesYear = { year: number; name: string; last: number };
type Series = {
  id: number;
  doc_type: string;
  doc_label: string;
  branch: number | null;
  branch_name: string;
  prefix: string;
  width: number;
  example: string;
  in_use: boolean;
  years: SeriesYear[];
};
type Overview = { masters: Master[]; formats: Series[]; doc_types: { value: string; label: string }[] };
type Branch = { id: number; name: string; is_active: boolean };

export function Numbering(props: { companyId: number; branches: Branch[]; canEdit: boolean; onChanged: () => void }) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<unknown>("");
  const load = useCallback(
    () =>
      api<Overview>(`v1/companies/${props.companyId}/numbering/`)
        .then(setData)
        .catch(setError),
    [props.companyId],
  );
  useEffect(() => {
    load();
  }, [load]);
  const [master, setMaster] = useState<Master | null>(null);
  const [series, setSeries] = useState<Series | "new" | null>(null);
  const [years, setYears] = useState<number | null>(null);
  const done = () => {
    setMaster(null);
    setSeries(null);
    load();
    props.onChanged();
  };
  if (!data) return error ? <ErrorNote error={error} /> : <p>Loading…</p>;
  return (
    <>
      <p className="small">
        A document series makes numbers like AO/SI/2627/00001: its prefix, then the number. {"{YY}"} in the prefix becomes
        the fiscal year (2627 for 2026-27; {"{FY}"} gives 2026-27), and every year counts again from 1.
      </p>
      {master && <MasterForm key={master.key} master={master} onDone={done} onCancel={() => setMaster(null)} />}
      {series && (
        <SeriesForm
          key={series === "new" ? "new" : series.id}
          series={series === "new" ? null : series}
          companyId={props.companyId}
          docTypes={data.doc_types}
          branches={props.branches.filter((b) => b.is_active)}
          onDone={done}
          onCancel={() => setSeries(null)}
        />
      )}
      <Section title="Master numbers (the same for every company)">
        <table>
          <thead>
            <tr>
              <th>Numbers for</th>
              <th>Prefix</th>
              <th className="num">Digits</th>
              <th className="num">Last used</th>
              <th>Next number</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.masters.map((m) => (
              <tr key={m.key}>
                <td>{m.label}</td>
                <td>{m.prefix}</td>
                <td className="num">{m.width}</td>
                <td className="num">{m.last}</td>
                <td>{m.next}</td>
                <td className="row-actions">
                  {props.canEdit && (
                    <button type="button" className="link" onClick={() => setMaster(m)}>
                      Edit
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      <Section title="Document series">
        <div className="page-head">
          <span className="small">A branch can have its own series for a kind of document.</span>
          {props.canEdit && !series && (
            <button type="button" className="secondary" onClick={() => setSeries("new")}>
              Add branch series
            </button>
          )}
        </div>
        <table>
          <thead>
            <tr>
              <th>Document</th>
              <th>Branch</th>
              <th>Prefix</th>
              <th className="num">Digits</th>
              <th>Looks like</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.formats.flatMap((f) => {
              const rows = [
                <tr key={f.id}>
                  <td>{f.doc_label}</td>
                  <td>{f.branch_name || "All branches"}</td>
                  <td>{f.prefix}</td>
                  <td className="num">{f.width}</td>
                  <td>{f.example}</td>
                  <td className="row-actions">
                    <button type="button" className="link" onClick={() => setYears(years === f.id ? null : f.id)}>
                      {years === f.id ? "Hide years" : "Years"}
                    </button>
                    {props.canEdit && (
                      <button type="button" className="link" onClick={() => setSeries(f)}>
                        Edit
                      </button>
                    )}
                  </td>
                </tr>,
              ];
              if (years === f.id)
                rows.push(
                  <tr key={`y${f.id}`} className="form-row">
                    <td colSpan={6}>
                      <YearsTable series={f} canEdit={props.canEdit} onChanged={done} />
                    </td>
                  </tr>,
                );
              return rows;
            })}
          </tbody>
        </table>
      </Section>
    </>
  );
}

function YearsTable(props: { series: Series; canEdit: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState<number | null>(null);
  const [value, setValue] = useState("");
  const [error, setError] = useState<unknown>("");
  const save = async (event: FormEvent, year: SeriesYear) => {
    event.preventDefault();
    setError("");
    try {
      await api(`v1/numbering/formats/${props.series.id}/years/${year.year}/`, { last: Number(value) }, "PATCH");
      setEditing(null);
      props.onChanged();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <>
      <table>
        <thead>
          <tr>
            <th>Fiscal year</th>
            <th className="num">Last number used</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {props.series.years.map((y) => (
            <tr key={y.year}>
              <td>{y.name}</td>
              <td className="num">
                {editing === y.year ? (
                  <form onSubmit={(e) => save(e, y)} className="inline-form">
                    <input
                      autoFocus
                      type="number"
                      min={y.last}
                      value={value}
                      aria-label={`Last number used in ${y.name}`}
                      onChange={(e) => setValue(e.target.value)}
                    />{" "}
                    <button>Save</button>{" "}
                    <button type="button" className="link" onClick={() => setEditing(null)}>
                      Cancel
                    </button>
                  </form>
                ) : (
                  y.last
                )}
              </td>
              <td className="row-actions">
                {props.canEdit && editing !== y.year && (
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      setEditing(y.year);
                      setValue(String(y.last));
                    }}
                  >
                    Set last number
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ErrorNote error={error} />
    </>
  );
}

function MasterForm(props: { master: Master; onDone: () => void; onCancel: () => void }) {
  const m = props.master;
  const [prefix, setPrefix] = useState(m.prefix);
  const [width, setWidth] = useState(String(m.width));
  const [last, setLast] = useState(String(m.last));
  const [error, setError] = useState<unknown>("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api(`v1/numbering/masters/${m.key}/`, { prefix, width: Number(width), last: Number(last) }, "PATCH");
      props.onDone();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <form className="card" onSubmit={save}>
      <h4>Edit {m.label.toLowerCase()}</h4>
      <Section title="Numbers">
        <div className="row">
          <label>
            Prefix
            <input value={prefix} maxLength={10} onChange={(e) => setPrefix(e.target.value)} />
          </label>
          <label>
            Digits
            <input required type="number" min={3} max={8} value={width} onChange={(e) => setWidth(e.target.value)} />
          </label>
          <label>
            Last number used (it can only go up)
            <input required type="number" min={m.last} value={last} onChange={(e) => setLast(e.target.value)} />
          </label>
        </div>
        <p className="small">
          A new prefix or digit count applies to numbers made from now on; numbers already given are not changed.
        </p>
      </Section>
      <ErrorNote error={error} />
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function SeriesForm(props: {
  series: Series | null;
  companyId: number;
  docTypes: { value: string; label: string }[];
  branches: Branch[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const s = props.series;
  const [docType, setDocType] = useState(s?.doc_type ?? "");
  const [branch, setBranch] = useState(s?.branch ? String(s.branch) : "");
  const [prefix, setPrefix] = useState(s?.prefix ?? "");
  const [width, setWidth] = useState(String(s?.width ?? 4));
  const [error, setError] = useState<unknown>("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (s) await api(`v1/numbering/formats/${s.id}/`, { prefix, width: Number(width) }, "PATCH");
      else
        await api(`v1/companies/${props.companyId}/numbering/formats/`, {
          doc_type: docType,
          branch: Number(branch),
          prefix,
          width: Number(width),
        });
      props.onDone();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <form className="card" onSubmit={save}>
      <h4>{s ? `Edit ${s.doc_label.toLowerCase()} series` : "Add branch series"}</h4>
      <Section title="Document series">
        {!s && (
          <div className="row">
            <label>
              Document
              <Combobox
                required
                value={docType}
                onChange={setDocType}
                empty="Pick a document"
                options={props.docTypes}
              />
            </label>
            <label>
              Branch
              <Combobox
                required
                value={branch}
                onChange={setBranch}
                empty="Pick a branch"
                options={props.branches.map((b) => ({ value: String(b.id), label: b.name }))}
              />
            </label>
          </div>
        )}
        <div className="row">
          <label>
            Prefix
            <input
              required
              autoFocus
              value={prefix}
              maxLength={20}
              placeholder="e.g. AO/SI/{YY}/"
              disabled={s?.in_use}
              onChange={(e) => setPrefix(e.target.value)}
            />
          </label>
          <label>
            Digits
            <input
              required
              type="number"
              min={3}
              max={8}
              value={width}
              disabled={s?.in_use}
              onChange={(e) => setWidth(e.target.value)}
            />
          </label>
        </div>
        <p className="small">
          Use {"{YY}"} for the fiscal year, for example AO/SI/{"{YY}"}/. A sales invoice, credit note or debit note number
          can be at most 16 characters (letters, digits, / and -). No two series of a company can share a prefix.
          {s?.in_use && " Numbers have been given from this series, so its prefix and digits can no longer change."}
        </p>
      </Section>
      <ErrorNote error={error} />
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
