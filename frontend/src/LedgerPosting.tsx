// What an entry posts to the books, and what stops it (Sidharth, 2026-11-17). Every entry screen
// that posts uses both: the "Ledger Posting" section once the entry is saved, and the popup
// listing every item group whose ledgers are not set when Submit is refused for that.
import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { money } from "./Companies";
import { Fold, openTab } from "./Master";

type PostingRow = {
  ledger: number | null;
  ledger_name: string;
  group_name: string;
  debit: string;
  credit: string;
  missing: boolean;
};
type Posting = {
  posted: boolean;
  reversed: boolean;
  rows: PostingRow[];
  note: string;
};

/**
 * The "Ledger Posting" section: Ledger, Ledger Group, Debit, Credit. On a draft it shows what Submit
 * will post; once submitted, what was posted. `url` answers as posting/api.py `preview` or `posted`;
 * change `stamp` to read it again (after each Save).
 */
export function LedgerPosting({
  url,
  stamp,
}: {
  url: string | null;
  stamp?: unknown;
}) {
  const [data, setData] = useState<Posting | null>(null);
  useEffect(() => {
    if (!url) return setData(null);
    api<Posting>(url).then(setData, () => setData(null));
  }, [url, stamp]);
  if (!url || !data) return null;
  const total = (key: "debit" | "credit") =>
    data.rows.reduce((s, r) => s + Number(r[key]), 0);
  const unset = data.rows.some((r) => r.missing);
  return (
    <Fold
      title="Ledger Posting"
      open
      summary={
        data.posted
          ? data.reversed
            ? "Reversed on cancel"
            : "Posted"
          : "Posts on Submit"
      }
    >
      {data.rows.length === 0 ? (
        <p className="small">Nothing to post yet: add the items received.</p>
      ) : (
        <div className="table-scroll">
          <table className="grid ledger-posting">
            <thead>
              <tr>
                <th>Ledger</th>
                <th>Ledger Group</th>
                <th className="num">Debit ₹</th>
                <th className="num">Credit ₹</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={r.ledger ?? `missing-${i}`}>
                  <td className={r.missing ? "bad-note" : undefined}>
                    {r.ledger_name}
                  </td>
                  <td>{r.group_name}</td>
                  <td className="num">
                    {Number(r.debit) ? money(r.debit) : ""}
                  </td>
                  <td className="num">
                    {Number(r.credit) ? money(r.credit) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={2}>Total</td>
                <td className="num">{money(total("debit"))}</td>
                <td className="num">{money(total("credit"))}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      {!data.posted && (
        <p className="small">
          {data.note}
          What Submit will post, from the last "Save".
          {unset
            ? " Set the missing ledgers on the item group (Masters › Item Groups) before Submit."
            : ""}
        </p>
      )}
      {data.reversed && (
        <p className="small">
          These entries were reversed when the entry was cancelled.
        </p>
      )}
    </Fold>
  );
}

export type MissingLedgers = {
  company: number;
  may_set: boolean;
  missing_accounts: {
    group: number;
    group_name: string;
    missing: string[];
    lines: string[];
  }[];
};

/** The refusal of a Submit whose items' groups lack their ledgers (posting/accounts.py), if `err` is one. */
export function missingLedgersOf(err: unknown): MissingLedgers | null {
  if (!(err instanceof ApiError) || !err.data || typeof err.data !== "object")
    return null;
  const data = err.data as Partial<MissingLedgers>;
  return Array.isArray(data.missing_accounts) && data.missing_accounts.length
    ? (data as MissingLedgers)
    : null;
}

/**
 * Every item group whose ledgers are missing, in one popup. A person who may change masters gets
 * "Set ledgers" (the item group in a new tab, at its ledgers); anyone else "Ask to set", a notice to
 * those who may. `document` names the entry in that notice, e.g. "the goods receipt from X".
 */
export function MissingLedgersPopup(props: {
  refusal: MissingLedgers;
  document: string;
  onClose: () => void;
}) {
  const { refusal } = props;
  const [asked, setAsked] = useState<Record<number, string>>({});
  const ask = (group: number) =>
    api(`v1/companies/${refusal.company}/ask-ledgers/`, {
      group,
      document: props.document,
    }).then(
      () => setAsked((a) => ({ ...a, [group]: "" })),
      (err) =>
        setAsked((a) => ({
          ...a,
          [group]: err instanceof Error ? err.message : String(err),
        })),
    );
  const failed = Object.values(asked).filter(Boolean);
  return (
    <div className="popup-back" role="presentation">
      <div
        className="popup grn-check"
        role="dialog"
        aria-modal="true"
        aria-label="Ledgers not set"
      >
        <h3>
          Can't submit yet: ledgers are not set on{" "}
          {refusal.missing_accounts.length === 1
            ? "this item group"
            : "these item groups"}
        </h3>
        <p>
          Each item posts to the "Stock Ledger" and "COGS/Expense Ledger" set on
          its main item group for this company. These are missing:
        </p>
        <table className="grid">
          <thead>
            <tr>
              <th>Item Group</th>
              <th>Items</th>
              <th>Missing</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {refusal.missing_accounts.map((g) => (
              <tr key={g.group}>
                <td>{g.group_name}</td>
                <td>
                  {g.lines.map((l) => (
                    <div key={l}>{l}</div>
                  ))}
                </td>
                <td className="bad-note">
                  {g.missing.map((m) => (
                    <div key={m}>{m}</div>
                  ))}
                </td>
                <td>
                  {refusal.may_set ? (
                    <button
                      type="button"
                      className="link"
                      onClick={() =>
                        openTab(`#/item-groups?form=${g.group}&at=ledgers`)
                      }
                    >
                      Set ledgers
                    </button>
                  ) : asked[g.group] === "" ? (
                    <button type="button" className="link" disabled>
                      Asked ✓
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="link"
                      onClick={() => ask(g.group)}
                    >
                      Ask to set
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {failed.length > 0 && <p className="error">{failed.join(" ")}</p>}
        <p className="small">
          {refusal.may_set
            ? '"Set ledgers" opens the item group in a new tab (Masters › Item Groups). Pick the ledgers for this company there and save, then Submit again.'
            : 'Your role cannot change item groups. "Ask to set" sends a notice under the bell to everyone whose role may change masters, naming the item group, the missing ledgers and this entry, with a link that opens the item group. Submit again once they have set it.'}{" "}
          Nothing has been submitted; "Save" keeps the draft.
        </p>
        <div className="popup-actions">
          <button type="button" onClick={props.onClose}>
            OK
          </button>
        </div>
      </div>
    </div>
  );
}
