import { DEDUCTEE_TYPES, TdsSectionPicker } from "./Tds";
import { CountryPicker, PinPicker } from "./Pin";
import { Section } from "./Brand";
import { SidePanel, SideRows } from "./Master";
import { PartyDocuments } from "./PartyDocuments";
import { PartyProducts, type PartyProduct } from "./PartyProducts";
import { Combobox } from "./Combobox";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { CourierAccount } from "./Shipments";
import { creatable } from "./Create";
import { useCreditTerms } from "./CreditTerms";
import { useTermsSets } from "./Terms";
import { useSalesPeople } from "./SalesPeople";
import { usePriceLists } from "./PriceLists";
import { PriceTable, rowFromServer, type PriceRow } from "./PriceLines";
import { money, type Company, StateSelect, useStates, type State } from "./Companies";
import { useReturns } from "./Refresh";

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
  /** TDS as a supplier: blank deductee type is read from the PAN. */
  deductee_type?: string;
  tds_section?: string;
  state_code: string;
  country: string;
  credit_limit: string;
  credit_term: number | null;
  credit_term_name?: string;
  /** A customer's Selling price list; its own item prices (below) win over it. */
  price_list?: number | null;
  price_list_name?: string;
  /** A supplier's Buying price list. */
  buying_price_list?: number | null;
  buying_price_list_name?: string;
  purchase_terms?: number | null;
  purchase_terms_name?: string;
  sales_terms?: number | null;
  sales_terms_name?: string;
  /** The customer's own rates, loaded and saved apart from the party (item_prices endpoint). */
  item_prices?: PriceRow[];
  salesman: number | null;
  salesman_name?: string;
  preferred_transporter?: number | null;
  preferred_transporter_name?: string;
  addresses: PartyAddress[];
  contacts: PartyContact[];
  products: PartyProduct[];
  lock?: LockInfo;
  /** Documents kept for the party (read only; the Documents tab saves its own). */
  document_count?: number;
};

/** The deductee type a PAN's 4th letter gives (C company, F firm, P/H individual or HUF). */
function panType(pan: string): string {
  if (pan.length !== 10) return "";
  const kind = { C: "company", F: "firm", P: "individual", H: "individual" }[pan[3]] ?? "others";
  return DEDUCTEE_TYPES.find((t) => t.value === kind)?.label ?? "";
}

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
  preferred_transporter: null,
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

export type PartyTab = "none" | "general" | "details" | "addresses" | "contacts" | "documents" | "products" | "prices" | "labels" | "extra";

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

/** A customer's own rates for single items: they win over its price list. The same lines show on
 * each item, as "Customer Prices" (one set of data seen from both sides). Saved with the ledger. */
function PartyItemPrices(props: { party: Party; onChange: (p: Party) => void; canEdit: boolean; supplier: boolean }) {
  const { party, onChange, supplier } = props;
  useEffect(() => {
    if (party.item_prices !== undefined || !party.id) return;
    api<(PriceRow & { min_qty: string; rate: string })[]>(`v1/parties/${party.id}/item-prices/?side=${supplier ? "buying" : "selling"}`).then((rows) =>
      onChange({ ...party, item_prices: rows.map(rowFromServer) }),
    );
    // Load once per party; `party` changes as the form is edited.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [party.id]);
  const rows = party.item_prices ?? [];
  return (
    <Section title="Item Prices">
      <p className="small">
        This {supplier ? "supplier's" : "customer's"} own rate for an item. Where it has any price for an item, only
        those are used for it; the price list covers the other items. Rates are before GST.
      </p>
      <PriceTable rows={rows} onChange={(item_prices) => onChange({ ...party, item_prices })} by="item" readOnly={!props.canEdit} />
    </Section>
  );
}

/**
 * Which rows of a list (addresses, contacts) are open for editing. Saved rows show as one
 * line with "Edit" (Sidharth, 2026-11-16); a row opened or newly added shows its fields
 * until "Done". Indexes shift down when a row is removed.
 */
function useOpenRows(resetKey: unknown) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  useEffect(() => setOpen(new Set()), [resetKey]);
  return {
    isOpen: (i: number) => open.has(i),
    show: (i: number) => setOpen((o) => new Set(o).add(i)),
    hide: (i: number) =>
      setOpen((o) => {
        const n = new Set(o);
        n.delete(i);
        return n;
      }),
    removed: (i: number) =>
      setOpen((o) => new Set([...o].filter((j) => j !== i).map((j) => (j > i ? j - 1 : j)))),
  };
}

/** "Done" folds a row only when its required boxes are filled; otherwise it points to the first empty one. */
function foldIfFilled(button: HTMLElement, fold: () => void) {
  const empty = button.closest(".address-card")?.querySelector<HTMLInputElement>(":invalid");
  if (empty) empty.reportValidity();
  else fold();
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
  const { lists: priceLists, refresh: refreshLists } = usePriceLists();
  const newList = creatable("price_list", "price-lists", refreshLists);
  const { sets: termsSets, refresh: refreshTermsSets } = useTermsSets();
  const newTermsSet = creatable("terms", "terms", refreshTermsSets);
  const ownTerms = (supplier ? p.purchase_terms : p.sales_terms) ?? null;
  const [companies, setCompanies] = useState<Company[]>([]);
  useEffect(() => {
    api<Company[]>("v1/companies/").then(setCompanies);
  }, []);
  const linked = new Set([companyId, ...(p.companies ?? []).map((c) => c.id)]);
  const term = terms.find((t) => t.id === p.credit_term);
  // From Masters > People: those ticked for this side, and not disabled.
  const { people, refresh: refreshPeople } = useSalesPeople();
  const newPerson = creatable("sales_person", "sales-people", refreshPeople, `as=${supplier ? "purchaser" : "salesman"}`);
  // A customer's usual transporter (when the company has Sales) or a supplier's (when it
  // has Purchase): one of this company's own. A supplier with none sends the goods itself.
  const modules = companies.find((c) => c.id === companyId)?.modules ?? [];
  const hasTransport = modules.includes(supplier ? "purchase" : "sales");
  const [transporters, setTransporters] = useState<CourierAccount[]>([]);
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  const refreshTransporters = useCallback(
    () => api<CourierAccount[]>(`v1/companies/${companyId}/courier-accounts/`).then(setTransporters),
    [companyId],
  );
  useEffect(() => {
    if (hasTransport) refreshTransporters();
  }, [hasTransport, refreshTransporters, visits]);
  const newTransporter = creatable("courier_account", `companies/${companyId}/couriers`, refreshTransporters);
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
  const openAddress = useOpenRows(p.id);
  const openContact = useOpenRows(p.id);
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
          Price list
          <Combobox
            value={(supplier ? p.buying_price_list : p.price_list) ? String(supplier ? p.buying_price_list : p.price_list) : ""}
            empty="None"
            options={priceLists
              .filter(
                (l) =>
                  l.kind === (supplier ? "buying" : "selling") &&
                  (l.is_active || l.id === (supplier ? p.buying_price_list : p.price_list)),
              )
              .map((l) => ({ value: String(l.id), label: l.name }))}
            onChange={(v) => set(supplier ? { buying_price_list: v ? Number(v) : null } : { price_list: v ? Number(v) : null })}
            create={newList}
          />
          <span className="small">
            {supplier ? "The rates this supplier sells to you at" : "The rates this customer is sold at"}. Its own Item
            Prices win.
          </span>
        </label>
        <label>
          Terms and Conditions
          <Combobox
            value={ownTerms ? String(ownTerms) : ""}
            empty="Company default"
            options={termsSets
              .filter((t) => t.kind === (supplier ? "purchase" : "sales") && (t.is_active || t.id === ownTerms))
              .map((t) => ({ value: String(t.id), label: t.name }))}
            onChange={(v) => set(supplier ? { purchase_terms: v ? Number(v) : null } : { sales_terms: v ? Number(v) : null })}
            create={newTermsSet}
          />
          <span className="small">
            Printed on {supplier ? "purchase orders" : "sales documents"} to this {supplier ? "supplier" : "customer"}; empty
            uses the company's default.
          </span>
        </label>
        <label>
          {supplier ? "Purchaser" : "Salesman"}
          <Combobox
            value={p.salesman === null ? "" : String(p.salesman)}
            empty="None"
            options={people
              .filter((x) => (supplier ? x.is_purchaser : x.is_salesman) && (x.is_active || x.id === p.salesman))
              .map((x) => ({ value: String(x.id), label: x.is_active ? x.name : `${x.name} (disabled)` }))}
            onChange={(v) => set({ salesman: v ? Number(v) : null })}
            create={newPerson}
          />
        </label>
        {hasTransport && (
          <label>
            Preferred Transporter
            <Combobox
              value={p.preferred_transporter == null ? "" : String(p.preferred_transporter)}
              empty={supplier ? "By Supplier" : "None"}
              options={transporters
                .filter((t) => t.is_active || t.id === p.preferred_transporter)
                .map((t) => ({ value: String(t.id), label: t.is_active ? t.name : `${t.name} (disabled)` }))}
              onChange={(v) => set({ preferred_transporter: v ? Number(v) : null })}
              create={newTransporter}
            />
          </label>
        )}
        {supplier && (
          <label>
            Deductee Type
            <Combobox
              value={p.deductee_type ?? ""}
              empty={`From the PAN${panType(p.pan) ? `: ${panType(p.pan)}` : ""}`}
              options={DEDUCTEE_TYPES}
              onChange={(v) => set({ deductee_type: v })}
            />
            <span className="small">Sets the TDS rate; no PAN means the higher rate</span>
          </label>
        )}
        {supplier && (
          <label>
            Default TDS Section
            <TdsSectionPicker value={p.tds_section ?? ""} onChange={(v) => set({ tds_section: v })} />
            <span className="small">Used for a bill line whose item or ledger names none</span>
          </label>
        )}
      </div>
      </div>
      </PanelBox>

      <PanelBox ctx={ctx} code="addresses">
      {p.addresses.length === 0 && <p className="small">No addresses yet.</p>}
      {p.addresses.length > 0 && (
        <table className="row-list">
          <thead>
            <tr>
              <th>Name</th>
              <th>Address</th>
              <th>State</th>
              {registered && <th>GSTIN</th>}
              <th>Default For</th>
              <th />
            </tr>
          </thead>
          <tbody>
          {p.addresses.map((a, i) =>
            !openAddress.isOpen(i) ? (
              <tr key={i}>
                <td>{a.label}</td>
                <td>
                  {[a.address.replace(/\s*\n\s*/g, ", "), a.city, a.pincode, overseas ? a.country : ""]
                    .filter(Boolean)
                    .join(", ")}
                </td>
                <td>{states.find((st) => st.code === a.state_code)?.name ?? ""}</td>
                {registered && <td>{a.gstin}</td>}
                <td>
                  {a.is_billing && <span className="tag">Billing</span>}
                  {a.is_shipping && <span className="tag">Shipping</span>}
                </td>
                <td className="row-edit">
                  <button type="button" className="link" onClick={() => openAddress.show(i)}>
                    Edit
                  </button>
                </td>
              </tr>
            ) : (
            <tr key={i}>
            <td colSpan={registered ? 6 : 5} className="row-open">
            <div className="address-card">
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
                {overseas ? (
                  <label>
                    Country
                    <CountryPicker value={a.country} onChange={(country) => setAddress(i, { country })} />
                  </label>
                ) : (
                  <label>
                    <span className="req">PIN code</span>
                    <PinPicker
                      value={a.pincode}
                      onPick={(r) => setAddress(i, { pincode: r.pin, city: r.city, state_code: r.state_code || a.state_code })}
                    />
                  </label>
                )}
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
                {overseas ? (
                  <>
                    <label>
                      Postal code
                      <input value={a.pincode} onChange={(e) => setAddress(i, { pincode: e.target.value })} />
                    </label>
                    <label>
                      City
                      <input value={a.city} onChange={(e) => setAddress(i, { city: e.target.value })} />
                    </label>
                  </>
                ) : (
                  <>
                    <label>
                      City
                      <input readOnly tabIndex={-1} value={a.city} placeholder="Shown when a PIN is picked" />
                    </label>
                    <label>
                      State
                      <input
                        readOnly
                        tabIndex={-1}
                        value={states.find((st) => st.code === a.state_code)?.name ?? ""}
                        placeholder="Shown when a PIN is picked"
                      />
                    </label>
                  </>
                )}
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
                  onClick={() => {
                    set({ addresses: p.addresses.filter((_, j) => j !== i) });
                    openAddress.removed(i);
                  }}
                >
                  Remove
                </button>
                <button type="button" onClick={(e) => foldIfFilled(e.currentTarget, () => openAddress.hide(i))}>
                  Done
                </button>
              </div>
            </div>
            </td>
            </tr>
            ),
          )}
          </tbody>
        </table>
      )}
      <button
        type="button"
        className="link"
        onClick={() => {
          openAddress.show(p.addresses.length);
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
          });
        }}
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

      <PanelBox ctx={ctx} code="prices">
        <PartyItemPrices party={p} onChange={onChange} canEdit={canEdit ?? true} supplier={supplier} />
      </PanelBox>

      <PanelBox ctx={ctx} code="contacts">
      {p.contacts.length === 0 && <p className="small">No contacts yet.</p>}
      {p.contacts.length > 0 && (
        <table className="row-list">
          <thead>
            <tr>
              <th>Name</th>
              <th>Designation</th>
              <th>Phone</th>
              <th>Email</th>
              <th>Type</th>
              <th />
            </tr>
          </thead>
          <tbody>
          {p.contacts.map((c, i) =>
            !openContact.isOpen(i) ? (
              <tr key={i}>
                <td>{c.name}</td>
                <td>{c.designation}</td>
                <td>{c.phone}</td>
                <td>{c.email}</td>
                <td>
                  {c.is_primary && <span className="tag">Main</span>}
                  {c.kinds.map((k) => (
                    <span className="tag" key={k}>
                      {kindLabel(k)}
                    </span>
                  ))}
                </td>
                <td className="row-edit">
                  <button type="button" className="link" onClick={() => openContact.show(i)}>
                    Edit
                  </button>
                </td>
              </tr>
            ) : (
            <tr key={i}>
            <td colSpan={6} className="row-open">
            <div className="address-card">
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
                <span className="small">Contact Type</span>
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
                  onClick={() => {
                    set({ contacts: p.contacts.filter((_, j) => j !== i) });
                    openContact.removed(i);
                  }}
                >
                  Remove
                </button>
                <button type="button" onClick={(e) => foldIfFilled(e.currentTarget, () => openContact.hide(i))}>
                  Done
                </button>
              </div>
            </div>
            </td>
            </tr>
            ),
          )}
          </tbody>
        </table>
      )}
      <button
        type="button"
        className="link"
        onClick={() => {
          openContact.show(p.contacts.length);
          set({ contacts: [...p.contacts, { ...blankContact(), is_primary: p.contacts.length === 0 }] });
        }}
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
    ["Price List", (supplier ? p.buying_price_list_name : p.price_list_name) ?? ""],
    ["Terms and Conditions", (supplier ? p.purchase_terms_name : p.sales_terms_name) || "Company default"],
    [supplier ? "Purchaser" : "Salesman", p.salesman_name ?? ""],
    ...(supplier
      ? ([
          ["Deductee Type", DEDUCTEE_TYPES.find((t) => t.value === p.deductee_type)?.label ?? `From the PAN${panType(p.pan) ? `: ${panType(p.pan)}` : ""}`],
          ["Default TDS Section", p.tds_section || "None"],
        ] as [string, string][])
      : []),
    ...(p.preferred_transporter_name ? ([["Preferred Transporter", p.preferred_transporter_name]] as [string, string][]) : []),
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
  city: string;
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
        city: r.city,
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
            city: r.city,
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
