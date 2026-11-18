import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { Attachments } from "./Attachments";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { ColumnSearch } from "./ColumnSearch";
import { Combobox } from "./Combobox";
import { money } from "./Companies";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName, type Creatable } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { Fold, FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useOnReturn } from "./Refresh";
import { ActionCells, ActionHeads } from "./RowActions";

/** Masters › Insurance Policies (Sidharth, 2026-11-18, previews 93a and 93d): the
 * company's marine, fire and stock policies, with the top-ups that refill a marine
 * policy's sum insured; and the "Transit Insurance" box of a purchase order. */

type TopUp = { date: string; endorsement_no: string; amount: string; premium: string };
export type Policy = {
  id: number;
  company: number;
  number: string;
  insurer: number;
  insurer_name: string;
  kind: string;
  kind_label: string;
  covers: string;
  covers_label: string;
  valid_from: string;
  valid_to: string;
  sum_insured: string;
  premium: string;
  transit_limit: string | null;
  insured_basis: string;
  insured_basis_label: string;
  default_for: string;
  default_for_label: string;
  alert_below: string | null;
  when_out: string;
  when_out_label: string;
  declare_to: string;
  copy_to: string;
  notes: string;
  is_active: boolean;
  is_transit: boolean;
  top_ups: TopUp[];
  cover: string;
  used: string;
  balance: string;
  low: boolean;
  orders: number;
  days_left: number;
  lock?: LockInfo;
};
type Setup = { insurers: { id: number; name: string; is_active: boolean }[]; supplier_group: number | null };

const KINDS: [string, string][] = [
  ["marine_inland", "Marine (inland transit)"],
  ["marine_export", "Marine (export)"],
  ["fire", "Fire"],
  ["stock", "Stock"],
];
const COVERS: [string, string][] = [
  ["both", "Purchases and Sales"],
  ["purchase", "Purchases"],
  ["sales", "Sales"],
];
const BASES: [string, string][] = [
  ["invoice_10", "Invoice value + 10%"],
  ["invoice", "Invoice value"],
];
const WHEN_OUT: [string, string][] = [
  ["warn", "Warn, keep insuring"],
  ["stop", "Stop until topped up"],
];
const TRANSIT = ["marine_inland", "marine_export"];
const opts = (rows: [string, string][]) => rows.map(([value, label]) => ({ value, label }));
const rupees = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? "" : `₹${money(v)}`);
const shortDate = (iso: string | null) => (iso ? iso.split("-").reverse().join("-") : "");
const pageHash = (company: number, query = "") => `#/companies/${company}/insurance${query}`;

function usePolicies(companyId: number) {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const reload = useCallback(
    () => api<Policy[]>(`v1/companies/${companyId}/insurance-policies/`).then(setPolicies, () => setPolicies([])),
    [companyId],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  useOnReturn(reload);
  return { policies, reload };
}

/** `?form=new`, `?form=<id>` or `?form=copy-<id>`: this tab adds, changes or duplicates one policy. */
export function InsurancePage({ companyId, session, companyName }: { companyId: number; session: SignedIn; companyName: string }) {
  const canEdit = session.permissions.includes("masters.edit");
  const form = hashParam("form");
  if (form) return <PolicyFormTab companyId={companyId} form={form} canEdit={canEdit} />;
  return <PolicyList companyId={companyId} session={session} canEdit={canEdit} companyName={companyName} />;
}

function PolicyList(props: { companyId: number; session: SignedIn; canEdit: boolean; companyName: string }) {
  const { companyId, canEdit } = props;
  const { policies, reload } = usePolicies(companyId);
  const [selectedId, setSelected] = useState<number | null>(null);
  useCreated("insurance_policy_saved", (p) => {
    reload();
    setSelected(p.id);
  });
  const startName = useNewName();
  useEffect(() => {
    if (startName && canEdit) window.location.hash = pageHash(companyId, `?form=new&new=${encodeURIComponent(startName)}`);
  }, [startName, canEdit, companyId]);
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && policies.some((p) => p.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, policies, opened]);
  const io = useExchange({ master: "insurance-policies", noun: "insurance policies", session: props.session, company: companyId, onImported: reload });
  const selected = policies.find((p) => p.id === selectedId) ?? null;
  const edit = (id: number | string) => openTab(pageHash(companyId, `?form=${id}`));
  return (
    <section className="page">
      <PageHeader
        title="Insurance Policies"
        sub={`${props.companyName}: marine policies for goods on the move, and fire and stock policies.`}
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>Add policy</button>}
          </>
        }
      />
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          {policies.length === 0 ? (
            <p className="small">No policies yet. Add each policy the company holds, with its sum insured and validity.</p>
          ) : (
            <table className="pick">
              <thead>
                <tr>
                  <th>Policy Number</th>
                  <th>Insurer</th>
                  <th>Type of Insurance</th>
                  <th>Valid To</th>
                  <th className="num">Total Cover ₹</th>
                  <th className="num">Balance ₹</th>
                  <ActionHeads />
                </tr>
                <ColumnSearch />
              </thead>
              <tbody>
                {policies.map((p) => (
                  <tr
                    key={p.id}
                    className={`${p.is_active ? "" : "off"}${selectedId === p.id ? " selected" : ""}`}
                    onClick={() => setSelected(p.id)}
                    onDoubleClick={() => edit(p.id)}
                  >
                    <td>
                      {p.number}
                      {!p.is_active && <span className="pill">Disabled</span>}
                      {p.days_left === 0 && p.is_active && <span className="pill">Expired</span>}
                    </td>
                    <td>{p.insurer_name}</td>
                    <td>{p.kind_label}</td>
                    <td>{shortDate(p.valid_to)}</td>
                    <td className="num">{money(p.cover)}</td>
                    <td className={`num${p.low ? " error" : ""}`}>{p.is_transit ? money(p.balance) : ""}</td>
                    <ActionCells canEdit={canEdit} onOpen={() => edit(p.id)} onDuplicate={() => edit(`copy-${p.id}`)} />
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="side-col">
          <SidePanel title="Policy Summary">
            {selected ? <PolicyFacts p={selected} /> : <p className="small">Click a row to see its details here.</p>}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog company={companyId} type="insurance_policy" id={selected?.id} stamp={JSON.stringify(selected ?? policies.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

function PolicyFacts({ p }: { p: Policy }) {
  return (
    <>
      <SideRows
        rows={[
          ["Policy Number", p.number],
          ["Insurer", p.insurer_name],
          ["Type", p.kind_label],
          ["Valid", `${shortDate(p.valid_from)} to ${shortDate(p.valid_to)}`],
          ["Days Left", String(p.days_left)],
          ["Total Cover", rupees(p.cover)],
          ...(p.is_transit
            ? ([
                ["Insured So Far", rupees(p.used)],
                ["Balance Cover", rupees(p.balance)],
                ["Orders", String(p.orders || "")],
              ] as [string, string][])
            : []),
          ["In Use", p.lock?.in_use.join(", ") ?? ""],
          ["Disabled", p.is_active ? "" : "Yes"],
        ]}
      />
      {p.low && <p className="error">Below {rupees(p.alert_below)}. Ask the insurer for a top-up.</p>}
    </>
  );
}

function PolicyFormTab(props: { companyId: number; form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const { policies } = usePolicies(props.companyId);
  const [loaded, setLoaded] = useState(props.form === "new");
  useEffect(() => {
    if (policies.length) setLoaded(true);
  }, [policies]);
  const startName = useNewName();
  const target = props.form === "new" ? null : (policies.find((p) => p.id === key) ?? null);
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("insurance_policy_saved", saved);
    closeThisTab(() => {
      window.location.hash = pageHash(props.companyId);
    });
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "Add Insurance Policy" : copy ? "Duplicate Insurance Policy" : readOnly ? "View Insurance Policy" : "Edit Insurance Policy";
  if (!loaded) return <section className="page"><PageHeader title={title} /></section>;
  if (props.form !== "new" && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That policy was not found.</p>
      </section>
    );
  if (readOnly && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view insurance policies.</p>
      </section>
    );
  return (
    <PolicyForm
      title={title}
      companyId={props.companyId}
      policy={editing ? target : null}
      copyOf={copy ? target : null}
      startNumber={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
    />
  );
}

function PolicyForm(props: {
  title: string;
  companyId: number;
  policy: Policy | null;
  copyOf: Policy | null;
  startNumber?: string;
  readOnly: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
}) {
  const p = props.policy;
  const from = p ?? props.copyOf; // a duplicate starts as a copy (without its top-ups) but is a new policy
  const [setup, setSetup] = useState<Setup | null>(null);
  const loadSetup = useCallback(
    () => api<Setup>(`v1/companies/${props.companyId}/insurance-policies/setup/`).then(setSetup),
    [props.companyId],
  );
  useEffect(() => {
    loadSetup();
  }, [loadSetup]);
  useOnReturn(loadSetup);
  const [number, setNumber] = useState(props.startNumber ?? (props.copyOf ? "" : (p?.number ?? "")));
  const [insurer, setInsurer] = useState(from ? String(from.insurer) : "");
  const [kind, setKind] = useState(from?.kind ?? "marine_inland");
  const [covers, setCovers] = useState(from?.covers ?? "both");
  const [validFrom, setValidFrom] = useState(props.copyOf ? "" : (p?.valid_from ?? ""));
  const [validTo, setValidTo] = useState(props.copyOf ? "" : (p?.valid_to ?? ""));
  const [sum, setSum] = useState(from?.sum_insured ?? "");
  const [premium, setPremium] = useState(props.copyOf ? "" : (p?.premium === "0.00" ? "" : (p?.premium ?? "")));
  const [limit, setLimit] = useState(from?.transit_limit ?? "");
  const [basis, setBasis] = useState(from?.insured_basis ?? "invoice_10");
  const [defaultFor, setDefaultFor] = useState(props.copyOf ? "" : (p?.default_for ?? ""));
  const [alertBelow, setAlertBelow] = useState(from?.alert_below ?? "");
  const [whenOut, setWhenOut] = useState(from?.when_out ?? "warn");
  const [declareTo, setDeclareTo] = useState(from?.declare_to ?? "");
  const [copyTo, setCopyTo] = useState(from?.copy_to ?? "");
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [topUps, setTopUps] = useState<TopUp[]>(props.copyOf ? [] : (p?.top_ups ?? []));
  const [disabled, setDisabled] = useState(p ? !p.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState(0);
  const locked = (field: string) => isLocked(p?.lock, field);
  const transit = TRANSIT.includes(kind);
  const total = (Number(sum) || 0) + topUps.reduce((s, t) => s + (Number(t.amount) || 0), 0);
  const addInsurer: Creatable | undefined = setup?.supplier_group
    ? {
        kind: "ledger",
        href: (name) =>
          `${window.location.pathname}${window.location.search}#/companies/${props.companyId}/ledgers?form=new-in-${setup.supplier_group}&new=${encodeURIComponent(name)}`,
        reload: loadSetup,
      }
    : undefined;
  const changeTopUp = (i: number, patch: Partial<TopUp>) => setTopUps((rows) => rows.map((r, n) => (n === i ? { ...r, ...patch } : r)));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = {
      number,
      insurer: Number(insurer) || null,
      kind,
      covers,
      valid_from: validFrom || null,
      valid_to: validTo || null,
      sum_insured: sum || "0",
      premium: premium || "0",
      transit_limit: transit && limit ? limit : null,
      insured_basis: basis,
      default_for: transit ? defaultFor : "",
      alert_below: transit && alertBelow ? alertBelow : null,
      when_out: whenOut,
      declare_to: transit ? declareTo : "",
      copy_to: transit ? copyTo : "",
      notes,
      top_ups: topUps.map((t) => ({ ...t, amount: t.amount || "0", premium: t.premium || "0" })),
    };
    try {
      if (p) {
        await api(`v1/insurance-policies/${p.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: p.id, name: number });
      } else {
        const made = await api<Policy>(`v1/companies/${props.companyId}/insurance-policies/`, body);
        announceCreated("insurance_policy", { id: made.id, name: made.number });
        props.onDone({ id: made.id, name: made.number });
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <FormPage
      title={props.title}
      sub={p ? p.number : undefined}
      formId="policy-form"
      onSubmit={save}
      onCancel={() => props.onDone()}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={p ? { value: disabled, set: setDisabled } : undefined}
      tips={
        <>
          <p className="small">
            A marine policy is used up by the orders insured under it. When the insurer tops it up, add the endorsement under "Sum Insured and Top-ups".
          </p>
          {p && (
            <SideRows
              rows={[
                ["Total Cover", rupees(p.cover)],
                ...(p.is_transit
                  ? ([
                      ["Insured So Far", rupees(p.used)],
                      ["Balance Cover", rupees(p.balance)],
                    ] as [string, string][])
                  : []),
                ["Days Left", String(p.days_left)],
              ]}
            />
          )}
          {p?.low && <p className="error">Below {rupees(p.alert_below)}. Ask the insurer for a top-up.</p>}
        </>
      }
      activity={p ? <ChangeLog company={props.companyId} type="insurance_policy" id={p.id} stamp={JSON.stringify(p) + files} /> : undefined}
    >
      <InUseNote lock={p?.lock} />
      <Section title="General">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Policy Number</span>
            <input required autoFocus value={number} maxLength={60} onChange={(e) => setNumber(e.target.value)} />
          </label>
          <label>
            <span className="req">Insurer</span>
            <Locked on={locked("insurer")}>
              <Combobox
                required
                value={insurer}
                onChange={setInsurer}
                create={addInsurer}
                placeholder="Type to search suppliers…"
                options={(setup?.insurers ?? []).filter((s) => s.is_active || String(s.id) === insurer).map((s) => ({ value: String(s.id), label: s.name }))}
              />
            </Locked>
            <span className="small">The insurance company, from the company's suppliers</span>
          </label>
          <label>
            <span className="req">Type of Insurance</span>
            <Locked on={locked("kind")}>
              <Combobox value={kind} onChange={setKind} options={opts(KINDS)} />
            </Locked>
            {transit && <span className="small">Picked on purchase orders (and later sales) for goods on the move</span>}
          </label>
          {transit && (
            <label>
              Covers
              <Combobox value={covers} onChange={setCovers} options={opts(COVERS)} />
            </label>
          )}
          <label>
            <span className="req">Valid From</span>
            <input type="date" required value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </label>
          <label>
            <span className="req">Valid To</span>
            <input type="date" required value={validTo} min={validFrom} onChange={(e) => setValidTo(e.target.value)} />
          </label>
          {transit && (
            <>
              <label>
                Limit per Transit ₹
                <input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} />
                <span className="small">An order above this is flagged on the order</span>
              </label>
              <label>
                Insured Value
                <Combobox value={basis} onChange={setBasis} options={opts(BASES)} />
              </label>
              <label>
                Default For
                <Combobox
                  value={defaultFor}
                  onChange={setDefaultFor}
                  empty="None"
                  options={opts(covers === "both" ? COVERS : COVERS.filter(([v]) => v === covers))}
                />
                <span className="small">New orders start with this policy</span>
              </label>
            </>
          )}
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      </Section>
      <Section title="Sum Insured and Top-ups">
        <div className="item-fields">
          <label>
            <span className="req">Starting Sum Insured ₹</span>
            <input required inputMode="decimal" value={sum} onChange={(e) => setSum(e.target.value)} />
            <span className="small">The cover when the policy was issued</span>
          </label>
          <label>
            Premium ₹
            <input inputMode="decimal" value={premium} onChange={(e) => setPremium(e.target.value)} />
          </label>
        </div>
        {topUps.length > 0 && (
          <table className="grid">
            <thead>
              <tr>
                <th>Date</th>
                <th>Endorsement No.</th>
                <th className="num">Cover Added ₹</th>
                <th className="num">Premium ₹</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {topUps.map((t, i) => (
                <tr key={i}>
                  <td>
                    <input type="date" required value={t.date} min={validFrom} max={validTo} onChange={(e) => changeTopUp(i, { date: e.target.value })} />
                  </td>
                  <td>
                    <input value={t.endorsement_no} maxLength={60} onChange={(e) => changeTopUp(i, { endorsement_no: e.target.value })} />
                  </td>
                  <td className="num">
                    <input required inputMode="decimal" value={t.amount} onChange={(e) => changeTopUp(i, { amount: e.target.value })} />
                  </td>
                  <td className="num">
                    <input inputMode="decimal" value={t.premium === "0.00" ? "" : t.premium} onChange={(e) => changeTopUp(i, { premium: e.target.value })} />
                  </td>
                  <td>
                    <button type="button" className="link danger" onClick={() => setTopUps((rows) => rows.filter((_, n) => n !== i))}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p>
          <button
            type="button"
            className="link"
            onClick={() => setTopUps((rows) => [...rows, { date: new Date().toISOString().slice(0, 10), endorsement_no: "", amount: "", premium: "" }])}
          >
            + Add Top-up
          </button>{" "}
          <b className="fact-label">Total Cover</b> {rupees(total)}
        </p>
        {transit && (
          <div className="item-fields">
            <label>
              Alert When Balance Falls Below ₹
              <input inputMode="decimal" value={alertBelow} onChange={(e) => setAlertBelow(e.target.value)} />
              <span className="small">Owners and Accountants get a bell notice once the balance drops below it</span>
            </label>
            <label>
              When Cover Runs Out
              <Combobox value={whenOut} onChange={setWhenOut} options={opts(WHEN_OUT)} />
              <span className="small">"Stop" refuses Submit on an order the balance cannot cover</span>
            </label>
          </div>
        )}
      </Section>
      {transit && (
        <Section title="Daily Declaration">
          <div className="item-fields">
            <label>
              Send Declaration To
              <input value={declareTo} placeholder="Insurer or broker emails, comma-separated" onChange={(e) => setDeclareTo(e.target.value)} />
            </label>
            <label>
              Copy To
              <input value={copyTo} onChange={(e) => setCopyTo(e.target.value)} />
            </label>
          </div>
          <p className="small">The daily list of insured orders for the insurer comes next, in the format the insurer asks for.</p>
        </Section>
      )}
      {p ? (
        <Attachments type="insurance_policy" id={p.id} onChange={() => setFiles((n) => n + 1)} />
      ) : (
        <Section title="Attachments">
          <p className="small">Save the policy first, then add its copy and the endorsements here.</p>
        </Section>
      )}
    </FormPage>
  );
}

// On orders -------------------------------------------------------------------------

export type PolicyPick = {
  id: number;
  number: string;
  insurer_name: string;
  kind_label: string;
  valid_from: string;
  valid_to: string;
  is_active: boolean;
  is_default: boolean;
  plus_ten: boolean;
  transit_limit: string | null;
  balance: string;
};
export type OrderInsurance = {
  insured_by: string;
  insured_by_label: string;
  insurance_policy: number | null;
  insurance_policy_label: string;
  insured_value: string;
};
const INSURED_BY: [string, string][] = [
  ["us", "Us"],
  ["supplier", "Supplier"],
  ["none", "Not insured"],
];

/** The policy a new order starts with: the default one valid on the order date. */
export function defaultPolicy(policies: PolicyPick[], day: string): PolicyPick | undefined {
  return policies.find((p) => p.is_default && p.is_active && p.valid_from <= day && day <= p.valid_to);
}

/** The "Transit Insurance" box of a purchase order being made (preview 93b). */
export function TransitInsuranceFold(props: {
  companyId: number;
  insuredBy: string;
  setInsuredBy: (v: string) => void;
  policy: string;
  setPolicy: (v: string) => void;
  policies: PolicyPick[];
  orderDate: string;
  total: number;
  rupeeOrder: boolean;
  canAdd: boolean;
  refresh: () => unknown;
}) {
  const picked = props.policies.find((p) => String(p.id) === props.policy);
  const value = picked ? Math.round(props.total * (picked.plus_ten ? 110 : 100)) / 100 : 0;
  const usable = props.policies.filter(
    (p) => String(p.id) === props.policy || (p.is_active && p.valid_from <= props.orderDate && props.orderDate <= p.valid_to),
  );
  const warnings = [
    picked?.transit_limit && value > Number(picked.transit_limit) && `Above the policy's limit per transit of ₹${money(picked.transit_limit)}.`,
    picked && value > Number(picked.balance) && `Only ₹${money(picked.balance)} of cover is left on this policy.`,
    props.insuredBy === "us" && !props.rupeeOrder && "Our marine policies insure rupee orders only.",
  ].filter(Boolean) as string[];
  const summary = props.insuredBy === "us" ? (picked ? `${picked.number} · ${rupees(value)}` : "Pick the policy") : (INSURED_BY.find(([v]) => v === props.insuredBy)?.[1] ?? "");
  return (
    <Fold title="Transit Insurance" open={props.insuredBy === "us"} summary={summary}>
      <div className="item-fields">
        <label>
          Insured By
          <Combobox value={props.insuredBy} onChange={props.setInsuredBy} options={opts(INSURED_BY)} />
          <span className="small">"Us" when the goods travel under one of our marine policies</span>
        </label>
        {props.insuredBy === "us" && (
          <label>
            <span className="req">Policy</span>
            <Combobox
              required
              value={props.policy}
              onChange={props.setPolicy}
              create={
                props.canAdd
                  ? {
                      kind: "insurance_policy",
                      href: (name) => `${window.location.pathname}${window.location.search}${pageHash(props.companyId, `?new=${encodeURIComponent(name)}`)}`,
                      reload: props.refresh,
                    }
                  : undefined
              }
              placeholder="Type to search policies…"
              options={usable.map((p) => ({ value: String(p.id), label: p.number, hint: `${p.insurer_name} · ${p.kind_label}` }))}
            />
            <span className="small">Valid marine policies covering purchases; the default one is filled in</span>
          </label>
        )}
        {props.insuredBy === "us" && picked && (
          <label>
            Insured Value ₹
            <input readOnly value={money(value)} />
            <span className="small">{picked.plus_ten ? "Order total + 10%" : "Order total"}, worked out on Save</span>
          </label>
        )}
      </div>
      {warnings.map((w) => (
        <p key={w} className="error">
          {w}
        </p>
      ))}
    </Fold>
  );
}

/** The transit insurance of a saved order, or of the orders behind a goods receipt or a bill. */
export function TransitInsuranceView({ rows }: { rows: (OrderInsurance & { order?: string })[] }) {
  if (!rows.length) return null;
  return (
    <Fold title="Transit Insurance" open summary={rows.map((r) => (r.insured_by === "us" ? r.insurance_policy_label.split(" · ")[0] : `By ${r.insured_by_label.toLowerCase()}`)).join(", ")}>
      <dl className="kv">
        {rows.map((r, i) => (
          <div key={i}>
            <dt>{r.order ? `Order ${r.order}` : r.insured_by === "us" ? "Policy" : "Insured By"}</dt>
            <dd>
              {r.insured_by === "us"
                ? `${r.insurance_policy_label} · insured for ${rupees(r.insured_value)}`
                : r.order
                  ? `Insured by ${r.insured_by_label.toLowerCase()}`
                  : r.insured_by_label}
            </dd>
          </div>
        ))}
      </dl>
    </Fold>
  );
}

