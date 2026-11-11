import { FormEvent, useEffect, useRef, useState } from "react";
import { api, type SignedIn } from "./api";
import { Activity, WithActivity } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { ActionCells, ActionHeads, ActiveButton, FormBody } from "./RowActions";

/** HSN / SAC codes: one list for every company in the group. */
export type Hsn = { id: number; hsn_code: string; description: string; is_active: boolean };
type Found = { total: number; results: Hsn[] };

const search = (q: string, pick: boolean) =>
  api<Found>(`v1/hsn/?q=${encodeURIComponent(q)}${pick ? "&limit=pick&active=1" : ""}`);

/** Rows of code and description from a CSV or tab-separated file; lines that
 * do not start with a code (headings, blanks) are skipped. */
export function parseHsnRows(text: string): { hsn_code: string; description: string }[] {
  const rows: { hsn_code: string; description: string }[] = [];
  for (const line of text.split(/\r?\n/)) {
    const cells = line.includes("\t")
      ? line.split("\t")
      : (line.match(/("([^"]|"")*"|[^,]*)(,|$)/g) ?? []).map((c) => c.replace(/,$/, "").replace(/^"|"$/g, "").replace(/""/g, '"'));
    const code = (cells[0] ?? "").trim().replace(/\s/g, "");
    const rest = cells.slice(1).map((c) => c.trim());
    while (rest.length && rest[rest.length - 1] === "") rest.pop();
    if (/^\d{2,8}$/.test(code)) rows.push({ hsn_code: code, description: rest.join(", ") });
  }
  return rows;
}

/** Masters > HSN codes. */
export function HsnPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Found>({ total: 0, results: [] });
  const [editing, setEditing] = useState<Hsn | "new" | null>(null);
  const [importing, setImporting] = useState(false);
  const [stamp, setStamp] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => search(q, false).then(setFound), 200);
    return () => clearTimeout(t);
  }, [q, stamp]);
  const done = () => {
    setEditing(null);
    setImporting(false);
    setStamp(stamp + 1);
  };
  return (
    <section className="page">
      <PageHeader
        title="HSN codes"
        sub={`${found.total} code${found.total === 1 ? "" : "s"} · searched when you enter an item's HSN. One list for every company in the group.`}
        actions={
          canEdit && (
            <span className="grp">
              <button className="link" onClick={() => setImporting(true)}>
                Import
              </button>
              <button onClick={() => setEditing("new")}>Add HSN code</button>
            </span>
          )
        }
      />
      <WithActivity activity={<Activity type="hsn" stamp={String(stamp)} />}>
        {importing && <HsnImport onImported={() => setStamp(stamp + 1)} onDone={done} onCancel={() => setImporting(false)} />}
        {editing && (
          <HsnForm
            key={editing === "new" ? "new" : editing.id}
            hsn={editing === "new" ? null : editing}
            readOnly={!canEdit}
            onDone={done}
            onCancel={() => setEditing(null)}
          />
        )}
        <input
          type="search"
          placeholder="Search by code or words in the description"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <table>
          <thead>
            <tr>
              <th>HSN code</th>
              <th>Description</th>
              <ActionHeads />
            </tr>
          </thead>
          <tbody>
            {found.results.map((h) => (
              <tr key={h.id} className={h.is_active ? "" : "off"}>
                <td>
                  {h.hsn_code}
                  {!h.is_active && <span className="pill">Inactive</span>}
                </td>
                <td>{h.description}</td>
                <ActionCells canEdit={canEdit} onOpen={() => setEditing(h)} />
              </tr>
            ))}
            {found.results.length === 0 && (
              <tr>
                <td colSpan={4} className="small">
                  {found.total === 0 ? 'No codes yet. Click "Import" to load the official list.' : "Nothing matches."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {found.total > found.results.length && q === "" && (
          <p className="small">Showing the first {found.results.length}. Type in the search box to find others.</p>
        )}
      </WithActivity>
    </section>
  );
}

function HsnForm(props: { hsn: Hsn | null; readOnly?: boolean; onDone: () => void; onCancel: () => void }) {
  const h = props.hsn;
  const [code, setCode] = useState(h?.hsn_code ?? "");
  const [description, setDescription] = useState(h?.description ?? "");
  const [error, setError] = useState("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (h) await api(`v1/hsn/${h.id}/`, { description }, "PATCH");
      else await api("v1/hsn/", { hsn_code: code, description });
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <form className="card" onSubmit={save}>
      <h4>{h ? `${props.readOnly ? "View" : "Edit"} ${h.hsn_code}` : "Add HSN code"}</h4>
      <FormBody readOnly={props.readOnly}>
        <Section title="HSN code">
          <div className="row">
            <label>
              Code (2, 4, 6 or 8 digits)
              <input required autoFocus={!h} disabled={!!h} value={code} maxLength={8} inputMode="numeric" onChange={(e) => setCode(e.target.value)} />
            </label>
          </div>
          <label>
            Description
            <input required value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </Section>
      </FormBody>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {!props.readOnly && <button>Save</button>}
        <button type="button" className="link" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
        {h && !props.readOnly && (
          <ActiveButton url={`v1/hsn/${h.id}/`} active={h.is_active} what={`HSN code ${h.hsn_code}`} onDone={props.onDone} onError={setError} />
        )}
      </div>
    </form>
  );
}

function HsnImport(props: { onImported: () => void; onDone: () => void; onCancel: () => void }) {
  const [rows, setRows] = useState<{ hsn_code: string; description: string }[] | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const pick = async (file: File | undefined) => {
    setError("");
    setResult("");
    if (!file) return;
    setRows(parseHsnRows(await file.text()));
  };
  const send = async () => {
    if (!rows) return;
    setBusy(true);
    setError("");
    try {
      const r = await api<{ added: number; updated: number; unchanged: number }>("v1/hsn/import/", { rows });
      setResult(`${r.added} added, ${r.updated} updated, ${r.unchanged} unchanged.`);
      setRows(null);
      props.onImported();
    } catch (err) {
      setError((err as Error).message);
    }
    setBusy(false);
  };
  return (
    <div className="card">
      <h4>Import HSN codes</h4>
      <Section title="File">
        <p className="small">
          A CSV or tab-separated file with the code in the first column and the description in the second. Heading lines are
          skipped. New codes are added; codes already in the list get the new description. Any bad row stops the whole import.
        </p>
        <input type="file" accept=".csv,.tsv,.txt" onChange={(e) => pick(e.target.files?.[0])} />
        {rows && <p>{rows.length} codes found in the file.</p>}
        {result && <p>{result}</p>}
      </Section>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button type="button" disabled={busy || !rows || rows.length === 0} onClick={send}>
          Save
        </button>
        <button type="button" className="link" onClick={result ? props.onDone : props.onCancel}>
          {result ? "Close" : "Cancel"}
        </button>
      </div>
    </div>
  );
}

/** The HSN box on the item form: type a code or words from the description
 * and pick from the list. A code that is not in the list can still be typed. */
export function HsnPicker(props: { value: string; onChange: (code: string) => void }) {
  const [text, setText] = useState("");
  const [typed, setTyped] = useState(false);
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Hsn[]>([]);
  const [cursor, setCursor] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open || !typed) return;
    const t = setTimeout(() => search(text, true).then((f) => setRows(f.results)), 150);
    return () => clearTimeout(t);
  }, [text, typed, open]);
  const close = () => {
    if (typed && /^\d{2,8}$/.test(text.trim())) props.onChange(text.trim());
    else if (typed && text.trim() === "") props.onChange("");
    setOpen(false);
    setTyped(false);
  };
  const pick = (h: Hsn) => {
    props.onChange(h.hsn_code);
    setOpen(false);
    setTyped(false);
  };
  return (
    <div
      className="combo"
      ref={box}
      onBlur={(e) => {
        if (!box.current?.contains(e.relatedTarget as Node | null)) close();
      }}
    >
      <input
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        autoComplete="off"
        inputMode="text"
        placeholder="Type a code or words, e.g. turmeric"
        value={typed ? text : props.value}
        onFocus={(e) => {
          setOpen(true);
          e.target.select();
        }}
        onChange={(e) => {
          setText(e.target.value);
          setTyped(true);
          setOpen(true);
          setCursor(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setCursor((c) => Math.min(c + 1, rows.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setCursor((c) => Math.max(c - 1, 0));
          } else if (e.key === "Enter" && open && typed && rows[cursor]) {
            e.preventDefault();
            pick(rows[cursor]);
          } else if (e.key === "Escape") {
            setOpen(false);
            setTyped(false);
          }
        }}
      />
      {open && typed && (
        <ul className="combo-list" role="listbox">
          {rows.length === 0 && <li className="combo-none">Nothing in the list matches</li>}
          {rows.map((h, i) => (
            <li
              key={h.id}
              role="option"
              aria-selected={h.hsn_code === props.value}
              className={`${i === cursor ? "on" : ""} ${h.hsn_code === props.value ? "chosen" : ""}`}
              tabIndex={-1}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(h)}
              onMouseMove={() => setCursor(i)}
            >
              <strong>{h.hsn_code}</strong> <span className="small">{h.description}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
