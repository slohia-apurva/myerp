import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { Activity, WithActivity } from "./Audit";
import { Chevron, LevelPicker, PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { useExchange } from "./Exchange";
import { ActiveButton, FormBody } from "./RowActions";

/** Item groups: one tree for every company in the group, like ledger groups. */
export type ItemGroup = {
  id: number;
  name: string;
  parent: number | null;
  notes: string;
  is_active: boolean;
  item_count: number;
};

export function useItemGroups() {
  const [groups, setGroups] = useState<ItemGroup[]>([]);
  const reload = useCallback(() => {
    api<ItemGroup[]>("v1/item-groups/").then(setGroups);
  }, []);
  useEffect(reload, [reload]);
  return { groups, reload };
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

type Editing = { group: ItemGroup | null; parent: number | null; copyOf?: ItemGroup };

/** Masters > Item groups. */
export function ItemGroupsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { groups, reload } = useItemGroups();
  const [editing, setEditing] = useState<Editing | null>(null);
  const [folded, setFolded] = useState<Set<number>>(new Set());
  const [level, setLevel] = useState<number | null>(Infinity);
  const io = useExchange({ master: "item-groups", noun: "item groups", session, onImported: reload });

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
  const done = () => {
    setEditing(null);
    reload();
  };

  const rows = (g: ItemGroup, depth: number): JSX.Element[] => {
    const kids = children.get(g.id) ?? [];
    const top = depth === 0;
    const out = [
      <tr key={g.id} className={`${top ? "group-top" : ""}${g.is_active ? "" : " off"}`}>
        <td>
          <span className="group-name" style={{ paddingLeft: depth * 22 }}>
            {kids.length > 0 ? (
              <button
                className="fold"
                aria-expanded={!folded.has(g.id)}
                aria-label={`${folded.has(g.id) ? "Show" : "Hide"} groups under ${g.name}`}
                onClick={() => toggle(g.id)}
              >
                <Chevron open={!folded.has(g.id)} />
              </button>
            ) : (
              <span className="branch" aria-hidden="true">
                {top ? "" : "└"}
              </span>
            )}
            <span className="gname">{g.name}</span>
            {!g.is_active && <span className="pill">Inactive</span>}
          </span>
        </td>
        <td className="small">{g.notes}</td>
        <td className="num">{total(g) > 0 ? total(g) : <span className="small">—</span>}</td>
        <td className="row-actions">
          {canEdit && (
            <button className="link" onClick={() => setEditing({ group: null, parent: g.id })}>
              + Sub-group
            </button>
          )}
          <button className="link" onClick={() => setEditing({ group: g, parent: g.parent })}>
            {canEdit ? "Edit" : "View"}
          </button>
          {canEdit && (
            <button className="link quiet" onClick={() => setEditing({ group: null, parent: g.parent, copyOf: g })}>
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
            {canEdit && <button onClick={() => setEditing({ group: null, parent: null })}>Add group</button>}
          </>
        }
      />
      <WithActivity activity={<Activity type="item_group" stamp={JSON.stringify(groups)} />}>
        {io.panel}
        {editing && (
          <GroupForm
            key={editing.group?.id ?? `new-${editing.parent}-${editing.copyOf?.id ?? ""}`}
            editing={editing}
            groups={groups}
            readOnly={!canEdit}
            onDone={done}
            onCancel={() => setEditing(null)}
          />
        )}
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
      </WithActivity>
    </section>
  );
}

function GroupForm(props: {
  editing: Editing;
  groups: ItemGroup[];
  readOnly?: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const g = props.editing.group;
  const copy = props.editing.copyOf;
  const [name, setName] = useState(copy ? `${copy.name} (copy)` : (g?.name ?? ""));
  const [parent, setParent] = useState(props.editing.parent === null ? "" : String(props.editing.parent));
  const [notes, setNotes] = useState(copy?.notes ?? g?.notes ?? "");
  const [error, setError] = useState("");
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

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = { name, parent: parent === "" ? null : Number(parent), notes };
    try {
      if (g) await api(`v1/item-groups/${g.id}/`, body, "PATCH");
      else await api("v1/item-groups/", body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h4>{g ? `${props.readOnly ? "View" : "Edit"} ${g.name}` : copy ? `Duplicate ${copy.name}` : "Add item group"}</h4>
      <FormBody readOnly={props.readOnly}>
        <Section title="Item group">
          <div className="row">
            <label>
              Name
              <input required autoFocus value={name} placeholder="e.g. Whole spices" onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
              Under
              <Combobox
                value={parent}
                empty="Main group (nothing above it)"
                placeholder="Type to search groups…"
                options={props.groups
                  .filter((o) => !below.has(o.id) && (o.is_active || String(o.id) === parent))
                  .map((o) => ({ value: String(o.id), label: paths.get(o.id) ?? o.name }))}
                onChange={setParent}
              />
            </label>
          </div>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </Section>
      </FormBody>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {!props.readOnly && <button>Save</button>}
        <button type="button" className="link" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
        {g && !props.readOnly && (
          <ActiveButton
            url={`v1/item-groups/${g.id}/`}
            active={g.is_active}
            what={`the item group ${g.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}
