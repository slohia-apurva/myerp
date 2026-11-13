import type { FormEvent, ReactNode } from "react";
import { PageHeader } from "./Brand";
import { ErrorNote } from "./ErrorNote";

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

/** The add / change / view page of a master, alone in its own tab (Sidharth, 2026-11-13):
 * Cancel and Save in the green band, the fields in boxes on the left, and Switches (the
 * "Disabled" tick), Tips and Activity on the right. */
export function FormPage(props: {
  title: string;
  sub?: string;
  formId: string;
  onSubmit: (event: FormEvent) => void;
  onCancel: () => void;
  busy?: boolean;
  error?: unknown;
  /** Only for a record being changed: the "Disabled" tick. */
  disabled?: { value: boolean; set: (v: boolean) => void };
  /** Only people who may look, not change: no Save, and the fields stay as shown. */
  readOnly?: boolean;
  tips?: ReactNode;
  activity?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="page item-edit">
      <PageHeader
        title={props.title}
        sub={props.sub}
        actions={
          <>
            <button type="button" className="link" onClick={props.onCancel}>
              {props.readOnly ? "Close" : "Cancel"}
            </button>
            {!props.readOnly && (
              <button type="submit" form={props.formId} disabled={props.busy}>
                Save
              </button>
            )}
          </>
        }
      />
      <form id={props.formId} className="side-layout" onSubmit={props.onSubmit}>
        <div className="side-main">
          <fieldset className="plain" disabled={props.readOnly}>
            {props.children}
          </fieldset>
          <ErrorNote error={props.error} />
        </div>
        <div className="side-col">
          {props.disabled && (
            <SidePanel title="Switches">
              <div className="item-switches">
                <label className="check">
                  <input
                    type="checkbox"
                    disabled={props.readOnly}
                    checked={props.disabled.value}
                    onChange={(e) => props.disabled!.set(e.target.checked)}
                  />
                  Disabled
                </label>
              </div>
            </SidePanel>
          )}
          <SidePanel title="Tips">
            <p className="small">A red * marks a field that must be filled in.</p>
            {props.tips}
          </SidePanel>
          {props.activity && <SidePanel title="Activity">{props.activity}</SidePanel>}
        </div>
      </form>
    </section>
  );
}
