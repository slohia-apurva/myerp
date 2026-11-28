import { useEffect, useState } from "react";
import { api } from "./api";
import type { MenuItem } from "./Exchange";
import { openTab } from "./Master";

/** "Connections" on every entry's view (Sidharth, 2026-11-26, previews
 * mockups/connections/1 and 2): the entries this one came from, the ones made
 * from it, and the returns, notes and adjustments against it, grouped, each with
 * its number, date and status. A number opens that entry here (same tab; "Close"
 * comes back). "+" makes a new linked entry as "Create ▾" does: the screen passes
 * `create` with the kinds it may make now. Read from
 * v1/companies/<company>/connections/<kind>/<id>/ (posting/connections.py).
 *
 * On a party or an item (kind "party" / "item", preview mockups/connections/3) the
 * counts are for the company being worked in; a party's "All n →" opens that list
 * already searched for the party (`listStart` in Master.tsx), and an item names its
 * latest few entries, as the lists cannot be searched for an item. */

type Doc = { id: number; number: string; date: string | null; status: string; status_label: string; note: string; href?: string };
type Kind = { type: string; name: string; page?: string; count?: number; docs?: Doc[]; later?: string; all?: { col: string; q: string } | null };
type Data = {
  type: string;
  chain: { type: string; name: string; me: boolean }[];
  groups: { title: string; kinds: Kind[] }[];
  summary: string;
};

/** One read of an entry's connections serves both the box and its screen's "Create ▾" (a few
 * seconds' memory, so the two do not ask twice). */
const recent = new Map<string, { at: number; answer: Promise<Data> }>();
function loadConnections(companyId: number, kind: string, id: number): Promise<Data> {
  const url = `v1/companies/${companyId}/connections/${kind}/${id}/`;
  const held = recent.get(url);
  if (held && Date.now() - held.at < 3000) return held.answer;
  const answer = api<Data>(url);
  recent.set(url, { at: Date.now(), answer });
  answer.catch(() => recent.delete(url));
  return answer;
}

/** A follow-on document saved as a draft and not yet submitted (an invoice from this receipt, a
 * debit note from this return…). */
export type SavedDraft = { id: number; number: string; page: string; name: string };

/** "Open Saved Draft" (Sidharth, 2026-11-28): when a draft of the next document already exists for
 * this entry, the button that would start a new one opens that draft instead, on every screen:
 * "Create ▾", the Connections "+", and the list side panels. Kind -> its first saved draft. */
export function useSavedDrafts(companyId: number, kind: string, id: number | null | undefined, stamp?: unknown): Record<string, SavedDraft> {
  const [drafts, setDrafts] = useState<Record<string, SavedDraft>>({});
  useEffect(() => {
    let live = true;
    setDrafts({});
    if (id) loadConnections(companyId, kind, id).then((d) => live && setDrafts(draftsOf(d)), () => undefined);
    return () => {
      live = false;
    };
  }, [companyId, kind, id, stamp]);
  return drafts;
}

/** Saved but not finished: a draft, or a pick list still being picked. */
const unfinished = (type: string, status: string) => status === "draft" || (type === "pick_list" && status === "open");

function draftsOf(d: Data): Record<string, SavedDraft> {
  const out: Record<string, SavedDraft> = {};
  for (const g of d.groups)
    for (const k of g.kinds) {
      const doc = (k.docs ?? []).find((x) => unfinished(k.type, x.status));
      if (doc && !out[k.type]) out[k.type] = { id: doc.id, number: doc.number, page: k.page ?? "", name: k.name };
    }
  return out;
}

export const draftHref = (companyId: number, d: SavedDraft) => `#/companies/${companyId}/${d.page}?view=${d.id}`;
export const openDraft = (companyId: number, d: SavedDraft) => openTab(draftHref(companyId, d));

/** A "Create ▾" item for `kind`: as given, or "Open Saved Draft" when one is waiting. */
export function draftOr(companyId: number, drafts: Record<string, SavedDraft>, kind: string, item: MenuItem): MenuItem {
  const d = drafts[kind];
  if (!d) return item;
  return { label: `Open Saved Draft: ${d.name}`, onClick: () => openDraft(companyId, d), title: "A draft is already saved: open it to finish and Submit" };
}

const day = (iso: string | null) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "";

const pillOf = (status: string) =>
  status === "cancelled" ? "pill bad" : status === "draft" || status === "open" ? "pill" : "pill on";

export function Connections(props: {
  companyId: number;
  kind: string;
  id: number;
  /** Re-read when this changes (the entry's status, a save). */
  stamp?: unknown;
  /** Kinds the person may make from this entry now, as in its "Create ▾". */
  create?: Record<string, () => void>;
}) {
  const { companyId, kind, id, stamp, create } = props;
  const [data, setData] = useState<Data | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    loadConnections(companyId, kind, id).then(
      (d) => live && (setData(d), setFailed(false)),
      () => live && setFailed(true),
    );
    return () => {
      live = false;
    };
  }, [companyId, kind, id, stamp]);

  if (failed) return null;
  const hrefOf = (page: string, d: Doc) => d.href ?? `#/companies/${companyId}/${page}?view=${d.id}`;
  const allHref = (k: Kind) =>
    k.all ? `#/companies/${companyId}/${k.page}?${new URLSearchParams({ show: "all", col: k.all.col, q: k.all.q })}` : "";
  const master = kind === "party" || kind === "item";
  // A party's box sits in the narrow column beside the ledger list: only what it has.
  const groups = (data?.groups ?? [])
    .map((g) => ({ ...g, kinds: kind === "party" ? g.kinds.filter((k) => k.type === "later" || k.count) : g.kinds }))
    .filter((g) => g.kinds.some((k) => k.type !== "later"));
  return (
    <details className="fold connections" open>
      <summary>
        <span className="fold-title">Connections</span>
        <span className="fold-summary">{data?.summary ?? "…"}</span>
      </summary>
      {data && (
        <div className="fold-body">
          {data.chain.length > 0 && (
            <div className="conn-chain">
              {data.chain.map((c, i) => (
                <span key={c.type} className="conn-step-wrap">
                  {i > 0 && <span className="conn-arrow">→</span>}
                  <span className={c.me ? "conn-step me" : "conn-step"}>{c.me ? `This ${c.name}` : c.name}</span>
                </span>
              ))}
            </div>
          )}
          <div className="conn-grid">
            {groups.map((g) => (
              <div key={g.title} className="conn-group">
                <h3>{g.title}</h3>
                {g.kinds.map((k) =>
                  k.type === "later" ? (
                    <div key={`later-${k.name}`} className="conn-later">
                      <b>{k.name}</b> · {k.later}
                    </div>
                  ) : (
                    <div key={k.type} className={k.count ? "conn-kind" : "conn-kind none"}>
                      <div className="conn-head">
                        <span className="conn-name">{k.name}</span>
                        <span className="conn-count">{k.count ?? 0}</span>
                        {k.all && (
                          <a
                            className="conn-all"
                            href={allHref(k)}
                            onClick={(e) => {
                              if (e.ctrlKey || e.metaKey) return;
                              e.preventDefault();
                              openTab(allHref(k));
                            }}
                          >
                            All {k.count} →
                          </a>
                        )}
                        {create?.[k.type] &&
                          (() => {
                            // A saved draft is opened, not a second one started.
                            const draft = (k.docs ?? []).find((x) => unfinished(k.type, x.status));
                            return (
                              <button
                                type="button"
                                className="link conn-plus"
                                title={draft ? `Open Saved Draft: ${k.name}` : `New ${k.name}`}
                                onClick={draft ? () => openTab(hrefOf(k.page ?? "", draft)) : create[k.type]}
                              >
                                +
                              </button>
                            );
                          })()}
                      </div>
                      {(k.docs ?? []).length > 0 && (
                        <div className="conn-docs">
                          {(k.docs ?? []).map((d) => (
                            <div key={d.id} className="conn-doc">
                              <span>
                                <a
                                  href={hrefOf(k.page ?? "", d)}
                                  onClick={(e) => {
                                    if (e.ctrlKey || e.metaKey) return;
                                    e.preventDefault();
                                    openTab(hrefOf(k.page ?? "", d));
                                  }}
                                >
                                  {d.number || `Draft ${d.id}`}
                                </a>
                                <span className="conn-note">{[day(d.date), d.note].filter(Boolean).join(" · ")}</span>
                              </span>
                              {d.status_label && <span className={pillOf(d.status)}>{d.status_label}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ),
                )}
              </div>
            ))}
          </div>
          {groups.length === 0 && <p className="small">Nothing yet in this company.</p>}
          <p className="small">
            {master
              ? kind === "party"
                ? 'For the company you are working in. "All n →" opens that list searched for this party.'
                : "For the company you are working in: the latest five of each, newest first. Click a number to open it."
              : 'Click a number to open that entry; "Close" there comes back here. "+" makes a new one from this entry, as "Create ▾" does, or opens the saved draft if there is one.'}
          </p>
        </div>
      )}
    </details>
  );
}
