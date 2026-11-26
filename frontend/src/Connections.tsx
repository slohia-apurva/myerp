import { useEffect, useState } from "react";
import { api } from "./api";
import { openTab } from "./Master";

/** "Connections" on every entry's view (Sidharth, 2026-11-26, previews
 * mockups/connections/1 and 2): the entries this one came from, the ones made
 * from it, and the returns, notes and adjustments against it, grouped, each with
 * its number, date and status. A number opens that entry here (same tab; "Close"
 * comes back). "+" makes a new linked entry as "Create ▾" does: the screen passes
 * `create` with the kinds it may make now. Read from
 * v1/companies/<company>/connections/<kind>/<id>/ (posting/connections.py). */

type Doc = { id: number; number: string; date: string | null; status: string; status_label: string; note: string };
type Kind = { type: string; name: string; page?: string; count?: number; docs?: Doc[]; later?: string };
type Data = {
  type: string;
  chain: { type: string; name: string; me: boolean }[];
  groups: { title: string; kinds: Kind[] }[];
  summary: string;
};

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
    api<Data>(`v1/companies/${companyId}/connections/${kind}/${id}/`).then(
      (d) => live && (setData(d), setFailed(false)),
      () => live && setFailed(true),
    );
    return () => {
      live = false;
    };
  }, [companyId, kind, id, stamp]);

  if (failed) return null;
  const open = (page: string, doc: number) => openTab(`#/companies/${companyId}/${page}?view=${doc}`);
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
            {data.groups.map((g) => (
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
                        {create?.[k.type] && (
                          <button type="button" className="link conn-plus" title={`New ${k.name}`} onClick={create[k.type]}>
                            +
                          </button>
                        )}
                      </div>
                      {(k.docs ?? []).length > 0 && (
                        <div className="conn-docs">
                          {(k.docs ?? []).map((d) => (
                            <div key={d.id} className="conn-doc">
                              <span>
                                <a
                                  href={`#/companies/${companyId}/${k.page}?view=${d.id}`}
                                  onClick={(e) => {
                                    if (e.ctrlKey || e.metaKey) return;
                                    e.preventDefault();
                                    open(k.page ?? "", d.id);
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
          <p className="small">
            Click a number to open that entry; "Close" there comes back here. "+" makes a new one from this entry, as "Create ▾" does.
          </p>
        </div>
      )}
    </details>
  );
}
