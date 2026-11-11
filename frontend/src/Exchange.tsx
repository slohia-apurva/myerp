import { FormEvent, useCallback, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api, upload, type SignedIn } from "./api";
import { Section } from "./Brand";

/**
 * Import, Export and Print for a masters screen: one standard set for every
 * master. The columns come from the server, from the same fields the form
 * saves, so they follow the form when fields are added. Import checks every
 * row the way the form does and saves nothing unless every row is right.
 *
 * Usage: const io = useExchange({ master: "units", noun: "units", ... });
 * put {io.buttons} in the PageHeader actions and {io.panel} above the list.
 */
export function useExchange(props: {
  /** The master's key on the server, e.g. "units". */
  master: string;
  /** What the list holds, in words: "units". */
  noun: string;
  session: SignedIn;
  /** For masters kept per company. */
  company?: number;
  /** Called after an import has saved, to reload the list. */
  onImported: () => void;
}): { buttons: ReactNode; panel: ReactNode } {
  const perms = props.session.permissions;
  const canImport = perms.includes("masters.edit") && perms.includes("masters.import");
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState<PrintSheet | null>(null);
  const [error, setError] = useState("");
  const closeSheet = useCallback(() => setSheet(null), []);
  const base = `/api/v1/exchange/${props.master}/`;
  const query = (extra: Record<string, string>) => {
    const q = new URLSearchParams(extra);
    if (props.company) q.set("company", String(props.company));
    return `?${q}`;
  };

  const print = async () => {
    setError("");
    try {
      setSheet(await api<PrintSheet>(`v1/exchange/${props.master}/${query({ as: "json" })}`));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const buttons = (
    <>
      {canImport && (
        <button type="button" className="link" onClick={() => setOpen(!open)}>
          Import
        </button>
      )}
      <a className="button" href={`${base}${query({ as: "xlsx" })}`} download>
        Export
      </a>
      <button type="button" className="link" onClick={print}>
        Print
      </button>
    </>
  );

  const panel = (
    <>
      {error && <p className="error">{error}</p>}
      {open && (
        <ImportForm
          {...props}
          template={`${base}${query({ as: "xlsx", blank: "1" })}`}
          onClose={() => setOpen(false)}
        />
      )}
      {sheet && <Printout sheet={sheet} onDone={closeSheet} />}
    </>
  );
  return { buttons, panel };
}

type PrintSheet = { title: string; scope: string; columns: string[]; rows: string[][] };

type Outcome = {
  rows: number;
  new: number;
  changed: number;
  same: number;
  errors: { row: number; messages: string[] }[];
  saved: boolean;
};

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function ImportForm(props: {
  master: string;
  noun: string;
  company?: number;
  template: string;
  onImported: () => void;
  onClose: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const send = async (commit: boolean) => {
    if (!file) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("file", file);
    form.append("commit", commit ? "1" : "0");
    if (props.company) form.append("company", String(props.company));
    try {
      const out = await upload<Outcome>(`v1/exchange/${props.master}/import/`, form);
      setOutcome(out);
      if (out.saved) props.onImported();
    } catch (err) {
      setOutcome(null);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const check = (event: FormEvent) => {
    event.preventDefault();
    send(false);
  };

  const summary = outcome && (
    <p>
      {plural(outcome.rows, "row")}: {outcome.new} new, {outcome.changed} changed, {outcome.same} with no change
      {outcome.errors.length > 0 && `, ${plural(outcome.errors.length, "row")} with problems`}.
    </p>
  );

  return (
    <form className="card" onSubmit={check}>
      <h4>Import {props.noun} from a file</h4>
      <Section title="File">
        <p className="small">
          Start from "Export" (it has every column, and the ID that tells MyERP which record to change) or from the{" "}
          <a href={props.template} download>
            blank template
          </a>
          . Leave the ID empty for a new one. Excel (.xlsx) or CSV. MyERP checks every row the way the form does, and
          saves nothing until every row is right.
        </p>
        <label>
          File to import
          <input
            type="file"
            required
            accept=".xlsx,.csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setOutcome(null);
            }}
          />
        </label>
      </Section>
      {outcome && !outcome.saved && (
        <Section title={outcome.errors.length ? "Fix these rows, then check again" : "Ready to import"}>
          {summary}
          {outcome.errors.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Problem</th>
                </tr>
              </thead>
              <tbody>
                {outcome.errors.map((e) => (
                  <tr key={e.row}>
                    <td>{e.row}</td>
                    <td>
                      {e.messages.map((m) => (
                        <div key={m}>{m}</div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="small">Nothing is saved yet. Press "Import" to save these rows.</p>
          )}
        </Section>
      )}
      {outcome?.saved && (
        <Section title="Imported">
          {summary}
        </Section>
      )}
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {outcome && !outcome.saved && outcome.errors.length === 0 ? (
          <button type="button" disabled={busy} onClick={() => send(true)}>
            Import
          </button>
        ) : (
          !outcome?.saved && <button disabled={busy || !file}>Check file</button>
        )}
        <button type="button" className="link" onClick={props.onClose}>
          {outcome?.saved ? "Close" : "Cancel"}
        </button>
      </div>
    </form>
  );
}

/** The list as a plain printed table: rendered outside the app, printed,
 * then removed. */
function Printout({ sheet, onDone }: { sheet: PrintSheet; onDone: () => void }) {
  useEffect(() => {
    document.body.classList.add("printing-sheet");
    const finish = () => {
      document.body.classList.remove("printing-sheet");
      onDone();
    };
    window.addEventListener("afterprint", finish, { once: true });
    const timer = window.setTimeout(() => window.print(), 50);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("afterprint", finish);
      document.body.classList.remove("printing-sheet");
    };
  }, [onDone]);
  const today = new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  return createPortal(
    <div className="print-sheet">
      <h1>{sheet.title}</h1>
      <p className="small">
        {sheet.scope} · printed {today} · {plural(sheet.rows.length, "row")}
      </p>
      <table>
        <thead>
          <tr>
            {sheet.columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sheet.rows.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => (
                <td key={j}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>,
    document.body,
  );
}
