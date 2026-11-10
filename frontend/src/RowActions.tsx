import { useState, type ReactNode } from "react";
import { api } from "./api";

/** The two action cells at the end of a table row: "Edit" (or "View" for
 * people who may only look), and "Duplicate" in a column of its own so the
 * words line up down the table. */
export function ActionCells(props: {
  canEdit: boolean;
  /** Who may duplicate; defaults to whoever may edit. */
  canDuplicate?: boolean;
  onOpen: () => void;
  onDuplicate?: () => void;
}) {
  return (
    <>
      <td className="act">
        <button className="link" onClick={props.onOpen}>
          {props.canEdit ? "Edit" : "View"}
        </button>
      </td>
      <td className="act">
        {(props.canDuplicate ?? props.canEdit) && props.onDuplicate && (
          <button className="link quiet" onClick={props.onDuplicate}>
            Duplicate
          </button>
        )}
      </td>
    </>
  );
}

/** Heading cells to match ActionCells. */
export function ActionHeads() {
  return (
    <>
      <th />
      <th />
    </>
  );
}

/** The fields of a form, locked when the person may only view the record. */
export function FormBody({ readOnly, children }: { readOnly?: boolean; children: ReactNode }) {
  return (
    <fieldset className="plain" disabled={readOnly}>
      {children}
    </fieldset>
  );
}

/** "Disable" (or "Enable") button shown only while editing an existing
 * record. It saves at once, after a confirmation. */
export function ActiveButton(props: {
  url: string;
  active: boolean;
  what: string; // e.g. "credit terms", for the confirmation
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    const verb = props.active ? "Disable" : "Enable";
    if (!window.confirm(`${verb} ${props.what}?`)) return;
    setBusy(true);
    props.onError("");
    try {
      await api(props.url, { is_active: !props.active }, "PATCH");
      props.onDone();
    } catch (err) {
      props.onError((err as Error).message);
      setBusy(false);
    }
  };
  return (
    <button type="button" className={`link ${props.active ? "danger" : ""}`} disabled={busy} onClick={toggle}>
      {props.active ? "Disable" : "Enable"}
    </button>
  );
}
