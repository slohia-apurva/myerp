import { FormEvent, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { closeThisTab } from "./Create";
import { Combobox } from "./Combobox";
import { FormPage } from "./Master";

/** Masters › Reminder Schedule (Sidharth, 2026-11-27, preview po-reminder/5): automatic
 * reminders to suppliers for purchase orders with goods still to come. One schedule for
 * every company in the group; sent once a day by the scheduler (buying/auto_reminders.py). */
type Step = { days: number; before: boolean; template: number | null };
type Schedule = {
  id: number;
  is_on: boolean;
  send_hour: number;
  skip_sundays: boolean;
  copy_purchaser: boolean;
  copy_submitter: boolean;
  repeat_days: number;
  repeat_max: number;
  repeat_template: number | null;
  steps: Step[];
  templates: { id: number; name: string; is_default: boolean; is_active: boolean }[];
  example: { expected: string; dates: { on: string; label: string }[] };
};

const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
const hourLabel = (h: number) => `${h % 12 === 0 ? 12 : h % 12}:00 ${h < 12 ? "am" : "pm"}`;
const HOURS = Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: hourLabel(h) }));
const SIDES = [
  { value: "before", label: "before" },
  { value: "after", label: "after" },
];

export function ReminderSchedulePage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const [s, setS] = useState<Schedule | null>(null);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState("");
  useEffect(() => {
    api<Schedule>("v1/reminder-schedule/").then(setS, setError);
  }, []);
  if (!s)
    return (
      <section className="page">
        <PageHeader title="Reminder Schedule" />
        {error ? <p className="error">{String((error as Error).message ?? error)}</p> : null}
      </section>
    );
  const set = (patch: Partial<Schedule>) => {
    setSaved("");
    setS({ ...s, ...patch });
  };
  const setStep = (i: number, patch: Partial<Step>) => set({ steps: s.steps.map((st, j) => (j === i ? { ...st, ...patch } : st)) });
  const defaultName = s.templates.find((t) => t.is_default)?.name;
  const templateOptions = (current: number | null) =>
    s.templates.filter((t) => t.is_active || t.id === current).map((t) => ({ value: String(t.id), label: t.is_active ? t.name : `${t.name} (disabled)` }));
  const empty = `Default${defaultName ? ` (${defaultName})` : ""}`;
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const out = await api<Schedule>("v1/reminder-schedule/", s, "PUT");
      setS(out);
      setSaved("Saved.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const num = (v: string) => Math.max(0, Math.min(365, Number(v.replace(/\D/g, "")) || 0));
  return (
    <FormPage
      title="Reminder Schedule"
      sub="Automatic reminders to suppliers for purchase orders with goods still to come. One schedule for every company in the group."
      formId="reminder-schedule"
      onSubmit={save}
      onCancel={() => closeThisTab(() => (window.location.hash = "#/"))}
      busy={busy}
      error={error}
      readOnly={!canEdit}
      switches={
        <>
          <label className="check">
            <input type="checkbox" checked={s.is_on} onChange={(e) => set({ is_on: e.target.checked })} />
            Automatic Reminders On
          </label>
          <p className="small">Untick to stop all automatic reminders. "Email Supplier" still works by hand.</p>
        </>
      }
      tips={
        <>
          <p className="fact-label">Leave Out</p>
          <p className="small">A supplier: tick "No Automatic Reminders" on its ledger (Purchaser And Transport).</p>
          <p className="small">One order: tick "No Automatic Reminders" in the order's "Reminders" box.</p>
          <p className="small">No mail account for the company, or no supplier contact with an email: nothing is sent and the purchaser gets a bell notice.</p>
        </>
      }
      activity={<ChangeLog type="reminder_schedule" id={s.id} stamp={JSON.stringify(s)} />}
    >
      {saved && <p className="use-note">{saved}</p>}
      <Section title="Steps">
        <table className="grid reminder-steps">
          <thead>
            <tr>
              <th>Step</th>
              <th>When</th>
              <th>Template</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {s.steps.map((st, i) => (
              <tr key={i}>
                <td className="nowrap">{ordinal(i + 1)} reminder</td>
                <td>
                  <span className="inline-fields">
                    <input className="days" inputMode="numeric" aria-label={`Days, step ${i + 1}`} value={st.days} onChange={(e) => setStep(i, { days: num(e.target.value) })} />
                    days
                    <Combobox
                      ariaLabel={`Before or after, step ${i + 1}`}
                      value={st.before ? "before" : "after"}
                      options={SIDES}
                      onChange={(v) => setStep(i, { before: v === "before" })}
                    />
                    Expected Delivery
                  </span>
                </td>
                <td>
                  <Combobox
                    ariaLabel={`Template, step ${i + 1}`}
                    value={st.template == null ? "" : String(st.template)}
                    empty={empty}
                    options={templateOptions(st.template)}
                    onChange={(v) => setStep(i, { template: v ? Number(v) : null })}
                  />
                </td>
                <td>
                  {s.steps.length > 1 && (
                    <button type="button" className="link danger" onClick={() => set({ steps: s.steps.filter((_, j) => j !== i) })}>
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
            <tr>
              <td>
                <b>Then</b>
              </td>
              <td>
                <span className="inline-fields">
                  every
                  <input className="days" inputMode="numeric" aria-label="Then every (days)" value={s.repeat_days} onChange={(e) => set({ repeat_days: num(e.target.value) })} />
                  days, up to
                  <input className="days" inputMode="numeric" aria-label="Up to (more reminders)" value={s.repeat_max} onChange={(e) => set({ repeat_max: Math.min(52, num(e.target.value)) })} />
                  more reminders
                </span>
              </td>
              <td>
                <Combobox
                  ariaLabel="Then template"
                  value={s.repeat_template == null ? "" : String(s.repeat_template)}
                  empty={empty}
                  options={templateOptions(s.repeat_template)}
                  onChange={(v) => set({ repeat_template: v ? Number(v) : null })}
                />
              </td>
              <td />
            </tr>
          </tbody>
        </table>
        <div className="buttons">
          <button type="button" className="link" onClick={() => set({ steps: [...s.steps, { days: 7, before: false, template: null }] })}>
            Add Step
          </button>
        </div>
        <p className="small">
          Example for a PO expected on {s.example.expected} (as last saved): {s.example.dates.map((d) => `${d.on} (${d.label.replace(" reminder", "")})`).join(", ")}, unless
          everything arrives first. Set "every 0 days" for no repeats.
        </p>
      </Section>
      <Section title="Sending">
        <div className="item-fields">
          <label>
            Send At
            <Combobox ariaLabel="Send At" value={String(s.send_hour)} options={HOURS} onChange={(v) => set({ send_hour: Number(v) })} />
            <span className="small">Checked once a day; a step missed (holiday, mailbox down) goes the next day.</span>
          </label>
          <div>
            <span className="fact-label">Copy To</span>
            <label className="check">
              <input type="checkbox" checked={s.copy_purchaser} onChange={(e) => set({ copy_purchaser: e.target.checked })} />
              The order's purchaser
            </label>
            <label className="check">
              <input type="checkbox" checked={s.copy_submitter} onChange={(e) => set({ copy_submitter: e.target.checked })} />
              The person who submitted the order
            </label>
          </div>
          <div>
            <span className="fact-label">Skip Days</span>
            <label className="check">
              <input type="checkbox" checked={s.skip_sundays} onChange={(e) => set({ skip_sundays: e.target.checked })} />
              Sundays (send on Monday)
            </label>
          </div>
          <div>
            <span className="fact-label">Stops When</span>
            <p>Every line is received or closed, or the order is cancelled. Only pending lines are listed in each mail.</p>
          </div>
        </div>
      </Section>
    </FormPage>
  );
}

type OrderReminders = {
  rows: { sent_at: string; how: string; template: string; to: string; lines: number; failed: string }[];
  schedule_on: boolean;
  no_auto_reminders: boolean;
  supplier_left_out: boolean;
  next: { label: string; when: string } | null;
};

/** The "Reminders" box on a submitted purchase order: what was sent, and the next automatic one. */
export function OrderRemindersBox({ orderId, canChange, stamp }: { orderId: number; canChange: boolean; stamp: number }) {
  const [data, setData] = useState<OrderReminders | null>(null);
  const [error, setError] = useState<unknown>("");
  const link = `v1/purchase-orders/${orderId}/reminders/`;
  useEffect(() => {
    api<OrderReminders>(link).then(setData, setError);
  }, [link, stamp]);
  if (!data) return error ? <p className="small">The reminders could not be loaded.</p> : null;
  const leaveOut = async (value: boolean) => {
    try {
      setData(await api<OrderReminders>(link, { no_auto_reminders: value }, "PATCH"));
    } catch (err) {
      setError(err);
    }
  };
  const next = !data.schedule_on
    ? "Automatic reminders are off (Masters › Reminder Schedule)."
    : data.supplier_left_out
      ? "No automatic reminders: this supplier is left out on its ledger."
      : data.no_auto_reminders
        ? "No automatic reminders for this order."
        : data.next
          ? `Next automatic reminder: ${data.next.when} (${data.next.label}).`
          : "No more automatic reminders for this order.";
  return (
    <>
      {data.rows.length > 0 ? (
        <table className="grid">
          <thead>
            <tr>
              <th>#</th>
              <th>Sent On</th>
              <th>How</th>
              <th>Template</th>
              <th>To</th>
              <th className="num">Lines</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td className="nowrap">{r.sent_at}</td>
                <td>{r.failed ? <span className="pill bad" title={r.failed}>Not sent</span> : r.how}</td>
                <td>{r.template}</td>
                <td>{r.failed ? <span className="small">{r.failed}</span> : r.to}</td>
                <td className="num">{r.lines} pending</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="small">No reminders sent yet.</p>
      )}
      <p className="small">{next}</p>
      <label className="check">
        <input type="checkbox" disabled={!canChange} checked={data.no_auto_reminders} onChange={(e) => leaveOut(e.target.checked)} />
        No Automatic Reminders
      </label>
    </>
  );
}
