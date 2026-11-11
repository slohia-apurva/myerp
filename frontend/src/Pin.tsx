import { useEffect, useState } from "react";
import { api } from "./api";
import { Combobox } from "./Combobox";

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
