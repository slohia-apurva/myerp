import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { PageHeader, Section } from "./Brand";
import { closeThisTab } from "./Create";

type Setting = {
  ocr: boolean;
  on_difference: "warn" | "refuse";
  choices: { value: string; label: string }[];
  ocr_available: boolean;
  changed_by_name: string;
  changed_at: string | null;
};

const NOTES: Record<string, string> = {
  warn: "The reason is kept in the entry's Activity.",
  refuse:
    "The entry must be corrected first; only an Owner may still submit it, with a reason.",
};

/** Admin › Bill Reading (Sidharth, 2026-11-26, preview 108c): how supplier bills attached to
 * purchase invoices are read for the Bill Check, and what Submit does when the bill differs.
 * Owner only; one setting for the whole group. Claude reading is shown for later. */
export function BillReadingPage() {
  const [s, setS] = useState<Setting | null>(null);
  const [ocr, setOcr] = useState(true);
  const [onDifference, setOnDifference] = useState("warn");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Setting>("v1/bill-reading/").then(
      (got) => {
        setS(got);
        setOcr(got.ocr);
        setOnDifference(got.on_difference);
      },
      (err) => setError((err as Error).message),
    );
  }, []);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNote("");
    try {
      const got = await api<Setting>(
        "v1/bill-reading/",
        { ocr, on_difference: onDifference },
        "PUT",
      );
      setS(got);
      setNote("Saved.");
    } catch (err) {
      setError((err as Error).message);
    }
    setBusy(false);
  };

  return (
    <section className="page">
      <PageHeader
        title="Bill Reading"
        sub="How MyERP reads supplier bills and challans attached to Purchase Invoices and Goods Receipts · Owner only"
        crumbs={[{ label: "Admin", href: "#/" }]}
        actions={
          <>
            <button
              type="button"
              className="link"
              onClick={() => closeThisTab(() => (window.location.hash = "#/"))}
            >
              Close
            </button>
            <button
              type="submit"
              form="bill-reading-form"
              disabled={busy || !s}
            >
              Save
            </button>
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {s && (
        <form id="bill-reading-form" className="bill-reading" onSubmit={save}>
          <Section title="Free Reading (on This Server)">
            <label className="tick-line">
              <input type="checkbox" checked disabled />
              <span>
                <b>Read the e-invoice QR code</b>
                <span className="small">
                  {" "}
                  Exact. Gives the supplier's and our GSTIN, invoice no and
                  date, total, main HSN and IRN. Always on.
                </span>
              </span>
            </label>
            <label className="tick-line">
              <input
                type="checkbox"
                checked={ocr}
                onChange={(e) => setOcr(e.target.checked)}
              />
              <span>
                <b>
                  Read the page with OCR when the bill has no QR code, and for
                  the item lines
                </b>
                <span className="small">
                  {" "}
                  Reads printed text from scanned PDFs and photos. A PDF made by
                  a computer is read from its own text. Anything not read
                  clearly shows as "Not read" and is never counted as a
                  difference.
                </span>
              </span>
            </label>
            {!s.ocr_available && (
              <p className="use-note">
                OCR is not installed on this server yet, so only the QR code and
                PDF text are read.
              </p>
            )}
          </Section>
          <Section title="Claude AI Reading (Later)">
            <div className="bill-reading-later">
              <p>
                <b>Model:</b> Off · Opus 5.5 about ₹5 a bill, Sonnet 5.5 about
                ₹2, Haiku 5.5 under ₹0.50
              </p>
              <p>
                <b>API Key:</b> your own key from Anthropic, kept encrypted and
                shown as its last 4 characters
              </p>
              <p className="small">
                Not available yet. When you want it, ask and it will be switched
                on here; bill pages are then sent to Anthropic to be read.
              </p>
            </div>
          </Section>
          <Section title="When the Bill Differs from the Entry on Submit">
            {s.choices.map((c) => (
              <label key={c.value} className="tick-line">
                <input
                  type="radio"
                  name="on-difference"
                  value={c.value}
                  checked={onDifference === c.value}
                  onChange={() => setOnDifference(c.value)}
                />
                <span>
                  <b>{c.label}</b>
                  <span className="small"> {NOTES[c.value]}</span>
                </span>
              </label>
            ))}
            <p className="small">
              A bill from a different supplier GSTIN, or addressed to another
              company's GSTIN, is always refused.
            </p>
          </Section>
          {note && <p className="use-note">{note}</p>}
          {s.changed_by_name && (
            <p className="small">
              Last changed by {s.changed_by_name}
              {s.changed_at
                ? ` on ${new Date(s.changed_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}`
                : ""}
            </p>
          )}
        </form>
      )}
    </section>
  );
}
