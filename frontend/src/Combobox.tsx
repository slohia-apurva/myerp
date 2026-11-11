import { useEffect, useMemo, useRef, useState } from "react";
import { type Creatable, type Created, openCreate, useCreated } from "./Create";

export type Option = { value: string; label: string; indent?: number; hint?: string };

const CREATE = "\u0000create";

/** A type-to-search picker for masters (groups, states, terms, parties...).
 * Typing narrows the list (every word typed must appear in the name, in any
 * order); arrow keys and Enter pick, Escape closes. `empty` adds a first
 * choice with value "" (for example "None" or "All groups").
 *
 * `create` (pass it only when the person may add that master) adds
 * 'Create "<typed>"' when no name matches exactly: it opens the master's
 * screen in a new tab, and the record saved there is picked here (Create.tsx). */
export function Combobox(props: {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  empty?: string;
  required?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  create?: Creatable;
}) {
  const { options, value } = props;
  const all = useMemo(
    () => (props.empty !== undefined ? [{ value: "", label: props.empty }, ...options] : options),
    [options, props.empty],
  );
  const chosen = all.find((o) => o.value === value);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [typed, setTyped] = useState(false); // text is a search, not the chosen name
  const [cursor, setCursor] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);

  const typedName = text.split(/\s+/).filter(Boolean).join(" ");
  const shown = useMemo(() => {
    if (!typed) return all;
    const words = typedName.toLowerCase().split(" ").filter(Boolean);
    const found = all.filter((o) => {
      const hay = `${o.label} ${o.hint ?? ""}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    });
    const exact = all.some((o) => o.label.toLowerCase() === typedName.toLowerCase());
    if (props.create && typedName && !exact) found.push({ value: CREATE, label: `Create "${typedName}"` });
    return found;
  }, [all, typedName, typed, props.create]);

  // A record saved in the tab that "Create …" opened: reload the list, pick it.
  const waiting = useRef(false);
  useCreated(props.create?.kind, async (c: Created) => {
    if (!waiting.current) return;
    waiting.current = false;
    await props.create?.reload();
    props.onChange(String(c.id));
  });

  useEffect(() => {
    if (list.current && open) list.current.children[cursor]?.scrollIntoView?.({ block: "nearest" });
  }, [cursor, open]);

  const close = () => {
    setOpen(false);
    setTyped(false);
  };
  const pick = (o: Option) => {
    if (o.value === CREATE && props.create) {
      waiting.current = true;
      openCreate(props.create, typedName);
    } else props.onChange(o.value);
    close();
  };
  const display = typed ? text : (chosen?.label ?? "");

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
        aria-label={props.ariaLabel}
        autoComplete="off"
        required={props.required && !chosen?.value}
        placeholder={props.placeholder ?? "Type to search…"}
        value={display}
        onFocus={(e) => {
          setOpen(true);
          setCursor(Math.max(0, all.findIndex((o) => o.value === value)));
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
            setOpen(true);
            setCursor((c) => Math.min(c + 1, shown.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setCursor((c) => Math.max(c - 1, 0));
          } else if (e.key === "Enter" && open) {
            e.preventDefault();
            if (shown[cursor]) pick(shown[cursor]);
          } else if (e.key === "Escape") {
            close();
          }
        }}
      />
      {open && (
        <ul className="combo-list" role="listbox" ref={list}>
          {shown.length === 0 && <li className="combo-none">Nothing matches</li>}
          {shown.map((o, i) => (
            <li
              key={o.value || "empty"}
              role="option"
              aria-selected={o.value === value}
              className={`${i === cursor ? "on" : ""} ${o.value === value ? "chosen" : ""} ${o.value === CREATE ? "create" : ""}`}
              style={{ paddingLeft: 12 + (typed ? 0 : (o.indent ?? 0) * 16) }}
              tabIndex={-1}
              onMouseDown={(e) => e.preventDefault()}
              onClick={(e) => {
                e.preventDefault();
                pick(o);
              }}
              onMouseMove={() => setCursor(i)}
            >
              {o.label}
              {o.hint && <span className="small"> {o.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
