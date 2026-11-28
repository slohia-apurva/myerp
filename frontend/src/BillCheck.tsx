import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { Fold } from "./Master";

/** One compared fact: what the entry says, what the supplier's bill says (buying/bill_check.py). */
export type CheckRow = {
  key: string;
  label: string;
  group: string;
  entry: string;
  bill: string;
  result: "same" | "differs" | "written" | "not_read" | "info";
  note: string;
  source: string;
};

export type BillCheck = {
  files: { id: number; filename: string; kind: string }[];
  file: { id: number; filename: string } | null;
  checked: boolean;
  can_read: boolean;
  source?: string;
  error?: string;
  read_at?: string;
  read_by_name?: string;
  seen_reason?: string;
  seen_by_name?: string;
  seen_at?: string | null;
  on_difference?: "warn" | "refuse";
  rows?: CheckRow[];
  differences?: number;
  refuse?: string[];
  owner_may_override?: boolean;
  headline?: string;
  summary?: string;
};

/** The Bill Check a refused Submit sent back, if that is why it was refused. */
export function billCheckOf(
  err: unknown,
): (BillCheck & { refusedSubmit: boolean; override: boolean }) | null {
  if (
    err instanceof ApiError &&
    err.data &&
    typeof err.data === "object" &&
    "bill_check" in err.data
  ) {
    const data = err.data as {
      bill_check: BillCheck;
      refused?: boolean;
      override?: boolean;
    };
    // "override": an Owner may submit a bill addressed to another company with a reason.
    const override = !!data.override;
    return {
      ...data.bill_check,
      override,
      refusedSubmit:
        !!data.refused || (!!data.bill_check.refuse?.length && !override),
    };
  }
  return null;
}

const SOURCE: Record<string, string> = {
  qr: "the e-invoice QR code",
  text: "the PDF's text",
  ocr: "OCR",
};

function readFrom(source?: string): string {
  return (source ?? "")
    .split("+")
    .filter(Boolean)
    .map((s) => SOURCE[s] ?? s)
    .join(" and ");
}

function Result({ row, doc }: { row: CheckRow; doc: string }) {
  const label =
    row.result === "same"
      ? row.key.endsWith("_hsn")
        ? "✓ Same heading"
        : "✓ Same"
      : row.result === "written"
        ? "Written differently"
        : row.result === "not_read"
          ? "Not read"
          : row.result === "info"
            ? row.note || `From the ${doc}`
            : row.note || "Differs";
  const cls =
    row.result === "same"
      ? "pill on"
      : row.result === "differs"
        ? "pill bad"
        : row.result === "written"
          ? "pill warn"
          : "pill";
  return (
    <>
      <span className={cls}>{label}</span>
      {row.result === "written" && row.note && (
        <div className="small">{row.note}</div>
      )}
    </>
  );
}

/** Words for the box: the invoice's Bill Check, or the Goods Receipt's Challan Check. */
export type CheckWords = { title: string; doc: string; entry: string };
export const BILL_WORDS: CheckWords = { title: "Bill Check", doc: "bill", entry: "entry" };
export const CHALLAN_WORDS: CheckWords = { title: "Challan Check", doc: "challan", entry: "receipt" };

const title = (w: string) => w.charAt(0).toUpperCase() + w.slice(1);

export function CheckTable({ rows, words = BILL_WORDS }: { rows: CheckRow[]; words?: CheckWords }) {
  let group = "";
  return (
    <table className="grid bill-check">
      <thead>
        <tr>
          <th>Check</th>
          <th>In This {title(words.entry)}</th>
          <th>On Supplier's {title(words.doc)}</th>
          <th>Result</th>
        </tr>
      </thead>
      <tbody>
        {rows.flatMap((r) => {
          const out = [];
          if (r.group && r.group !== group) {
            group = r.group;
            out.push(
              <tr key={`g-${r.key}`} className="bill-check-group">
                <td colSpan={4}>{r.group}</td>
              </tr>,
            );
          }
          out.push(
            <tr
              key={r.key}
              className={
                r.result === "differs" || r.result === "written"
                  ? "bill-check-bad"
                  : undefined
              }
            >
              <td className="bill-check-label">{r.label}</td>
              <td>{r.entry || "—"}</td>
              <td>
                {r.bill || "—"}
                {r.source && <span className="small"> {r.source}</span>}
              </td>
              <td>
                <Result row={r} doc={words.doc} />
              </td>
            </tr>,
          );
          return out;
        })}
      </tbody>
    </table>
  );
}

function headlineOf(c: BillCheck): string {
  if (c.refuse?.length) return c.refuse.join(" ");
  return c.headline || "";
}

/** "Bill Check" box on a purchase invoice (Sidharth, 2026-11-26, preview 108a): the supplier's
 * bill in Attachments is read once (QR code, the PDF's text, or OCR) and compared with the entry.
 * The Goods Receipt's "Challan Check" (preview 109a) is the same box: pass `path` and `words`. */
export function BillCheckBox(props: {
  invoiceId: number;
  stamp: string;
  canSeen: boolean;
  path?: string;
  words?: CheckWords;
}) {
  const { invoiceId, stamp, canSeen } = props;
  const words = props.words ?? BILL_WORDS;
  const path = props.path ?? `v1/purchase-invoices/${invoiceId}/bill-check/`;
  const [check, setCheck] = useState<BillCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [seeing, setSeeing] = useState(false);
  const [reason, setReason] = useState("");

  const run = useCallback(
    async (again: boolean, attachment?: number) => {
      setBusy(true);
      setError("");
      try {
        setCheck(
          await api<BillCheck>(
            path,
            { again, attachment },
          ),
        );
      } catch (err) {
        setError((err as Error).message);
      }
      setBusy(false);
    },
    [path],
  );

  useEffect(() => {
    let live = true;
    api<BillCheck>(path).then(
      (c) => {
        if (!live) return;
        setCheck(c);
        // A bill not read yet is read straight away (it takes a few seconds for a scan).
        if (!c.checked && c.file) run(false);
      },
      (err) => live && setError((err as Error).message),
    );
    return () => {
      live = false;
    };
  }, [path, stamp, run]);

  const markSeen = async () => {
    setError("");
    try {
      setCheck(
        await api<BillCheck>(
          `${path}seen/`,
          { reason },
        ),
      );
      setSeeing(false);
      setReason("");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (!check) return null;
  const n = check.differences ?? 0;
  const refused = !!check.refuse?.length;
  const summary = busy
    ? `Reading the ${words.doc}…`
    : !check.file
      ? `No ${words.doc} attached`
      : !check.checked
        ? "Not checked yet"
        : check.error && !check.rows?.length
          ? "Could not read"
          : refused
            ? `Wrong ${words.doc}?`
            : n
              ? `${n} difference${n === 1 ? "" : "s"}`
              : "Matches";
  const headline = headlineOf(check);
  return (
    <Fold title={words.title} summary={summary} open={!!check.file}>
      {!check.file && (
        <p className="small">
          {words.doc === "challan"
            ? `Add the supplier's challan or invoice (a PDF or photo, type "Supplier's challan") in Attachments, and it is checked against what was received.`
            : `Add the supplier's bill (a PDF or photo, type "Supplier's invoice") in Attachments, and it is checked against this entry.`}
        </p>
      )}
      {busy && (
        <p className="popup-wait" role="status">
          Reading {check.file?.filename}… a scanned page takes a few seconds.
        </p>
      )}
      {!busy && check.checked && (
        <>
          {check.error && !check.rows?.length && (
            <p className="use-note">{check.error}</p>
          )}
          {headline && (
            <p className={refused || n ? "bill-check-alert" : "use-note"}>
              {headline}
            </p>
          )}
          {!!check.rows?.length && !n && !refused && (
            <p className="use-note">
              The supplier's {words.doc} matches this {words.entry} wherever it
              could be read.
            </p>
          )}
          {!!check.rows?.length && <CheckTable rows={check.rows} words={words} />}
          {check.seen_reason && (
            <p className="small">
              {refused ? "Submitted anyway by" : "Differences accepted by"}{" "}
              {check.seen_by_name}: {check.seen_reason}
            </p>
          )}
          {seeing && (
            <div className="bill-check-seen">
              <label htmlFor="bill-check-reason">
                Why Are the Differences All Right?
              </label>
              <input
                id="bill-check-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. 5 Pcs short received, debit note to follow"
                autoFocus
              />
              <button
                type="button"
                onClick={markSeen}
                disabled={!reason.trim()}
              >
                Save
              </button>
              <button
                type="button"
                className="link"
                onClick={() => setSeeing(false)}
              >
                Cancel
              </button>
            </div>
          )}
        </>
      )}
      {error && <p className="error">{error}</p>}
      {check.file && !busy && (
        <div className="bill-check-foot">
          <button
            type="button"
            className="link"
            onClick={() => run(true, check.file?.id)}
          >
            Check Again
          </button>
          {canSeen &&
            check.checked &&
            n > 0 &&
            !refused &&
            !check.seen_reason &&
            !seeing && (
              <button
                type="button"
                className="link"
                onClick={() => setSeeing(true)}
              >
                Mark as Seen…
              </button>
            )}
          {check.checked && (
            <span className="small">
              Read from {check.file.filename}
              {check.source ? ` (${readFrom(check.source)})` : ""}
              {check.read_by_name ? ` · checked by ${check.read_by_name}` : ""}
            </span>
          )}
        </div>
      )}
    </Fold>
  );
}

/** Submit refused because the bill differs (preview 108b): the differences, and Submit with a reason. */
export function BillCheckPopup(props: {
  check: BillCheck & { refusedSubmit: boolean; override?: boolean };
  busy: boolean;
  onSubmit: (reason: string) => void;
  onClose: () => void;
  words?: CheckWords;
}) {
  const { check } = props;
  const words = props.words ?? BILL_WORDS;
  const heading = `The supplier's ${words.doc} does not match this ${words.entry}`;
  const [reason, setReason] = useState("");
  const rows = (check.rows ?? []).filter(
    (r) => r.result === "differs" || r.result === "written",
  );
  const hard = !!check.refuse?.length;
  return (
    <div
      className="popup-back"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && props.onClose()}
    >
      <div
        className="popup grn-check"
        role="dialog"
        aria-modal="true"
        aria-label={heading}
      >
        <h3>{heading}</h3>
        {headlineOf(check) && (
          <p className="bill-check-alert">{headlineOf(check)}</p>
        )}
        <CheckTable rows={rows} words={words} />
        {props.check.refusedSubmit ? (
          <p className="small">
            {hard
              ? `This ${words.doc} cannot be submitted against this ${words.entry}. Check the supplier, the company or the file.`
              : `Correct the ${words.entry} first: only an Owner may submit it as it is.`}
          </p>
        ) : (
          <>
            {hard && (
              <p className="small">
                As an Owner you may submit it anyway, for example when the
                supplier will not correct the e-invoice. The red note stays on
                the {words.title}.
              </p>
            )}
            <label htmlFor="bill-check-submit-reason">
              To Go Ahead Anyway, Say Why (Kept in Activity)
            </label>
            <input
              id="bill-check-submit-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={
                hard
                  ? "e.g. Supplier raised the e-invoice to the wrong GSTIN, credit note asked for"
                  : "e.g. 5 Pcs short received, debit note to follow"
              }
              autoFocus
            />
          </>
        )}
        <div className="popup-actions">
          <button type="button" className="link" onClick={props.onClose}>
            Cancel
          </button>
          {!props.check.refusedSubmit && (
            <button
              type="button"
              disabled={!reason.trim() || props.busy}
              onClick={() => props.onSubmit(reason.trim())}
            >
              {hard ? "Submit Anyway" : "Submit with Reason"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
