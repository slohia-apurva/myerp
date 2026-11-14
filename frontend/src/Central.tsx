import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, upload, uploadForFile } from "./api";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu } from "./Exchange";
import { ActiveButton } from "./RowActions";
import type { AdditionRequest } from "./RequestAddition";

type Info = {
  tables: {
    key: string;
    label: string;
    about: string;
    count: number;
    open: string;
  }[];
  tenants: { slug: string; name: string; status: string; created: string }[];
};

/** Central: for MyERP platform admins. The tables kept once for every customer, and the customers. */
export function CentralPage() {
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"customers" | "lists" | "gst" | "couriers" | "requests">("customers");
  const printing = usePrintMenu({ title: "Central tables" });
  const reload = useCallback(
    () =>
      api<Info>("v1/central/").then(setInfo, (e) =>
        setError(String(e.message ?? e)),
      ),
    [],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  if (error) return <p className="error">{error}</p>;
  if (!info) return <p>Loading…</p>;
  return (
    <section className="page">
      <PageHeader
        title="Central"
        sub="For the MyERP owner: the customers, and the lists kept once for every customer."
        actions={printing.buttons}
      />
      {printing.panel}
      <div className="form-tabs" role="tablist">
        {(
          [
            ["customers", "Customers"],
            ["lists", "Shared lists"],
            ["gst", "GST Rates"],
            ["couriers", "Couriers"],
            ["requests", "Requests"],
          ] as const
        ).map(([code, label]) => (
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
      {tab === "customers" && (
        <>
      <Section title="Customers">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Short name</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {info.tenants.map((t) => (
              <tr key={t.slug}>
                <td>{t.name}</td>
                <td>{t.slug}</td>
                <td>{t.status}</td>
                <td>{t.created}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
          <NewCustomer onDone={reload} />
        </>
      )}
      {tab === "lists" && (
        <>
      <Section title="Central tables">
        <table>
          <thead>
            <tr>
              <th>Table</th>
              <th>What it is for</th>
              <th>Rows</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {info.tables.map((t) => (
              <tr key={t.key}>
                <td>{t.label}</td>
                <td>{t.about}</td>
                <td>{t.count}</td>
                <td>{t.open && <a href={t.open}>Open</a>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
          <LoadLists />
        </>
      )}
      {tab === "gst" && <GstRates />}
      {tab === "requests" && <AdditionRequests />}
      {tab === "couriers" && (
        <>
      <Couriers />
      <CourierRequests />
        </>
      )}
    </section>
  );
}

type Courier = {
  id: number;
  name: string;
  kind: string;
  awb_pattern: string;
  awb_hint: string;
  tracking_url: string;
  is_active: boolean;
};

const KINDS: [string, string][] = [
  ["courier", "Courier"],
  ["aggregator", "Aggregator (books with many couriers)"],
  ["airline", "Airline or air cargo"],
  ["transporter", "Road transporter"],
];

/** The couriers every customer can pick on a transporter: only platform admins add to it. */
function Couriers() {
  const [rows, setRows] = useState<Courier[]>([]);
  const [editing, setEditing] = useState<Courier | "new" | null>(null);
  const load = useCallback(
    () => api<Courier[]>("v1/central/carriers/").then(setRows),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);
  const done = () => {
    setEditing(null);
    load();
  };
  return (
    <Section title="Couriers">
      <div className="page-head">
        <p className="small">
          Every customer picks from this list when adding a transporter. Add a
          courier here once MyERP can look it up: its tracking page, tracking
          number format and, later, its API.
        </p>
        {!editing && (
          <button
            type="button"
            className="secondary"
            onClick={() => setEditing("new")}
          >
            Add courier
          </button>
        )}
      </div>
      {editing && (
        <CourierForm
          key={editing === "new" ? "new" : editing.id}
          courier={editing === "new" ? null : editing}
          onDone={done}
          onCancel={() => setEditing(null)}
        />
      )}
      <table>
        <thead>
          <tr>
            <th>Courier</th>
            <th>Kind</th>
            <th>Tracking number</th>
            <th>Tracking page</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} className={c.is_active ? "" : "off"}>
              <td>
                {c.name}
                {!c.is_active && <span className="pill">Disabled</span>}
              </td>
              <td>{KINDS.find(([k]) => k === c.kind)?.[1]}</td>
              <td>{c.awb_hint}</td>
              <td>
                {c.tracking_url && (
                  <span className="small">{c.tracking_url}</span>
                )}
              </td>
              <td className="row-actions">
                <button
                  type="button"
                  className="link"
                  onClick={() => setEditing(c)}
                >
                  Edit
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

type CentralGstRate = { id: number; rate: string; label: string; is_active: boolean };

/** The GST rates every customer's items pick from: only platform admins add to it. */
function GstRates() {
  const [rows, setRows] = useState<CentralGstRate[]>([]);
  const [rate, setRate] = useState("");
  const [error, setError] = useState<unknown>("");
  const load = useCallback(() => api<CentralGstRate[]>("v1/central/gst-rates/").then(setRows), []);
  useEffect(() => {
    load();
  }, [load]);
  const add = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api("v1/central/gst-rates/", { rate: rate.trim() });
      setRate("");
      load();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Section title="GST Rates">
      <p className="small">
        The rates an item's GST rate is chosen from. A disabled rate is no longer offered for new entries; items that already
        use it keep it. Rates are never deleted.
      </p>
      <form onSubmit={add} className="row" style={{ alignItems: "flex-end" }}>
        <label>
          <span className="req">GST Rate (%)</span>
          <input required className="num" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} />
        </label>
        <button>Add rate</button>
      </form>
      <ErrorNote error={error} />
      <table>
        <thead>
          <tr>
            <th>Rate</th>
            <th className="num">GST %</th>
            <th className="num">CGST %</th>
            <th className="num">SGST %</th>
            <th className="num">IGST %</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const n = Number(r.rate);
            return (
              <tr key={r.id} className={r.is_active ? "" : "off"}>
                <td>{r.label}</td>
                <td className="num">{n}</td>
                <td className="num">{n / 2}</td>
                <td className="num">{n / 2}</td>
                <td className="num">{n}</td>
                <td>{r.is_active ? <span className="pill on">Active</span> : <span className="pill">Disabled</span>}</td>
                <td className="row-actions">
                  <ActiveButton
                    url={`v1/central/gst-rates/${r.id}/`}
                    active={r.is_active}
                    what={r.label}
                    onDone={load}
                    onError={setError}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Section>
  );
}

type CourierRequest = {
  id: number;
  customer: string;
  name: string;
  gstin: string;
  note: string;
  requested_by: string;
  status: string;
  created_at: string;
};

/** Transporters that customers saved with "Not in the list", for the team to add as couriers. */
function CourierRequests() {
  const [rows, setRows] = useState<CourierRequest[]>([]);
  const [error, setError] = useState<unknown>("");
  const load = useCallback(
    () => api<CourierRequest[]>("v1/central/carrier-requests/").then(setRows),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);
  const set = async (r: CourierRequest, status: string) => {
    setError("");
    try {
      await api(`v1/central/carrier-requests/${r.id}/`, { status }, "PATCH");
      load();
    } catch (err) {
      setError(err);
    }
  };
  const label: Record<string, string> = {
    open: "Open",
    added: "Added to the list",
    declined: "Not needed",
  };
  return (
    <Section title="Courier requests">
      <p className="small">
        Transporters that customers saved with "Not in the list". Add the
        courier above if MyERP can look it up, then mark the request as added.
      </p>
      <table>
        <thead>
          <tr>
            <th>Transporter</th>
            <th>GSTIN</th>
            <th>Customer</th>
            <th>Note</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={r.status === "open" ? "" : "off"}>
              <td>{r.name}</td>
              <td>{r.gstin}</td>
              <td>
                {r.customer}
                <div className="small">{r.requested_by}</div>
              </td>
              <td>{r.note}</td>
              <td>{label[r.status] ?? r.status}</td>
              <td className="row-actions">
                {r.status === "open" ? (
                  <>
                    <button
                      type="button"
                      className="link"
                      onClick={() => set(r, "added")}
                    >
                      Mark as added
                    </button>
                    <button
                      type="button"
                      className="link"
                      onClick={() => set(r, "declined")}
                    >
                      Not needed
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="link"
                    onClick={() => set(r, "open")}
                  >
                    Reopen
                  </button>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6} className="small">
                No requests.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <ErrorNote error={error} />
    </Section>
  );
}

function CourierForm(props: {
  courier: Courier | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const c = props.courier;
  const [name, setName] = useState(c?.name ?? "");
  const [kind, setKind] = useState(c?.kind ?? "courier");
  const [hint, setHint] = useState(c?.awb_hint ?? "");
  const [pattern, setPattern] = useState(c?.awb_pattern ?? "");
  const [url, setUrl] = useState(c?.tracking_url ?? "");
  const [error, setError] = useState<unknown>("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = {
      name,
      kind,
      awb_hint: hint,
      awb_pattern: pattern,
      tracking_url: url,
    };
    try {
      if (c) await api(`v1/central/carriers/${c.id}/`, body, "PATCH");
      else await api("v1/central/carriers/", body);
      props.onDone();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <form className="card" onSubmit={save}>
      <h4>{c ? `Edit ${c.name}` : "Add courier"}</h4>
      <Section title="Courier">
        <div className="row">
          <label>
            Name
            <input
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            Kind
            <Combobox
              value={kind}
              onChange={setKind}
              options={KINDS.map(([value, label]) => ({ value, label }))}
            />
          </label>
        </div>
        <div className="row">
          <label>
            Tracking number looks like (words, for people)
            <input
              value={hint}
              placeholder="e.g. 11 digits"
              onChange={(e) => setHint(e.target.value)}
            />
          </label>
          <label>
            Tracking number pattern (optional, a regular expression)
            <input
              value={pattern}
              placeholder="e.g. \d{11}"
              onChange={(e) => setPattern(e.target.value)}
            />
          </label>
        </div>
        <label>
          Tracking page (with {"{awb}"} where the number goes)
          <input
            value={url}
            placeholder="https://courier.example/track?awb={awb}"
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
      </Section>
      <ErrorNote error={error} />
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {c && (
          <ActiveButton
            url={`v1/central/carriers/${c.id}/`}
            active={c.is_active}
            what={`the courier ${c.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}

type Checked = {
  added?: number;
  updated?: number;
  unchanged?: number;
  problems?: string[];
  repeated?: string[];
  pins_added?: number;
  state_filled?: number;
  coverage?: number;
  replaced?: number;
  courier?: string;
  saved: boolean;
};

type Picked = { what: "hsn" | "pins"; file: File; carrier: string };

/** The pop-up for loading a list: check the file, show everything found at once, then load it. */
function LoadDialog(props: { picked: Picked; onClose: () => void }) {
  const { what, file, carrier } = props.picked;
  const [stage, setStage] = useState<"checking" | "report" | "loading" | "done" | "error">("checking");
  const [report, setReport] = useState<Checked | null>(null);
  const [error, setError] = useState("");
  const send = useCallback(
    async (commit: boolean) => {
      const form = new FormData();
      form.append("file", file);
      form.append("commit", commit ? "1" : "0");
      if (what === "pins") form.append("carrier", carrier);
      return upload<Checked>(`v1/central/import/${what}/`, form);
    },
    [file, what, carrier],
  );
  useEffect(() => {
    let live = true;
    send(false).then(
      (r) => {
        if (!live) return;
        setReport(r);
        setStage("report");
      },
      (e) => {
        if (!live) return;
        setError(String(e.message ?? e));
        setStage("error");
      },
    );
    return () => {
      live = false;
    };
  }, [send]);
  const load = async () => {
    setStage("loading");
    try {
      setReport(await send(true));
      setStage("done");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setStage("error");
    }
  };
  const problems = report?.problems ?? [];
  const leftOut = async () => {
    const form = new FormData();
    form.append("file", file);
    form.append("download", "1");
    if (what === "pins") form.append("carrier", carrier);
    try {
      await uploadForFile(
        `v1/central/import/${what}/`,
        form,
        what === "hsn" ? "hsn-left-out.xlsx" : "pins-left-out.xlsx",
      );
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  };
  const summary = report
    ? what === "hsn"
      ? `${report.added} new, ${report.updated} changed and ${report.unchanged} already in the list.`
      : `${report.pins_added} new PIN codes, ${report.state_filled} given a state. ${report.courier} will cover ${report.coverage} PIN codes (${report.replaced} earlier ones replaced).`
    : "";
  return (
    <div className="popup-back" role="presentation">
      <div className="popup" role="dialog" aria-modal="true" aria-label="Load a list">
        <h3>{what === "hsn" ? "HSN and SAC codes" : "PIN codes and courier coverage"}</h3>
        <p className="small">{file.name}</p>
        {(stage === "checking" || stage === "loading") && (
          <div className="popup-wait" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <span>
              {stage === "checking"
                ? "Checking the file… a large file can take up to a minute."
                : "Loading… please keep this window open."}
            </span>
          </div>
        )}
        {stage === "report" && report && (
          <>
            <p>
              <b>File checked.</b> {summary}
            </p>
            {(report.repeated?.length ?? 0) > 0 && (
              <p className="small">
                Codes that appear more than once (the last one is used): {report.repeated!.slice(0, 20).join(", ")}
                {report.repeated!.length > 20 ? " …" : ""}
              </p>
            )}
            {problems.length > 0 ? (
              <>
                <p className="error">
                  {problems.length} {problems.length === 1 ? "row has" : "rows have"} a problem and will be left out:
                </p>
                <ul className="popup-list">
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="note">No problems found.</p>
            )}
            {error && <p className="error">{error}</p>}
            <div className="buttons">
              <button type="button" onClick={load}>
                {problems.length > 0 ? "Load the rest" : "Load"}
              </button>
              {problems.length > 0 && (
                <button type="button" className="secondary" onClick={leftOut}>
                  Download the left-out rows (Excel)
                </button>
              )}
              <button type="button" className="secondary" onClick={props.onClose}>
                Cancel
              </button>
            </div>
          </>
        )}
        {stage === "done" && report && (
          <>
            <p className="note">
              <b>Loaded.</b> {summary}
            </p>
            {problems.length > 0 && (
              <p className="small">
                {problems.length} rows were left out. Download them, correct them and load the file again.
              </p>
            )}
            {error && <p className="error">{error}</p>}
            <div className="buttons">
              <button type="button" onClick={props.onClose}>
                Close
              </button>
              {problems.length > 0 && (
                <button type="button" className="secondary" onClick={leftOut}>
                  Download the left-out rows (Excel)
                </button>
              )}
            </div>
          </>
        )}
        {stage === "error" && (
          <>
            <p className="error">{error}</p>
            <p className="small">Nothing was loaded.</p>
            <div className="buttons">
              <button type="button" onClick={props.onClose}>
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** Load the HSN list and a courier's PIN coverage from files. */
function LoadLists() {
  const [couriers, setCouriers] = useState<Courier[]>([]);
  const [carrier, setCarrier] = useState("");
  const [picked, setPicked] = useState<Picked | null>(null);
  const [error, setError] = useState("");
  const [shown, setShown] = useState(0);
  useEffect(() => {
    api<Courier[]>("v1/central/carriers/").then(setCouriers);
  }, []);
  const choose = (what: "hsn" | "pins", file: File | undefined) => {
    if (!file) return;
    setError("");
    if (what === "pins" && !carrier) {
      setError("Pick the courier the PIN file is from.");
      return;
    }
    setPicked({ what, file, carrier });
  };
  return (
    <Section title="Load lists from a file">
      <div className="grid">
        <label>
          HSN and SAC codes
          <input
            key={`hsn${shown}`}
            type="file"
            accept=".csv,.tsv,.txt,.xlsx"
            onChange={(e) => choose("hsn", e.target.files?.[0])}
          />
          <span className="small">
            An Excel, CSV or tab-separated file with the code in the first column and the description in the second (every sheet
            of an Excel file is read). New codes are added and descriptions of existing ones refreshed.
          </span>
        </label>
        <label>
          PIN codes and a courier's coverage
          <Combobox
            value={carrier}
            empty="Pick the courier"
            placeholder="Type to search couriers…"
            options={couriers.filter((c) => c.is_active).map((c) => ({ value: String(c.id), label: c.name }))}
            onChange={setCarrier}
          />
          <input
            key={`pins${shown}`}
            type="file"
            accept=".csv"
            onChange={(e) => choose("pins", e.target.files?.[0])}
          />
          <span className="small">
            The courier's serviceability CSV (Pin, Facility City, Facility State, ODA…). PIN codes we lack are added and that
            courier's earlier coverage is replaced by the file's.
          </span>
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      {picked && (
        <LoadDialog
          picked={picked}
          onClose={() => {
            setPicked(null);
            setShown((n) => n + 1);
          }}
        />
      )}
    </Section>
  );
}

/** Add a customer (tenant) with its first Owner. */
function NewCustomer(props: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [email, setEmail] = useState("");
  const [person, setPerson] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>("");
  const [done, setDone] = useState("");
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("v1/central/tenants/", { name, slug, owner_email: email, owner_name: person });
      setDone(`${name} is ready. ${email} can sign in with Google at ${slug}.`);
      setOpen(false);
      setName("");
      setSlug("");
      setEmail("");
      setPerson("");
      props.onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Section title="Add customer">
      {done && <p className="note">{done}</p>}
      {!open ? (
        <button type="button" className="secondary" onClick={() => setOpen(true)}>
          Add customer
        </button>
      ) : (
        <form onSubmit={save}>
          <p className="small">
            Creates the customer's own database and its first Owner. This can take half a minute.
          </p>
          <div className="grid">
            <label>
              Customer name
              <input required value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
              Short name (web address)
              <input
                required
                maxLength={40}
                value={slug}
                placeholder="apurvam"
                onChange={(e) => setSlug(e.target.value.toLowerCase())}
              />
            </label>
            <label>
              Owner's sign-in email
              <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
              Owner's name
              <input value={person} onChange={(e) => setPerson(e.target.value)} />
            </label>
          </div>
          <ErrorNote error={error} />
          <div className="buttons">
            <button disabled={busy}>{busy ? "Creating…" : "Save"}</button>
            <button type="button" className="secondary" disabled={busy} onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </Section>
  );
}

type OwnerRequest = AdditionRequest & { customer: string };

/** Additions customers asked for from a "Request Addition" screen. "Approve & Add" puts the
 * entry in its list and tells the customer; "Not needed" tells them it was declined. */
function AdditionRequests() {
  const [rows, setRows] = useState<OwnerRequest[]>([]);
  const [error, setError] = useState<unknown>("");
  const load = useCallback(() => api<OwnerRequest[]>("v1/central/requests/").then(setRows), []);
  useEffect(() => {
    load();
  }, [load]);
  const set = async (r: OwnerRequest, status: string) => {
    setError("");
    try {
      await api(`v1/central/requests/${r.id}/`, { status }, "PATCH");
      load();
    } catch (err) {
      setError(err);
    }
  };
  const day = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  return (
    <Section title="Requests">
      <p className="small">
        Entries customers asked for in the HSN, GST rate, country or PIN code lists. "Approve &amp; Add" puts the entry in the list for every
        company and shows the customer a notice; "Not needed" shows them that it was declined.
      </p>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Customer</th>
            <th>List</th>
            <th>Entry</th>
            <th>Note</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={r.status === "open" ? "" : "off"}>
              <td>{day(r.created_at)}</td>
              <td>
                {r.customer}
                <div className="small">{r.requested_by}</div>
              </td>
              <td>{r.kind_label}</td>
              <td>
                {r.entry}
                {(r.description || r.city) && <div className="small">{[r.description, r.city, r.state_code && `state ${r.state_code}`].filter(Boolean).join(" · ")}</div>}
              </td>
              <td>{r.note}</td>
              <td>{r.status_label}</td>
              <td className="row-actions">
                {r.status === "open" ? (
                  <>
                    <button type="button" onClick={() => set(r, "added")}>
                      Approve &amp; Add
                    </button>
                    <button type="button" className="link danger" onClick={() => set(r, "declined")}>
                      Not needed
                    </button>
                  </>
                ) : (
                  <button type="button" className="link" onClick={() => set(r, "open")}>
                    Reopen
                  </button>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7}>No requests yet.</td>
            </tr>
          )}
        </tbody>
      </table>
      <ErrorNote error={error} />
    </Section>
  );
}
