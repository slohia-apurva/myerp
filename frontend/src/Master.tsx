import type { FormEvent, ReactNode } from "react";
import { PageHeader } from "./Brand";
import { ErrorNote } from "./ErrorNote";

/** Pieces every master screen shares in the new layout (Sidharth, 2026-11-13):
 * a right-hand column of panels, folding sections, and pages that open in the same tab. */

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
        .map(([k, v], n) => (
          // By place: an entry may list the same item on several lines.
          <div key={n} className="side-row">
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

/** Screens open in the same tab (Sidharth, 2026-11-25: too many tabs; was a new tab for
 * everything since 2026-11-13). Takes a page address ("#/…") or a server path ("/api/…", a PDF):
 * - a page opens here, and its "Close" or "Cancel" comes back (see `closeThisTab`);
 * - a print page ("?print=") or a server file opens in the one shared print tab;
 * - a download ("download=1") just downloads, with no tab;
 * - Ctrl+click (or Cmd+click) on the button still opens a new tab, for two side by side.
 * A server path is opened as it is: put after the page's own path it would read "//api/…",
 * which the browser takes for a web site called "api". */
export function openTab(target: string) {
  const url = target.startsWith("/") ? target : `${window.location.pathname}${window.location.search}${target}`;
  if (target.startsWith("/") && /[?&]download=1/.test(target)) {
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } else if (wantsNewTab()) window.open(url, "_blank");
  else if (target.startsWith("/") || /[?&]print=/.test(target)) window.open(url, PRINT_TAB);
  else goTo(target);
}

/** Only where the person must come back to a half-filled form ("Set ledgers", "Request
 * Addition"; "Create …" in a dropdown has its own, Create.tsx): a new tab. */
export function openNewTab(target: string) {
  window.open(target.startsWith("/") ? target : `${window.location.pathname}${window.location.search}${target}`, "_blank");
}

/** The one tab every print and PDF shares, so printing never piles up tabs. */
const PRINT_TAB = "myerp-print";

/** Go to a page address in this tab, as a step "Close" can come back from. */
export function goTo(hash: string) {
  if (hash === window.location.hash) return;
  window.history.pushState({ myerpBack: true }, "", `${window.location.pathname}${window.location.search}${hash}`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/** Was this page reached from another screen in this tab (so "Close" goes back to it)? */
export const cameFromAnotherScreen = () => Boolean(window.history.state?.myerpBack);

/** Ctrl / Cmd / Shift held on the click being handled now (cleared once it is done). */
let newTabClick = false;
const wantsNewTab = () => newTabClick;

/** Once, at start: remember Ctrl / Cmd clicks (for `openTab`), and let plain links to other
 * screens ("#/…") open here as a step "Close" comes back from. */
export function followLinksHere() {
  window.addEventListener(
    "click",
    (e) => {
      newTabClick = e.ctrlKey || e.metaKey || e.shiftKey;
      if (newTabClick) setTimeout(() => (newTabClick = false));
    },
    true,
  );
  window.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const a = (e.target as Element | null)?.closest?.("a");
    const href = a?.getAttribute("href") ?? "";
    if (!a || !href.startsWith("#/") || (a.target && a.target !== "_self") || a.hasAttribute("download")) return;
    e.preventDefault();
    goTo(href);
  });
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
  /** More ticks for the Switches box (beside "Disabled"). */
  switches?: ReactNode;
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
          {(props.disabled || props.switches) && (
            <SidePanel title="Switches">
              <div className="item-switches">
                {props.disabled && (
                  <label className="check">
                    <input
                      type="checkbox"
                      disabled={props.readOnly}
                      checked={props.disabled.value}
                      onChange={(e) => props.disabled!.set(e.target.checked)}
                    />
                    Disabled
                  </label>
                )}
                {props.switches}
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
