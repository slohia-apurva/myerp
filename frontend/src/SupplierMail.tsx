import { useEffect, useMemo, useState } from "react";
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
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PILL: Record<DiffLine["kind"], string> = { short: "pill warn", not_received: "pill bad", over: "pill on" };

/** The subject and closing words for the ticked lines (Sidharth, 2026-11-15):
 * "Short and Excess Supply against PO No : …". */
function wording(lines: DiffLine[], number: string, d: Draft): [string, string] {
  const short = lines.some((l) => l.kind !== "over");
  const over = lines.some((l) => l.kind === "over");
  const what = short && over ? "Short and Excess Supply" : over ? "Excess Supply" : "Short Supply";
  return [`${what} against PO No : ${number}`, [short && d.short_ask, over && d.over_ask].filter(Boolean).join(" ")];
}

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
export function SupplierMail({ orderId, grn, onClose, onSent }: { orderId: number; grn: string; onClose: () => void; onSent: (to: string[]) => void }) {
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
    api<Draft>(`${link}?grn=${grn}`).then((d) => {
      setDraft(d);
      setTo(d.to);
      setCc(d.cc);
      setTicked(d.lines.map((l) => l.id));
      setReceipt(d.grn ? String(d.grn) : "");
    }, setError);
  }, [link, grn]);
  const chosen = useMemo(() => (draft ? draft.lines.filter((l) => ticked.includes(l.id)) : []), [draft, ticked]);
  if (!draft)
    return (
      <Fold title="Email Supplier" open>
        <ErrorNote error={error} />
      </Fold>
    );
  const [autoSubject, autoClosing] = wording(chosen, draft.order_number, draft);
  const shownSubject = subject ?? autoSubject;
  const shownIntro = intro ?? draft.intros[receipt] ?? "";
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
      });
      onSent(done.sent_to);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Fold title="Email Supplier" open summary={draft.mail_ready ? `From ${draft.from}` : "Mail account not set up"}>
      {!draft.mail_ready && (
        <p className="use-note">
          The company's mail account is not set up yet. An Owner sets it under Admin › Company › Edit › "Mail Account".
        </p>
      )}
      {draft.lines.length === 0 ? (
        <p className="small">Every line has come as ordered or is closed; there is nothing to write about.</p>
      ) : (
        <div className="supplier-mail">
          <div>
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
};

/** "Email PO": the submitted order to the supplier, its PDF attached. */
export function OrderMail({ orderId, onClose, onSent }: { orderId: number; onClose: () => void; onSent: (to: string[]) => void }) {
  const [draft, setDraft] = useState<OrderDraft | null>(null);
  const [to, setTo] = useState<Person[]>([]);
  const [cc, setCc] = useState<Person[]>([]);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const link = `v1/purchase-orders/${orderId}/mail/`;
  useEffect(() => {
    api<OrderDraft>(link).then((d) => {
      setDraft(d);
      setTo(d.to);
      setCc(d.cc);
      setSubject(d.subject);
      setMessage(d.message);
    }, setError);
  }, [link]);
  if (!draft)
    return (
      <Fold title="Email PO" open>
        <ErrorNote error={error} />
      </Fold>
    );
  const greeting = draft.to_options.find((o) => o.email === to[0]?.email)?.name || "Sir/Madam";
  const send = async () => {
    setBusy(true);
    setError("");
    try {
      const done = await api<{ sent_to: string[] }>(link, { to: to.map((p) => p.email), cc: cc.map((p) => p.email), subject, message });
      onSent(done.sent_to);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Fold title="Email PO" open summary={draft.mail_ready ? `From ${draft.from}` : "Mail account not set up"}>
      {!draft.mail_ready && (
        <p className="use-note">
          The company's mail account is not set up yet. An Owner sets it under Admin › Company › Edit › "Mail Account".
        </p>
      )}
      <div className="supplier-mail">
        <div>
          <People label="To" value={to} options={draft.to_options} onChange={setTo} />
          <People label="CC" value={cc} options={draft.cc_options} onChange={setCc} />
          <label className="field">
            <span className="fact-label">Subject</span>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} />
          </label>
          <div className="field">
            <span className="fact-label">Attached</span>
            <a href={`/api/v1/purchase-orders/${orderId}/pdf/`} target="_blank" rel="noreferrer">
              {draft.attachment}
            </a>
          </div>
        </div>
        <div className="mail-preview">
          <span className="fact-label">The Mail (the text box can be changed)</span>
          <p>Dear {greeting},</p>
          <textarea rows={5} value={message} onChange={(e) => setMessage(e.target.value)} aria-label="Message" />
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
