import { useEffect, useMemo, useRef, useState } from "react";
import { type Creatable, type Created, openCreate, useCreated } from "./Create";
import { FloatingList } from "./FloatingList";

export type Option = { value: string; label: string; indent?: number; hint?: string };

const CREATE = "\u0000create";
const LIMIT = 50;

/** A type-to-search picker for masters (groups, states, terms, parties...).
 * Typing narrows the list (every word typed must appear in the name, in any
 * order); arrow keys and Enter pick, Escape closes. `empty` adds a first
 * choice with value "" (for example "None" or "All groups").
 *
 * `create` (pass it only when the person may add that master) adds
 * 'Create "<typed>"' when no name matches exactly: it opens the master's
 * screen in a new tab, and the record saved there is picked here (Create.tsx).
 *
 * `createHere` is the one exception (Sidharth, 2026-11-15): a record made on the
 * line itself, such as a new batch on a goods receipt. It offers 'New "<typed>"'
 * and hands the typed text back instead of opening a tab.
 *
 * `onType` hears each change of the typed text, so a long list (items) can be
 * fetched from the server as the person types. */
export function Combobox(props: {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  empty?: string;
  required?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  create?: Creatable;
  createHere?: { label: string; pick: (typed: string) => void };
  /** Told what is typed, for a list the server searches (useItemSearch, ItemSearch.ts). */
  onType?: (typed: string) => void;
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
    if (props.createHere && typedName && !exact) found.push({ value: CREATE, label: `${props.createHere.label} "${typedName}"` });
    return found;
  }, [all, typedName, typed, props.create, props.createHere]);

  // Only the first LIMIT matches are drawn (12,000 items made each item picker slow to open,
  // Sidharth 2026-11-24); a line under them says how many more there are, to type more.
  const visible = useMemo(() => {
    if (shown.length <= LIMIT) return shown;
    const head = shown.slice(0, LIMIT);
    const last = shown[shown.length - 1];
    if (last.value === CREATE) head.push(last);
    const picked = shown.find((o) => o.value === value);
    if (picked && !head.includes(picked)) head.unshift(picked);
    return head;
  }, [shown, value]);
  const more = shown.length - visible.length;

  // A record saved in the tab that "Create …" opened: reload the list, pick it.
  const waiting = useRef(false);
  useCreated(props.create?.kind, async (c: Created) => {
    if (!waiting.current) return;
    waiting.current = false;
    await props.create?.reload();
    props.onChange(String(c.id));
  });

  useEffect(() => {
    // Scroll only the list itself to the highlighted name; scrollIntoView would also scroll the page and
    // any box around the field.
    const ul = list.current;
    const li = ul?.children[cursor] as HTMLElement | undefined;
    if (!ul || !li || !open) return;
    if (li.offsetTop < ul.scrollTop) ul.scrollTop = li.offsetTop;
    else if (li.offsetTop + li.offsetHeight > ul.scrollTop + ul.clientHeight)
      ul.scrollTop = li.offsetTop + li.offsetHeight - ul.clientHeight;
  }, [cursor, open]);

  const close = () => {
    setOpen(false);
    setTyped(false);
  };
  const pick = (o: Option) => {
    if (o.value === CREATE && props.createHere) props.createHere.pick(typedName);
    else if (o.value === CREATE && props.create) {
      waiting.current = true;
      openCreate(props.create, typedName);
    } else props.onChange(o.value);
    close();
  };
  const display = typed ? text : (chosen?.label ?? "");

  return (
    <div
      className={open ? "combo open" : "combo"}
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
        onClick={() => setOpen(true)}
        onFocus={(e) => {
          setOpen(true);
          setCursor(Math.max(0, visible.findIndex((o) => o.value === value)));
          e.target.select();
        }}
        onChange={(e) => {
          setText(e.target.value);
          props.onType?.(e.target.value);
          setTyped(true);
          setOpen(true);
          setCursor(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setCursor((c) => Math.min(c + 1, visible.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setCursor((c) => Math.max(c - 1, 0));
          } else if (e.key === "Enter" && open) {
            e.preventDefault();
            if (visible[cursor]) pick(visible[cursor]);
          } else if (e.key === "Escape") {
            close();
          }
        }}
      />
      {/* The small down arrow that says this field opens a list (Sidharth, 2026-11-14). */}
      <svg className="combo-arrow" viewBox="0 0 16 16" aria-hidden="true">
        <path d="M3.5 6l4.5 4.5L12.5 6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {open && (
        <FloatingList anchor={box} listRef={list}>
          {shown.length === 0 && <li className="combo-none">Nothing matches</li>}
          {visible.map((o, i) => (
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
          {more > 0 && (
            <li className="combo-none" aria-hidden="true">
              {more.toLocaleString("en-IN")} more: type more of the name to narrow the list
            </li>
          )}
        </FloatingList>
      )}
    </div>
  );
}
