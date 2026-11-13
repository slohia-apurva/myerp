import type { ReactNode } from "react";

/** Pieces every master screen shares in the new layout (Sidharth, 2026-11-13):
 * a right-hand column of panels, folding sections, and pages that open in a new tab. */

/** A panel in the right-hand column: a light green title strip over a white body. */
export function SidePanel(props: { title: string; tag?: string; children: ReactNode }) {
  return (
    <section className="side-panel">
      <h3>
        {props.title}
        {props.tag && <em>{props.tag}</em>}
      </h3>
      <div className="side-body">{props.children}</div>
    </section>
  );
}

/** Label on the left, value against the right edge; empty values are left out. */
export function SideRows({ rows }: { rows: [string, string][] }) {
  return (
    <>
      {rows
        .filter(([, v]) => v)
        .map(([k, v]) => (
          <div key={k} className="side-row">
            <span>{k}</span>
            <span>{v}</span>
          </div>
        ))}
    </>
  );
}

/** A folding section: the title strip always shows a one-line summary of what is inside. */
export function Fold(props: { title: string; summary?: string; open?: boolean; children?: ReactNode }) {
  return (
    <details className="fold" open={props.open}>
      <summary>
        <span className="fold-title">{props.title}</span>
        {props.summary && <span className="fold-summary">{props.summary}</span>}
      </summary>
      {props.children && <div className="fold-body">{props.children}</div>}
    </details>
  );
}

/** A value from the query part of the page address, for example `form` in #/items?form=3. */
export function hashParam(name: string): string | null {
  const query = window.location.hash.split("?")[1] ?? "";
  return new URLSearchParams(query).get(name);
}

/** Every function opens in a new browser tab, beside the list (Sidharth, 2026-11-13). */
export function openTab(hash: string) {
  window.open(`${window.location.pathname}${window.location.search}${hash}`, "_blank");
}
