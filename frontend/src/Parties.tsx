import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { money, StateSelect, useStates, type State } from "./Companies";

/** Customer or supplier details kept beside a debtor or creditor ledger. */
export type PartyAddress = {
  label: string;
  address: string;
  pincode: string;
  state_code: string;
  country: string;
  gstin: string;
  is_billing: boolean;
  is_shipping: boolean;
};
export type PartyContact = {
  name: string;
  designation: string;
  phone: string;
  email: string;
  is_primary: boolean;
};
export type Party = {
  gst_type: string;
  gstin: string;
  pan: string;
  state_code: string;
  country: string;
  credit_limit: string;
  credit_days: number | null;
  salesman: number | null;
  salesman_name?: string;
  addresses: PartyAddress[];
  contacts: PartyContact[];
};

export const GST_TYPES: [string, string][] = [
  ["regular", "Registered (regular)"],
  ["composition", "Registered (composition)"],
  ["unregistered", "Unregistered business"],
  ["consumer", "Consumer"],
  ["sez", "SEZ unit or developer"],
  ["overseas", "Overseas"],
];
const REGISTERED = ["regular", "composition", "sez"];

export const blankParty = (stateCode: string): Party => ({
  gst_type: "unregistered",
  gstin: "",
  pan: "",
  state_code: stateCode,
  country: "India",
  credit_limit: "",
  credit_days: null,
  salesman: null,
  addresses: [],
  contacts: [],
});

const blankAddress = (stateCode: string): PartyAddress => ({
  label: "",
  address: "",
  pincode: "",
  state_code: stateCode,
  country: "India",
  gstin: "",
  is_billing: false,
  is_shipping: false,
});

const blankContact = (): PartyContact => ({ name: "", designation: "", phone: "", email: "", is_primary: false });

type Person = { id: number; name: string };
type Tab = "details" | "addresses" | "contacts";

/** The "Party details" part of the ledger form. */
export function PartyFields({ value: p, onChange }: { value: Party; onChange: (p: Party) => void }) {
  const states = useStates();
  const [people, setPeople] = useState<Person[]>([]);
  useEffect(() => {
    api<Person[]>("v1/people/").then(setPeople);
  }, []);
  const [tab, setTab] = useState<Tab>("details");
  const box = useRef<HTMLFieldSetElement>(null);
  useEffect(() => {
    // A required field left empty on a hidden tab: open that tab and point at it.
    const el = box.current;
    if (!el) return;
    const onInvalid = (e: Event) => {
      const target = e.target as HTMLInputElement;
      const panel = target.closest<HTMLElement>("[data-tab]");
      if (panel?.hidden) {
        setTab(panel.dataset.tab as Tab);
        requestAnimationFrame(() => target.reportValidity());
      }
    };
    el.addEventListener("invalid", onInvalid, true);
    return () => el.removeEventListener("invalid", onInvalid, true);
  }, []);
  const set = (change: Partial<Party>) => onChange({ ...p, ...change });
  const overseas = p.gst_type === "overseas";
  const registered = REGISTERED.includes(p.gst_type);
  const onGstin = (raw: string) => {
    const v = raw.toUpperCase();
    const change: Partial<Party> = { gstin: v };
    if (v.length >= 2 && states.some((s) => s.code === v.slice(0, 2))) change.state_code = v.slice(0, 2);
    if (v.length >= 12) change.pan = v.slice(2, 12);
    set(change);
  };
  const setAddress = (i: number, change: Partial<PartyAddress>) =>
    set({
      addresses: p.addresses.map((a, j) => {
        if (j === i) return { ...a, ...change };
        // Only one default billing and one default shipping address.
        const off: Partial<PartyAddress> = {};
        if (change.is_billing) off.is_billing = false;
        if (change.is_shipping) off.is_shipping = false;
        return { ...a, ...off };
      }),
    });
  const setContact = (i: number, change: Partial<PartyContact>) =>
    set({
      contacts: p.contacts.map((c, j) =>
        j === i ? { ...c, ...change } : change.is_primary ? { ...c, is_primary: false } : c,
      ),
    });
  const tabs: [Tab, string][] = [
    ["details", "GST and credit"],
    ["addresses", `Addresses (${p.addresses.length})`],
    ["contacts", `Contacts (${p.contacts.length})`],
  ];

  return (
    <fieldset ref={box}>
      <legend>Party details</legend>
      <div className="form-tabs" role="tablist">
        {tabs.map(([code, label]) => (
          <button
            key={code}
            type="button"
            role="tab"
            aria-selected={tab === code}
            className={tab === code ? "active" : ""}
            onClick={() => setTab(code)}
          >
            {label}
          </button>
        ))}
      </div>
      <div data-tab="details" hidden={tab !== "details"}>
      <div className="row">
        <label>
          GST type
          <select
            value={p.gst_type}
            onChange={(e) => {
              const t = e.target.value;
              set({
                gst_type: t,
                ...(REGISTERED.includes(t) ? {} : { gstin: "" }),
                ...(t === "overseas" ? { state_code: "", country: p.country === "India" ? "" : p.country } : {}),
                ...(t !== "overseas" && p.gst_type === "overseas" ? { country: "India" } : {}),
              });
            }}
          >
            {GST_TYPES.map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {registered && (
          <label>
            GSTIN
            <input required value={p.gstin} maxLength={15} onChange={(e) => onGstin(e.target.value)} />
          </label>
        )}
      </div>
      <div className="row">
        {overseas ? (
          <label>
            Country
            <input required value={p.country} onChange={(e) => set({ country: e.target.value })} />
          </label>
        ) : (
          <label>
            State (decides the place of supply)
            <StateSelect states={states} value={p.state_code} onChange={(code) => set({ state_code: code })} />
          </label>
        )}
        {!overseas && (
          <label>
            PAN
            <input value={p.pan} maxLength={10} onChange={(e) => set({ pan: e.target.value.toUpperCase() })} />
          </label>
        )}
      </div>
      <div className="row">
        <label>
          Credit limit (₹, blank = no limit)
          <input
            className="num"
            inputMode="decimal"
            value={Number(p.credit_limit) ? p.credit_limit : ""}
            onChange={(e) => set({ credit_limit: e.target.value })}
          />
        </label>
        <label>
          Credit days
          <input
            className="num"
            inputMode="numeric"
            value={p.credit_days ?? ""}
            onChange={(e) => set({ credit_days: e.target.value === "" ? null : Number(e.target.value) || 0 })}
          />
        </label>
        <label>
          Salesman
          <select
            value={p.salesman ?? ""}
            onChange={(e) => set({ salesman: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">None</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      </div>

      <div data-tab="addresses" hidden={tab !== "addresses"}>
      {p.addresses.length === 0 && <p className="small">No addresses yet.</p>}
      {p.addresses.length > 0 && (
        <div className="addresses">
          {p.addresses.map((a, i) => (
            <div className="address-card" key={i}>
              <div className="row">
                <label>
                  Name
                  <input
                    required
                    value={a.label}
                    placeholder="e.g. Head office, Bhiwandi godown"
                    onChange={(e) => setAddress(i, { label: e.target.value })}
                  />
                </label>
                <label>
                  {overseas ? "Country" : "State"}
                  {overseas ? (
                    <input value={a.country} onChange={(e) => setAddress(i, { country: e.target.value })} />
                  ) : (
                    <StateSelect
                      states={states}
                      value={a.state_code}
                      onChange={(code) => setAddress(i, { state_code: code })}
                    />
                  )}
                </label>
              </div>
              <label>
                Address
                <textarea
                  required
                  rows={2}
                  value={a.address}
                  onChange={(e) => setAddress(i, { address: e.target.value })}
                />
              </label>
              <div className="row">
                <label>
                  PIN code
                  <input value={a.pincode} onChange={(e) => setAddress(i, { pincode: e.target.value })} />
                </label>
                {registered && (
                  <label>
                    GSTIN at this address (if different)
                    <input
                      value={a.gstin}
                      maxLength={15}
                      onChange={(e) => setAddress(i, { gstin: e.target.value.toUpperCase() })}
                    />
                  </label>
                )}
              </div>
              <div className="address-flags">
                <label className="check">
                  <input
                    type="checkbox"
                    checked={a.is_billing}
                    onChange={(e) => setAddress(i, { is_billing: e.target.checked })}
                  />
                  Default billing address
                </label>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={a.is_shipping}
                    onChange={(e) => setAddress(i, { is_shipping: e.target.checked })}
                  />
                  Default shipping address
                </label>
                <button
                  type="button"
                  className="link danger"
                  onClick={() => set({ addresses: p.addresses.filter((_, j) => j !== i) })}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        className="link"
        onClick={() =>
          set({
            addresses: [
              ...p.addresses,
              {
                ...blankAddress(p.state_code),
                country: overseas ? p.country : "India",
                is_billing: p.addresses.length === 0,
                is_shipping: p.addresses.length === 0,
              },
            ],
          })
        }
      >
        + Add address
      </button>
      </div>

      <div data-tab="contacts" hidden={tab !== "contacts"}>
      {p.contacts.length === 0 && <p className="small">No contacts yet.</p>}
      {p.contacts.length > 0 && (
        <div className="addresses">
          {p.contacts.map((c, i) => (
            <div className="address-card" key={i}>
              <div className="row">
                <label>
                  Name
                  <input required value={c.name} onChange={(e) => setContact(i, { name: e.target.value })} />
                </label>
                <label>
                  Designation
                  <input
                    value={c.designation}
                    placeholder="e.g. Purchase manager, Accounts"
                    onChange={(e) => setContact(i, { designation: e.target.value })}
                  />
                </label>
              </div>
              <div className="row">
                <label>
                  Phone
                  <input value={c.phone} onChange={(e) => setContact(i, { phone: e.target.value })} />
                </label>
                <label>
                  Email
                  <input type="email" value={c.email} onChange={(e) => setContact(i, { email: e.target.value })} />
                </label>
              </div>
              <div className="address-flags">
                <label className="check">
                  <input
                    type="checkbox"
                    checked={c.is_primary}
                    onChange={(e) => setContact(i, { is_primary: e.target.checked })}
                  />
                  Main contact
                </label>
                <button
                  type="button"
                  className="link danger"
                  onClick={() => set({ contacts: p.contacts.filter((_, j) => j !== i) })}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        className="link"
        onClick={() =>
          set({ contacts: [...p.contacts, { ...blankContact(), is_primary: p.contacts.length === 0 }] })
        }
      >
        + Add contact
      </button>
      </div>
    </fieldset>
  );
}

/** Party details in the ledger side panel. */
export function PartySummary({ party: p, states }: { party: Party; states?: State[] }) {
  const gstType = GST_TYPES.find(([code]) => code === p.gst_type)?.[1] ?? p.gst_type;
  const stateName = (code: string) => states?.find((s) => s.code === code)?.name ?? code;
  const place = p.gst_type === "overseas" ? p.country : stateName(p.state_code);
  const rows: [string, string][] = [
    ["GST", p.gstin ? `${gstType} · ${p.gstin}` : gstType],
    ["State / country", place],
    ["PAN", p.pan],
    ["Credit limit", Number(p.credit_limit) ? `₹ ${money(p.credit_limit)}` : "No limit"],
    ["Credit days", p.credit_days !== null ? String(p.credit_days) : ""],
    ["Salesman", p.salesman_name ?? ""],
  ];
  return (
    <>
      <h3>Party details</h3>
      <dl className="kv">
        {rows
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
      </dl>
      {p.addresses.length > 0 && (
        <>
          <h3>Addresses</h3>
          <ul className="address-list">
            {p.addresses.map((a) => (
              <li key={a.label}>
                <strong>{a.label}</strong>
                {a.is_billing && <span className="pill on">Billing</span>}
                {a.is_shipping && <span className="pill on">Shipping</span>}
                <div className="pre">{a.address}</div>
                <div className="small">
                  {[a.pincode, a.state_code ? stateName(a.state_code) : a.country, a.gstin && `GSTIN ${a.gstin}`]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      {p.contacts.length > 0 && (
        <>
          <h3>Contacts</h3>
          <ul className="address-list">
            {p.contacts.map((c, i) => (
              <li key={i}>
                <strong>{c.name}</strong>
                {c.designation && <span className="small"> · {c.designation}</span>}
                {c.is_primary && <span className="pill on">Main</span>}
                <div className="small">{[c.phone, c.email].filter(Boolean).join(" · ")}</div>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
