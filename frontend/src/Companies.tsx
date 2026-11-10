import { Combobox } from "./Combobox";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Activity, WithActivity } from "./Audit";
import { api, SignedIn } from "./api";
import { Chevron, LevelPicker, PageHeader } from "./Brand";
import { ActionCells, ActionHeads, ActiveButton, FormBody } from "./RowActions";

// Address and contact, shared by companies and branches.
type Contact = { address: string; pincode: string; phone: string; email: string; contact_person: string };
const NO_CONTACT: Contact = { address: "", pincode: "", phone: "", email: "", contact_person: "" };
const contactOf = (x: Contact | null | undefined): Contact =>
  x
    ? { address: x.address, pincode: x.pincode, phone: x.phone, email: x.email, contact_person: x.contact_person }
    : NO_CONTACT;

function ContactFields(props: { value: Contact; onChange: (c: Contact) => void; addressLabel?: string }) {
  const v = props.value;
  const set = (field: keyof Contact) => (e: { target: { value: string } }) => props.onChange({ ...v, [field]: e.target.value });
  return (
    <>
      <label>
        {props.addressLabel ?? "Address"}
        <textarea rows={2} value={v.address} onChange={set("address")} />
      </label>
      <div className="row">
        <label>
          PIN code
          <input value={v.pincode} maxLength={6} inputMode="numeric" onChange={set("pincode")} />
        </label>
        <label>
          Contact person
          <input value={v.contact_person} onChange={set("contact_person")} />
        </label>
      </div>
      <div className="row">
        <label>
          Phone
          <input type="tel" value={v.phone} maxLength={20} placeholder="+91 98200 12345" onChange={set("phone")} />
        </label>
        <label>
          Email
          <input type="email" value={v.email} onChange={set("email")} />
        </label>
      </div>
    </>
  );
}

function contactLines(x: Contact) {
  const reach = [x.contact_person, x.phone, x.email].filter(Boolean).join(" · ");
  return { where: [x.address, x.pincode].filter(Boolean).join(" ") || "—", reach: reach || "—" };
}

export type Company = Contact & {
  id: number;
  name: string;
  entity_type: string;
  cin: string;
  incorporation_date: string | null;
  tan: string;
  abbr: string;
  gstin: string;
  pan: string;
  state_code: string;
  state: string;
  fiscal_year_start_month: number;
  books_start: string;
  multi_currency: boolean;
  modules: string[];
  base_currency: string;
};
type DefaultFlag = "default_billing" | "default_ship_to" | "default_ship_from";
const DEFAULTS: [DefaultFlag, string][] = [
  ["default_billing", "Default billing address"],
  ["default_ship_to", "Default ship to"],
  ["default_ship_from", "Default ship from"],
];
const ENTITY_TYPES: [string, string][] = [
  ["proprietorship", "Proprietorship"],
  ["partnership", "Partnership firm"],
  ["llp", "LLP"],
  ["private_limited", "Private limited company"],
  ["public_limited", "Public limited company"],
  ["opc", "One person company"],
];
const MCA_TYPES = ["llp", "private_limited", "public_limited", "opc"];
const cinLabel = (type: string) => (type === "llp" ? "LLPIN" : "CIN");

type Module = { code: string; label: string; what: string; needs: string[] };

function useModules() {
  const [modules, setModules] = useState<Module[]>([]);
  useEffect(() => {
    api<Module[]>("v1/modules/").then(setModules);
  }, []);
  return modules;
}

// Ticking a module also ticks what it needs; unticking one unticks what needs it.
function toggleModule(all: Module[], chosen: string[], code: string, on: boolean): string[] {
  const set = new Set(chosen);
  const add = (c: string) => {
    set.add(c);
    all.find((m) => m.code === c)?.needs.forEach(add);
  };
  const remove = (c: string) => {
    set.delete(c);
    all.filter((m) => m.needs.includes(c) && set.has(m.code)).forEach((m) => remove(m.code));
  };
  if (on) add(code);
  else remove(code);
  return all.map((m) => m.code).filter((c) => set.has(c) || c === "accounts");
}

function ModulePicker(props: { modules: Module[]; value: string[]; onChange?: (v: string[]) => void }) {
  const label = (code: string) => props.modules.find((m) => m.code === code)?.label ?? code;
  return (
    <table className="modules">
      <thead>
        <tr>
          <th>{props.onChange ? "Use" : "Status"}</th>
          <th>Module</th>
          <th>What it covers</th>
          <th>Needs</th>
        </tr>
      </thead>
      <tbody>
        {props.modules.map((m) => {
          const on = props.value.includes(m.code) || m.code === "accounts";
          return (
            <tr key={m.code} className={on ? "" : "off"}>
              <td>
                {props.onChange ? (
                  <input
                    type="checkbox"
                    aria-label={`Use ${m.label}`}
                    checked={on}
                    disabled={m.code === "accounts"}
                    onChange={(e) => props.onChange?.(toggleModule(props.modules, props.value, m.code, e.target.checked))}
                  />
                ) : (
                  <span className={on ? "pill on" : "pill"}>{on ? "In use" : "Not used"}</span>
                )}
              </td>
              <td className="module-name">
                {m.label}
              </td>
              <td>{m.what}</td>
              <td className="small">{m.needs.length ? m.needs.map(label).join(", ") : "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ModulesSection(props: { company: Company; isOwner: boolean; reload: () => void }) {
  const all = useModules();
  const [editing, setEditing] = useState(false);
  const [chosen, setChosen] = useState(props.company.modules);
  const [error, setError] = useState("");
  const save = async () => {
    setError("");
    try {
      await api(`v1/companies/${props.company.id}/`, { modules: chosen }, "PATCH");
      setEditing(false);
      props.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <>
      <div className="page-head">
        <h3>Modules</h3>
        {props.isOwner && !editing && (
          <button className="link" onClick={() => setEditing(true)}>
            Choose modules
          </button>
        )}
      </div>
      <p className="small">
        {all.filter((m) => props.company.modules.includes(m.code) || m.code === "accounts").length} of {all.length} modules in
        use. Screens for modules that are not used stay hidden for this company.
      </p>
      <div>
        {editing ? (
          <>
            <ModulePicker modules={all} value={chosen} onChange={setChosen} />
            {error && <p className="error">{error}</p>}
            <div className="buttons">
              <button onClick={save}>Save</button>
              <button
                className="link"
                onClick={() => {
                  setChosen(props.company.modules);
                  setEditing(false);
                }}
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <ModulePicker modules={all} value={props.company.modules} />
        )}
      </div>
    </>
  );
}

type Certificate = {
  id: number;
  kind: string;
  kind_label: string;
  name: string;
  number: string;
  issued_by: string;
  branch: number | null;
  branch_name: string;
  valid_from: string | null;
  valid_until: string | null;
  notes: string;
};
const CERTIFICATE_KINDS: [string, string][] = [
  ["fssai", "FSSAI licence / registration"],
  ["udyam", "Udyam (MSME) registration"],
  ["iec", "IEC (importer-exporter code)"],
  ["organic", "Organic certificate (NPOP / NOP / EU)"],
  ["iso", "ISO certificate"],
  ["fssc", "FSSC 22000"],
  ["lut", "LUT for exports"],
  ["factory", "Factory licence"],
  ["pollution", "Pollution control consent"],
  ["trade", "Shop / trade licence"],
  ["other", "Other"],
];

type Branch = Contact & Record<DefaultFlag, boolean> & {
  id: number;
  name: string;
  state_code: string;
  gstin: string;
  is_head_office: boolean;
  is_active: boolean;
};
export type Group = {
  id: number;
  name: string;
  parent: number | null;
  nature: "asset" | "liability" | "income" | "expense";
  affects_gross_profit: boolean;
  code: string;
  is_standard: boolean;
  schedule_iii: string;
  ledger_count: number;
  is_bank: boolean;
  bill_wise_default: boolean;
};
export type State = { code: string; name: string };
type Opening = { dr: string; cr: string; difference: string };
type Detail = { company: Company; branches: Branch[]; certificates: Certificate[]; ledger_groups: Group[]; opening: Opening };

export const money = (v: string | number) =>
  Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const longDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const NATURE = { asset: "Asset", liability: "Liability", income: "Income", expense: "Expense" };

export function useStates() {
  const [states, setStates] = useState<State[]>([]);
  useEffect(() => {
    api<State[]>("v1/states/").then(setStates);
  }, []);
  return states;
}

export function StateSelect(props: {
  states: State[];
  value: string;
  onChange: (code: string) => void;
  optional?: boolean;
}) {
  return (
    <Combobox
      required={!props.optional}
      value={props.value}
      placeholder="Type a state or its code…"
      options={props.states.map((s) => ({ value: s.code, label: `${s.name} (${s.code})` }))}
      onChange={props.onChange}
    />
  );
}

export function CompaniesPage({ session }: { session: SignedIn }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [adding, setAdding] = useState(false);
  const [copyOf, setCopyOf] = useState<Company | null>(null);
  const [error, setError] = useState("");
  const states = useStates();
  const reload = useCallback(() => {
    api<Company[]>("v1/companies/")
      .then(setCompanies)
      .catch((err: Error) => setError(err.message));
  }, []);
  useEffect(reload, [reload]);

  return (
    <section className="page">
      <PageHeader
        title="Companies"
        crumbs={[{ label: "Masters", href: "#/companies" }]}
        actions={
          session.user.is_owner && (
            <button
              onClick={() => {
                setCopyOf(null);
                setAdding(true);
              }}
            >
              Add company
            </button>
          )
        }
      />
      <p className="small">
        Each company keeps its own books, GST registration and document numbers. A new company starts with a Head
        office branch and the standard ledger groups.
      </p>
      {error && <p className="error">{error}</p>}
      {adding && (
        <CompanyForm
          key={copyOf?.id ?? "new"}
          company={null}
          copyOf={copyOf}
          states={states}
          onDone={(c) => {
            setAdding(false);
            window.location.hash = `#/companies/${c.id}`;
          }}
          onCancel={() => setAdding(false)}
        />
      )}
      <table>
        <thead>
          <tr>
            <th>Company</th>
            <th>Short code</th>
            <th>GSTIN</th>
            <th>State</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {companies.map((c) => (
            <tr key={c.id}>
              <td>
                <a href={`#/companies/${c.id}`}>{c.name}</a>
              </td>
              <td>{c.abbr}</td>
              <td>{c.gstin || <span className="small">Unregistered</span>}</td>
              <td>{c.state}</td>
              <td className="act">
                {session.user.is_owner && (
                  <button
                    className="link quiet"
                    onClick={() => {
                      setCopyOf(c);
                      setAdding(true);
                    }}
                  >
                    Duplicate
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function CompanyForm(props: {
  company: Company | null;
  /** Duplicate: the setup of this company, but not its name, code or registrations. */
  copyOf?: Company | null;
  states: State[];
  onDone: (c: Company) => void;
  onCancel: () => void;
}) {
  const c = props.company;
  const from = c ?? props.copyOf;
  const [name, setName] = useState(c?.name ?? "");
  const [abbr, setAbbr] = useState(c?.abbr ?? "");
  const [gstin, setGstin] = useState(c?.gstin ?? "");
  const [pan, setPan] = useState(c?.pan ?? "");
  const [entityType, setEntityType] = useState(from?.entity_type ?? "");
  const [cin, setCin] = useState(c?.cin ?? "");
  const [incorporated, setIncorporated] = useState(c?.incorporation_date ?? "");
  const [tan, setTan] = useState(c?.tan ?? "");
  const [stateCode, setStateCode] = useState(from?.state_code ?? "");
  const [contact, setContact] = useState(contactOf(from));
  const [fyMonth, setFyMonth] = useState(from?.fiscal_year_start_month ?? 4);
  const [booksStart, setBooksStart] = useState(c?.books_start ?? "");
  const [multiCurrency, setMultiCurrency] = useState(from?.multi_currency ?? false);
  const allModules = useModules();
  const [modules, setModules] = useState<string[] | null>(props.copyOf?.modules ?? null);
  const [error, setError] = useState("");

  // A GSTIN starts with the state code and contains the PAN.
  const onGstin = (value: string) => {
    const v = value.toUpperCase();
    setGstin(v);
    if (v.length >= 2 && props.states.some((s) => s.code === v.slice(0, 2))) setStateCode(v.slice(0, 2));
    if (v.length >= 12) setPan(v.slice(2, 12));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = {
      name,
      gstin,
      pan,
      entity_type: entityType,
      cin: MCA_TYPES.includes(entityType) ? cin : "",
      incorporation_date: incorporated || null,
      tan,
      state_code: stateCode,
      ...contact,
      fiscal_year_start_month: fyMonth,
      ...(booksStart ? { books_start: booksStart } : {}),
      multi_currency: multiCurrency,
      ...(!c && modules ? { modules } : {}),
      ...(c ? {} : abbr ? { abbr } : {}),
    };
    try {
      props.onDone(c ? await api<Company>(`v1/companies/${c.id}/`, body, "PATCH") : await api<Company>("v1/companies/", body));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h3>{c ? `Edit ${c.name}` : props.copyOf ? `Duplicate ${props.copyOf.name}` : "Add company"}</h3>
      <label>
        Legal name
        <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {!c && (
        <label>
          Short code for document numbers (leave blank to use initials)
          <input value={abbr} maxLength={10} placeholder="e.g. AOL" onChange={(e) => setAbbr(e.target.value.toUpperCase())} />
        </label>
      )}
      <div className="row">
        <label>
          GSTIN (blank if unregistered)
          <input value={gstin} maxLength={15} onChange={(e) => onGstin(e.target.value)} />
        </label>
        <label>
          PAN
          <input value={pan} maxLength={10} onChange={(e) => setPan(e.target.value.toUpperCase())} />
        </label>
      </div>
      <label>
        State
        <StateSelect states={props.states} value={stateCode} onChange={setStateCode} />
      </label>
      <div className="row">
        <label>
          Type of entity
          <select value={entityType} onChange={(e) => setEntityType(e.target.value)}>
            <option value="">Choose…</option>
            {ENTITY_TYPES.map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {MCA_TYPES.includes(entityType) && (
          <label>
            {cinLabel(entityType)}
            <input
              value={cin}
              maxLength={21}
              placeholder={entityType === "llp" ? "AAB-1234" : "U01100MH2015PTC123456"}
              onChange={(e) => setCin(e.target.value.toUpperCase())}
            />
          </label>
        )}
      </div>
      <div className="row">
        <label>
          Date of incorporation
          <input type="date" value={incorporated} onChange={(e) => setIncorporated(e.target.value)} />
        </label>
        <label>
          TAN (for deducting TDS)
          <input value={tan} maxLength={10} onChange={(e) => setTan(e.target.value.toUpperCase())} />
        </label>
      </div>
      <ContactFields value={contact} onChange={setContact} addressLabel="Registered address" />
      <label>
        Financial year starts in
        <select value={fyMonth} onChange={(e) => setFyMonth(Number(e.target.value))}>
          {MONTHS.map((m, i) => (
            <option key={m} value={i + 1}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label>
        Books beginning from (opening balances are as at this date; blank = start of this financial year)
        <input type="date" value={booksStart} onChange={(e) => setBooksStart(e.target.value)} />
      </label>
      <label className="check">
        <input type="checkbox" checked={multiCurrency} onChange={(e) => setMultiCurrency(e.target.checked)} />
        Use foreign currencies (exports, imports, EEFC accounts). Books stay in INR.
      </label>
      {!c && (
        <fieldset>
          <legend>Modules this company uses (the Owner can change them later)</legend>
          <ModulePicker modules={allModules} value={modules ?? allModules.map((m) => m.code)} onChange={setModules} />
        </fieldset>
      )}
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function CompanyPage(props: { id: number; session: SignedIn; tab?: string }) {
  const { id, session } = props;
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const states = useStates();
  const canEdit = session.permissions.includes("masters.edit");
  const reload = useCallback(() => {
    api<Detail>(`v1/companies/${id}/`)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [id]);
  useEffect(reload, [reload]);

  if (!detail) return <section className="page">{error ? <p className="error">{error}</p> : <p>Loading…</p>}</section>;
  const c = detail.company;
  const tab = TABS.some(([code]) => code === props.tab) ? props.tab : "";
  const sub = [
    ENTITY_TYPES.find(([code]) => code === c.entity_type)?.[1],
    c.state,
    c.gstin ? `GSTIN ${c.gstin}` : "Unregistered for GST",
    `Books from ${longDate(c.books_start)}`,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <section className="page">
      <PageHeader
        title={c.name}
        crumbs={[{ label: "Companies", href: "#/companies" }]}
        sub={sub}
        actions={
          <>
            {canEdit && !editing && (
              <button
                onClick={() => {
                  setEditing(true);
                  if (tab) window.location.hash = `#/companies/${c.id}`;
                }}
              >
                Edit details
              </button>
            )}
          </>
        }
      >
        <nav className="tabs" aria-label="Company sections">
          {TABS.map(([code, label]) => (
            <a
              key={code}
              href={`#/companies/${c.id}${code ? `/${code}` : ""}`}
              className={tab === code ? "active" : ""}
              aria-current={tab === code ? "page" : undefined}
            >
              {label}
            </a>
          ))}
        </nav>
      </PageHeader>
      <WithActivity activity={<Activity company={c.id} filter stamp={JSON.stringify(detail)} />}>
        {tab === "" &&
          (editing ? (
            <CompanyForm
              company={c}
              states={states}
              onDone={() => {
                setEditing(false);
                reload();
              }}
              onCancel={() => setEditing(false)}
            />
          ) : (
            <Overview detail={detail} />
          ))}
        {tab === "branches" && (
          <Branches company={c} branches={detail.branches} states={states} canEdit={canEdit} reload={reload} />
        )}
        {tab === "certificates" && (
          <Certificates
            company={c}
            certificates={detail.certificates}
            branches={detail.branches}
            canEdit={canEdit}
            reload={reload}
          />
        )}
        {tab === "modules" && (
          <ModulesSection key={c.modules.join()} company={c} isOwner={session.user.is_owner} reload={reload} />
        )}
      </WithActivity>
    </section>
  );
}

const TABS: [string, string][] = [
  ["", "Overview"],
  ["branches", "Branches"],
  ["certificates", "Licences and certificates"],
  ["modules", "Modules"],
];

function Overview({ detail }: { detail: Detail }) {
  const c = detail.company;
  const diff = Number(detail.opening.difference);
  const next = detail.certificates
    .filter((x) => x.valid_until)
    .sort((a, b) => (a.valid_until! < b.valid_until! ? -1 : 1))[0];
  const renewal = next ? renewalNote(next.valid_until) : null;
  const open = detail.branches.filter((b) => b.is_active);
  const { where, reach } = contactLines(c);
  return (
    <>
      <div className="stats">
        <div className="stat">
          <span className="stat-label">Opening balance difference</span>
          <span className={`stat-value ${diff !== 0 ? "error" : "ok"}`}>
            {diff === 0 ? "Balanced" : `${money(Math.abs(diff))} ${diff > 0 ? "Dr" : "Cr"}`}
          </span>
          <span className="stat-note">
            Dr {money(detail.opening.dr)} · Cr {money(detail.opening.cr)}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Next renewal</span>
          <span className={`stat-value ${renewal?.cls === "small" ? "" : (renewal?.cls ?? "")}`}>
            {next ? longDate(next.valid_until!) : "None due"}
          </span>
          <span className="stat-note">
            {next ? `${next.kind === "other" ? next.name : next.kind_label} · ${next.branch_name || "Company"}` : "No licence with a renewal date"}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Branches</span>
          <span className="stat-value">{open.length}</span>
          <span className="stat-note">{open.map((b) => b.name).join(" · ")}</span>
        </div>
      </div>
      <div className="cards">
        <div className="card">
          <h2>Registration</h2>
          <dl className="kv">
            <div>
              <dt>Short code</dt>
              <dd>{c.abbr}</dd>
            </div>
            <div>
              <dt>Type of entity</dt>
              <dd>{ENTITY_TYPES.find(([code]) => code === c.entity_type)?.[1] ?? "—"}</dd>
            </div>
            <div>
              <dt>GSTIN</dt>
              <dd>{c.gstin || "Unregistered"}</dd>
            </div>
            <div>
              <dt>PAN</dt>
              <dd>{c.pan || "—"}</dd>
            </div>
            {MCA_TYPES.includes(c.entity_type) && (
              <div>
                <dt>{cinLabel(c.entity_type)}</dt>
                <dd>{c.cin || "—"}</dd>
              </div>
            )}
            <div>
              <dt>TAN</dt>
              <dd>{c.tan || "—"}</dd>
            </div>
            <div>
              <dt>Incorporated</dt>
              <dd>{c.incorporation_date ? longDate(c.incorporation_date) : "—"}</dd>
            </div>
            <div>
              <dt>State</dt>
              <dd>{c.state}</dd>
            </div>
          </dl>
        </div>
        <div className="card">
          <h2>Registered address and contact</h2>
          <p className="pre">{where}</p>
          {reach !== "—" && <p>{reach}</p>}
        </div>
        <div className="card">
          <h2>Books</h2>
          <dl className="kv">
            <div>
              <dt>Financial year</dt>
              <dd>
                {MONTHS[c.fiscal_year_start_month - 1]} to {MONTHS[(c.fiscal_year_start_month + 10) % 12]}
              </dd>
            </div>
            <div>
              <dt>Books beginning from</dt>
              <dd>{longDate(c.books_start)}</dd>
            </div>
            <div>
              <dt>Base currency</dt>
              <dd>{c.base_currency}</dd>
            </div>
            <div>
              <dt>Currencies</dt>
              <dd>{c.multi_currency ? "INR, plus foreign currencies on ledgers" : "INR only"}</dd>
            </div>
          </dl>
        </div>
      </div>
    </>
  );
}

function Branches(props: { company: Company; branches: Branch[]; states: State[]; canEdit: boolean; reload: () => void }) {
  const [editing, setEditing] = useState<Branch | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<Branch | null>(null);
  const stateName = (code: string) => props.states.find((s) => s.code === code)?.name ?? code;
  return (
    <>
      <div className="page-head">
        <h3>Branches</h3>
        {props.canEdit && (
          <button
            className="link"
            onClick={() => {
              setCopyOf(null);
              setEditing("new");
            }}
          >
            Add branch
          </button>
        )}
      </div>
      {editing && (
        <BranchForm
          company={props.company}
          key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
          branch={editing === "new" ? null : editing}
          copyOf={copyOf}
          readOnly={!props.canEdit}
          states={props.states}
          onDone={() => {
            setEditing(null);
            setCopyOf(null);
            props.reload();
          }}
          onCancel={() => {
            setEditing(null);
            setCopyOf(null);
          }}
        />
      )}
      <table>
        <thead>
          <tr>
            <th>Branch</th>
            <th>State</th>
            <th>GSTIN</th>
            <th>Address</th>
            <th>Contact</th>
            <ActionHeads />
          </tr>
        </thead>
        <tbody>
          {props.branches.map((b) => (
            <tr key={b.id} className={b.is_active ? "" : "inactive"}>
              <td>
                {b.name}
                {b.is_head_office && <span className="small"> · head office</span>}
                <div>
                  {DEFAULTS.filter(([flag]) => b[flag]).map(([flag]) => (
                    <span key={flag} className="tag">
                      {{ default_billing: "Billing", default_ship_to: "Ship to", default_ship_from: "Ship from" }[flag]}
                    </span>
                  ))}
                </div>
                {!b.is_active && <span className="small"> · closed</span>}
              </td>
              <td>{stateName(b.state_code)}</td>
              <td>{b.gstin || <span className="small">Company's</span>}</td>
              <td className="pre small">{contactLines(b).where}</td>
              <td className="small">{contactLines(b).reach}</td>
              <ActionCells
                canEdit={props.canEdit}
                onOpen={() => {
                  setCopyOf(null);
                  setEditing(b);
                }}
                onDuplicate={() => {
                  setCopyOf(b);
                  setEditing("new");
                }}
              />
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function BranchForm(props: {
  company: Company;
  branch: Branch | null;
  copyOf?: Branch | null;
  readOnly?: boolean;
  states: State[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const b = props.branch;
  const from = b ?? props.copyOf; // a duplicate copies the place and contacts, not the name, GSTIN or defaults
  const [name, setName] = useState(b?.name ?? "");
  const [stateCode, setStateCode] = useState(from?.state_code ?? props.company.state_code);
  const [gstin, setGstin] = useState(b?.gstin ?? "");
  const [contact, setContact] = useState(contactOf(from));
  const [flags, setFlags] = useState<Record<DefaultFlag, boolean>>({
    default_billing: b?.default_billing ?? false,
    default_ship_to: b?.default_ship_to ?? false,
    default_ship_from: b?.default_ship_from ?? false,
  });
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    // Only newly ticked defaults are sent; ticking moves it from the other branch.
    const ticked = Object.fromEntries(DEFAULTS.filter(([f]) => flags[f] && !b?.[f]).map(([f]) => [f, true]));
    const body = { name, state_code: stateCode, gstin, ...contact, ...ticked };
    try {
      if (b) await api(`v1/branches/${b.id}/`, body, "PATCH");
      else await api(`v1/companies/${props.company.id}/branches/`, body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h4>{b ? `${props.readOnly ? "View" : "Edit"} ${b.name}` : props.copyOf ? `Duplicate ${props.copyOf.name}` : "Add branch"}</h4>
      <FormBody readOnly={props.readOnly}>
      <label>
        Name
        <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Bhiwandi warehouse" />
      </label>
      <div className="row">
        <label>
          State
          <StateSelect states={props.states} value={stateCode} onChange={setStateCode} />
        </label>
        <label>
          GSTIN (only if registered separately in that state)
          <input value={gstin} maxLength={15} onChange={(e) => setGstin(e.target.value.toUpperCase())} />
        </label>
      </div>
      <ContactFields value={contact} onChange={setContact} />
      <fieldset>
        <legend>Default addresses (picked first on documents, can be changed on each)</legend>
        {DEFAULTS.map(([flag, label]) => (
          <label key={flag} className="check">
            <input
              type="checkbox"
              checked={flags[flag]}
              disabled={b?.[flag]}
              onChange={(e) => setFlags({ ...flags, [flag]: e.target.checked })}
            />
            {label}
            {b?.[flag] ? " (to move it, tick it on another branch)" : ""}
          </label>
        ))}
      </fieldset>
      </FormBody>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {!props.readOnly && <button>Save</button>}
        <button type="button" className="link" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
        {b && !b.is_head_office && !props.readOnly && (
          <ActiveButton
            url={`v1/branches/${b.id}/`}
            active={b.is_active}
            what={`the branch ${b.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}

export function renewalNote(until: string | null) {
  if (!until) return { text: "No renewal", cls: "small" };
  const days = Math.ceil((new Date(until).getTime() - Date.now()) / 86400000);
  if (days < 0) return { text: `Expired ${longDate(until)}`, cls: "error" };
  if (days <= 90) return { text: `Renew by ${longDate(until)} (${days} days)`, cls: "warn" };
  return { text: `Renew by ${longDate(until)}`, cls: "" };
}

function Certificates(props: {
  company: Company;
  certificates: Certificate[];
  branches: Branch[];
  canEdit: boolean;
  reload: () => void;
}) {
  const [editing, setEditing] = useState<Certificate | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<Certificate | null>(null);
  return (
    <>
      <div className="page-head">
        <h3>Licences and certificates</h3>
        {props.canEdit && (
          <button
            className="link"
            onClick={() => {
              setCopyOf(null);
              setEditing("new");
            }}
          >
            Add certificate
          </button>
        )}
      </div>
      {editing && (
        <CertificateForm
          company={props.company}
          key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
          certificate={editing === "new" ? null : editing}
          copyOf={copyOf}
          readOnly={!props.canEdit}
          branches={props.branches}
          onDone={() => {
            setEditing(null);
            setCopyOf(null);
            props.reload();
          }}
          onCancel={() => {
            setEditing(null);
            setCopyOf(null);
          }}
        />
      )}
      {props.certificates.length === 0 ? (
        <p className="small">None yet. Add the FSSAI licence, Udyam, IEC, organic and ISO certificates with their renewal dates.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Certificate</th>
              <th>Number</th>
              <th>Branch</th>
              <th>Renewal</th>
              <ActionHeads />
            </tr>
          </thead>
          <tbody>
            {props.certificates.map((x) => {
              const note = renewalNote(x.valid_until);
              return (
                <tr key={x.id}>
                  <td>
                    {x.kind_label}
                    {x.name && <div className="small">{x.name}</div>}
                  </td>
                  <td>
                    {x.number}
                    {x.issued_by && <div className="small">{x.issued_by}</div>}
                  </td>
                  <td>{x.branch_name || <span className="small">Whole company</span>}</td>
                  <td className={note.cls}>{note.text}</td>
                  <ActionCells
                    canEdit={props.canEdit}
                    onOpen={() => {
                      setCopyOf(null);
                      setEditing(x);
                    }}
                    onDuplicate={() => {
                      setCopyOf(x);
                      setEditing("new");
                    }}
                  />
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
}

function CertificateForm(props: {
  company: Company;
  certificate: Certificate | null;
  copyOf?: Certificate | null;
  readOnly?: boolean;
  branches: Branch[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const x = props.certificate;
  const from = x ?? props.copyOf; // a duplicate keeps the kind and issuer, not the number or dates
  const [kind, setKind] = useState(from?.kind ?? "fssai");
  const [name, setName] = useState(from?.name ?? "");
  const [number, setNumber] = useState(x?.number ?? "");
  const [issuedBy, setIssuedBy] = useState(from?.issued_by ?? "");
  const [branch, setBranch] = useState<number | null>(from?.branch ?? null);
  const [validFrom, setValidFrom] = useState(x?.valid_from ?? "");
  const [validUntil, setValidUntil] = useState(x?.valid_until ?? "");
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = {
      kind,
      name,
      number,
      issued_by: issuedBy,
      branch,
      valid_from: validFrom || null,
      valid_until: validUntil || null,
      notes,
    };
    try {
      if (x) await api(`v1/certificates/${x.id}/`, body, "PATCH");
      else await api(`v1/companies/${props.company.id}/certificates/`, body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h4>{x ? `${props.readOnly ? "View" : "Edit"} ${x.kind_label}` : props.copyOf ? "Duplicate certificate" : "Add certificate"}</h4>
      <FormBody readOnly={props.readOnly}>
      <div className="row">
        <label>
          Type
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {CERTIFICATE_KINDS.map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Name {kind === "other" ? "" : "(optional, e.g. ISO 9001:2015)"}
          <input value={name} required={kind === "other"} onChange={(e) => setName(e.target.value)} />
        </label>
      </div>
      <div className="row">
        <label>
          Number
          <input required value={number} onChange={(e) => setNumber(e.target.value)} />
        </label>
        <label>
          Issued by
          <input value={issuedBy} placeholder="e.g. FSSAI, DGFT, certification body" onChange={(e) => setIssuedBy(e.target.value)} />
        </label>
      </div>
      <label>
        Branch (for licences issued per premises)
        <Combobox
          value={branch === null ? "" : String(branch)}
          empty="Whole company"
          options={props.branches.map((b) => ({ value: String(b.id), label: b.name }))}
          onChange={(v) => setBranch(v ? Number(v) : null)}
        />
      </label>
      <div className="row">
        <label>
          Valid from
          <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
        </label>
        <label>
          Renewal date (blank if it does not lapse)
          <input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
        </label>
      </div>
      <label>
        Notes
        <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <p className="small">A renewed certificate is added as a new one, so the old one stays on record.</p>
      </FormBody>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {!props.readOnly && <button>Save</button>}
        <button type="button" className="link" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
      </div>
    </form>
  );
}

export function LedgerGroupsPage({ id, session }: { id: number; session: SignedIn }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Detail>(`v1/companies/${id}/`)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [id]);
  useEffect(reload, [reload]);
  if (!detail) return <section className="page">{error ? <p className="error">{error}</p> : <p>Loading…</p>}</section>;
  return (
    <section className="page">
      <PageHeader
        title="Ledger groups"
        crumbs={[
          { label: "Companies", href: "#/companies" },
          { label: detail.company.name, href: `#/companies/${id}` },
        ]}
        actions={
          <a className="button" href={`#/companies/${id}/ledgers`}>
            Ledgers
          </a>
        }
      />
      <WithActivity activity={<Activity company={id} type="ledger_group" stamp={JSON.stringify(detail)} />}>
        <LedgerGroups
          company={detail.company}
          groups={detail.ledger_groups}
          canEdit={session.permissions.includes("masters.edit")}
          reload={reload}
        />
      </WithActivity>
    </section>
  );
}

function LedgerGroups(props: { company: Company; groups: Group[]; canEdit: boolean; reload: () => void }) {
  const [editing, setEditing] = useState<{ group: Group | null; parent: number | null; copyName?: string } | null>(null);
  const children = useMemo(() => {
    const map = new Map<number | null, Group[]>();
    for (const g of props.groups) map.set(g.parent, [...(map.get(g.parent) ?? []), g]);
    return map;
  }, [props.groups]);

  const [folded, setFolded] = useState<Set<number>>(new Set());
  const [level, setLevel] = useState<number | null>(Infinity);
  const tops = children.get(null) ?? [];
  const depthOf = useMemo(() => {
    const d = new Map<number, number>();
    const walk = (parent: number | null, depth: number) =>
      (children.get(parent) ?? []).forEach((g) => {
        d.set(g.id, depth);
        walk(g.id, depth + 1);
      });
    walk(null, 0);
    return d;
  }, [children]);
  const deepest = Math.max(0, ...depthOf.values());
  const showLevels = (n: number) => {
    setLevel(n);
    setFolded(new Set(props.groups.filter((g) => children.has(g.id) && (depthOf.get(g.id) ?? 0) >= n - 1).map((g) => g.id)));
  };
  const toggle = (id: number) =>
    setFolded((f) => {
      setLevel(null);
      const next = new Set(f);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const total = (g: Group): number => g.ledger_count + (children.get(g.id) ?? []).reduce((t, c) => t + total(c), 0);
  function done() {
    setEditing(null);
    props.reload();
  }
  const formRow = (key: string, form: JSX.Element) => (
    <tr key={key} className="form-row">
      <td colSpan={5}>{form}</td>
    </tr>
  );

  const rows = (g: Group, depth: number): JSX.Element[] => {
    const kids = children.get(g.id) ?? [];
    const top = depth === 0;
    const out = [
      <tr key={g.id} className={top ? "group-top" : ""}>
        <td>
          <span className="group-name" style={{ paddingLeft: depth * 22 }}>
            {kids.length > 0 ? (
              <button
                className="fold"
                aria-expanded={!folded.has(g.id)}
                aria-label={`${folded.has(g.id) ? "Show" : "Hide"} groups under ${g.name}`}
                onClick={() => toggle(g.id)}
              >
                <Chevron open={!folded.has(g.id)} />
              </button>
            ) : (
              <span className="branch" aria-hidden="true">
                {top ? "" : "└"}
              </span>
            )}
            <span className="gname">
              {g.name}
              {g.schedule_iii && <span className="sch3 sub">{g.schedule_iii}</span>}
            </span>
            {!g.is_standard && <span className="tag">added</span>}
          </span>
        </td>
        <td>
          {NATURE[g.nature]}
          {top && g.affects_gross_profit && <span className="small"> · trading</span>}
        </td>
        <td className="num">
          {total(g) > 0 ? (
            <a href={`#/companies/${props.company.id}/ledgers/${g.id}`}>{total(g)}</a>
          ) : (
            <span className="small">—</span>
          )}
        </td>
        <td className="row-actions">
          {props.canEdit && (
            <>
              <button className="link" onClick={() => setEditing({ group: null, parent: g.id })}>
                + Sub-group
              </button>
              {!g.is_standard && (
                <button className="link" onClick={() => setEditing({ group: g, parent: g.parent })}>
                  Edit
                </button>
              )}
              {g.parent !== null && (
                <button
                  className="link"
                  onClick={() => setEditing({ group: null, parent: g.parent, copyName: `${g.name} (copy)` })}
                >
                  Duplicate
                </button>
              )}
            </>
          )}
        </td>
      </tr>,
    ];
    if (editing && editing.parent === g.id && editing.group === null)
      out.push(
        formRow(
          `new-${g.id}`,
          <GroupForm company={props.company} groups={props.groups} group={null} parent={g.id} initialName={editing.copyName} onDone={done} onCancel={() => setEditing(null)} />,
        ),
      );
    if (editing?.group?.id === g.id)
      out.push(
        formRow(
          `edit-${g.id}`,
          <GroupForm company={props.company} groups={props.groups} group={g} parent={g.parent} onDone={done} onCancel={() => setEditing(null)} />,
        ),
      );
    if (!folded.has(g.id)) for (const c of kids) out.push(...rows(c, depth + 1));
    return out;
  };

  return (
    <>
      <div className="page-head">
        <p className="small">
          {props.groups.length} groups. The standard groups follow Schedule III of the Companies Act and cannot be
          changed; add your own under them, for example Export debtors under Sundry Debtors.
        </p>
        <LevelPicker levels={deepest} value={level} onPick={showLevels} />
      </div>
      <table className="groups">
        <thead>
          <tr>
            <th>Group</th>
            <th>Nature</th>
            <th className="num">Ledgers</th>
            <th />
          </tr>
        </thead>
        <tbody>{tops.flatMap((g) => rows(g, 0))}</tbody>
      </table>
    </>
  );
}

function GroupForm(props: {
  company: Company;
  groups: Group[];
  group: Group | null;
  parent: number | null;
  initialName?: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const g = props.group;
  const [name, setName] = useState(g?.name ?? props.initialName ?? "");
  const [parent, setParent] = useState<number | null>(props.parent);
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (g) await api(`v1/ledger-groups/${g.id}/`, { name, parent }, "PATCH");
      else await api(`v1/companies/${props.company.id}/ledger-groups/`, { name, parent });
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const remove = async () => {
    if (!g || !window.confirm(`Delete the group ${g.name}?`)) return;
    try {
      await api(`v1/ledger-groups/${g.id}/`, undefined, "DELETE");
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card inline" onSubmit={save}>
      <div className="row">
        <label>
          {g ? "Name" : "New group name"}
          <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        {g && (
          <label>
            Under
            <Combobox
              required
              value={parent === null ? "" : String(parent)}
              options={props.groups.filter((o) => o.id !== g.id).map((o) => ({ value: String(o.id), label: o.name }))}
              onChange={(v) => setParent(Number(v))}
            />
          </label>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {g && (
          <button type="button" className="link danger" onClick={remove}>
            Delete group
          </button>
        )}
      </div>
    </form>
  );
}
