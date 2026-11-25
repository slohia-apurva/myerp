import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";

/** The id of the step this tab is on now (one per address visited), made on first ask. */
function stepId(): string {
  const state = window.history.state as { myerpStep?: string } | null;
  if (state?.myerpStep) return state.myerpStep;
  const id = Math.random().toString(36).slice(2, 10);
  window.history.replaceState({ ...(state ?? {}), myerpStep: id }, "");
  return id;
}

/**
 * Like `useState`, but kept for this step of the tab (Sidharth, 2026-11-25: screens open in the
 * same tab). When "Close" or the browser's Back comes back to a list or report, it shows the
 * same page, column searches, view and selected row as before; opened afresh from the menu, it
 * starts clean. Values must survive JSON (no Sets or Infinity).
 */
/** A value kept for this step of the tab under `name`, or null. */
export function keptGet<T>(name: string): T | null {
  try {
    const saved = window.sessionStorage.getItem(`kept:${stepId()}:${name}`);
    return saved === null ? null : (JSON.parse(saved) as T);
  } catch {
    return null;
  }
}

/** Keep a value for this step of the tab (see `useKept`). */
export function keptSet(name: string, value: unknown) {
  try {
    window.sessionStorage.setItem(`kept:${stepId()}:${name}`, JSON.stringify(value));
  } catch {
    // Storage full or blocked: nothing is kept.
  }
}

export function useKept<T>(name: string, initial: T | (() => T)): [T, Dispatch<SetStateAction<T>>] {
  const key = useMemo(() => `kept:${stepId()}:${name}`, [name]);
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = window.sessionStorage.getItem(key);
      if (saved !== null) return JSON.parse(saved) as T;
    } catch {
      // Private window or blocked storage: start clean.
    }
    return typeof initial === "function" ? (initial as () => T)() : initial;
  });
  useEffect(() => {
    try {
      window.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage full or blocked: the list simply starts clean next time.
    }
  }, [key, value]);
  return [value, setValue];
}
