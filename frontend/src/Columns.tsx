import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { MenuItem } from "./Exchange";

/** One column a list can show. `fixed` columns always show, first; `standard` ones show until the
 * person chooses their own. `search` names the server's column search for it (lists that search
 * the server); a column without one gets no search box. */
export type Column<T> = {
  key: string;
  label: string;
  fixed?: boolean;
  standard?: boolean;
  num?: boolean;
  /** Keep the cell on one line (dates). */
  nowrap?: boolean;
  search?: string;
  /** Lists that search on the screen: the words a search box under this column matches. */
  text?: (row: T) => string;
  /** Added up in the list's Total line (amounts). */
  total?: (row: T) => number;
  /** false: the heading cannot be clicked to sort (a figure worked out per company, say). */
  sort?: false;
  cell: (row: T) => ReactNode;
};

/**
 * "Choose Columns…" (Sidharth, 2026-11-24): each person picks and orders the columns of a list,
 * kept under their sign-in (v1/my-columns/<list>/) so it follows them to any computer. Returns the
 * columns to show, the menu item for the screen's "Actions ▾" and the pop-up.
 */
export function useColumns<T>(
  list: string,
  all: Column<T>[],
  /** sort: false for a list the server does not sort: its headings stay plain. */
  options: { sort?: false } = {},
): { shown: Column<T>[]; item: MenuItem; panel: ReactNode; sort: string; heading: (c: Column<T>) => ReactNode } {
  const [chosen, setChosen] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const sortable = options.sort !== false;
  // The column the list is sorted by: "hsn" A to Z, "-hsn" Z to A, "" the screen's own order. Kept
  // under the person's sign-in with their columns (Sidharth, 2026-11-24).
  const [sort, setSort] = useState("");
  useEffect(() => {
    api<{ columns: string[] }>(`v1/my-columns/${list}/`).then(
      (r) => setChosen(r.columns),
      () => undefined,
    );
    // A list the server does not sort keeps no sort to fetch.
    if (sortable)
      api<{ columns: string[] }>(`v1/my-columns/${list}-sort/`).then(
        (r) => setSort(r.columns[0] ?? ""),
        () => undefined,
      );
  }, [list, sortable]);
  const sortBy = (key: string) => {
    const next = sort === key ? `-${key}` : key;
    setSort(next);
    api(`v1/my-columns/${list}-sort/`, { columns: [next] }, "PUT").catch(() => undefined);
  };
  /** A heading: click to sort by it (▲ A to Z, ▼ Z to A); the others show a grey ⇅. */
  const heading = (c: Column<T>) => {
    if (c.sort === false || !sortable) return c.label;
    const on = sort === c.key ? "▲" : sort === `-${c.key}` ? "▼" : "";
    return (
      // A span, not a button, so Print still reads the heading; the arrow is left out of print.
      <span
        role="button"
        tabIndex={0}
        className={`sort-head${on ? " on" : ""}`}
        title={on === "▲" ? "Sorted A to Z: click for Z to A" : "Click to sort by this column"}
        onClick={() => sortBy(c.key)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            sortBy(c.key);
          }
        }}
      >
        {c.label}{" "}
        <span className="sort-arrow" aria-hidden="true">
          {on || "⇅"}
        </span>
      </span>
    );
  };
  const fixed = all.filter((c) => c.fixed);
  const byKey = new Map(all.map((c) => [c.key, c]));
  const picked = chosen.map((k) => byKey.get(k)).filter((c): c is Column<T> => !!c && !c.fixed);
  const shown = [...fixed, ...(picked.length ? picked : all.filter((c) => c.standard && !c.fixed))];
  const save = useCallback(
    async (keys: string[]) => {
      const r = await api<{ columns: string[] }>(`v1/my-columns/${list}/`, { columns: keys }, "PUT");
      setChosen(r.columns);
      setOpen(false);
    },
    [list],
  );
  const panel = open ? (
    <ChooseColumns all={all} shown={shown.map((c) => c.key)} onSave={save} onCancel={() => setOpen(false)} />
  ) : null;
  return { shown, item: { label: "Choose Columns…", onClick: () => setOpen(true) }, panel, sort, heading };
}

function ChooseColumns<T>(props: { all: Column<T>[]; shown: string[]; onSave: (keys: string[]) => Promise<void>; onCancel: () => void }) {
  // The order: fixed columns, then those shown, then the rest as the screen lists them.
  const start = () => {
    const rest = props.all.filter((c) => !c.fixed && !props.shown.includes(c.key)).map((c) => c.key);
    return [...props.shown.filter((k) => props.all.some((c) => c.key === k && !c.fixed)), ...rest];
  };
  const [order, setOrder] = useState<string[]>(start);
  const [on, setOn] = useState<Set<string>>(() => new Set(props.shown));
  const [drag, setDrag] = useState<string | null>(null);
  const [error, setError] = useState("");
  const label = (k: string) => props.all.find((c) => c.key === k)?.label ?? k;
  const move = (from: string, to: string) => {
    if (from === to) return;
    const next = order.filter((k) => k !== from);
    next.splice(next.indexOf(to), 0, from);
    setOrder(next);
  };
  const shift = (k: string, by: number) => {
    const at = order.indexOf(k);
    const to = at + by;
    if (to < 0 || to >= order.length) return;
    const next = [...order];
    [next[at], next[to]] = [next[to], next[at]];
    setOrder(next);
  };
  const run = (keys: string[]) => props.onSave(keys).catch((e: Error) => setError(e.message));
  return (
    <div className="popup-back" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && props.onCancel()}>
      <div className="popup choose-columns" role="dialog" aria-label="Choose Columns">
        <h3>Choose Columns</h3>
        <p className="small">Tick what this list shows for you. Drag ⋮⋮ (or use ▲ ▼) to change the order.</p>
        <ul>
          {props.all
            .filter((c) => c.fixed)
            .map((c) => (
              <li key={c.key} className="fixed">
                <span className="grip">⋮⋮</span>
                <label>
                  <input type="checkbox" checked disabled /> {c.label} <span className="small">(always shown)</span>
                </label>
              </li>
            ))}
          {order.map((k) => (
            <li
              key={k}
              draggable
              className={drag === k ? "dragging" : ""}
              onDragStart={() => setDrag(k)}
              onDragEnd={() => setDrag(null)}
              onDragOver={(e) => {
                e.preventDefault();
                if (drag) move(drag, k);
              }}
            >
              <span className="grip" title="Drag to move">
                ⋮⋮
              </span>
              <label>
                <input
                  type="checkbox"
                  checked={on.has(k)}
                  onChange={(e) => {
                    const next = new Set(on);
                    if (e.target.checked) next.add(k);
                    else next.delete(k);
                    setOn(next);
                  }}
                />{" "}
                {label(k)}
              </label>
              <span className="moves">
                <button type="button" className="link" aria-label={`Move ${label(k)} up`} onClick={() => shift(k, -1)}>
                  ▲
                </button>
                <button type="button" className="link" aria-label={`Move ${label(k)} down`} onClick={() => shift(k, 1)}>
                  ▼
                </button>
              </span>
            </li>
          ))}
        </ul>
        {error && <p className="error">{error}</p>}
        <div className="popup-actions">
          <button type="button" onClick={() => run(order.filter((k) => on.has(k)))} disabled={on.size === 0}>
            Save
          </button>
          <button type="button" className="secondary" onClick={props.onCancel}>
            Cancel
          </button>
          <button type="button" className="secondary" style={{ marginLeft: "auto" }} onClick={() => run([])} title="Back to the standard columns">
            Reset
          </button>
        </div>
      </div>
    </div>
  );
}

/** A list that searches on the screen: the rows whose columns hold every word typed under them. */
export function matching<T>(rows: T[], all: Column<T>[], search: Record<string, string>): T[] {
  const asked = all
    .filter((c) => c.text)
    .map((c) => ({ text: c.text!, words: (search[c.key] ?? "").toLowerCase().split(/\s+/).filter(Boolean) }))
    .filter((c) => c.words.length);
  if (!asked.length) return rows;
  return rows.filter((r) => asked.every((c) => {
    const value = c.text(r).toLowerCase();
    return c.words.every((w) => value.includes(w));
  }));
}

/** The headings of a list that searches on the screen, with a search box under each shown column. */
export function ListHeads<T>(props: {
  shown: Column<T>[];
  search: Record<string, string>;
  setSearch: (next: Record<string, string>) => void;
  heading?: (c: Column<T>) => ReactNode;
}) {
  return (
    <>
      <tr>
        {props.shown.map((c) => (
          <th key={c.key} className={c.num ? "num" : undefined}>
            {props.heading ? props.heading(c) : c.label}
          </th>
        ))}
      </tr>
      <tr className="col-search no-print">
        {props.shown.map((c) => (
          <th key={c.key}>
            {c.text && (
              <input
                type="search"
                aria-label={`Search ${c.label}`}
                placeholder="Search"
                value={props.search[c.key] ?? ""}
                onChange={(e) => props.setSearch({ ...props.search, [c.key]: e.target.value })}
              />
            )}
          </th>
        ))}
      </tr>
    </>
  );
}

/** One row's cells, in the person's columns. */
export function Cells<T>({ shown, row }: { shown: Column<T>[]; row: T }) {
  return (
    <>
      {shown.map((c) => (
        <td key={c.key} className={c.num ? "num" : c.nowrap ? "nowrap" : undefined}>
          {c.cell(row)}
        </td>
      ))}
    </>
  );
}

/** The "Total" line under a list: each shown column with a `total` added up, the word "Total" in
 * the first column; nothing when no amount column is shown. */
export function TotalRow<T>(props: { shown: Column<T>[]; rows: T[]; show: (n: number) => ReactNode; extra?: number }) {
  if (!props.shown.some((c) => c.total)) return null;
  return (
    <tfoot>
      <tr>
        {props.shown.map((c, i) => (
          <td key={c.key} className={c.total ? "num" : undefined}>
            {c.total ? props.show(Math.round(props.rows.reduce((sum, r) => sum + c.total!(r), 0) * 100) / 100) : i === 0 ? "Total" : null}
          </td>
        ))}
        {Array.from({ length: props.extra ?? 0 }, (_, i) => (
          <td key={`x${i}`} />
        ))}
      </tr>
    </tfoot>
  );
}
