/* "Create …" from a dropdown (Sidharth, 2026-11-11).
 *
 * When what you type in a master's dropdown is not in its list, the list
 * offers 'Create "<what you typed>"'. That opens the master's own screen in a
 * new browser tab, with the Add form open and the name filled in, so nothing
 * on the screen you were on is lost. Saving there runs the master's full
 * checks (and the server's permission check); the new tab tells the first one
 * over a BroadcastChannel, closes itself, and the dropdown reloads its list and
 * picks the new record.
 */
import { useEffect, useRef, useState } from "react";

/** What a Combobox needs to offer "Create …" for its master. */
export type Creatable = {
  kind: string; // the master, as in existingHref (ErrorNote.tsx): "unit", "brand", ...
  href: (name: string) => string; // its screen with ?new=<name>
  reload: () => unknown; // reload the dropdown's list (may return a promise)
};

const CHANNEL = "myerp-created";

export type Created = { kind: string; id: number; name: string };

/** The name to start an Add form with when this tab was opened by "Create …"
 * (#/units?new=Kilogram), or null. */
export function newName(): string | null {
  const query = window.location.hash.split("?")[1] ?? "";
  const name = new URLSearchParams(query).get("new");
  return name && name.trim() ? name.trim() : null;
}

/** `?new=<name>` for this page, read once when it opens. */
export function useNewName(): string | null {
  const [name] = useState(newName);
  return name;
}

/** Call after a master's Add form saves. Tells the tab that asked for it,
 * and closes this tab if it was opened for that. */
export function announceCreated(kind: string, record: { id: number; name: string }) {
  const opened = newName() !== null;
  try {
    const channel = new BroadcastChannel(CHANNEL);
    channel.postMessage({ kind, id: record.id, name: record.name } satisfies Created);
    channel.close();
  } catch {
    // Very old browsers: the person picks the new record by hand.
  }
  if (opened) window.close(); // allowed: the tab was opened by script
}

/** Listen for records of `kind` saved in another tab. */
export function useCreated(kind: string | undefined, onCreated: (c: Created) => void) {
  const handler = useRef(onCreated);
  handler.current = onCreated;
  useEffect(() => {
    if (!kind || typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = (e: MessageEvent<Created>) => {
      if (e.data?.kind === kind) handler.current(e.data);
    };
    return () => channel.close();
  }, [kind]);
}

/** Open the master's screen in a new tab, with the Add form filled in. */
export function openCreate(create: Creatable, name: string) {
  window.open(create.href(name), "_blank");
}

/** "Create …" for the master whose screen is at #/<page> (for example
 * "units" or "companies/3/branches"). */
export function creatable(kind: string, page: string, reload: () => unknown, extra = ""): Creatable {
  return {
    kind,
    href: (name) => `${window.location.pathname}${window.location.search}#/${page}?new=${encodeURIComponent(name)}${extra ? `&${extra}` : ""}`,
    reload,
  };
}

/** Tell the other tabs a record of `kind` was saved (for a list to refresh and select it). */
export function announceSaved(kind: string, record: { id: number; name: string }) {
  try {
    const channel = new BroadcastChannel(CHANNEL);
    channel.postMessage({ kind, id: record.id, name: record.name } satisfies Created);
    channel.close();
  } catch {
    // Very old browsers: the list is refreshed by hand.
  }
}

/** "Close" / "Cancel" on a page: back to the screen it was opened from in this tab
 * (Sidharth, 2026-11-25). A tab opened by the page itself ("Create …", print, Ctrl+click) is
 * closed; a tab the person opened by hand cannot be closed by script, so after a moment `stay`
 * runs instead (show the list there). */
export function closeThisTab(stay: () => void) {
  if (window.history.state?.myerpBack) {
    window.history.back();
    return;
  }
  window.close();
  setTimeout(() => {
    if (!window.closed) stay();
  }, 300);
}
