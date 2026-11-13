import { useEffect, useRef, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader } from "./Brand";
import { usePrintMenu } from "./Exchange";

/** HSN / SAC codes: one central list kept by MyERP, the same for every customer. */
export type Hsn = { id: number; hsn_code: string; description: string; is_active: boolean };
type Found = { total: number; results: Hsn[] };

const search = (q: string, pick: boolean) =>
  api<Found>(`v1/hsn/?q=${encodeURIComponent(q)}${pick ? "&limit=pick" : ""}`);

/** Masters > HSN codes: the central list, to look up and search. */
export function HsnPage(_props: { session: SignedIn }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Found>({ total: 0, results: [] });
  useEffect(() => {
    const t = setTimeout(() => search(q, false).then(setFound), 200);
    return () => clearTimeout(t);
  }, [q]);
  const printing = usePrintMenu({ title: "HSN codes", scope: q ? `Search: ${q}` : "" });
  return (
    <section className="page">
      <PageHeader
        title="HSN codes"
        actions={printing.buttons}
        sub={`${found.total} code${found.total === 1 ? "" : "s"} · kept centrally by MyERP, the same for every company. Searched when you enter an item's HSN.`}
      />
      {printing.panel}
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
            </tr>
          ))}
          {found.results.length === 0 && (
            <tr>
              <td colSpan={2} className="small">
                {found.total === 0 ? "The list has not been loaded yet." : "Nothing matches."}
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {found.total > found.results.length && q === "" && (
        <p className="small">Showing the first {found.results.length}. Type in the search box to find others.</p>
      )}
    </section>
  );
}

/** The description of the picked HSN code, shown read-only beside the picker. */
export function HsnDescription(props: { code: string }) {
  const [text, setText] = useState("");
  useEffect(() => {
    if (!props.code) {
      setText("");
      return;
    }
    let live = true;
    search(props.code, true).then((f) => {
      if (live) setText(f.results.find((h) => h.hsn_code === props.code)?.description ?? "");
    });
    return () => {
      live = false;
    };
  }, [props.code]);
  return <input readOnly tabIndex={-1} value={text} placeholder="Shown when a code is picked" />;
}

/** The HSN box on the item form: type a code or words from the description
 * and pick from the list. A code that is not in the list is refused. */
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
  const [refused, setRefused] = useState("");
  // Typed text counts only when it is exactly a code in the list; anything
  // else is dropped and the last picked code stays.
  const close = () => {
    const wanted = text.trim().replace(/\s+/g, "");
    setOpen(false);
    setTyped(false);
    if (!typed) return;
    if (wanted === "") {
      props.onChange("");
      setRefused("");
      return;
    }
    search(wanted, true).then((f) => {
      const hit = f.results.find((h) => h.hsn_code === wanted);
      if (hit) {
        props.onChange(hit.hsn_code);
        setRefused("");
      } else setRefused(`${text.trim()} is not in the HSN list. Pick a code from the list.`);
    });
  };
  const pick = (h: Hsn) => {
    props.onChange(h.hsn_code);
    setRefused("");
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
      {refused && <span className="error small">{refused}</span>}
    </div>
  );
}
