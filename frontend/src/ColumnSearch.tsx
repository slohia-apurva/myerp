import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { keptGet, keptSet } from "./Keep";

/** Does every word typed in a column's box appear in that cell (capitals ignored)? */
const matches = (text: string, typed: string) => {
  const t = text.toLowerCase();
  return typed
    .toLowerCase()
    .split(/\s+/)
    .every((w) => t.includes(w));
};

/**
 * The row of search boxes under a master list's column headings (Sidharth, 2026-11-15). Put it in
 * the table's `<thead>`, right after the headings row: it adds a box under every column that has a
 * heading, and the list keeps only the rows that match every box (with the search box above the
 * list too). Rows are hidden, not dropped, so printing leaves them out as well.
 *
 * A list that only holds the first rows of a long central list (HSN, PIN codes) passes `onSearch`
 * instead: the boxes then ask the server, and nothing is hidden here.
 */
export function ColumnSearch(props: { onSearch?: (values: string[]) => void }) {
  const row = useRef<HTMLTableRowElement>(null);
  const [heads, setHeads] = useState<boolean[]>([]);
  const [values, setValues] = useState<string[]>([]);
  // What was typed is kept for when "Close" comes back to the list (Keep.ts), under the
  // column headings, so two lists on one screen keep theirs apart.
  const [keepAs, setKeepAs] = useState("");
  const [none, setNone] = useState(false);

  // Which columns have a heading: the headings row is the one just above.
  useLayoutEffect(() => {
    const above = row.current?.previousElementSibling;
    if (!above) return;
    // A heading marked `data-no-search` (a figure the server cannot search, like In Stock) gets no box.
    setHeads(Array.from(above.children).map((th) => (th.textContent ?? "").trim() !== "" && !(th as HTMLElement).hasAttribute("data-no-search")));
    const name = `cols:${Array.from(above.children)
      .map((th) => (th.textContent ?? "").trim())
      .join("|")}`;
    setKeepAs(name);
    const kept = keptGet<string[]>(name);
    if (kept) setValues(kept);
  }, []);
  useEffect(() => {
    if (keepAs) keptSet(keepAs, values);
  }, [keepAs, values]);

  const typed = values.some((v) => v.trim() !== "");
  const onSearch = props.onSearch;
  useEffect(() => {
    if (onSearch) onSearch(values);
  }, [onSearch, values]);

  // Hide the rows that do not match; again whenever the list redraws.
  useEffect(() => {
    if (onSearch) return;
    const body = row.current?.closest("table")?.tBodies[0];
    if (!body) return;
    const apply = () => {
      let shown = 0;
      let rows = 0;
      for (const tr of Array.from(body.rows)) {
        // A message row ("Nothing matches", "No units yet") spans the table: leave it alone.
        if (tr.cells.length < heads.length) continue;
        rows += 1;
        const keep = !typed || values.every((v, i) => !v.trim() || matches(tr.cells[i]?.textContent ?? "", v.trim()));
        if (tr.hidden === keep) tr.hidden = !keep;
        if (keep) shown += 1;
      }
      setNone(typed && rows > 0 && shown === 0);
    };
    apply();
    const watch = new MutationObserver(apply);
    watch.observe(body, { childList: true, subtree: true, characterData: true });
    return () => {
      watch.disconnect();
      for (const tr of Array.from(body.rows)) tr.hidden = false;
    };
  }, [onSearch, heads, values, typed]);

  return (
    <>
      <tr className="col-search no-print" ref={row}>
        {heads.map((on, i) => (
          <th key={i}>
            {on && (
              <input
                type="search"
                placeholder="Search"
                aria-label={`Search ${(row.current?.previousElementSibling?.children[i]?.textContent ?? "").trim()}`}
                value={values[i] ?? ""}
                onChange={(e) => {
                  const next = heads.map((_, j) => values[j] ?? "");
                  next[i] = e.target.value;
                  setValues(next);
                }}
              />
            )}
          </th>
        ))}
      </tr>
      {none && (
        <tr className="col-search-none">
          <th colSpan={heads.length} className="small">
            Nothing matches the column searches.
          </th>
        </tr>
      )}
    </>
  );
}
