import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, upload } from "./api";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { usePrintMenu } from "./Exchange";
import { ActiveButton } from "./RowActions";

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
  const printing = usePrintMenu({ title: "Central tables" });
  useEffect(() => {
    api<Info>("v1/central/").then(setInfo, (e) =>
      setError(String(e.message ?? e)),
    );
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!info) return <p>Loading…</p>;
  return (
    <section className="page">
      <PageHeader
        title="Central tables"
        sub="Kept once by MyERP for every customer. Customers can read these lists but not change them."
        actions={printing.buttons}
      />
      {printing.panel}
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
      <Couriers />
      <CourierRequests />
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

type Loaded = Record<string, number>;

/** Load the HSN list and a courier's PIN coverage from files. */
function LoadLists() {
  const [couriers, setCouriers] = useState<Courier[]>([]);
  const [carrier, setCarrier] = useState("");
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<{ what: string; text: string } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Courier[]>("v1/central/carriers/").then(setCouriers);
  }, []);
  const send = async (what: "hsn" | "pins", file: File | undefined) => {
    if (!file) return;
    setError("");
    setResult(null);
    if (what === "pins" && !carrier) {
      setError("Pick the courier the PIN file is from.");
      return;
    }
    setBusy(what);
    const form = new FormData();
    form.append("file", file);
    if (what === "pins") form.append("carrier", carrier);
    try {
      const done = await upload<Loaded>(`v1/central/import/${what}/`, form);
      setResult({
        what,
        text:
          what === "hsn"
            ? `${done.added} HSN codes added, ${done.updated} updated, ${done.unchanged} unchanged.`
            : `${done.pins_added} PIN codes added, ${done.state_filled} given a state; the courier now covers ${done.coverage} (replaced ${done.replaced}).`,
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <Section title="Load lists from a file">
      <div className="grid">
        <label>
          HSN and SAC codes
          <input
            type="file"
            accept=".csv,.tsv,.txt"
            disabled={busy !== ""}
            onChange={(e) => {
              send("hsn", e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <span className="small">
            A CSV or tab-separated file with the code in the first column and the description in the second. New codes are
            added and descriptions of existing ones refreshed.
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
            type="file"
            accept=".csv"
            disabled={busy !== ""}
            onChange={(e) => {
              send("pins", e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <span className="small">
            The courier's serviceability CSV (Pin, Facility City, Facility State, ODA…). PIN codes we lack are added and that
            courier's earlier coverage is replaced by the file's.
          </span>
        </label>
      </div>
      {busy && <p className="small">Loading… a large file can take a minute.</p>}
      {result && <p className="note">{result.text}</p>}
      {error && <p className="error">{error}</p>}
    </Section>
  );
}
