import { FormEvent, Fragment, useCallback, useEffect, useState } from "react";
import { creatable, type Creatable } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { api, type SignedIn } from "./api";
import { PageHeader, Section } from "./Brand";
import { usePrintMenu } from "./Exchange";
import { Combobox } from "./Combobox";
import { type Company, type Contact } from "./Companies";
import { useOnReturn, useReturns } from "./Refresh";

/** Couriers, transporters and shipments (spec 06, step 1). Statuses are
 * typed by hand until each courier's tracking API is connected. */

export type Carrier = {
  id: number;
  name: string;
  kind: string;
  kind_label: string;
  awb_hint: string;
  integration: string;
  credential_fields: { key: string; label: string; secret: boolean }[];
  is_active: boolean;
};

export type CourierAccount = Contact & {
  id: number;
  carrier_id: number | null;
  carrier_name: string;
  name: string;
  gstin: string;
  state_code: string;
  service: string;
  service_label: string;
  account_code: string;
  notes: string;
  credential_fields?: { key: string; label: string; secret: boolean; saved: boolean; value: string }[];
  is_active: boolean;
};

type TrackingEvent = {
  id: number;
  at: string;
  status: string;
  status_label: string;
  place: string;
  carrier_text: string;
  received_by: string;
  source: string;
  by: string;
};

type Shipment = {
  id: number;
  company: number;
  branch: number | null;
  account: number;
  account_name: string;
  carrier_name: string;
  awb: string;
  booked_on: string;
  party: number | null;
  party_name: string;
  reference: string;
  ship_to_city: string;
  ship_to_pincode: string;
  packages: number;
  weight_kg: string | null;
  payment: string;
  cod_amount: string | null;
  expected_on: string | null;
  notes: string;
  status: string;
  status_label: string;
  is_open: boolean;
  last_event_at: string | null;
  last_place: string;
  delivered_at: string | null;
  received_by: string;
  cancelled: boolean;
  cancel_reason: string;
  alerts: string[];
  tracking_link: string;
  days_out: number;
  events?: TrackingEvent[];
};

export const SERVICES: [string, string][] = [
  ["b2c", "B2C (parcel / express)"],
  ["b2b", "B2B (freight)"],
  ["aggregator", "Aggregator"],
];

const PAYMENTS: [string, string][] = [
  ["prepaid", "Prepaid"],
  ["to_pay", "To pay"],
  ["cod", "Cash on delivery"],
];

// The statuses a person can type, in the order a parcel usually goes.
const STATUSES: [string, string][] = [
  ["picked_up", "Picked up"],
  ["in_transit", "In transit"],
  ["out_for_delivery", "Out for delivery"],
  ["delivered", "Delivered"],
  ["delivery_failed", "Delivery failed"],
  ["held", "Held"],
  ["rto", "Returning to us (RTO)"],
  ["rto_delivered", "Returned to us"],
  ["lost", "Lost or damaged"],
  ["cancelled", "Booking cancelled"],
  ["booked", "Booked"],
];

const VIEWS: [string, string][] = [
  ["action", "Needs action"],
  ["open", "Open"],
  ["delivered", "Delivered"],
  ["all", "All"],
];

const when = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
const day = (iso: string | null) =>
  iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "";

/** A local date-time for <input type="datetime-local">, to the minute. */
function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function today(): string {
  return nowLocal().slice(0, 10);
}

export function useCarriers() {
  const [carriers, setCarriers] = useState<Carrier[]>([]);
  useEffect(() => {
    api<Carrier[]>("v1/carriers/").then(setCarriers);
  }, []);
  return carriers;
}

export function useCourierAccounts(companyId: number) {
  const [accounts, setAccounts] = useState<CourierAccount[]>([]);
  const refresh = useCallback(
    () =>
      api<CourierAccount[]>(`v1/companies/${companyId}/courier-accounts/`).then(
        setAccounts,
      ),
    [companyId],
  );
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { accounts, reload, refresh };
}

type Branch = { id: number; name: string };

function useCompanyDetail(companyId: number) {
  const [detail, setDetail] = useState<{
    company: Company;
    branches: Branch[];
  } | null>(null);
  useEffect(() => {
    api<{ company: Company; branches: Branch[] }>(
      `v1/companies/${companyId}/`,
    ).then(setDetail);
  }, [companyId]);
  return detail;
}

export function useCompany(companyId: number) {
  return useCompanyDetail(companyId)?.company ?? null;
}

export function NoSales({ company }: { company: Company }) {
  return (
    <section className="page">
      <PageHeader title="Shipments" sub={company.name} />
      <p className="card">
        {company.name} does not use the Sales module. An Owner can switch it on
        under "Admin", "Company", "Modules".
      </p>
    </section>
  );
}

// Shipments -------------------------------------------------------------------

type Party = { id: number; name: string };

/** Sales > Shipments: every AWB sent out, where it is now, and what needs action. */
export function ShipmentsPage({
  companyId,
  session,
}: {
  companyId: number;
  session: SignedIn;
}) {
  const canEnter = session.permissions.some(
    (p) => p === "sales.create" || p === "stock.create",
  );
  const canMasters = session.permissions.includes("masters.view");
  const company = useCompany(companyId);
  const { accounts, refresh: refreshAccounts } = useCourierAccounts(companyId);
  // "Create …" a transporter from the shipment form, for those who may add masters.
  const newAccount = session.permissions.includes("masters.edit")
    ? creatable(
        "courier_account",
        `companies/${companyId}/couriers`,
        refreshAccounts,
      )
    : undefined;
  const [view, setView] = useState("action");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Shipment[]>([]);
  const [open, setOpen] = useState<number | "new" | null>(null);
  const [stamp, setStamp] = useState(0);
  const reload = useCallback(() => {
    const params = new URLSearchParams({ view, q });
    api<Shipment[]>(`v1/companies/${companyId}/shipments/?${params}`).then(
      setRows,
    );
  }, [companyId, view, q]);
  useEffect(() => {
    const t = window.setTimeout(reload, q ? 250 : 0);
    return () => window.clearTimeout(t);
  }, [reload, q, stamp]);
  const viewLabel = VIEWS.find(([code]) => code === view)?.[1] ?? "";
  const printing = usePrintMenu({
    title: `Shipments: ${viewLabel}`,
    scope: [company?.name, q && `Search: ${q}`].filter(Boolean).join(" · "),
  });
  if (company && !company.modules.includes("sales"))
    return <NoSales company={company} />;
  const changed = () => setStamp((n) => n + 1);

  return (
    <section className="page">
      <PageHeader
        title="Shipments"
        sub={`${company?.name ?? ""}: every AWB sent out and where it is now.`}
        actions={
          <>
            {printing.buttons}
            {canMasters && (
              <a
                className="button secondary"
                href={`#/companies/${companyId}/couriers`}
              >
                Transporters
              </a>
            )}
            {canEnter && (
              <button onClick={() => setOpen("new")}>Add shipment</button>
            )}
          </>
        }
      >
        <nav className="tabs" aria-label="Shipment lists">
          {VIEWS.map(([code, label]) => (
            <a
              key={code}
              href={`#/companies/${companyId}/shipments`}
              className={view === code ? "active" : ""}
              aria-current={view === code ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                setView(code);
                setOpen(null);
              }}
            >
              {label}
            </a>
          ))}
        </nav>
      </PageHeader>
      {printing.panel}
      <>
        {open === "new" && (
          <ShipmentForm
            companyId={companyId}
            accounts={accounts}
            createAccount={newAccount}
            shipment={null}
            onDone={(s) => {
              setOpen(s.id);
              changed();
            }}
            onCancel={() => setOpen(null)}
          />
        )}
        {typeof open === "number" && (
          <ShipmentCard
            key={`${open}-${stamp}`}
            id={open}
            companyId={companyId}
            accounts={accounts}
            createAccount={newAccount}
            canEnter={canEnter}
            onChanged={changed}
            onClose={() => setOpen(null)}
          />
        )}
        {accounts.length === 0 && canEnter && (
          <p className="small">
            Add your transporters first (the "Transporters" button above), then
            add shipments against them.
          </p>
        )}
        <div className="row">
          <label>
            Search
            <input
              value={q}
              placeholder="AWB, customer, invoice, city or PIN"
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
        </div>
        {rows.length === 0 ? (
          <p className="small">
            {view === "action" ? "Nothing needs action." : "No shipments here."}
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Booked</th>
                <th>AWB and courier</th>
                <th>Customer and invoice</th>
                <th>To</th>
                <th>Status</th>
                <th>Last update</th>
                <th>Days out</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className={s.cancelled ? "off" : ""}>
                  <td style={{ whiteSpace: "nowrap" }}>{day(s.booked_on)}</td>
                  <td>
                    {s.tracking_link ? (
                      <a
                        href={s.tracking_link}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {s.awb}
                      </a>
                    ) : (
                      s.awb
                    )}
                    <div className="small">{s.account_name}</div>
                  </td>
                  <td>
                    {s.party_name}
                    {s.reference && <div className="small">{s.reference}</div>}
                  </td>
                  <td>
                    {[s.ship_to_city, s.ship_to_pincode]
                      .filter(Boolean)
                      .join(" ")}
                  </td>
                  <td>
                    {s.cancelled ? (
                      <span className="pill">Cancelled</span>
                    ) : s.alerts.includes(s.status_label) ? (
                      <span className="pill action-delete">
                        {s.status_label}
                      </span>
                    ) : (
                      s.status_label
                    )}
                    {s.alerts
                      .filter((a) => a !== s.status_label)
                      .map((a) => (
                        <span key={a} className="pill action-delete">
                          {a}
                        </span>
                      ))}
                  </td>
                  <td>
                    <span style={{ whiteSpace: "nowrap" }}>
                      {when(s.last_event_at)}
                    </span>
                    {s.last_place && (
                      <div className="small">{s.last_place}</div>
                    )}
                  </td>
                  <td>{s.is_open ? s.days_out : ""}</td>
                  <td className="act">
                    <button className="link" onClick={() => setOpen(s.id)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </>
    </section>
  );
}

function ShipmentForm(props: {
  companyId: number;
  accounts: CourierAccount[];
  createAccount?: Creatable;
  shipment: Shipment | null;
  onDone: (s: Shipment) => void;
  onCancel: () => void;
}) {
  const s = props.shipment;
  const [parties, setParties] = useState<Party[]>([]);
  const branches = useCompanyDetail(props.companyId)?.branches ?? [];
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  useEffect(() => {
    api<Party[]>("v1/parties/").then(setParties);
  }, [visits]);
  const [account, setAccount] = useState(s ? String(s.account) : "");
  const [awb, setAwb] = useState(s?.awb ?? "");
  const [bookedOn, setBookedOn] = useState(s?.booked_on ?? today());
  const [party, setParty] = useState(s?.party ? String(s.party) : "");
  const [branch, setBranch] = useState(s?.branch ? String(s.branch) : "");
  const [reference, setReference] = useState(s?.reference ?? "");
  const [city, setCity] = useState(s?.ship_to_city ?? "");
  const [pin, setPin] = useState(s?.ship_to_pincode ?? "");
  const [packages, setPackages] = useState(String(s?.packages ?? 1));
  const [weight, setWeight] = useState(s?.weight_kg ?? "");
  const [payment, setPayment] = useState(s?.payment ?? "prepaid");
  const [cod, setCod] = useState(s?.cod_amount ?? "");
  const [expected, setExpected] = useState(s?.expected_on ?? "");
  const [notes, setNotes] = useState(s?.notes ?? "");
  const [error, setError] = useState<unknown>("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = {
      account: Number(account),
      awb,
      booked_on: bookedOn,
      party: party ? Number(party) : null,
      branch: branch ? Number(branch) : null,
      reference,
      ship_to_city: city,
      ship_to_pincode: pin,
      packages: Number(packages) || 1,
      weight_kg: weight || null,
      payment,
      cod_amount: payment === "cod" ? cod || null : null,
      expected_on: expected || null,
      notes,
    };
    try {
      const saved = s
        ? await api<Shipment>(`v1/shipments/${s.id}/`, body, "PATCH")
        : await api<Shipment>(
            `v1/companies/${props.companyId}/shipments/`,
            body,
          );
      props.onDone(saved);
    } catch (err) {
      setError(err);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h4>{s ? `Edit shipment ${s.awb}` : "Add shipment"}</h4>
      <Section title="Courier">
        <div className="row">
          <label>
            Transporter
            <Combobox
              required
              value={account}
              onChange={setAccount}
              create={props.createAccount}
              empty="Pick an account"
              options={props.accounts
                .filter((a) => a.is_active || String(a.id) === account)
                .map((a) => ({
                  value: String(a.id),
                  label: a.name,
                  hint: a.carrier_name,
                }))}
            />
          </label>
          <label>
            AWB (tracking number)
            <input
              required
              autoFocus={!s}
              value={awb}
              onChange={(e) => setAwb(e.target.value)}
            />
          </label>
          <label>
            Booked on
            <input
              required
              type="date"
              value={bookedOn}
              onChange={(e) => setBookedOn(e.target.value)}
            />
          </label>
          <label>
            Expected delivery
            <input
              type="date"
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
            />
          </label>
        </div>
      </Section>
      <Section title="Sent to">
        <div className="row">
          <label>
            Customer
            <Combobox
              value={party}
              onChange={setParty}
              empty="None"
              options={parties.map((p) => ({
                value: String(p.id),
                label: p.name,
              }))}
            />
          </label>
          <label>
            Invoice or delivery note number
            <input
              value={reference}
              placeholder="e.g. the ERPNext invoice number"
              onChange={(e) => setReference(e.target.value)}
            />
          </label>
        </div>
        <div className="row">
          <label>
            City
            <input value={city} onChange={(e) => setCity(e.target.value)} />
          </label>
          <label>
            PIN code
            <input
              value={pin}
              inputMode="numeric"
              maxLength={6}
              onChange={(e) => setPin(e.target.value)}
            />
          </label>
          <label>
            Sent from branch
            <Combobox
              value={branch}
              onChange={setBranch}
              empty="Not given"
              options={branches.map((b) => ({
                value: String(b.id),
                label: b.name,
              }))}
            />
          </label>
        </div>
      </Section>
      <Section title="Parcel">
        <div className="row">
          <label>
            Packages
            <input
              type="number"
              min={1}
              value={packages}
              onChange={(e) => setPackages(e.target.value)}
            />
          </label>
          <label>
            Weight (kg)
            <input
              type="number"
              min={0}
              step="0.001"
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
            />
          </label>
          <label>
            Payment
            <Combobox
              value={payment}
              onChange={setPayment}
              options={PAYMENTS.map(([value, label]) => ({ value, label }))}
            />
          </label>
          {payment === "cod" && (
            <label>
              Amount to collect (₹)
              <input
                required
                type="number"
                min={0}
                step="0.01"
                value={cod}
                onChange={(e) => setCod(e.target.value)}
              />
            </label>
          )}
        </div>
        <label>
          Notes
          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
      </Section>
      <ErrorNote error={error} />
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** One shipment: its details, its status history and "Add status". */
function ShipmentCard(props: {
  id: number;
  companyId: number;
  accounts: CourierAccount[];
  createAccount?: Creatable;
  canEnter: boolean;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [s, setS] = useState<Shipment | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    api<Shipment>(`v1/shipments/${props.id}/`).then(setS);
  }, [props.id]);
  if (!s) return null;
  const canChange = props.canEnter && !s.cancelled;

  if (editing)
    return (
      <ShipmentForm
        companyId={props.companyId}
        accounts={props.accounts}
        createAccount={props.createAccount}
        shipment={s}
        onDone={() => {
          setEditing(false);
          props.onChanged();
        }}
        onCancel={() => setEditing(false)}
      />
    );

  const cancel = async () => {
    const reason = window.prompt(
      `Cancel shipment ${s.awb}? Say why (for example "wrong AWB typed").`,
    );
    if (!reason) return;
    setError("");
    try {
      await api(`v1/shipments/${s.id}/cancel/`, { reason });
      props.onChanged();
    } catch (err) {
      setError(err);
    }
  };

  const facts: [string, string][] = [
    [
      "Courier",
      s.carrier_name ? `${s.account_name} (${s.carrier_name})` : s.account_name,
    ],
    ["Booked on", day(s.booked_on)],
    ["Expected delivery", day(s.expected_on)],
    ["Customer", s.party_name],
    ["Invoice / reference", s.reference],
    ["To", [s.ship_to_city, s.ship_to_pincode].filter(Boolean).join(" ")],
    ["Packages", String(s.packages)],
    ["Weight (kg)", s.weight_kg ? String(Number(s.weight_kg)) : ""],
    [
      "Payment",
      (PAYMENTS.find(([v]) => v === s.payment)?.[1] ?? s.payment) +
        (s.cod_amount ? ` ₹${s.cod_amount}` : ""),
    ],
    [
      "Delivered",
      s.delivered_at
        ? `${when(s.delivered_at)}${s.received_by ? `, received by ${s.received_by}` : ""}`
        : "",
    ],
    ["Notes", s.notes],
  ];

  return (
    <div className="card">
      <h4>
        Shipment {s.awb}{" "}
        <span
          className={`pill${!s.cancelled && s.alerts.includes(s.status_label) ? " action-delete" : ""}`}
        >
          {s.cancelled ? "Cancelled" : s.status_label}
        </span>
        {s.alerts
          .filter((a) => a !== s.status_label)
          .map((a) => (
            <span key={a} className="pill action-delete">
              {a}
            </span>
          ))}
      </h4>
      {s.cancelled && <p className="small">Cancelled: {s.cancel_reason}</p>}
      <dl className="facts">
        {facts
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <Fragment key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </Fragment>
          ))}
      </dl>
      {s.tracking_link && (
        <p>
          <a href={s.tracking_link} target="_blank" rel="noreferrer">
            Track on {s.carrier_name}'s website
          </a>
        </p>
      )}
      <Section title="Status history">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Status</th>
              <th>Place</th>
              <th>Remarks</th>
              <th>Entered by</th>
            </tr>
          </thead>
          <tbody>
            {[...(s.events ?? [])].reverse().map((e) => (
              <tr key={e.id}>
                <td>{when(e.at)}</td>
                <td>{e.status_label}</td>
                <td>{e.place}</td>
                <td>
                  {e.carrier_text}
                  {e.received_by && ` Received by ${e.received_by}.`}
                </td>
                <td>{e.source === "Typed" ? e.by : e.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      {canChange && <AddStatus shipment={s} onDone={props.onChanged} />}
      <ErrorNote error={error} />
      <div className="buttons">
        {canChange && (
          <button
            type="button"
            className="secondary"
            onClick={() => setEditing(true)}
          >
            Edit details
          </button>
        )}
        <button type="button" className="link" onClick={props.onClose}>
          Close
        </button>
        {canChange && (
          <button type="button" className="link danger" onClick={cancel}>
            Cancel shipment
          </button>
        )}
      </div>
    </div>
  );
}

function AddStatus({
  shipment,
  onDone,
}: {
  shipment: Shipment;
  onDone: () => void;
}) {
  const [status, setStatus] = useState("");
  const [at, setAt] = useState(nowLocal);
  const [place, setPlace] = useState("");
  const [remarks, setRemarks] = useState("");
  const [receivedBy, setReceivedBy] = useState("");
  const [error, setError] = useState<unknown>("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api(`v1/shipments/${shipment.id}/events/`, {
        status,
        at: new Date(at).toISOString(),
        place,
        carrier_text: remarks,
        received_by: status === "delivered" ? receivedBy : "",
      });
      onDone();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <form onSubmit={save}>
      <Section title="Add status">
        <div className="row">
          <label>
            Status
            <Combobox
              required
              value={status}
              onChange={setStatus}
              empty="Pick a status"
              options={STATUSES.map(([value, label]) => ({ value, label }))}
            />
          </label>
          <label>
            When
            <input
              required
              type="datetime-local"
              value={at}
              onChange={(e) => setAt(e.target.value)}
            />
          </label>
          <label>
            Place
            <input
              value={place}
              placeholder="e.g. Delhi hub"
              onChange={(e) => setPlace(e.target.value)}
            />
          </label>
          {status === "delivered" && (
            <label>
              Received by
              <input
                value={receivedBy}
                onChange={(e) => setReceivedBy(e.target.value)}
              />
            </label>
          )}
        </div>
        <label>
          Remarks
          <input
            value={remarks}
            placeholder="What the courier's website says"
            onChange={(e) => setRemarks(e.target.value)}
          />
        </label>
        <ErrorNote error={error} />
        <div className="buttons">
          <button>Save</button>
        </div>
      </Section>
    </form>
  );
}
