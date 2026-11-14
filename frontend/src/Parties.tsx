import { CountryPicker, PinInput } from "./Pin";
import { Section } from "./Brand";
import { SidePanel, SideRows } from "./Master";
import { PartyDocuments } from "./PartyDocuments";
import { PartyProducts, type PartyProduct } from "./PartyProducts";
import { Combobox } from "./Combobox";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { creatable } from "./Create";
import { useCreditTerms } from "./CreditTerms";
import { money, type Company, StateSelect, useStates, type State } from "./Companies";

/** Customer or supplier details kept beside a debtor or creditor ledger. */
export type PartyAddress = {
  label: string;
  address: string;
  pincode: string;
  city: string;
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
  /** "Main": one per party. */
  is_primary: boolean;
  /** The other types: automated emails go to the contacts of the right type. */
  kinds: string[];
};

/** What a contact is for, besides Main. Keep in step with CONTACT_KINDS in core/models.py. */
export const CONTACT_KINDS: [string, string][] = [
  ["accounts", "Accounting"],
  ["shipping", "Shipping"],
  ["purchase", "Purchase"],
  ["sales", "Sales"],
];
const kindLabel = (code: string) => CONTACT_KINDS.find(([k]) => k === code)?.[1] ?? code;
export type Party = {
  id?: number;
  name?: string;
  /** Companies that have a ledger for this party (shared by the group). */
  companies?: { id: number; name: string; ledger: number; side?: "customer" | "supplier" | "" }[];
  /** Given on Save the first time a company deals with the party as a customer or supplier. */
  customer_number: string;
  vendor_number: string;
  gst_type: string;
  gstin: string;
  pan: string;
  state_code: string;
  country: string;
  credit_limit: string;
  credit_term: number | null;
  credit_term_name?: string;
  salesman: number | null;
  salesman_name?: string;
  addresses: PartyAddress[];
  contacts: PartyContact[];
  products: PartyProduct[];
  lock?: LockInfo;
  /** Documents kept for the party (read only; the Documents tab saves its own). */
  document_count?: number;
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
  customer_number: "",
  vendor_number: "",
  gst_type: "unregistered",
  gstin: "",
  pan: "",
  state_code: stateCode,
  country: "India",
  credit_limit: "",
  credit_term: null,
  salesman: null,
  addresses: [],
  contacts: [],
  products: [],
});

const blankAddress = (stateCode: string): PartyAddress => ({
  label: "",
  address: "",
  pincode: "",
  city: "",
  state_code: stateCode,
  country: "India",
  gstin: "",
  is_billing: false,
  is_shipping: false,
});

const blankContact = (): PartyContact => ({ name: "", designation: "", phone: "", email: "", is_primary: false, kinds: [] });

type Person = { id: number; name: string };
export type PartyTab = "general" | "details" | "addresses" | "contacts" | "documents" | "products" | "labels" | "extra";

/** The tab strip at the top of a customer/supplier ledger form. */
export function PartyTabBar(props: {
  tab: PartyTab;
  onTab: (t: PartyTab) => void;
  party: Party;
  extraLabel: string;
  /** Suppliers do not get the "Labels" tab. */
  supplier?: boolean;
}) {
  const tabs: [PartyTab, string][] = [
    ["general", "General"],
    ["details", "GST and credit"],
    ["addresses", `Addresses (${props.party.addresses.length})`],
    ["contacts", `Contacts (${props.party.contacts.length})`],
    ["documents", `Documents (${props.party.document_count ?? 0})`],
    ["products", `Products (${(props.party.products ?? []).length})`],
    ...(props.supplier ? [] : ([["labels", "Labels"]] as [PartyTab, string][])),
    ["extra", props.extraLabel],
  ];
  return (
    <div className="form-tabs" role="tablist">
      {tabs.map(([code, label]) => (
        <button
          key={code}
          type="button"
          role="tab"
          aria-selected={props.tab === code}
          className={props.tab === code ? "active" : ""}
          onClick={() => props.onTab(code)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** One section of the party details: a tab panel (hidden unless its tab shows) or, when the form
 * uses folding sections, the body of its fold. */
function PanelBox(props: {
  ctx: { tab: PartyTab; fold?: (code: PartyTab, body: ReactNode) => ReactNode };
  code: PartyTab;
  off?: boolean;
  children: ReactNode;
}) {
  const { tab, fold } = props.ctx;
  if (fold) return props.off ? null : <>{fold(props.code, <div data-tab={props.code}>{props.children}</div>)}</>;
  return (
    <div data-tab={props.code} hidden={tab !== props.code || props.off}>
      {props.children}
    </div>
  );
}

/** The "Party details" part of the ledger form. */
export function PartyFields({
  value: p,
  onChange,
  supplier,
  extraTab,
  tab,
  fold,
  canEdit,
  companyId,
  alsoIn,
  onAlsoIn,
}: {
  value: Party;
  /** A supplier has a purchaser where a customer has a salesman. */
  supplier: boolean;
  companyId: number;
  /** Other companies to add this party's ledger to on Save. */
  alsoIn: number[];
  onAlsoIn: (ids: number[]) => void;
  onChange: (p: Party) => void;
  /** The tab being shown; the strip itself is PartyTabBar, at the top of the form. */
  tab: PartyTab;
  /** Folding sections instead of tabs (Sidharth, 2026-11-14): wraps each section in its fold. */
  fold?: (code: PartyTab, body: ReactNode) => ReactNode;
  /** Whether the person may add and change documents. */
  canEdit?: boolean;
  /** The content of the "Opening balance" tab, from the ledger form. */
  extraTab?: { label: string; content: ReactNode };
}) {
  const states = useStates();
  const { terms, refresh: refreshTerms } = useCreditTerms();
  const newTerm = creatable("credit_term", "credit-terms", refreshTerms);
  const [companies, setCompanies] = useState<Company[]>([]);
  useEffect(() => {
    api<Company[]>("v1/companies/").then(setCompanies);
  }, []);
  const linked = new Set([companyId, ...(p.companies ?? []).map((c) => c.id)]);
  const term = terms.find((t) => t.id === p.credit_term);
  const [people, setPeople] = useState<Person[]>([]);
  useEffect(() => {
    api<Person[]>("v1/people/").then(setPeople);
  }, []);
  const set = (change: Partial<Party>) => onChange({ ...p, ...change });
  const ctx = { tab, fold };
  const overseas = p.gst_type === "overseas";
  const registered = REGISTERED.includes(p.gst_type);
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
  return (
    <div hidden={fold ? false : tab === "general"} style={fold ? { display: "contents" } : undefined}>
      <PanelBox ctx={ctx} code="details">
      <InUseNote lock={p.lock}>The locked fields cannot be changed. Everything else stays open.</InUseNote>
      <p className="note">
        Shared by all companies in the group: GST details, addresses, contacts and credit terms changed here change for
        every company. The {supplier ? "purchaser" : "salesman"}, credit limit, balance and bills belong to this
        company.
      </p>
      <div className="panel-card">
      <h4>GST</h4>
      {companies.length > 1 && (
        <div className="company-ticks">
          <span className="small">Companies that deal with this party</span>
          {companies.map((c) => (
            <label key={c.id} className="check">
              <input
                type="checkbox"
                disabled={linked.has(c.id)}
                checked={linked.has(c.id) || alsoIn.includes(c.id)}
                onChange={(e) => onAlsoIn(e.target.checked ? [...alsoIn, c.id] : alsoIn.filter((x) => x !== c.id))}
              />
              {c.name}
            </label>
          ))}
        </div>
      )}
      <div className="row">
        <label>
          GST type
          <Locked on={isLocked(p.lock, "gst_type")}>
          <Combobox
            value={p.gst_type}
            options={GST_TYPES.map(([value, label]) => ({ value, label }))}
            onChange={(t) => {
              set({
                gst_type: t,
                ...(REGISTERED.includes(t) ? {} : { gstin: "" }),
                ...(t === "overseas" ? { state_code: "", country: p.country === "India" ? "" : p.country } : {}),
                ...(t !== "overseas" && p.gst_type === "overseas" ? { country: "India" } : {}),
              });
            }}
          />
          </Locked>
        </label>
      </div>
      <div className="row">
        {overseas ? (
          <label>
            Country
            <CountryPicker required value={p.country} onChange={(country) => set({ country })} />
          </label>
        ) : (
          <label>
            State (decides the place of supply)
            <Locked on={isLocked(p.lock, "state_code")}>
              <StateSelect states={states} value={p.state_code} onChange={(code) => set({ state_code: code })} />
            </Locked>
          </label>
        )}
        {!overseas && (
          <label>
            PAN
            <Locked on={isLocked(p.lock, "pan")}>
              <input value={p.pan} maxLength={10} onChange={(e) => set({ pan: e.target.value.toUpperCase() })} />
            </Locked>
          </label>
        )}
      </div>
      </div>
      <div className="panel-card">
      <h4>Credit</h4>
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
          Credit terms
          <Combobox
            value={p.credit_term === null ? "" : String(p.credit_term)}
            empty="None"
            options={terms
              .filter((t) => t.is_active || t.id === p.credit_term)
              .map((t) => ({ value: String(t.id), label: t.name }))}
            onChange={(v) => set({ credit_term: v ? Number(v) : null })}
            create={newTerm}
          />
          {term && <span className="small">{term.summary}</span>}
        </label>
        <label>
          {supplier ? "Purchaser" : "Salesman"}
          <Combobox
            value={p.salesman === null ? "" : String(p.salesman)}
            empty="None"
            options={people.map((person) => ({ value: String(person.id), label: person.name }))}
            onChange={(v) => set({ salesman: v ? Number(v) : null })}
          />
        </label>
      </div>
      </div>
      </PanelBox>

      <PanelBox ctx={ctx} code="addresses">
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
                    <CountryPicker value={a.country} onChange={(country) => setAddress(i, { country })} />
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
                  <PinInput
                    value={a.pincode}
                    onChange={(pincode) => setAddress(i, { pincode })}
                    onFound={(f) => {
                      const change: Partial<PartyAddress> = {};
                      if (!a.city && f.city) change.city = f.city;
                      if (!overseas && !a.state_code && f.state_code) change.state_code = f.state_code;
                      if (Object.keys(change).length) setAddress(i, change);
                    }}
                  />
                </label>
                <label>
                  City
                  <input value={a.city} onChange={(e) => setAddress(i, { city: e.target.value })} />
                </label>
                {registered && (
                  <label>
                    GSTIN at this address (if different)
                    <AddressGstin
                      value={a.gstin}
                      onChange={(gstin) => setAddress(i, { gstin })}
                      onFound={(change) => setAddress(i, change)}
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
      </PanelBox>

      <PanelBox ctx={ctx} code="labels" off={supplier}>
        <Section>
          <p className="small">
            The label format for each item this customer buys will be set here: one format for
            a customer and one item, another for the same customer and another item. When labels are printed for a
            despatch, MyERP will use the format set here, otherwise the customer's default format, otherwise the item's
            default format. This tab is a placeholder until the sales and despatch screens are built.
          </p>
        </Section>
      </PanelBox>

      <PanelBox ctx={ctx} code="documents">
        <PartyDocuments
          partyId={p.id}
          canEdit={canEdit ?? true}
          onCount={(n) => {
            if (n !== (p.document_count ?? 0)) set({ document_count: n });
          }}
        />
      </PanelBox>

      <PanelBox ctx={ctx} code="products">
        <PartyProducts
          value={p.products ?? []}
          onChange={(products) => set({ products })}
          supplier={supplier}
          canEdit={canEdit ?? true}
          partyName={p.name}
        />
      </PanelBox>

      <PanelBox ctx={ctx} code="contacts">
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
                <span className="small">Contact type</span>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={c.is_primary}
                    onChange={(e) => setContact(i, { is_primary: e.target.checked })}
                  />
                  Main
                </label>
                {CONTACT_KINDS.map(([code, label]) => (
                  <label className="check" key={code}>
                    <input
                      type="checkbox"
                      checked={c.kinds.includes(code)}
                      onChange={(e) =>
                        setContact(i, {
                          kinds: e.target.checked ? [...c.kinds, code] : c.kinds.filter((k) => k !== code),
                        })
                      }
                    />
                    {label}
                  </label>
                ))}
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
      </PanelBox>
      {extraTab && (
        <PanelBox ctx={ctx} code="extra">
          {extraTab.content}
        </PanelBox>
      )}
    </div>
  );
}

/** Party details in the ledger side panel. */
export function PartySummary({ party: p, states, supplier }: { party: Party; states?: State[]; supplier?: boolean }) {
  const gstType = GST_TYPES.find(([code]) => code === p.gst_type)?.[1] ?? p.gst_type;
  const stateName = (code: string) => states?.find((s) => s.code === code)?.name ?? code;
  const place = p.gst_type === "overseas" ? p.country : stateName(p.state_code);
  const gstRows: [string, string][] = [
    supplier ? ["Vendor Number", p.vendor_number] : ["Customer Number", p.customer_number],
    ["GST", p.gstin ? `${gstType} · ${p.gstin}` : gstType],
    ["State / Country", place],
    ["PAN", p.pan],
  ];
  const creditRows: [string, string][] = [
    ["Credit Limit", Number(p.credit_limit) ? `₹ ${money(p.credit_limit)}` : "No limit"],
    ["Credit Terms", p.credit_term_name ?? ""],
    [supplier ? "Purchaser" : "Salesman", p.salesman_name ?? ""],
  ];
  return (
    <>
      <SidePanel title="GST And Credit">
        <SideRows rows={[...gstRows, ...creditRows]} />
      </SidePanel>
      {p.addresses.length > 0 && (
        <SidePanel title="Addresses">
          <ul className="address-list cards-2">
            {p.addresses.map((a) => (
              <li key={a.label} className="address-card">
                <div>
                  <strong>{a.label}</strong>
                </div>
                <div className="pre">{a.address}</div>
                <div className="small">
                  {[a.city, a.pincode, a.state_code ? stateName(a.state_code) : a.country, a.gstin && `GSTIN ${a.gstin}`]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
                {(a.is_billing || a.is_shipping) && (
                  <div>
                    {a.is_billing && <span className="pill on">Billing</span>}
                    {a.is_shipping && <span className="pill on">Shipping</span>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </SidePanel>
      )}
      {p.contacts.length > 0 && (
        <SidePanel title="Contacts">
          <ul className="address-list cards-2">
            {p.contacts.map((c, i) => (
              <li key={i} className="address-card">
                <div>
                  <strong>{c.name}</strong>
                  {c.designation && <span className="small"> · {c.designation}</span>}
                </div>
                <div>
                  {c.is_primary && <span className="pill on">Main</span>}
                  {c.kinds.map((k) => (
                    <span className="pill" key={k}>
                      {kindLabel(k)}
                    </span>
                  ))}
                </div>
                <div className="small">{[c.phone, c.email].filter(Boolean).join(" · ")}</div>
              </li>
            ))}
          </ul>
        </SidePanel>
      )}
    </>
  );
}

type GstinDetails = {
  status?: string;
  state_code: string;
  pan: string;
  legal_name: string;
  trade_name: string;
  gst_type: string;
  address: string;
  pincode: string;
};

/** The GSTIN of one extra address, with "Fetch details" to fill that address
 * (name, state, address, PIN). Everything stays editable afterwards. */
function AddressGstin(props: {
  value: string;
  onChange: (gstin: string) => void;
  onFound: (change: Partial<PartyAddress>) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const fetchDetails = async () => {
    setBusy(true);
    setNote("");
    try {
      const r = await api<GstinDetails>(`v1/gstin-lookup/?gstin=${props.value}`);
      props.onFound({
        label: r.trade_name || r.legal_name,
        address: r.address,
        pincode: r.pincode,
        state_code: r.state_code,
      });
      const found = r.legal_name ? `Found: ${r.legal_name}` : "Found.";
      setNote(r.status && r.status !== "Active" ? `${found} Warning: this GSTIN is ${r.status}.` : found);
    } catch (err) {
      setNote((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <span className="inline">
        <input value={props.value} maxLength={15} onChange={(e) => props.onChange(e.target.value.toUpperCase())} />
        <button type="button" className="secondary" disabled={props.value.length !== 15 || busy} onClick={fetchDetails}>
          Fetch details
        </button>
      </span>
      {note && <span className="small">{note}</span>}
    </>
  );
}

/** The customer or vendor number, at the top of a party ledger form. */
export function PartyNumber(props: { party: Party; supplier: boolean; onChange: (p: Party) => void }) {
  const { party: p, supplier } = props;
  const set = (change: Partial<Party>) => props.onChange({ ...p, ...change });
  return (
    <label>
      {supplier ? "Vendor number" : "Customer number"}
      <input
        value={supplier ? p.vendor_number : p.customer_number}
        maxLength={20}
        placeholder="Assigned when you save"
        onChange={(e) =>
          set(supplier ? { vendor_number: e.target.value.toUpperCase() } : { customer_number: e.target.value.toUpperCase() })
        }
      />
    </label>
  );
}

/** The GSTIN, first among the party's details: it fills in the state and PAN
 * and can fetch the rest from the GST portal. */
export function GstinField(props: {
  party: Party;
  onChange: (p: Party) => void;
  /** The registered name found on the portal, to offer as the ledger's name. */
  onName: (name: string) => void;
}) {
  const { party: p } = props;
  const states = useStates();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const registered = REGISTERED.includes(p.gst_type);
  const valid = p.gstin.length === 15;
  const set = (change: Partial<Party>) => props.onChange({ ...p, ...change });
  const onGstin = (raw: string) => {
    const v = raw.toUpperCase();
    const change: Partial<Party> = { gstin: v };
    // Typing a GSTIN makes the party a registered one, unless it already is.
    if (v && !REGISTERED.includes(p.gst_type)) change.gst_type = "regular";
    if (v.length >= 2 && states.some((s) => s.code === v.slice(0, 2))) change.state_code = v.slice(0, 2);
    if (v.length >= 12) change.pan = v.slice(2, 12);
    setNote("");
    set(change);
  };
  const fetchDetails = async () => {
    setBusy(true);
    setNote("");
    try {
      const r = await api<GstinDetails>(`v1/gstin-lookup/?gstin=${p.gstin}`);
      const change: Partial<Party> = { state_code: r.state_code, pan: r.pan, gst_type: r.gst_type || "regular" };
      if (r.address && p.addresses.length === 0)
        change.addresses = [
          {
            label: r.trade_name || r.legal_name,
            address: r.address,
            pincode: r.pincode,
            city: "",
            state_code: r.state_code,
            country: "India",
            gstin: "",
            is_billing: true,
            is_shipping: true,
          },
        ];
      set(change);
      props.onName(r.trade_name || r.legal_name);
      const found = r.legal_name ? `Found: ${r.legal_name}` : "Found.";
      setNote(r.status && r.status !== "Active" ? `${found} Warning: this GSTIN is ${r.status}.` : found);
    } catch (err) {
      setNote((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <label>
        GSTIN
        <span className="inline">
          <Locked on={isLocked(p.lock, "gstin")}>
            <input required={registered} value={p.gstin} maxLength={15} onChange={(e) => onGstin(e.target.value)} />
          </Locked>
          <button type="button" className="secondary" disabled={!valid || busy} onClick={fetchDetails}>
            Fetch details
          </button>
        </span>
      </label>
      {note && <span className="small">{note}</span>}
    </div>
  );
}
