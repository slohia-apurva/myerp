import { useEffect, useRef, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader } from "./Brand";

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
  return (
    <section className="page">
      <PageHeader
        title="HSN codes"
        sub={`${found.total} code${found.total === 1 ? "" : "s"} · kept centrally by MyERP, the same for every company. Searched when you enter an item's HSN.`}
      />
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
