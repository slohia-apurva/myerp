import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";

/** The items an entry form's item pickers offer, asked from the server as the
 * person types instead of loading every item when the form opens (12,457 items
 * on staging, Sidharth 2026-11-24).
 *
 * `url` is the form's own items address with its query (supplier, date…), or null
 * while it cannot be asked yet. `lineIds` are the items already on the lines: they
 * are always fetched, so the lines show their names and details. Pass `onType`
 * to every item `Combobox` (its `onType` prop). `items` holds every item fetched
 * for this url, sorted by name, so `items.find(...)` keeps working. `again` (the
 * screen's `useReturns()` count) asks afresh when the person comes back to the tab. */
export function useItemSearch<T extends { id: number; name: string }>(
  url: string | null,
  lineIds: (string | number | null | undefined)[],
  again?: number,
) {
  const [rows, setRows] = useState<Map<number, T>>(new Map());
  const [typed, setTyped] = useState("");
  const [q, setQ] = useState("");
  const lastQ = useRef<string | null>(null); // the search last asked, so it is not asked twice
  const loading = useRef(false); // a fresh start is on its way with the lines' items
  const ids = [...new Set(lineIds.map((v) => String(v ?? "")).filter((v) => /^\d+$/.test(v)))].sort().join(",");
  const ask = (extra: string) => api<T[]>(`${url}${url?.includes("?") ? "&" : "?"}search=1${extra}`);
  const keep = (got: T[], fresh = false) =>
    setRows((prev) => {
      const m = fresh ? new Map<number, T>() : new Map(prev);
      for (const r of got) m.set(r.id, r);
      return m;
    });

  // Typing waits a moment so each key press does not ask the server.
  useEffect(() => {
    const t = setTimeout(() => setQ(typed.trim()), 250);
    return () => clearTimeout(t);
  }, [typed]);

  // A new supplier, customer, date or place: start afresh (rates and names differ).
  useEffect(() => {
    if (!url) return setRows(new Map());
    let live = true;
    lastQ.current = q;
    loading.current = true;
    ask(`&q=${encodeURIComponent(q)}&ids=${ids}`)
      .then(
        (r) => live && keep(r, true),
        () => live && setRows(new Map()),
      )
      .finally(() => {
        if (live) loading.current = false;
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, again]);

  // What was typed.
  useEffect(() => {
    if (!url || lastQ.current === q) return;
    lastQ.current = q;
    let live = true;
    ask(`&q=${encodeURIComponent(q)}`).then((r) => live && keep(r), () => undefined);
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  // Items on the lines that were not fetched yet (an opened draft, a copied order).
  useEffect(() => {
    if (!url || !ids || loading.current) return;
    const missing = ids.split(",").filter((id) => !rows.has(Number(id)));
    if (!missing.length) return;
    ask(`&ids=${missing.join(",")}`).then((r) => keep(r), () => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids, url]);

  const items = useMemo(() => [...rows.values()].sort((a, b) => a.name.localeCompare(b.name)), [rows]);
  return { items, onType: setTyped };
}
