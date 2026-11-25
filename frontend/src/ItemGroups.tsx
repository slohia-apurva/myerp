import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { Chevron, LevelPicker, PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import type { Company, Detail } from "./Companies";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { InUseNote, type LockInfo } from "./Lock";
import type { Ledger } from "./Ledgers";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useOnReturn, useReturns } from "./Refresh";
import { useKept } from "./Keep";

/** Item groups: one tree for every company in the group, like ledger groups. */
export type ItemGroup = {
  id: number;
  name: string;
  parent: number | null;
  notes: string;
  is_active: boolean;
  item_count: number;
  lock?: LockInfo;
  /** The accounts its items post to: its own rows, or its main group's when it is a sub-group. */
  accounts?: AccountRow[];
  /** For a sub-group: the main group its accounts come from. */
  accounts_from?: { id: number; name: string } | null;
};

/** One company's accounts on a main item group. `locked` says why the row can no longer change. */
export type AccountRow = {
  company: number;
  company_name: string;
  stock_ledger: number | null;
  stock_ledger_name: string;
  cogs_ledger: number | null;
  cogs_ledger_name: string;
  sales_ledger: number | null;
  sales_ledger_name: string;
  locked: string[];
};

type Picks = { stock: string; cogs: string; sales: string };

export function useItemGroups(full = false) {
  const [groups, setGroups] = useState<ItemGroup[]>([]);
  // refresh returns the request, so "Create …" can wait for the new record. Only the Item groups
  // screen asks for `full` (in-use checks and accounts); pickers skip them, so screens open fast.
  const refresh = useCallback(() => api<ItemGroup[]>(`v1/item-groups/${full ? "?full=1" : ""}`).then(setGroups), [full]);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
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
  const { groups, reload } = useItemGroups(true);
  const form = formParam();
  if (form) return <GroupFormTab form={form} canEdit={canEdit} />;
  return <GroupList session={session} canEdit={canEdit} groups={groups} reload={reload} />;
}

function GroupList(props: { session: SignedIn; canEdit: boolean; groups: ItemGroup[]; reload: () => void }) {
  const { groups, canEdit, reload } = props;
  const [selectedId, setSelected] = useKept<number | null>("ItemGroups.selectedId", null);
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
        <td className="num">
          {total(g) > 0 ? (
            <a href={`#/items?group=${g.id}`} onClick={(e) => e.stopPropagation()}>
              {total(g)}
            </a>
          ) : (
            <span className="small">—</span>
          )}
        </td>
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
          <SidePanel title="Accounts">
            {selected && (selected.accounts ?? []).length > 0 ? (
              <>
                {selected.accounts_from && (
                  <p className="small">From the main group {selected.accounts_from.name}.</p>
                )}
                {(selected.accounts ?? []).map((a) => (
                  <SideRows
                    key={a.company}
                    rows={[
                      ["Company", a.company_name],
                      ["Stock Ledger", a.stock_ledger_name],
                      ["COGS/Expense Ledger", a.cogs_ledger_name],
                      ["Sales Ledger", a.sales_ledger_name],
                    ]}
                  />
                ))}
              </>
            ) : (
              <p className="small">{selected ? "No accounts set yet." : "Click a group to see its accounts here."}</p>
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
    api<ItemGroup[]>("v1/item-groups/?full=1").then(setGroups);
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
  // "Set ledgers" on an entry's missing-ledgers popup opens the group here, at its ledgers (Sidharth, 2026-11-17).
  useEffect(() => {
    if (hashParam("at") !== "ledgers") return;
    const timer = window.setTimeout(() => document.getElementById("group-ledgers")?.scrollIntoView({ behavior: "smooth", block: "start" }), 300);
    return () => window.clearTimeout(timer);
  }, []);
  const [busy, setBusy] = useState(false);
  // Accounts per company (main groups only): the ledger ids picked, as text.
  const startRows = copy?.accounts ?? g?.accounts ?? [];
  const [picks, setPicks] = useState<Record<number, Picks>>(() =>
    Object.fromEntries(
      startRows.map((a) => [
        a.company,
        { stock: String(a.stock_ledger ?? ""), cogs: String(a.cogs_ledger ?? ""), sales: String(a.sales_ledger ?? "") },
      ]),
    ),
  );
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
    const num = (v: string) => (v === "" ? null : Number(v));
    const body: Record<string, unknown> = { name, parent: num(parent), notes };
    if (parent === "")
      body.accounts_in = Object.entries(picks)
        .filter(([, p]) => p.stock || p.cogs || p.sales)
        .map(([company, p]) => ({
          company: Number(company),
          stock_ledger: num(p.stock),
          cogs_ledger: num(p.cogs),
          sales_ledger: num(p.sales),
        }));
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
      <div id="group-ledgers" />
      <Section title="Accounts">
        {parent === "" ? (
          <AccountGrid
            rows={g?.accounts ?? []}
            picks={picks}
            onPick={(company, next) => setPicks((all) => ({ ...all, [company]: next }))}
            readOnly={props.readOnly}
          />
        ) : (
          <InheritedAccounts
            main={props.groups.find((x) => x.id === rootOf(Number(parent)))}
            sourceName={paths.get(rootOf(Number(parent))) ?? ""}
          />
        )}
      </Section>
    </FormPage>
  );
}

/** Sub-groups show their main group's accounts, read only. */
function InheritedAccounts(props: { main?: ItemGroup; sourceName: string }) {
  const rows = props.main?.accounts ?? [];
  return (
    <>
      <p className="small">
        From the main group <b>{props.sourceName}</b>. Change them there; every group under it uses the same accounts.
        {props.main && (
          <>
            {" "}
            <button type="button" className="link" onClick={() => openTab(`#/item-groups?form=${props.main!.id}`)}>
              Open {props.sourceName}
            </button>
          </>
        )}
      </p>
      {rows.length === 0 ? (
        <p className="small">No accounts are set on {props.sourceName} yet.</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Company</th>
              <th>Stock Ledger</th>
              <th>COGS/Expense Ledger</th>
              <th>Sales Ledger</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.company}>
                <td>{a.company_name}</td>
                <td>{a.stock_ledger_name || "—"}</td>
                <td>{a.cogs_ledger_name || "—"}</td>
                <td>{a.sales_ledger_name || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

/** A main group's accounts: one row per company, three ledger pickers each. A company's row locks
 * once entries exist (Sidharth, 2026-11-14). */
function AccountGrid(props: {
  rows: AccountRow[];
  picks: Record<number, Picks>;
  onPick: (company: number, next: Picks) => void;
  readOnly?: boolean;
}) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [ledgers, setLedgers] = useState<Record<number, { ledgers: Ledger[]; stockGroups: Set<number> }>>({});
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  useEffect(() => {
    api<Company[]>("v1/companies/").then((list) => {
      setCompanies(list);
      list.forEach((c) =>
        Promise.all([api<Ledger[]>(`v1/companies/${c.id}/ledgers/`), api<Detail>(`v1/companies/${c.id}/`)]).then(
          ([ls, detail]) => {
            // The groups at and under Stock-in-Hand.
            const stock = new Set<number>();
            const root = detail.ledger_groups.find((x) => x.code === "stock_in_hand");
            const walk = (id: number) => {
              stock.add(id);
              detail.ledger_groups.filter((x) => x.parent === id).forEach((x) => walk(x.id));
            };
            if (root) walk(root.id);
            setLedgers((all) => ({ ...all, [c.id]: { ledgers: ls, stockGroups: stock } }));
          },
        ),
      );
    });
  }, [visits]);
  const empty: Picks = { stock: "", cogs: "", sales: "" };
  if (companies.length === 0) return <p className="small">Loading companies…</p>;
  return (
    <>
      <p className="small">
        The accounts the items of this group post to, for each company. Groups under this one use the same accounts.
        Leave a company empty if it does not use this group.
      </p>
      <table className="grid account-grid">
        <thead>
          <tr>
            <th>Company</th>
            <th>Stock Ledger</th>
            <th>COGS/Expense Ledger</th>
            <th>Sales Ledger</th>
          </tr>
        </thead>
        <tbody>
          {companies.map((c) => {
            const row = props.rows.find((r) => r.company === c.id);
            const locked = row?.locked ?? [];
            const picks = props.picks[c.id] ?? empty;
            const data = ledgers[c.id];
            const pick = (key: keyof Picks, kind: "stock" | "expense" | "income") => {
              const options = (data?.ledgers ?? [])
                .filter((l) => (l.is_active || String(l.id) === picks[key]) && (kind === "stock" ? data!.stockGroups.has(l.group) : l.nature === kind))
                .map((l) => ({ value: String(l.id), label: l.name }));
              return (
                <Combobox
                  value={picks[key]}
                  empty="—"
                  placeholder="Type to search ledgers…"
                  ariaLabel={`${key} ledger of ${c.name}`}
                  options={options}
                  onChange={(v) => props.onPick(c.id, { ...picks, [key]: v })}
                />
              );
            };
            const off = props.readOnly || locked.length > 0;
            // A Sales Ledger still blank may be set on a row in use (Sidharth, 2026-11-20).
            const salesOff = props.readOnly || (locked.length > 0 && !!row?.sales_ledger);
            const wrap = (el: JSX.Element) => (off ? <span className="locked-field" {...({ inert: "" } as object)}>{el}</span> : el);
            return (
              <tr key={c.id}>
                <td>
                  {c.name}
                  {locked.length > 0 && (
                    <>
                      <div className="small">In use: {locked.join(", ")}</div>
                    </>
                  )}
                </td>
                <td>{wrap(pick("stock", "stock"))}</td>
                <td>{wrap(pick("cogs", "expense"))}</td>
                <td>{salesOff ? <span className="locked-field" {...({ inert: "" } as object)}>{pick("sales", "income")}</span> : pick("sales", "income")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="small">
        Stock Ledger holds the value of stock on hand. COGS/Expense takes the cost of stock goods when they are sold,
        stock used inside the company or written off, and the cost of items that keep no stock (stationery, services).
        Sales Ledger takes the group's sales on sales invoices (an income ledger, such as one under Sales Accounts).
      </p>
    </>
  );
}
