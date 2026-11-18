/* Dropdown lists stay up to date (Sidharth, 2026-11-18).
 *
 * Every function opens in its own browser tab, so a record is often added in
 * another tab or window while a form is open here (a ledger that was missing
 * from the list, say). A screen loads its dropdown lists when it opens; these
 * hooks load them again whenever the person comes back to this tab or window,
 * so the new record is already in the list. Only the lists are read again:
 * what is typed on the form stays as it is.
 */
import { useEffect, useRef, useSyncExternalStore } from "react";

let returns = 0;
let last = 0;
const listeners = new Set<() => void>();

function cameBack() {
  // Switching tabs fires both "visibilitychange" and "focus": count it once.
  const now = Date.now();
  if (now - last < 1000) return;
  last = now;
  returns += 1;
  listeners.forEach((f) => f());
}

if (typeof window !== "undefined") {
  window.addEventListener("focus", cameBack);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") cameBack();
  });
}

function subscribe(f: () => void) {
  listeners.add(f);
  return () => {
    listeners.delete(f);
  };
}

/** How many times the person has come back to this page. Add it to the
 * dependencies of an effect that loads a dropdown's list. */
export function useReturns(): number {
  return useSyncExternalStore(subscribe, () => returns);
}

/** Run `reload` (a list loader) each time the person comes back to this page. */
export function useOnReturn(reload: () => unknown) {
  const ref = useRef(reload);
  ref.current = reload;
  useEffect(
    () =>
      subscribe(() => {
        ref.current();
      }),
    [],
  );
}
