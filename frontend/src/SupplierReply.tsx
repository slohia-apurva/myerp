// The supplier's page (Sidharth, 2026-11-15): opened from the private link in
// a mailed purchase order, without signing in. The supplier sees the order and
// can "Accept Order" (with an expected dispatch date) or "Report an Issue", and
// add comments later from the same link. Served by buying/supplier_link.py.
import { useEffect, useState } from "react";
import { api } from "./api";
import { ErrorNote } from "./ErrorNote";

type Reply = { kind: string; name: string; at: string; dispatch_date: string | null; comment: string };
type Page = {
  state: "open" | "done" | "cancelled" | "expired";
  supplier_status: string;
  company_name: string;
  number: string;
  company_city?: string;
  supplier_name?: string;
  order_date?: string;
  expected_date?: string | null;
  deliver_to?: string;
  currency_symbol?: string;
  total?: string;
  lines?: { item_name: string; description: string; qty: string; unit_name: string; rate: string; taxable: string }[];
  replies?: Reply[];
};

const dmy = (iso?: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const when = (iso: string) => {
  const d = new Date(iso);
  return `${dmy(iso)} at ${d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true }).toLowerCase()}`;
};
const money = (v: string) => Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const KIND = { accepted: "Accepted", issue: "Issue", comment: "Comment" } as Record<string, string>;

export function SupplierReplyPage({ token }: { token: string }) {
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState<unknown>("");
  const [name, setName] = useState("");
  const [dispatch, setDispatch] = useState("");
  const [comment, setComment] = useState("");
  const [done, setDone] = useState<Reply | null>(null);
  const [busy, setBusy] = useState(false);
  const path = `v1/public/po/${encodeURIComponent(token)}/`;

  useEffect(() => {
    api<Page>(path)
      .then((p) => {
        setPage(p);
        document.title = `${p.number} · ${p.company_name}`;
      })
      .catch(setError);
  }, [path]);

  const send = async (kind: string) => {
    setError("");
    setBusy(true);
    try {
      const p = await api<Page>(path, { kind, name, comment, dispatch_date: kind === "accepted" ? dispatch : "" });
      setPage(p);
      setDone(p.replies?.[p.replies.length - 1] ?? null);
      setComment("");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  if (!page)
    return (
      <main className="reply-page">
        <div className="reply-card">{error ? <ErrorNote error={error} /> : <p>Loading…</p>}</div>
      </main>
    );

  const head = (
    <div className="reply-top">
      <div className="reply-logo">{page.company_name.slice(0, 1)}</div>
      <div>
        <b>{page.company_name}</b>
        <div className="small">{page.supplier_name ? `Purchase order for ${page.supplier_name}` : "Purchase order"}</div>
      </div>
    </div>
  );
  if (page.state === "cancelled" || page.state === "expired")
    return (
      <main className="reply-page">
        <div className="reply-card">
          {head}
          <h1>{page.number}</h1>
          <p className="use-note">
            {page.state === "cancelled" ? "This order has been cancelled." : "This link has expired. Please ask the buyer to send the order again."}
          </p>
        </div>
      </main>
    );

  const accepted = page.supplier_status === "accepted";
  const sym = page.currency_symbol ?? "₹";
  return (
    <main className="reply-page">
      <div className="reply-card">
        {head}
        <div className="reply-order">
          <div>
            <h1>{page.number}</h1>
            <div className="small">
              Dated {dmy(page.order_date)} · Deliver to {page.deliver_to}
              {page.expected_date && ` · Expected ${dmy(page.expected_date)}`}
            </div>
          </div>
          <a className="button link" href={`/api/${path}pdf/`} target="_blank" rel="noreferrer">
            Download PDF
          </a>
        </div>
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>#</th>
                <th>Item</th>
                <th className="num">Qty</th>
                <th className="num rate">Rate {sym}</th>
                <th className="num">Amount {sym}</th>
              </tr>
            </thead>
            <tbody>
              {page.lines?.map((l, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td>
                    {l.item_name}
                    {l.description && <div className="line-desc">{l.description}</div>}
                  </td>
                  <td className="num nowrap">
                    {l.qty} {l.unit_name}
                  </td>
                  <td className="num rate">{money(l.rate)}</td>
                  <td className="num">{money(l.taxable)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td />
                <td colSpan={2}>
                  <b>Total (with GST and charges)</b>
                </td>
                <td className="rate" />
                <td className="num">
                  <b>{money(page.total ?? "0")}</b>
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        {!!page.replies?.length && (
          <div className="replies">
            {page.replies.map((r, i) => (
              <div key={i} className={`reply ${r.kind}`}>
                <b>{KIND[r.kind]}</b> by {r.name} · {when(r.at)}
                {r.dispatch_date && ` · dispatch expected ${dmy(r.dispatch_date)}`}
                {r.comment && <div className="pre">"{r.comment}"</div>}
              </div>
            ))}
          </div>
        )}

        {done && (
          <div className="reply-done">
            <span className={done.kind === "issue" ? "pill warn" : "pill on"}>
              {done.kind === "accepted" ? "Order accepted" : done.kind === "issue" ? "Issue sent" : "Comment sent"}
            </span>
            <p>
              Thank you, {done.name}. {page.company_name} has been told
              {done.kind === "accepted" ? ` that you accepted ${page.number} on ${when(done.at)}.` : " and will get back to you."}
            </p>
            <p className="small">You can come back to this link to add a comment.</p>
          </div>
        )}

        <div className="reply-form">
          <label className="field">
            <span className="fact-label">
              Your Name<span className="req" />
            </span>
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
          </label>
          {page.state === "open" && !accepted && (
            <label className="field">
              <span className="fact-label">Expected Dispatch Date (optional)</span>
              <input type="date" value={dispatch} onChange={(e) => setDispatch(e.target.value)} className="reply-date" />
            </label>
          )}
          <label className="field">
            <span className="fact-label">Comment{page.state === "open" && !accepted ? ' (needed for "Report an Issue")' : ""}</span>
            <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <ErrorNote error={error} />
          <div className="buttons">
            {page.state === "open" && !accepted && (
              <button type="button" disabled={busy} onClick={() => send("accepted")}>
                Accept Order
              </button>
            )}
            {page.state === "open" && (
              <button type="button" className="link" disabled={busy} onClick={() => send("issue")}>
                Report an Issue
              </button>
            )}
            {(accepted || page.state === "done") && (
              <button type="button" className={page.state === "done" ? "" : "link"} disabled={busy} onClick={() => send("comment")}>
                Add Comment
              </button>
            )}
          </div>
          {page.state === "done" && <p className="small">This order is complete. You can still add a comment.</p>}
        </div>
      </div>
    </main>
  );
}
