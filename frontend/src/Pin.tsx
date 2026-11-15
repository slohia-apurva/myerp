import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { FloatingList } from "./FloatingList";
import { Combobox } from "./Combobox";
import { openRequestAddition } from "./RequestAddition";

/** What the central PIN list knows about a PIN code. */
export type PinInfo = {
  pin: string;
  city: string;
  state_code: string;
  state_name: string;
  couriers: { courier: string; oda: boolean | null }[];
};

/** A PIN code box. When six digits are typed it looks the PIN up in the central
 * list, tells the caller (to fill the state) and shows the city, state and the
 * couriers that deliver there. Typing over the answer is always allowed. */
export function PinInput(props: {
  value: string;
  onChange: (pin: string) => void;
  onFound?: (info: PinInfo) => void;
  maxLength?: number;
}) {
  const [info, setInfo] = useState<PinInfo | null>(null);
  const [missing, setMissing] = useState(false);
  const { value, onFound } = props;
  useEffect(() => {
    setInfo(null);
    setMissing(false);
    if (!/^[1-9][0-9]{5}$/.test(value)) return;
    let live = true;
    api<PinInfo>(`v1/pin/${value}/`).then(
      (found) => {
        if (!live) return;
        setInfo(found);
        onFound?.(found);
      },
      () => live && setMissing(true),
    );
    return () => {
      live = false;
    };
    // onFound is a fresh function on every render; the PIN alone decides a lookup.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  const couriers = info?.couriers.map((c) => `${c.courier}${c.oda ? " (out of delivery area)" : ""}`).join(", ");
  return (
    <>
      <input
        value={value}
        maxLength={props.maxLength ?? 10}
        inputMode="numeric"
        onChange={(e) => props.onChange(e.target.value)}
      />
      {info && (
        <span className="small">
          {[info.city, info.state_name].filter(Boolean).join(", ")}
          {couriers ? ` · Delivers: ${couriers}` : " · No courier list covers this PIN"}
        </span>
      )}
      {missing && <span className="small">This PIN is not in the central list.</span>}
    </>
  );
}

type Country = { code: string; name: string };
let countries: Promise<Country[]> | null = null;

/** Type-to-search picker over the central country list. An older free-text
 * country that is not in the list is kept as it is. */
export function CountryPicker(props: { value: string; onChange: (name: string) => void; required?: boolean }) {
  const [list, setList] = useState<Country[]>([]);
  useEffect(() => {
    countries ??= api<Country[]>("v1/countries/");
    countries.then(setList, () => (countries = null));
  }, []);
  const options = list.map((c) => ({ value: c.name, label: c.name }));
  if (props.value && !list.some((c) => c.name === props.value)) options.unshift({ value: props.value, label: props.value });
  return <Combobox options={options} value={props.value} onChange={props.onChange} required={props.required} />;
}

/** A PIN code in the central list, as the picker offers it. */
export type PinRow = { id: number; pin: string; city: string; state_code: string; state_name: string; is_active: boolean };
type PinFound = { total: number; results: PinRow[] };

export const searchPins = (q: string, pick: boolean) =>
  api<PinFound>(`v1/pin-codes/?q=${encodeURIComponent(q)}${pick ? "&limit=pick" : ""}`);

/** The PIN box of an Indian address: type a PIN, or words of the city or state, and pick from
 * the central list. Typed text counts only when it is exactly a PIN in the list; anything else
 * is dropped. `onPick` gets the row, so the caller can fill the city and the state. */
export function PinPicker(props: { value: string; onPick: (row: PinRow) => void; onClear?: () => void }) {
  const [text, setText] = useState("");
  const [typed, setTyped] = useState(false);
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<PinRow[]>([]);
  const [cursor, setCursor] = useState(0);
  const [refused, setRefused] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open || !typed) return;
    const t = setTimeout(() => searchPins(text, true).then((f) => setRows(f.results)), 150);
    return () => clearTimeout(t);
  }, [text, typed, open]);
  const close = () => {
    const wanted = text.trim().replace(/\s+/g, "");
    setOpen(false);
    setTyped(false);
    if (!typed) return;
    if (wanted === "") {
      props.onClear?.();
      setRefused("");
      return;
    }
    searchPins(wanted, true).then((f) => {
      const hit = f.results.find((r) => r.pin === wanted);
      if (hit) {
        props.onPick(hit);
        setRefused("");
      } else setRefused(`${text.trim()} is not in the PIN list. Pick one from the list, or Request Addition.`);
    });
  };
  const pick = (r: PinRow) => {
    props.onPick(r);
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
        placeholder="Type a PIN or a city, e.g. 560001"
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
        <FloatingList anchor={box}>
          {rows.length === 0 && <li className="combo-none">Nothing in the list matches</li>}
          {rows.map((r, i) => (
            <li
              key={r.id}
              role="option"
              aria-selected={r.pin === props.value}
              className={`${i === cursor ? "on" : ""} ${r.pin === props.value ? "chosen" : ""}`}
              tabIndex={-1}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(r)}
              onMouseMove={() => setCursor(i)}
            >
              <strong>{r.pin}</strong> <span className="small">{[r.city, r.state_name].filter(Boolean).join(", ")}</span>
            </li>
          ))}
        </FloatingList>
      )}
      {refused && <span className="error small">{refused}</span>}
      <button type="button" className="link" onClick={() => openRequestAddition("pin")}>
        PIN not in the list? Request Addition
      </button>
    </div>
  );
}
