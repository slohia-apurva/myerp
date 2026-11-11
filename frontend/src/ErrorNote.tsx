import { useCallback, useEffect, useState } from "react";
import { ApiError, type Existing } from "./api";

/** Where the screen for a master record lives, for the "Open" link shown
 * when a save is refused as a duplicate (core/duplicates.py). */
export function existingHref(e: Existing): string | null {
  const company = e.company ? `#/companies/${e.company}` : "";
  switch (e.kind) {
    case "unit":
      return `#/units?open=${e.id}`;
    case "item":
      return `#/items?open=${e.id}`;
    case "brand":
      return `#/brands?open=${e.id}`;
    case "item_group":
      return `#/item-groups?open=${e.id}`;
    case "credit_term":
      return `#/credit-terms?open=${e.id}`;
    case "role":
      return `#/roles?open=${e.id}`;
    case "user":
      return `#/users?open=${e.id}`;
    case "company":
      return `#/companies/${e.id}`;
    case "branch":
      return company && `${company}/branches?open=${e.id}`;
    case "ledger_group":
      return company && `${company}/groups?open=${e.id}`;
    case "ledger":
      return company && `${company}/ledgers?open=${e.id}`;
    case "courier_account":
      return company && `${company}/couriers?open=${e.id}`;
    default:
      return null;
  }
}

/** A form's error line. When the save was refused because the record
 * already exists, it also links to that record. Takes the caught error
 * (or a plain message). */
export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  const existing = error instanceof ApiError ? error.existing : undefined;
  const href = existing && existingHref(existing);
  return (
    <p className="error">
      {message}
      {href && (
        <>
          {" "}
          <a href={href}>Open “{existing.name}”</a>
        </>
      )}
    </p>
  );
}

/** The record named by `?open=ID` in the address (#/units?open=5), which
 * the page should open. Call `opened()` once it has: that takes `?open=`
 * off the address so the same link works again later. */
export function useOpenParam(): [number | null, () => void] {
  const [id, setId] = useState(readOpen);
  useEffect(() => {
    const onHash = () => setId(readOpen());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const opened = useCallback(() => {
    setId(null);
    const [path, query] = window.location.hash.split("?");
    if (!query) return;
    const params = new URLSearchParams(query);
    params.delete("open");
    const rest = params.toString();
    const url = `${window.location.pathname}${window.location.search}${path}${rest ? `?${rest}` : ""}`;
    window.history.replaceState(null, "", url);
  }, []);
  return [id, opened];
}

function readOpen(): number | null {
  const query = window.location.hash.split("?")[1] ?? "";
  const id = Number(new URLSearchParams(query).get("open"));
  return id > 0 ? id : null;
}
