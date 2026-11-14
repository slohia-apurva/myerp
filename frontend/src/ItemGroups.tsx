import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { Chevron, LevelPicker, PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { InUseNote, type LockInfo } from "./Lock";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";

/** Item groups: one tree for every company in the group, like ledger groups. */
export type ItemGroup = {
  id: number;
  name: string;
  parent: number | null;
  notes: string;
  is_active: boolean;
  item_count: number;
  lock?: LockInfo;
};

export function useItemGroups() {
  const [groups, setGroups] = useState<ItemGroup[]>([]);
  // refresh returns the request, so "Create …" can wait for the new record.
  const refresh = useCallback(() => api<ItemGroup[]>("v1/item-groups/").then(setGroups), []);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  return { groups, reload, refresh };
}

/** "Raw material > Spices > Whole spices": the name a picker shows. */
export function groupPaths(groups: ItemGroup[]): Map<number, string> {
  const byId = new Map(groups.map((g) => [g.id, g]));
  const path = (g: ItemGroup): string => {
    const parent = g.parent === null ? null : byId.get(g.parent);
    return parent ? `${path(parent)} > ${g.name}` : g.name;
  };
  return new Map(groups.map((g) => [g.id, path(g)]));
}

/** `?form=new`, `?form=<id>`, `?form=sub-<parent id>` or `?form=copy-<id>`: this tab was
 * opened to add, change, view or duplicate one item group (Sidharth, 2026-11-13). */
const formParam = () => hashParam("form");

/** Masters > Item groups: the tree on the left, the selected group's details on the right.
 * Add, Edit, Sub-group and Duplicate each open in a new tab. */
export function ItemGroupsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { groups, reload } = useItemGroups();
  const form = formParam();
  if (form) return <GroupFormTab form={form} canEdit={canEdit} />;
  return <GroupList session={session} canEdit={canEdit} groups={groups} reload={reload} />;
}

function GroupList(props: { session: SignedIn; canEdit: boolean; groups: ItemGroup[]; reload: () => void }) {
  const { groups, canEdit, reload } = props;
  const [selectedId, setSelected] = useState<number | null>(null);
  const [folded, setFolded] = useState<Set<number>>(new Set());
  const [level, setLevel] = useState<number | null>(Infinity);
  useCreated("item_group_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const io = useExchange({ master: "item-groups", noun: "item groups", session: props.session, onImported: reload });
  const startName = useNewName();
  useEffect(() => {
    // Opened by "Create …" in a dropdown: go straight to the Add page.
    if (startName && canEdit) window.location.hash = `#/item-groups?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    // Opened from a link (for example a duplicate-name refusal): unfold and select that group.
    if (openId && groups.some((g) => g.id === openId)) {
      setFolded(new Set());
      setSelected(openId);
      opened();
    }
  }, [openId, groups, opened]);

  const children = useMemo(() => {
    const map = new Map<number | null, ItemGroup[]>();
    for (const g of groups) map.set(g.parent, [...(map.get(g.parent) ?? []), g]);
    return map;
  }, [groups]);
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
  const deepest = Math.max(0, ...depthOf.values()) + 1;
  const showLevels = (n: number) => {
    setLevel(n);
    setFolded(new Set(groups.filter((g) => children.has(g.id) && (depthOf.get(g.id) ?? 0) >= n - 1).map((g) => g.id)));
  };
  const toggle = (id: number) =>
    setFolded((f) => {
      setLevel(null);
      const next = new Set(f);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const total = (g: ItemGroup): number => g.item_count + (children.get(g.id) ?? []).reduce((t, c) => t + total(c), 0);
  const selected = groups.find((g) => g.id === selectedId) ?? null;
  const edit = (what: number | string) => openTab(`#/item-groups?form=${what}`);

  const rows = (g: ItemGroup, depth: number): JSX.Element[] => {
    const kids = children.get(g.id) ?? [];
    const top = depth === 0;
    const stop = (fn: () => void) => (e: { stopPropagation: () => void }) => {
      e.stopPropagation();
      fn();
    };
    const out = [
      <tr
        key={g.id}
        className={`${top ? "group-top" : ""}${selectedId === g.id ? " selected" : ""}${g.is_active ? "" : " off"}`}
        onClick={() => setSelected(g.id)}
        onDoubleClick={() => edit(g.id)}
      >
        <td>
          <span className="group-name" style={{ paddingLeft: depth * 22 }}>
            {kids.length > 0 ? (
              <button
                className="fold"
                aria-expanded={!folded.has(g.id)}
                aria-label={`${folded.has(g.id) ? "Show" : "Hide"} groups under ${g.name}`}
                onClick={stop(() => toggle(g.id))}
              >
                <Chevron open={!folded.has(g.id)} />
              </button>
            ) : (
              <span className="branch" aria-hidden="true">
                {top ? "" : "└"}
              </span>
            )}
            <span className="gname">{g.name}</span>
            {!g.is_active && <span className="pill">Disabled</span>}
          </span>
        </td>
        <td className="small">{g.notes}</td>
        <td className="num">{total(g) > 0 ? total(g) : <span className="small">—</span>}</td>
        <td className="row-actions">
          {canEdit && (
            <button className="link" onClick={stop(() => edit(`sub-${g.id}`))}>
              + Sub-group
            </button>
          )}
          <button className="link" onClick={stop(() => edit(g.id))}>
            {canEdit ? "Edit" : "View"}
          </button>
          {canEdit && (
            <button className="link quiet" onClick={stop(() => edit(`copy-${g.id}`))}>
              Duplicate
            </button>
          )}
        </td>
      </tr>,
    ];
    if (!folded.has(g.id)) for (const c of kids) out.push(...rows(c, depth + 1));
    return out;
  };

  return (
    <section className="page">
      <PageHeader
        title="Item groups"
        sub="Groups and sub-groups for items, such as Raw material > Spices > Whole spices. One tree for every company in the group."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>Add group</button>}
          </>
        }
      />
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          <div className="page-head">
            <p className="small">{groups.length} groups.</p>
            <LevelPicker levels={deepest} value={level} onPick={showLevels} />
          </div>
          <table className="groups">
            <thead>
              <tr>
                <th>Group</th>
                <th>Notes</th>
                <th className="num">Items</th>
                <th />
              </tr>
            </thead>
            <tbody>{(children.get(null) ?? []).flatMap((g) => rows(g, 0))}</tbody>
          </table>
        </div>
        <div className="side-col">
          <SidePanel title="Group Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.name],
                  ["Under", groups.find((g) => g.id === selected.parent)?.name ?? "Top level"],
                  ["Items", String(selected.item_count)],
                  ["In Use", selected.lock?.in_use.join(", ") ?? ""],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                  ["Notes", selected.notes],
                ]}
              />
            ) : (
              <p className="small">Click a group to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="item_group" id={selected?.id} stamp={JSON.stringify(selected ?? groups.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one item group, alone in its own tab: Save and Cancel close the tab. */
function GroupFormTab(props: { form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const sub = props.form.startsWith("sub-");
  const key = Number(props.form.replace(/^(copy|sub)-/, ""));
  const [groups, setGroups] = useState<ItemGroup[] | null>(null);
  useEffect(() => {
    api<ItemGroup[]>("v1/item-groups/").then(setGroups);
  }, []);
  const startName = useNewName();
  const target = props.form === "new" ? null : (groups?.find((g) => g.id === key) ?? null);
  const toList = () => {
    window.location.hash = "#/item-groups";
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("item_group_saved", saved);
    closeThisTab(toList);
  };
  const editing = props.form !== "new" && !copy && !sub;
  const readOnly = !props.canEdit;
  const title = editing ? (readOnly ? "View item group" : "Edit item group") : sub ? "Add sub-group" : copy ? "Duplicate item group" : "Add item group";
  if (groups === null)
    return (
      <section className="page">
        <PageHeader title={title} />
      </section>
    );
  if (props.form !== "new" && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That item group was not found.</p>
      </section>
    );
  if (readOnly && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view item groups.</p>
      </section>
    );
  return (
    <GroupForm
      title={title}
      groups={groups}
      group={editing ? target : null}
      copyOf={copy ? target : null}
      parent={sub ? key : target ? target.parent : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function GroupForm(props: {
  title: string;
  groups: ItemGroup[];
  group: ItemGroup | null;
  copyOf?: ItemGroup | null;
  parent: number | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const g = props.group;
  const copy = props.copyOf;
  const [name, setName] = useState(props.startName ?? (copy ? `${copy.name} (copy)` : (g?.name ?? "")));
  const [parent, setParent] = useState(props.parent === null ? "" : String(props.parent));
  const [notes, setNotes] = useState(copy?.notes ?? g?.notes ?? "");
  const [disabled, setDisabled] = useState(g ? !g.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const paths = useMemo(() => groupPaths(props.groups), [props.groups]);
  const below = useMemo(() => {
    // A group cannot be moved under itself or a group below it.
    const out = new Set<number>();
    if (!g) return out;
    const walk = (id: number) =>
      props.groups.filter((x) => x.parent === id).forEach((x) => (out.add(x.id), walk(x.id)));
    out.add(g.id);
    walk(g.id);
    return out;
  }, [g, props.groups]);
  const rootOf = (id: number): number => {
    const x = props.groups.find((o) => o.id === id);
    return x && x.parent !== null ? rootOf(x.parent) : id;
  };
  // A group in use may move only within its own main group (Sidharth, 2026-11-13).
  const inUse = !!g?.lock && g.lock.in_use.length > 0;
  const home = g ? rootOf(g.id) : null;

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = { name, parent: parent === "" ? null : Number(parent), notes };
    try {
      if (g) {
        await api(`v1/item-groups/${g.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: g.id, name });
      } else {
        const made = await api<{ id: number; name: string }>("v1/item-groups/", body);
        announceCreated("item_group", made);
        props.onDone(made);
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <FormPage
      title={props.title}
      sub={g ? g.name : undefined}
      formId="item-group-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={g ? { value: disabled, set: setDisabled } : undefined}
      activity={g ? <ChangeLog type="item_group" id={g.id} stamp={JSON.stringify(g)} /> : undefined}
    >
      <InUseNote lock={g?.lock}>
        The group can move only within its own main group. Everything else stays open.
      </InUseNote>
      <Section title="General">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Name</span>
            <input required autoFocus value={name} placeholder="e.g. Whole spices" onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Under
            <Combobox
              value={parent}
              empty="Main group (nothing above it)"
              placeholder="Type to search groups…"
              options={props.groups
                .filter(
                  (o) =>
                    !below.has(o.id) &&
                    (o.is_active || String(o.id) === parent) &&
                    (!inUse || rootOf(o.id) === home),
                )
                .map((o) => ({ value: String(o.id), label: paths.get(o.id) ?? o.name }))}
              onChange={setParent}
            />
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      </Section>
    </FormPage>
  );
}
