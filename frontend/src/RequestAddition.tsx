import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { hashParam, openTab } from "./Master";

/** A request to add an entry to a central list, sent to the MyERP team (Sidharth, 2026-11-14). */
export type AdditionRequest = {
  id: number;
  kind: Kind;
  kind_label: string;
  entry: string;
  description: string;
  note: string;
  requested_by: string;
  status: "open" | "added" | "declined";
  status_label: string;
  city: string;
  state_code: string;
  created_at: string;
  seen: boolean;
};

export type Kind = "hsn" | "gst_rate" | "country" | "pin";

export const REQUEST_LISTS = [
  { value: "hsn", label: "HSN or SAC code" },
  { value: "gst_rate", label: "GST rate" },
  { value: "country", label: "Country" },
  { value: "pin", label: "PIN code" },
];

/** Opens the "Request Addition" screen in a new tab, the list (and a typed entry) filled in. */
export function openRequestAddition(kind: Kind, entry = "") {
  openTab(`#/request-addition?kind=${kind}${entry ? `&entry=${encodeURIComponent(entry)}` : ""}`);
}

/** "Not in the list? Request Addition" link for a dropdown that picks from a central list. */
export function RequestAdditionLink(props: { kind: Kind; label?: string }) {
  return (
    <button type="button" className="link" onClick={() => openRequestAddition(props.kind)}>
      {props.label ?? "Not in the list? Request Addition"}
    </button>
  );
}

const ENTRY_LABEL: Record<string, string> = {
  hsn: "HSN Or SAC Code",
  gst_rate: "GST Rate (%)",
  country: "Country Name",
  pin: "PIN Code",
};

const day = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });

/** The screen opened by every "Request Addition" button. */
export function RequestAdditionPage() {
  const asked = hashParam("kind");
  const [kind, setKind] = useState<string>(REQUEST_LISTS.some((l) => l.value === asked) ? asked! : "hsn");
  const [entry, setEntry] = useState(hashParam("entry") ?? "");
  const [description, setDescription] = useState("");
  const [note, setNote] = useState("");
  const [city, setCity] = useState("");
  const [stateCode, setStateCode] = useState("");
  const [states, setStates] = useState<{ value: string; label: string }[]>([]);
  useEffect(() => {
    api<{ code: string; name: string }[]>("v1/states/").then(
      (rows) => setStates(rows.map((r) => ({ value: r.code, label: r.name }))),
      () => setStates([]),
    );
  }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [sent, setSent] = useState("");
  const [mine, setMine] = useState<AdditionRequest[]>([]);
  const load = () => api<AdditionRequest[]>("v1/central-requests/").then(setMine, () => setMine([]));
  useEffect(() => {
    load();
  }, []);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSent("");
    try {
      const made = await api<AdditionRequest>("v1/central-requests/", { kind, entry, description, note, city, state_code: stateCode });
      setSent(made.entry);
      setEntry("");
      setDescription("");
      setNote("");
      setCity("");
      setStateCode("");
      load();
    } catch (err) {
      setError(err);
    }
    setBusy(false);
  };

  return (
    <section className="page item-edit">
      <PageHeader
        title="Request Addition"
        sub="Ask the MyERP team to add to a central list."
        actions={
          <>
            <button type="button" className="link" onClick={() => closeThisTab(() => (window.location.hash = "#/"))}>
              Close
            </button>
            <button type="submit" form="request-form" disabled={busy}>
              Send Request
            </button>
          </>
        }
      />
      <form id="request-form" className="side-layout" onSubmit={send}>
        <div className="side-main">
          <Section title="Request">
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <label>
                <span className="req">List</span>
                <Combobox options={REQUEST_LISTS} value={kind} onChange={(v) => v && setKind(v)} ariaLabel="List" />
              </label>
              <label>
                <span className="req">{ENTRY_LABEL[kind]}</span>
                <input required value={entry} onChange={(e) => setEntry(e.target.value)} />
              </label>
              {(kind === "hsn" || kind === "country") && (
                <label>
                  <span className="req">{kind === "hsn" ? "Description" : "2-Letter Country Code"}</span>
                  <input
                    required
                    maxLength={kind === "hsn" ? 500 : 2}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </label>
              )}
              {kind === "pin" && (
                <>
                  <label>
                    <span className="req">City</span>
                    <input required value={city} onChange={(e) => setCity(e.target.value)} />
                  </label>
                  <label>
                    <span className="req">State</span>
                    <Combobox options={states} value={stateCode} onChange={setStateCode} required ariaLabel="State" />
                  </label>
                </>
              )}
              <label>
                Note For The MyERP Team
                <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
            </div>
          </Section>
          <ErrorNote error={error} />
          {sent && (
            <p className="small">
              Request for {sent} sent. You will see the decision under "My requests" below and on your Dashboard.
            </p>
          )}
          <Section title="My Requests">
            {mine.length === 0 ? (
              <p className="small">You have not sent any request yet.</p>
            ) : (
              <table className="pick">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>List</th>
                    <th>Entry</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {mine.map((r) => (
                    <tr key={r.id}>
                      <td>{day(r.created_at)}</td>
                      <td>{r.kind_label}</td>
                      <td>
                        {r.entry}
                        {r.description ? ` · ${r.description}` : ""}
                        {r.city ? ` · ${r.city}` : ""}
                      </td>
                      <td>{r.status_label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>
        </div>
      </form>
    </section>
  );
}
