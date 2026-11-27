import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { Fold } from "./Master";

type Person = { name: string; email: string; of?: string };
type DiffLine = {
  id: number;
  position: number;
  item_name: string;
  unit: string;
  ordered: string;
  received: string;
  difference: string;
  kind: "short" | "not_received" | "over";
  kind_label: string;
};
type Draft = {
  order_number: string;
  supplier_name: string;
  mail_ready: boolean;
  from: string;
  to: Person[];
  to_options: Person[];
  cc: Person[];
  cc_options: Person[];
  lines: DiffLine[];
  receipts: { id: number; number: string; date: string }[];
  grn: number | null;
  intros: Record<string, string>;
  short_ask: string;
  over_ask: string;
  signature: string;
  // From the picked mail template (absent when the group has none).
  template?: number;
  subject_pattern?: string;
  closing?: string;
  attach_default?: boolean;
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PILL: Record<DiffLine["kind"], string> = { short: "pill warn", not_received: "pill bad", over: "pill on" };

/** The subject and closing words for the ticked lines (Sidharth, 2026-11-15):
 * "Short and Excess Supply against PO No : …". */
function wording(lines: DiffLine[], number: string, d: Draft): [string, string] {
  const short = lines.some((l) => l.kind !== "over");
  const over = lines.some((l) => l.kind === "over");
  const what = short && over ? "Short and Excess" : over ? "Excess" : "Short";
  if (d.subject_pattern !== undefined) return [d.subject_pattern.replace(/\{\s*short\s+or\s+excess\s*\}/gi, what), d.closing ?? ""];
  return [`${what} Supply against PO No : ${number}`, [short && d.short_ask, over && d.over_ask].filter(Boolean).join(" ")];
}

/** The mail's own heading and its Template picker, when opened from "Email Supplier". */
type Picked = { template?: number; picker?: ReactNode; title?: string };
const withTemplate = (link: string, template?: number, more = "") => {
  const q = [template ? `template=${template}` : "", more].filter(Boolean).join("&");
  return q ? `${link}?${q}` : link;
};

export function People({ label, value, options, onChange }: { label: string; value: Person[]; options: Person[]; onChange: (p: Person[]) => void }) {
  const left = options.filter((o) => !value.some((v) => v.email.toLowerCase() === o.email.toLowerCase()));
  return (
    <div className="field mail-people">
      <span className="fact-label">{label}</span>
      <div className="chips">
        {value.map((p) => (
          <span key={p.email} className="chip">
            {p.name && p.name !== p.email ? `${p.name} <${p.email}>` : p.email}
            <button type="button" aria-label={`Remove ${p.email}`} onClick={() => onChange(value.filter((v) => v !== p))}>
              ×
            </button>
          </span>
        ))}
      </div>
      <Combobox
        ariaLabel={label}
        value=""
        placeholder="Type to add a contact, a colleague or an address…"
        options={left.map((o) => ({ value: o.email, label: `${o.name} <${o.email}>`, hint: o.of }))}
        onChange={(email) => {
          const found = left.find((o) => o.email === email);
          if (found) onChange([...value, found]);
        }}
        createHere={{
          label: "Add address",
          pick: (typed) => {
            const e = typed.trim();
            if (EMAIL.test(e)) onChange([...value, { name: "", email: e }]);
          },
        }}
      />
    </div>
  );
}

/** "Email Supplier" on a purchase order: one mail about the lines that came
 * short, did not come, or came in excess, with a grid of them. */
export function SupplierMail({
  orderId,
  grn,
  onClose,
  onSent,
  template,
  picker,
  title = "Email Supplier",
}: { orderId: number; grn: string; onClose: () => void; onSent: (to: string[]) => void } & Picked) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [to, setTo] = useState<Person[]>([]);
  const [cc, setCc] = useState<Person[]>([]);
  const [ticked, setTicked] = useState<number[]>([]);
  const [receipt, setReceipt] = useState("");
  const [subject, setSubject] = useState<string | null>(null); // null: follows the ticks
  const [intro, setIntro] = useState<string | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const [withOrder, setWithOrder] = useState(false);
  const link = `v1/purchase-orders/${orderId}/supplier-mail/`;
  useEffect(() => {
    api<Draft>(withTemplate(link, template, `grn=${grn}`)).then((d) => {
      setDraft(d);
      setTo(d.to);
      setCc(d.cc);
      setTicked(d.lines.map((l) => l.id));
      setReceipt(d.grn && d.attach_default !== false ? String(d.grn) : "");
    }, setError);
  }, [link, grn, template]);
  const chosen = useMemo(() => (draft ? draft.lines.filter((l) => ticked.includes(l.id)) : []), [draft, ticked]);
  if (!draft)
    return (
      <Fold title={title} open>
        {picker}
        <ErrorNote error={error} />
      </Fold>
    );
  const [autoSubject, autoClosing] = wording(chosen, draft.order_number, draft);
  const shownSubject = subject ?? autoSubject;
  const shownIntro = intro ?? draft.intros[receipt] ?? draft.intros[String(draft.grn ?? "")] ?? "";
  const shownClosing = closing ?? autoClosing;
  const greeting = draft.to_options.find((o) => o.email === to[0]?.email)?.name || "Sir/Madam";
  const send = async () => {
    setBusy(true);
    setError("");
    try {
      const done = await api<{ sent_to: string[] }>(link, {
        to: to.map((p) => p.email),
        cc: cc.map((p) => p.email),
        subject: shownSubject,
        intro: shownIntro,
        closing: shownClosing,
        lines: ticked,
        grn: receipt ? Number(receipt) : null,
        attach_order: withOrder,
        template: draft.template,
      });
      onSent(done.sent_to);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Fold title={title} open summary={draft.mail_ready ? `From ${draft.from}` : "Mail account not set up"}>
      {!draft.mail_ready && (
        <p className="use-note">
          The company's mail account is not set up yet. An Owner sets it under Admin › Company › Edit › "Mail Account".
        </p>
      )}
      {draft.lines.length === 0 ? (
        <>
          {picker}
          <p className="small">Every line has come as ordered or is closed; there is nothing to write about.</p>
        </>
      ) : (
        <div className="supplier-mail">
          <div>
            {picker}
            <People label="To" value={to} options={draft.to_options} onChange={setTo} />
            <People label="CC" value={cc} options={draft.cc_options} onChange={setCc} />
            <label className="field">
              <span className="fact-label">Subject</span>
              <input value={shownSubject} onChange={(e) => setSubject(e.target.value)} />
            </label>
            <div className="field">
              <span className="fact-label">Lines</span>
              {draft.lines.map((l) => (
                <label key={l.id} className="check">
                  <input
                    type="checkbox"
                    checked={ticked.includes(l.id)}
                    onChange={(e) => setTicked(e.target.checked ? [...ticked, l.id] : ticked.filter((x) => x !== l.id))}
                  />
                  {l.item_name} ({l.difference} {l.unit} {l.kind_label.toLowerCase()})
                </label>
              ))}
            </div>
            <div className="field">
              <span className="fact-label">Attach</span>
              <Combobox
                ariaLabel="Attach"
                value={receipt}
                onChange={(v) => {
                  setReceipt(v);
                  setIntro(null);
                }}
                empty="No attachment"
                options={draft.receipts.map((r) => ({ value: String(r.id), label: `Goods Receipt Note ${r.number} (PDF)`, hint: r.date }))}
              />
              <label className="check">
                <input type="checkbox" checked={withOrder} onChange={(e) => setWithOrder(e.target.checked)} />
                Purchase order {draft.order_number} (PDF)
              </label>
            </div>
          </div>
          <div className="mail-preview">
            <span className="fact-label">The Mail (the two text boxes can be changed)</span>
            <p>Dear {greeting},</p>
            <textarea rows={3} value={shownIntro} onChange={(e) => setIntro(e.target.value)} aria-label="Opening" />
            <table className="grid mail-grid">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Item</th>
                  <th className="num">Ordered</th>
                  <th className="num">Received</th>
                  <th className="num">Difference</th>
                  <th>Remark</th>
                </tr>
              </thead>
              <tbody>
                {chosen.map((l, i) => (
                  <tr key={l.id}>
                    <td>{i + 1}</td>
                    <td>{l.item_name}</td>
                    <td className="num">
                      {l.ordered} {l.unit}
                    </td>
                    <td className="num">
                      {l.received} {l.unit}
                    </td>
                    <td className="num">
                      <b>
                        {l.difference} {l.unit}
                      </b>
                    </td>
                    <td>
                      <span className={PILL[l.kind]}>{l.kind_label}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <textarea rows={3} value={shownClosing} onChange={(e) => setClosing(e.target.value)} aria-label="Closing" />
            <p className="pre">Regards,{"\n" + draft.signature}</p>
          </div>
        </div>
      )}
      <ErrorNote error={error} />
      <div className="buttons">
        <button type="button" className="link" onClick={onClose}>
          Cancel
        </button>
        {draft.lines.length > 0 && (
          <button type="button" disabled={busy || !draft.mail_ready || !to.length || !chosen.length} onClick={send}>
            {busy ? "Sending…" : "Send"}
          </button>
        )}
      </div>
    </Fold>
  );
}

type OrderDraft = {
  order_number: string;
  mail_ready: boolean;
  from: string;
  to: Person[];
  to_options: Person[];
  cc: Person[];
  cc_options: Person[];
  subject: string;
  message: string;
  signature: string;
  attachment: string;
  template?: number | null;
};

/** "Email PO": the submitted order to the supplier, its PDF attached. */
/** "Email PO" on a purchase order, or "Email Customer" on a sales order (`path`
 * "sales-orders", Sidharth 2026-11-19: the order confirmation, no reply link). */
export function OrderMail({
  orderId,
  onClose,
  onSent,
  path = "purchase-orders",
  title = "Email PO",
  template,
  picker,
}: {
  orderId: number;
  onClose: () => void;
  onSent: (to: string[]) => void;
  path?: string;
} & Picked) {
  const sale = path === "sales-orders";
  const [draft, setDraft] = useState<OrderDraft | null>(null);
  const [to, setTo] = useState<Person[]>([]);
  const [cc, setCc] = useState<Person[]>([]);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const link = `v1/${path}/${orderId}/mail/`;
  useEffect(() => {
    api<OrderDraft>(withTemplate(link, template)).then((d) => {
      setDraft(d);
      setTo(d.to);
      setCc(d.cc);
      setSubject(d.subject);
      setMessage(d.message);
    }, setError);
  }, [link, template]);
  if (!draft)
    return (
      <Fold title={title} open>
        {picker}
        <ErrorNote error={error} />
      </Fold>
    );
  const greeting = draft.to_options.find((o) => o.email === to[0]?.email)?.name || "Sir/Madam";
  const send = async () => {
    setBusy(true);
    setError("");
    try {
      const done = await api<{ sent_to: string[] }>(link, {
        to: to.map((p) => p.email),
        cc: cc.map((p) => p.email),
        subject,
        message,
        template: draft.template ?? undefined,
      });
      onSent(done.sent_to);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Fold title={title} open summary={draft.mail_ready ? `From ${draft.from}` : "Mail account not set up"}>
      {!draft.mail_ready && (
        <p className="use-note">
          The company's mail account is not set up yet. An Owner sets it under Admin › Company › Edit › "Mail Account".
        </p>
      )}
      <div className="supplier-mail">
        <div>
          {picker}
          <People label="To" value={to} options={draft.to_options} onChange={setTo} />
          <People label="CC" value={cc} options={draft.cc_options} onChange={setCc} />
          <label className="field">
            <span className="fact-label">Subject</span>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} />
          </label>
          <div className="field">
            <span className="fact-label">Attached</span>
            <a href={`/api/v1/${path}/${orderId}/pdf/`} target="myerp-print" rel="noreferrer">
              {draft.attachment}
            </a>
          </div>
        </div>
        <div className="mail-preview">
          <span className="fact-label">The Mail (the text box can be changed)</span>
          <p>Dear {greeting},</p>
          <textarea rows={5} value={message} onChange={(e) => setMessage(e.target.value)} aria-label="Message" />
          {!sale && (
            <>
              <p>
                <span className="mail-button">View and Accept Order</span>
              </p>
              <p className="small">The supplier's private link is added here: they can accept the order or report an issue without signing in.</p>
            </>
          )}
          <p className="pre">Regards,{"\n" + draft.signature}</p>
        </div>
      </div>
      <ErrorNote error={error} />
      <div className="buttons">
        <button type="button" className="link" onClick={onClose}>
          Cancel
        </button>
        <button type="button" disabled={busy || !draft.mail_ready || !to.length} onClick={send}>
          {busy ? "Sending…" : "Send"}
        </button>
      </div>
    </Fold>
  );
}

type PendingLine = {
  id: number;
  item_code: string;
  item_name: string;
  unit: string;
  ordered: string;
  received: string;
  pending: string;
  expected: string;
  days_late: number;
};
type ReminderDraft = {
  order_number: string;
  mail_ready: boolean;
  from: string;
  to: Person[];
  to_options: Person[];
  cc: Person[];
  cc_options: Person[];
  lines: PendingLine[];
  subject: string;
  intro: string;
  closing: string;
  signature: string;
  attachment: string;
  last: { date: string; by: string; to: string[] } | null;
  count: number;
  template: number | null;
  attach_default: boolean;
};

const lateWords = (d: number) => (d ? `${d} day${d === 1 ? "" : "s"} late` : "");

/** "Send Reminder" on an open purchase order (Sidharth, 2026-11-27): asks the
 * supplier when the quantity still to come will be supplied, with a grid of
 * those lines. */
export function SupplierReminder({
  orderId,
  onClose,
  onSent,
  template,
  picker,
  title = "Send Reminder",
}: { orderId: number; onClose: () => void; onSent: (to: string[]) => void } & Picked) {
  const [draft, setDraft] = useState<ReminderDraft | null>(null);
  const [to, setTo] = useState<Person[]>([]);
  const [cc, setCc] = useState<Person[]>([]);
  const [ticked, setTicked] = useState<number[]>([]);
  const [subject, setSubject] = useState("");
  const [intro, setIntro] = useState("");
  const [closing, setClosing] = useState("");
  const [withOrder, setWithOrder] = useState(true);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const link = `v1/purchase-orders/${orderId}/reminder/`;
  useEffect(() => {
    api<ReminderDraft>(withTemplate(link, template)).then((d) => {
      setDraft(d);
      setTo(d.to);
      setCc(d.cc);
      setTicked(d.lines.map((l) => l.id));
      setSubject(d.subject);
      setIntro(d.intro);
      setClosing(d.closing);
      setWithOrder(d.attach_default);
    }, setError);
  }, [link, template]);
  const chosen = useMemo(() => (draft ? draft.lines.filter((l) => ticked.includes(l.id)) : []), [draft, ticked]);
  if (!draft)
    return (
      <Fold title={title} open>
        {picker}
        <ErrorNote error={error} />
      </Fold>
    );
  const greeting = draft.to_options.find((o) => o.email === to[0]?.email)?.name || "Sir/Madam";
  const send = async () => {
    setBusy(true);
    setError("");
    try {
      const done = await api<{ sent_to: string[] }>(link, {
        to: to.map((p) => p.email),
        cc: cc.map((p) => p.email),
        subject,
        intro,
        closing,
        lines: ticked,
        attach_order: withOrder,
        template: draft.template ?? undefined,
      });
      onSent(done.sent_to);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Fold title={title} open summary={draft.mail_ready ? `From ${draft.from}` : "Mail account not set up"}>
      {!draft.mail_ready && (
        <p className="use-note">
          The company's mail account is not set up yet. An Owner sets it under Admin › Company › Edit › "Mail Account".
        </p>
      )}
      {draft.lines.length === 0 ? (
        <>
          {picker}
          <p className="small">Every line has come in full or is closed; there is nothing to chase.</p>
        </>
      ) : (
        <div className="supplier-mail">
          <div>
            {picker}
            <People label="To" value={to} options={draft.to_options} onChange={setTo} />
            <People label="CC" value={cc} options={draft.cc_options} onChange={setCc} />
            <label className="field">
              <span className="fact-label">Subject</span>
              <input value={subject} onChange={(e) => setSubject(e.target.value)} />
            </label>
            <div className="field">
              <span className="fact-label">Lines</span>
              {draft.lines.map((l) => (
                <label key={l.id} className="check">
                  <input
                    type="checkbox"
                    checked={ticked.includes(l.id)}
                    onChange={(e) => setTicked(e.target.checked ? [...ticked, l.id] : ticked.filter((x) => x !== l.id))}
                  />
                  {l.item_code} {l.item_name} ({l.pending} {l.unit} pending)
                </label>
              ))}
            </div>
            <div className="field">
              <span className="fact-label">Attach</span>
              <label className="check">
                <input type="checkbox" checked={withOrder} onChange={(e) => setWithOrder(e.target.checked)} />
                Purchase Order {draft.order_number} (PDF)
              </label>
            </div>
            {draft.last && (
              <p className="use-note">
                Last reminder: {draft.last.date} by {draft.last.by}
                {draft.last.to.length ? ` to ${draft.last.to.join(", ")}` : ""} ({draft.count} reminder{draft.count === 1 ? "" : "s"} sent so far).
              </p>
            )}
          </div>
          <div className="mail-preview">
            <span className="fact-label">The Mail (the two text boxes can be changed)</span>
            <p>Dear {greeting},</p>
            <textarea rows={3} value={intro} onChange={(e) => setIntro(e.target.value)} aria-label="Opening" />
            <table className="grid mail-grid">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Item Code</th>
                  <th>Item</th>
                  <th className="num">Ordered</th>
                  <th className="num">Received</th>
                  <th className="num">Pending</th>
                  <th>Expected Delivery</th>
                </tr>
              </thead>
              <tbody>
                {chosen.map((l, i) => (
                  <tr key={l.id}>
                    <td>{i + 1}</td>
                    <td className="nowrap">{l.item_code}</td>
                    <td>{l.item_name}</td>
                    <td className="num nowrap">
                      {l.ordered} {l.unit}
                    </td>
                    <td className="num nowrap">
                      {l.received} {l.unit}
                    </td>
                    <td className="num nowrap">
                      <b>
                        {l.pending} {l.unit}
                      </b>
                    </td>
                    <td className={l.days_late ? "late nowrap" : "nowrap"}>
                      {l.expected}
                      {l.days_late > 0 && <div className="small">{lateWords(l.days_late)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <textarea rows={3} value={closing} onChange={(e) => setClosing(e.target.value)} aria-label="Closing" />
            <p className="pre">Regards,{"\n" + draft.signature}</p>
          </div>
        </div>
      )}
      <ErrorNote error={error} />
      <div className="buttons">
        <button type="button" className="link" onClick={onClose}>
          Cancel
        </button>
        {draft.lines.length > 0 && (
          <button type="button" disabled={busy || !draft.mail_ready || !to.length || !chosen.length || !subject.trim()} onClick={send}>
            {busy ? "Sending…" : "Send"}
          </button>
        )}
      </div>
    </Fold>
  );
}

type Offered = { id: number; name: string; used_for: "purchase_order" | "short_excess" | "reminder"; used_for_label: string; is_default: boolean };

/** "Email Supplier" on a purchase order (Sidharth, 2026-11-27): one button; the
 * "Template" picker (Masters › Mail templates) decides the mail: the order itself,
 * short / excess supply against a receipt, or a reminder for what is still to come. */
export function EmailSupplier({ orderId, grn, onClose, onSent }: { orderId: number; grn: string; onClose: () => void; onSent: (to: string[]) => void }) {
  const [offered, setOffered] = useState<Offered[] | null>(null);
  const [pick, setPick] = useState("");
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    api<Offered[]>(`v1/purchase-orders/${orderId}/mail-templates/`).then((ts) => {
      setOffered(ts);
      // Opened from a receipt notice: the short / excess mail; else a reminder while goods are due; else the order.
      const first =
        (grn && ts.find((t) => t.used_for === "short_excess")) || ts.find((t) => t.used_for === "reminder") || ts.find((t) => t.used_for === "purchase_order") || ts[0];
      setPick(first ? String(first.id) : "");
    }, setError);
  }, [orderId, grn]);
  const t = offered?.find((x) => String(x.id) === pick);
  if (!offered || !t)
    return (
      <Fold title="Email Supplier" open>
        {offered && <p className="small">No mail template fits this order. Add one under Masters › Mail templates.</p>}
        <ErrorNote error={error} />
        <div className="buttons">
          <button type="button" className="link" onClick={onClose}>
            Cancel
          </button>
        </div>
      </Fold>
    );
  const picker = (
    <div className="field">
      <span className="fact-label">Template</span>
      <Combobox ariaLabel="Template" value={pick} onChange={setPick} options={offered.map((x) => ({ value: String(x.id), label: x.name, hint: x.used_for_label }))} />
    </div>
  );
  const common = { orderId, onClose, onSent, template: t.id, picker, title: "Email Supplier" };
  if (t.used_for === "purchase_order") return <OrderMail key={pick} {...common} />;
  if (t.used_for === "short_excess") return <SupplierMail key={pick} {...common} grn={grn} />;
  return <SupplierReminder key={pick} {...common} />;
}
