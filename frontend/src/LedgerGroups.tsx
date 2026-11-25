import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { Chevron, LevelPicker, PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { type Company, type Detail, type Group, NATURE } from "./Companies";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { ErrorNote, useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useKept } from "./Keep";

/** `?form=new`, `?form=<id>`, `?form=sub-<parent id>` or `?form=copy-<id>`: this tab was
 * opened to add, change or duplicate one ledger group (Sidharth, 2026-11-13). */
const formParam = () => hashParam("form");

const groupsHash = (company: number, query = "") => `#/companies/${company}/groups${query}`;

/** Ledger groups: the tree on the left, the selected group's details on the right.
 * Add, Edit, Sub-group and Duplicate each open in a new tab. */
export function LedgerGroupsPage({ id, session }: { id: number; session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    api<Detail>(`v1/companies/${id}/`)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [id]);
  useEffect(reload, [reload]);
  const form = formParam();
  if (form && canEdit) return <GroupFormTab companyId={id} form={form} detail={detail} error={error} />;
  return <GroupList id={id} canEdit={canEdit} session={session} detail={detail} error={error} reload={reload} />;
}

function GroupList(props: {
  id: number;
  canEdit: boolean;
  session: SignedIn;
  detail: Detail | null;
  error: string;
  reload: () => void;
}) {
  const { id, detail, canEdit } = props;
  const printing = useExchange({
    master: "ledger-groups",
    noun: "ledger groups",
    session: props.session,
    company: id,
    onImported: props.reload,
    printScreen: { title: "Ledger groups", scope: detail?.company.name },
  });
  const [selectedId, setSelected] = useKept<number | null>("LedgerGroups.selectedId", null);
  useCreated("ledger_group_saved", (c) => {
    props.reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    // Opened by "Create …" in a dropdown: go straight to a new group's form.
    if (startName && canEdit) window.location.hash = groupsHash(id, `?form=new&new=${encodeURIComponent(startName)}`);
  }, [startName, canEdit, id]);
  if (!detail)
    return <section className="page">{props.error ? <p className="error">{props.error}</p> : <p>Loading…</p>}</section>;
  const groups = detail.ledger_groups;
  const selected = groups.find((g) => g.id === selectedId) ?? null;
  return (
    <section className="page">
      <PageHeader
        title="Ledger groups"
        crumbs={[
          { label: "Companies", href: "#/companies" },
          { label: detail.company.name, href: `#/companies/${id}` },
        ]}
        actions={printing.buttons}
      />
      {printing.panel}
      <div className="side-layout">
        <div className="side-main">
          <GroupTree
            company={detail.company}
            groups={groups}
            canEdit={canEdit}
            selectedId={selectedId}
            onSelect={setSelected}
          />
        </div>
        <div className="side-col">
          <SidePanel title="Group Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.name],
                  ["Under", groups.find((g) => g.id === selected.parent)?.name ?? "Top level"],
                  ["Nature", NATURE[selected.nature]],
                  ["Schedule III", selected.schedule_iii],
                  ["Type", selected.is_standard ? "Standard" : "Added"],
                  ["Ledgers", String(selected.ledger_count)],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                ]}
              />
            ) : (
              <p className="small">Click a group to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog
              company={id}
              type="ledger_group"
              id={selected?.id}
              stamp={JSON.stringify(selected ?? detail.ledger_groups.length)}
            />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

function GroupTree(props: {
  company: Company;
  groups: Group[];
  canEdit: boolean;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const children = useMemo(() => {
    const map = new Map<number | null, Group[]>();
    for (const g of props.groups) map.set(g.parent, [...(map.get(g.parent) ?? []), g]);
    return map;
  }, [props.groups]);
  const [folded, setFolded] = useState<Set<number>>(new Set());
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (!openId || !props.groups.some((g) => g.id === openId)) return;
    // Unfold the tree and bring the group asked for into view.
    setFolded(new Set());
    props.onSelect(openId);
    opened();
    window.setTimeout(() => document.getElementById(`group-${openId}`)?.scrollIntoView({ block: "center" }), 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId, props.groups, opened]);
  const [level, setLevel] = useState<number | null>(Infinity);
  const tops = children.get(null) ?? [];
  const depthOf = useMemo(() => {
    const d = new Map<number, number>();
    const walk = (parent: number | null, depth: number) =>
      (children.get(parent) ?? []).forEach((g) => {
        d.set(g.id, depth);
        walk(g.id, depth + 1);
      });
    walk(null, 0);
    return d;
  }, [children]);
  const deepest = Math.max(0, ...depthOf.values());
  const showLevels = (n: number) => {
    setLevel(n);
    setFolded(
      new Set(
        props.groups.filter((g) => children.has(g.id) && (depthOf.get(g.id) ?? 0) >= n - 1).map((g) => g.id),
      ),
    );
  };
  const toggle = (id: number) =>
    setFolded((f) => {
      setLevel(null);
      const next = new Set(f);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const total = (g: Group): number =>
    g.ledger_count + (children.get(g.id) ?? []).reduce((t, c) => t + total(c), 0);
  const company = props.company.id;

  const rows = (g: Group, depth: number): JSX.Element[] => {
    const kids = children.get(g.id) ?? [];
    const top = depth === 0;
    const out = [
      <tr
        key={g.id}
        id={`group-${g.id}`}
        className={`${top ? "group-top" : ""}${props.selectedId === g.id ? " selected" : ""}${g.is_active ? "" : " inactive"}`}
        onClick={() => props.onSelect(g.id)}
      >
        <td>
          <span className="group-name" style={{ paddingLeft: depth * 22 }} data-indent={depth}>
            {kids.length > 0 ? (
              <button
                className="fold"
                aria-expanded={!folded.has(g.id)}
                aria-label={`${folded.has(g.id) ? "Show" : "Hide"} groups under ${g.name}`}
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(g.id);
                }}
              >
                <Chevron open={!folded.has(g.id)} />
              </button>
            ) : (
              <span className="branch" aria-hidden="true">
                {top ? "" : "└"}
              </span>
            )}
            <span className="gname">
              {g.name}
              {g.schedule_iii && <span className="sch3 sub">{g.schedule_iii}</span>}
            </span>
            {!g.is_standard && <span className="tag">added</span>}
            {!g.is_active && <span className="tag">disabled</span>}
          </span>
        </td>
        <td>
          {NATURE[g.nature]}
          {top && g.affects_gross_profit && <span className="small"> · trading</span>}
        </td>
        <td className="num">
          {total(g) > 0 ? (
            <a href={`#/companies/${company}/ledgers/${g.id}`} onClick={(e) => e.stopPropagation()}>
              {total(g)}
            </a>
          ) : (
            <span className="small">—</span>
          )}
        </td>
        <td className="row-actions">
          {props.canEdit && (
            <>
              {g.is_active && (
                <button
                  className="link"
                  onClick={(e) => {
                    e.stopPropagation();
                    openTab(groupsHash(company, `?form=sub-${g.id}`));
                  }}
                >
                  + Sub-group
                </button>
              )}
              {!g.is_standard && (
                <button
                  className="link"
                  onClick={(e) => {
                    e.stopPropagation();
                    openTab(groupsHash(company, `?form=${g.id}`));
                  }}
                >
                  Edit
                </button>
              )}
              {g.parent !== null && (
                <button
                  className="link"
                  onClick={(e) => {
                    e.stopPropagation();
                    openTab(groupsHash(company, `?form=copy-${g.id}`));
                  }}
                >
                  Duplicate
                </button>
              )}
            </>
          )}
        </td>
      </tr>,
    ];
    if (!folded.has(g.id)) for (const c of kids) out.push(...rows(c, depth + 1));
    return out;
  };

  return (
    <>
      <div className="page-head">
        <p className="small">
          {props.groups.length} groups. The standard groups follow Schedule III of the Companies Act and cannot be
          changed; add your own under them, for example Export debtors under Sundry Debtors.
        </p>
        <LevelPicker levels={deepest} value={level} onPick={showLevels} />
      </div>
      <table className="groups">
        <thead>
          <tr>
            <th>Group</th>
            <th>Nature</th>
            <th className="num">Ledgers</th>
            <th />
          </tr>
        </thead>
        <tbody>{tops.flatMap((g) => rows(g, 0))}</tbody>
      </table>
    </>
  );
}

/** The add / change form of one ledger group, alone in its own tab: Save and Cancel close the tab. */
function GroupFormTab(props: { companyId: number; form: string; detail: Detail | null; error: string }) {
  const { companyId: id, form, detail } = props;
  const copy = form.startsWith("copy-");
  const sub = form.startsWith("sub-");
  const key = Number(form.replace(/^(copy|sub)-/, ""));
  const target = detail?.ledger_groups.find((g) => g.id === key) ?? null;
  const startName = useNewName();
  const toList = () => {
    window.location.hash = groupsHash(id);
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("ledger_group_saved", saved);
    closeThisTab(toList);
  };
  const editing = form !== "new" && !copy && !sub;
  const title = editing ? "Edit ledger group" : sub ? "Add sub-group" : copy ? "Duplicate ledger group" : "Add ledger group";
  const missing = detail && form !== "new" && target === null;
  return (
    <section className="page item-edit">
      {props.error && <p className="error">{props.error}</p>}
      {missing && <p className="error">That group was not found.</p>}
      {detail && !missing && (
        <GroupForm
          title={title}
          company={detail.company}
          groups={detail.ledger_groups}
          group={editing ? target : null}
          parent={sub ? key : target ? target.parent : null}
          initialName={copy && target ? `${target.name} (copy)` : (startName ?? undefined)}
          onDone={(saved) => finish(saved)}
          onCancel={() => finish()}
        />
      )}
      {!detail && !props.error && <PageHeader title={title} />}
    </section>
  );
}

function GroupForm(props: {
  title: string;
  company: Company;
  groups: Group[];
  group: Group | null;
  parent: number | null;
  initialName?: string;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const g = props.group;
  const [name, setName] = useState(g?.name ?? props.initialName ?? "");
  const [parent, setParent] = useState<number | null>(props.parent);
  const [disabled, setDisabled] = useState(g ? !g.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (g) {
        await api(`v1/ledger-groups/${g.id}/`, { name, parent, is_active: !disabled }, "PATCH");
        props.onDone({ id: g.id, name });
      } else {
        const made = await api<{ id: number; name: string }>(`v1/companies/${props.company.id}/ledger-groups/`, {
          name,
          parent,
        });
        announceCreated("ledger_group", made);
        props.onDone(made);
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeader
        title={props.title}
        sub={g ? `${props.company.name}` : props.company.name}
        actions={
          <>
            <button type="button" className="link" onClick={props.onCancel}>
              Cancel
            </button>
            <button type="submit" form="group-form" disabled={busy}>
              Save
            </button>
          </>
        }
      />
      <form id="group-form" className="side-layout" onSubmit={save}>
        <div className="side-main">
          <Section title="General">
            <p className="small">
              <span className="req-star">*</span> Required
            </p>
            <div className="item-fields">
              <label>
                <span className="req">Group Name</span>
                <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label>
                <span className="req">Under</span>
                <Combobox
                  required
                  value={parent === null ? "" : String(parent)}
                  placeholder="Type to search groups…"
                  options={props.groups
                    .filter((o) => o.id !== g?.id && (o.is_active || o.id === g?.parent))
                    .map((o) => ({ value: String(o.id), label: o.name }))}
                  onChange={(v) => setParent(Number(v))}
                />
              </label>
            </div>
          </Section>
          <ErrorNote error={error} />
        </div>
        <div className="side-col">
          {g && (
            <SidePanel title="Switches">
              <div className="item-switches">
                <label className="check">
                  <input type="checkbox" checked={disabled} onChange={(e) => setDisabled(e.target.checked)} />
                  Disabled
                </label>
              </div>
            </SidePanel>
          )}
          <SidePanel title="Tips">
            <p className="small">A red * marks a field that must be filled in.</p>
            <p className="small">Your own groups sit under a standard group, for example Export debtors under Sundry Debtors.</p>
          </SidePanel>
          {g && (
            <SidePanel title="Activity">
              <ChangeLog company={props.company.id} type="ledger_group" id={g.id} stamp={JSON.stringify(g)} />
            </SidePanel>
          )}
        </div>
      </form>
    </>
  );
}
