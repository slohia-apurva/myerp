import { useState, type ReactNode } from "react";

/** One page of a long list, as the server sends it (Sidharth, 2026-11-24: 25 rows a page). */
export type Paged<T> = { count: number; page: number; pages: number; page_size: number; results: T[] };

/** The page numbers to show: the first, the last and those around the current one. */
function numbers(page: number, pages: number): (number | "gap")[] {
  const keep = new Set([1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages));
  const out: (number | "gap")[] = [];
  let last = 0;
  for (const n of [...keep].sort((a, b) => a - b)) {
    if (n - last > 1) out.push("gap");
    out.push(n);
    last = n;
  }
  return out;
}

/** "Showing 26–50 of 12,457 items" and the page buttons under a long list. */
export function Pager({ data, noun, onPage, children }: { data: Paged<unknown> | null; noun: string; onPage: (page: number) => void; children?: ReactNode }) {
  if (!data) return null;
  const from = (data.page - 1) * data.page_size + 1;
  const to = from + data.results.length - 1;
  const n = (v: number) => v.toLocaleString("en-IN");
  return (
    <div className="pager no-print">
      <span className="pager-left">
        {data.count > 0 && (
          <span className="small">
            Showing {n(from)}–{n(to)} of {n(data.count)} {noun}
          </span>
        )}
        {children}
      </span>
      {data.pages > 1 && (
        <span className="pages">
          <button type="button" className="secondary" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>
            ‹ Previous
          </button>
          {numbers(data.page, data.pages).map((p, i) =>
            p === "gap" ? (
              <span key={`gap${i}`}>…</span>
            ) : (
              <button
                key={p}
                type="button"
                className={p === data.page ? undefined : "secondary"}
                aria-current={p === data.page ? "page" : undefined}
                onClick={() => onPage(p)}
              >
                {n(p)}
              </button>
            ),
          )}
          <button type="button" className="secondary" disabled={data.page >= data.pages} onClick={() => onPage(data.page + 1)}>
            Next ›
          </button>
        </span>
      )}
    </div>
  );
}

const INACTIVE_KEY = "myerp.showInactive";

/** "Show Inactive Items": inactive records stay hidden unless ticked (Sidharth, 2026-11-24). The
 * tick is remembered in this browser, one setting for every list. */
export function useShowInactive(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem(INACTIVE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const set = (v: boolean) => {
    setOn(v);
    try {
      localStorage.setItem(INACTIVE_KEY, v ? "1" : "0");
    } catch {
      // private window: the tick lasts for this page only
    }
  };
  return [on, set];
}

/** The tick under a list, beside the page buttons. */
export function ShowInactive({ noun, on, onChange }: { noun: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="show-inactive">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} /> Show Inactive {noun}
    </label>
  );
}
