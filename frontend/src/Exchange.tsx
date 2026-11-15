import { FormEvent, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api, download, upload, type SignedIn } from "./api";
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
  /** Print and PDF the screen's own table (a tree, say) instead of the
   * export's columns. */
  printScreen?: { title: string; scope?: string };
}): { buttons: ReactNode; panel: ReactNode } {
  const screen = usePrintMenu(props.printScreen ?? { title: "" });
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

  const buttons = screen.menu([
    ...(canImport ? [{ label: "Import from Excel…", onClick: () => setOpen(true) }] : []),
    { label: "Export to Excel", href: `${base}${query({ as: "xlsx" })}` },
    ...(props.printScreen
      ? screen.items
      : [
          { label: "Print", onClick: print },
          { label: "Download PDF", href: `${base}${query({ as: "pdf" })}` },
        ]),
  ]);

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
      {screen.panel}
    </>
  );
  return { buttons, panel };
}

/**
 * Print and PDF for any list screen that is not a master: the "Actions" button
 * with "Print" and "Download PDF". The report is the screen's own table(s),
 * read as they are shown, so it follows the screen when columns change.
 *
 * Tables inside the page (`section.page`) are read, except those inside a
 * form, an open card or anything marked `no-print`. Columns with no heading
 * (Edit, Duplicate) are left out, as are buttons and rows holding a form. A
 * table's `data-title` (or the box it sits in) names its sheet; `data-indent`
 * on a cell's part indents it (tree lists).
 *
 * Usage: const printing = usePrintMenu({ title: "Users" }); put
 * {printing.buttons} in the PageHeader actions and {printing.panel} below it.
 */
export function usePrintMenu(props: {
  title: string;
  scope?: string;
  /** For a screen whose table sits inside a form: give the sheets directly instead of reading the page. */
  read?: () => PrintSheet["sheets"];
}): {
  buttons: ReactNode;
  panel: ReactNode;
  /** "Print" and "Download PDF", to put in a menu with other actions. */
  items: MenuItem[];
  /** The Actions button with these items, able to find its page. */
  menu: (items: MenuItem[]) => ReactNode;
} {
  const [sheet, setSheet] = useState<PrintSheet | null>(null);
  const [error, setError] = useState("");
  const closeSheet = useCallback(() => setSheet(null), []);
  const here = useRef<HTMLSpanElement>(null);
  const read = (): PrintSheet => {
    if (props.read) return { title: props.title, scope: props.scope ?? "", sheets: props.read() };
    const page = here.current?.closest("section.page") ?? document.querySelector("section.page");
    return { title: props.title, scope: props.scope ?? "", sheets: page ? readTables(page, props.title) : [] };
  };
  const print = () => {
    setError("");
    const s = read();
    if (!s.sheets.length) return setError("There is nothing on this screen to print.");
    setSheet(s);
  };
  const pdf = async () => {
    setError("");
    const s = read();
    if (!s.sheets.length) return setError("There is nothing on this screen to put in a PDF.");
    const stem = `${props.title}-${new Date().toISOString().slice(0, 10)}`;
    try {
      await download("v1/print/pdf/", s, `${stem.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.pdf`);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const items: MenuItem[] = [
    { label: "Print", onClick: print },
    { label: "Download PDF", onClick: pdf },
  ];
  const menu = (list: MenuItem[]) => (
    <span ref={here} className="actions-holder">
      <ActionsMenu items={list} />
    </span>
  );
  const panel = (
    <>
      {error && <p className="error">{error}</p>}
      {sheet && <Printout sheet={sheet} onDone={closeSheet} />}
    </>
  );
  return { buttons: menu(items), panel, items, menu };
}

const NUMBER = /^-?₹?\s?[\d,]+(\.\d+)?( (Dr|Cr))?$/;

/** The tables shown in a page, as report sheets. */
export function readTables(page: Element, title: string): PrintSheet["sheets"] {
  const out: PrintSheet["sheets"] = [];
  for (const table of Array.from(page.querySelectorAll("table"))) {
    if (table.closest("form, .card, .no-print, .print-sheet, .actions-panel")) continue;
    const heads = Array.from(table.querySelectorAll(":scope > thead > tr:first-child > th"));
    const keep = heads.map((th) => cellText(th) !== "");
    if (!keep.some(Boolean)) continue;
    const columns = heads.map(cellText).filter((_, i) => keep[i]);
    const rows: string[][] = [];
    for (const tr of Array.from(table.querySelectorAll(":scope > tbody > tr"))) {
      const cells = Array.from(tr.children);
      if (cells.length !== heads.length || tr.querySelector("form")) continue;
      rows.push(cells.map(cellText).filter((_, i) => keep[i]));
    }
    const heading = table.closest(".panel-card")?.querySelector(":scope > h4")?.textContent;
    const right = columns.map((_, j) => {
      const values = rows.map((r) => r[j]).filter((v) => v && v !== "—");
      return values.length > 0 && values.every((v) => NUMBER.test(v));
    });
    out.push({ title: table.dataset.title || heading || title, columns, rows, right });
  }
  return out;
}

/** A cell's words: each part (a name, its note below, a tag) joined with " · ";
 * buttons, inputs and decorations left out. */
function cellText(cell: Element): string {
  const parts: string[] = [];
  let buf = "";
  const flush = () => {
    const t = buf
      .replace(/\s*\n\s*/g, ", ")
      .replace(/\s+/g, " ")
      .replace(/^[\s·,]+|[\s·,]+$/g, "");
    if (t) parts.push(t);
    buf = "";
  };
  const walk = (node: Node) => {
    for (const child of Array.from(node.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) {
        buf += child.textContent ?? "";
        continue;
      }
      if (!(child instanceof Element)) continue;
      if (["BUTTON", "INPUT", "SELECT", "TEXTAREA", "svg"].includes(child.tagName)) continue;
      if (child.getAttribute("aria-hidden") === "true" || child.classList.contains("no-print")) continue;
      flush();
      if (child.tagName === "BR") continue;
      const indent = Number((child as HTMLElement).dataset?.indent ?? 0);
      const before = parts.length;
      walk(child);
      flush();
      if (indent > 0 && parts.length > before) parts[before] = "   ".repeat(indent) + parts[before];
    }
  };
  walk(cell);
  flush();
  return parts.join(" · ");
}

type MenuItem = { label: string; onClick?: () => void; href?: string };

/** One "Actions" button whose list holds a screen's Import, Export, Print
 * and PDF. The same button on every screen. */
export function ActionsMenu({ items }: { items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className="actions-menu" ref={box}>
      <button type="button" className="link" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        Actions <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="actions-panel" role="menu">
          {items.map((item) =>
            item.href ? (
              <a key={item.label} role="menuitem" href={item.href} download onClick={() => setOpen(false)}>
                {item.label}
              </a>
            ) : (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  item.onClick?.();
                }}
              >
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}

export type PrintSheet = {
  title: string;
  scope: string;
  /** The list, then any rows kept inside its records (parts, units of measure). */
  sheets: { title: string; columns: string[]; rows: string[][]; right?: boolean[] }[];
};

type Outcome = {
  rows: number;
  new: number;
  changed: number;
  same: number;
  errors: { sheet: string; row: number; messages: string[] }[];
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
                  <th>Sheet</th>
                  <th>Row</th>
                  <th>Problem</th>
                </tr>
              </thead>
              <tbody>
                {outcome.errors.map((e) => (
                  <tr key={`${e.sheet}-${e.row}`}>
                    <td>{e.sheet}</td>
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
/** The company's image for the top of page 1 (core/print_mark.py), fetched once. */
let markRequest: Promise<string> | null = null;
function printMark(): Promise<string> {
  markRequest ??= api<{ mark: string }>("v1/print/mark/")
    .then((r) => r.mark)
    .catch(() => {
      markRequest = null;
      return "";
    });
  return markRequest;
}

function Printout({ sheet, onDone }: { sheet: PrintSheet; onDone: () => void }) {
  const [mark, setMark] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    printMark().then((m) => live && setMark(m));
    return () => {
      live = false;
    };
  }, []);
  return mark === null ? null : <PrintoutSheet sheet={sheet} mark={mark} onDone={onDone} />;
}

function PrintoutSheet({ sheet, mark, onDone }: { sheet: PrintSheet; mark: string; onDone: () => void }) {
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
      {mark && <img className="print-mark" src={mark} alt="" />}
      <h1>{sheet.title}</h1>
      <p className="small">
        {[sheet.scope, `printed ${today}`, plural(sheet.sheets[0].rows.length, "row")].filter(Boolean).join(" · ")}
      </p>
      {sheet.sheets.map((t, n) => (
        <section key={t.title}>
          {n > 0 && <h2>{t.title}</h2>}
          <table>
            <thead>
              <tr>
                {t.columns.map((c, j) => (
                  <th key={c} className={t.right?.[j] ? "num" : undefined}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {t.rows.map((r, i) => (
                <tr key={i}>
                  {r.map((v, j) => (
                    <td key={j} className={t.right?.[j] ? "num" : undefined}>
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>,
    document.body,
  );
}
