import { FormEvent, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";

type Info = {
  allowed: boolean;
  levels: { value: string; label: string }[];
  companies: { id: number; name: string }[];
  all_phrase: string;
  preview?: { label: string; count: number }[];
};
type Done = { removed: { label: string; count: number }[]; filename: string; backup: unknown };

/** Admin > Reset data: Owner only. Clears a company, or the whole group, back to a clean start. */
export function DataResetPage(_props: { session: SignedIn }) {
  const [info, setInfo] = useState<Info | null>(null);
  const [level, setLevel] = useState("masters");
  const [company, setCompany] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Done | null>(null);

  useEffect(() => {
    const q = level === "all" || company ? `?level=${level}${level === "all" ? "" : `&company=${company}`}` : "";
    api<Info>(`v1/admin/reset/${q}`).then(setInfo);
  }, [level, company, done]);

  if (!info) return <p>Loading…</p>;
  const whole = level === "all";
  const target = whole ? info.all_phrase : (info.companies.find((c) => String(c.id) === company)?.name ?? "");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!window.confirm("Clear this data? This cannot be undone except from the backup file.")) return;
    setBusy(true);
    try {
      const r = await api<Done & { backup: unknown }>("v1/admin/reset/", {
        level,
        company: whole ? null : Number(company),
        confirm,
      });
      // Save the backup file first, so a closed tab cannot lose it.
      const blob = new Blob([JSON.stringify(r.backup)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = r.filename;
      a.click();
      URL.revokeObjectURL(a.href);
      setDone(r);
      setConfirm("");
    } catch (err) {
      setError((err as Error).message);
    }
    setBusy(false);
  };

  return (
    <section className="page">
      <PageHeader
        title="Reset data"
        sub="Owners only. Clear a company, or the whole group, back to a clean start. For staging and trial runs, not live books."
      />
      {!info.allowed && (
        <p className="error">
          Resetting data is switched off here, so nothing can be cleared on this system.
        </p>
      )}
      {done && (
        <div className="card">
          <h4>Done</h4>
          <p>
            Removed:{" "}
            {done.removed
              .filter((r) => r.count)
              .map((r) => `${r.count} ${r.label.toLowerCase()}`)
              .join(", ") || "nothing"}
            .
          </p>
          <p className="small">A backup file ({done.filename}) was saved to your downloads. Keep it safe.</p>
        </div>
      )}
      <form className="card" onSubmit={save}>
        <FormFields
          info={info}
          level={level}
          setLevel={setLevel}
          company={company}
          setCompany={setCompany}
          whole={whole}
          target={target}
          confirm={confirm}
          setConfirm={setConfirm}
        />
        {error && <p className="error">{error}</p>}
        <div className="buttons">
          <button className="link danger" disabled={busy || !info.allowed || confirm.trim() !== target || !target}>
            Reset data
          </button>
        </div>
      </form>
      <TrialData companies={info.companies} />
    </section>
  );
}

type Trial = { allowed: boolean; counts: Record<string, number>; will_make: Record<string, number> };
const TRIAL_KINDS: [string, string][] = [
  ["customers", "customers"],
  ["suppliers", "suppliers"],
  ["transporters", "transporters"],
  ["people", "people (salesmen, purchasers, stores)"],
];

/** Trial data (Sidharth, 2026-11-25): thousands of made-up records named "TRIAL …" to try long
 * lists, and one button that removes them all again (core/trial_data.py). */
function TrialData({ companies }: { companies: { id: number; name: string }[] }) {
  const [trial, setTrial] = useState<Trial | null>(null);
  const [company, setCompany] = useState(companies.length === 1 ? String(companies[0].id) : "");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    api<Trial>("v1/admin/trial-data/").then(setTrial, () => setTrial(null));
  }, []);
  if (!trial) return null;
  const loaded = Object.values(trial.counts).some((n) => n > 0);
  const list = (c: Record<string, number>) => TRIAL_KINDS.map(([k, label]) => `${(c[k] ?? 0).toLocaleString("en-IN")} ${label}`).join(", ");
  const act = async (action: "load" | "remove") => {
    if (action === "remove" && !window.confirm("Remove all trial data?")) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      const r = await api<{ counts: Record<string, number>; made?: Record<string, number>; removed?: Record<string, number> }>("v1/admin/trial-data/", {
        action,
        company: Number(company) || null,
      });
      setTrial({ ...trial, counts: r.counts });
      setNote(action === "load" ? `Made ${list(r.made ?? {})}.` : `Removed ${list(r.removed ?? {})}.`);
    } catch (err) {
      setError((err as Error).message);
    }
    setBusy(false);
  };
  return (
    <div className="card">
      <Section title="Trial Data">
        <p className="small">
          Made-up records for trying long lists: {list(trial.will_make)}. Every name starts with "TRIAL", customers and
          suppliers are numbered TCUST- and TVEND-, and nothing is posted. Customers, suppliers and transporters get
          their ledgers and accounts in the company you choose.
        </p>
        <p>
          <b>Now:</b> {loaded ? list(trial.counts) : "no trial data"}
        </p>
        {!trial.allowed && <p className="error">Trial data is switched off here, as on live books.</p>}
        {!loaded && (
          <label>
            <span className="req">Company</span>
            <Combobox required value={company} onChange={setCompany} empty="Choose…" options={companies.map((c) => ({ value: String(c.id), label: c.name }))} />
          </label>
        )}
        {note && <p>{note}</p>}
        {error && <p className="error">{error}</p>}
        <div className="buttons">
          {!loaded && (
            <button type="button" disabled={busy || !trial.allowed || !company} onClick={() => act("load")}>
              {busy ? "Loading…" : "Load Trial Data"}
            </button>
          )}
          {loaded && (
            <button type="button" className="link danger" disabled={busy || !trial.allowed} onClick={() => act("remove")}>
              {busy ? "Removing…" : "Remove Trial Data"}
            </button>
          )}
        </div>
      </Section>
    </div>
  );
}

function FormFields(props: {
  info: Info;
  level: string;
  setLevel: (v: string) => void;
  company: string;
  setCompany: (v: string) => void;
  whole: boolean;
  target: string;
  confirm: string;
  setConfirm: (v: string) => void;
}) {
  const { info } = props;
  return (
    <>
      <Section title="What to clear">
        <label>
          Level
          <Combobox
            required
            value={props.level}
            onChange={props.setLevel}
            options={info.levels}
          />
        </label>
        {!props.whole && (
          <label>
            Company
            <Combobox
              required
              value={props.company}
              onChange={props.setCompany}
              empty="Choose…"
              options={info.companies.map((c) => ({ value: String(c.id), label: c.name }))}
            />
          </label>
        )}
        <p className="small">
          {props.level === "entries" &&
            "Vouchers and stock entries are removed. Masters and opening balances stay."}
          {props.level === "masters" &&
            "Also removes what was added to this company: ledgers with their opening balances, its own ledger groups, branches other than the head office, licences and certificates, and customers or suppliers no other company uses. The standard groups, head office and Cash ledger stay."}
          {props.level === "all" &&
            "Every company is cleared as above, and the shared items, the credit terms and units you added, and the running numbers (ITEM-, CUST-, VEND-) start again. Companies, users and roles stay."}
        </p>
      </Section>
      {(props.whole || props.company) && info.preview && (
        <Section title="This will remove">
          <ul>
            {info.preview.map((r) => (
              <li key={r.label}>
                {r.count} {r.label.toLowerCase()}
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="Confirm">
        <label>
          <span>
            Type <strong>{props.target || "the company name"}</strong> to confirm
          </span>
          <input
            value={props.confirm}
            autoComplete="off"
            onChange={(e) => props.setConfirm(e.target.value)}
            disabled={!props.target}
          />
        </label>
        <p className="small">
          A backup file of everything removed is saved to your computer as soon as the reset is done. The reset is also
          written to the company's Activity.
        </p>
      </Section>
    </>
  );
}
