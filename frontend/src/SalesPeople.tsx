import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { ActionCells, ActionHeads } from "./RowActions";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { ColumnSearch } from "./ColumnSearch";
import { useOnReturn } from "./Refresh";
import { useColumns } from "./Columns";
import { Pager, ShowInactive, useShowInactive, type Paged } from "./Pager";

/** People (Sidharth, 2026-11-16, preview 83; "Stores" added 2026-11-17, preview 88): the
 * people who sell to customers, buy from suppliers or receive goods in the stores, with or
 * without a MyERP sign-in. One list for every company in the group; a customer picks a
 * Salesman, a supplier a Purchaser, a goods receipt its Received By and QC By from Stores. */
export type SalesPerson = {
  id: number;
  name: string;
  is_salesman: boolean;
  is_purchaser: boolean;
  is_stores: boolean;
  mobile: string;
  email: string;
  user: number | null;
  user_name: string;
  notes: string;
  is_active: boolean;
  party_count: number;
};

export function useSalesPeople() {
  const [people, setPeople] = useState<SalesPerson[]>([]);
  // refresh returns the request, so "Create …" can wait for the new record.
  const refresh = useCallback(() => api<SalesPerson[]>("v1/sales-people/").then(setPeople), []);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { people, reload, refresh };
}

export const worksAs = (p: SalesPerson) =>
  [p.is_salesman && "Salesman", p.is_purchaser && "Purchaser", p.is_stores && "Stores"].filter(Boolean).join(", ");

const formParam = () => hashParam("form");

/** Masters > People. Add, Edit and Duplicate open in a new tab. */
export function SalesPeoplePage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const form = formParam();
  if (form) return <PersonFormTab form={form} canEdit={canEdit} />;
  return <PeopleList session={session} canEdit={canEdit} />;
}

function PeopleList(props: { session: SignedIn; canEdit: boolean }) {
  const { canEdit } = props;
  // One page of 25 at a time, found on the server (Sidharth, 2026-11-24: large lists).
  const [data, setData] = useState<Paged<SalesPerson> | null>(null);
  const [page, setPage] = useState(1);
  const [searches, setSearches] = useState<Record<string, string>>({});
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [inactive, setInactive] = useShowInactive();
  const [selected, setSelected] = useState<SalesPerson | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (JSON.stringify(typed) === JSON.stringify(searches)) return;
    const wait = setTimeout(() => {
      setSearches(typed);
      setPage(1);
      setSelected(null);
    }, 300);
    return () => clearTimeout(wait);
  }, [typed, searches]);
  const turnPage = (p: number) => {
    setPage(p);
    setSelected(null);
  };
  const columns = useColumns<SalesPerson>("sales-people", [
    {
      key: "name",
      label: "Name",
      fixed: true,
      search: "name",
      cell: (p) => (
        <>
          {p.name}
          {!p.is_active && <span className="pill">Disabled</span>}
        </>
      ),
    },
    { key: "works", label: "Works As", standard: true, search: "works", cell: worksAs },
    { key: "mobile", label: "Mobile", standard: true, search: "mobile", cell: (p) => p.mobile },
    { key: "user", label: "MyERP User", standard: true, search: "user", cell: (p) => p.user_name },
    { key: "parties", label: "Parties", standard: true, num: true, cell: (p) => (p.party_count > 0 ? p.party_count : <span className="small">—</span>) },
    { key: "email", label: "Email", search: "email", cell: (p) => p.email },
    { key: "notes", label: "Notes", search: "notes", cell: (p) => p.notes },
  ]);
  const sortKey = columns.sort;
  const reload = useCallback(() => {
    const q = new URLSearchParams({ page: String(page) });
    Object.entries(searches).forEach(([k, v]) => {
      if (v.trim()) q.set(k, v.trim());
    });
    if (inactive) q.set("inactive", "1");
    if (sortKey) q.set("sort", sortKey);
    return api<Paged<SalesPerson>>(`v1/sales-people/?${q}`)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [page, searches, inactive, sortKey]);
  useEffect(() => {
    reload();
  }, [reload]);
  useOnReturn(reload);
  const shown = columns.shown;
  const onSearch = useCallback(
    (values: string[]) => {
      const next: Record<string, string> = {};
      shown.forEach((c, i) => {
        if (c.search && values[i]?.trim()) next[c.search] = values[i];
      });
      setTyped((was) => (JSON.stringify(was) === JSON.stringify(next) ? was : next));
    },
    [shown],
  );
  const people = useMemo(() => data?.results ?? [], [data]);
  // Show one person at the right, even when not on this page (just saved, or opened by link).
  const show = useCallback((id: number) => {
    api<SalesPerson>(`v1/sales-people/${id}/`).then(setSelected, () => undefined);
  }, []);
  useCreated("sales_person_saved", (c) => {
    reload();
    show(c.id);
  });
  const startName = useNewName();
  const startAs = hashParam("as");
  useEffect(() => {
    // Opened by "Create …" in a dropdown: go straight to the Add page.
    if (startName && canEdit) window.location.hash = `#/sales-people?form=new&new=${encodeURIComponent(startName)}${startAs ? `&as=${startAs}` : ""}`;
  }, [startName, startAs, canEdit]);
  const io = useExchange({
    master: "sales-people",
    noun: "people",
    session: props.session,
    onImported: () => void reload(),
    printScreen: { title: "People" },
    extra: [columns.item],
  });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId) {
      show(openId);
      opened();
    }
  }, [openId, opened, show]);
  const current = selected ?? people[0] ?? null;
  const edit = (what: number | string) => openTab(`#/sales-people?form=${what}`);
  const filtered = Object.values(searches).some((v) => v.trim());
  const count = data?.count ?? 0;
  return (
    <section className="page">
      <PageHeader
        title="People"
        sub={`${data === null ? "Loading…" : `${count.toLocaleString("en-IN")}${inactive ? "" : " active"} ${count === 1 ? "person" : "people"}${filtered ? " match" : ""} · `}the people who sell to customers, buy from suppliers or receive goods in the stores, with or without a MyERP sign-in. One list for every company in the group.`}
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>Add person</button>}
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {io.panel}
      {columns.panel}
      <div className="side-layout">
        <div className="side-main">
          <table className="pick">
            <thead>
              <tr>
                {shown.map((c) => (
                  <th key={c.key} className={c.num ? "num" : undefined} data-no-search={c.search ? undefined : ""}>
                    {columns.heading(c)}
                  </th>
                ))}
                <ActionHeads />
              </tr>
              <ColumnSearch key={shown.map((c) => c.key).join(",")} onSearch={onSearch} />
            </thead>
            <tbody>
              {people.map((p) => (
                <tr
                  key={p.id}
                  className={`${p.is_active ? "" : "off"}${current?.id === p.id ? " selected" : ""}`}
                  onClick={() => setSelected(p)}
                  onDoubleClick={() => edit(p.id)}
                >
                  {shown.map((c) => (
                    <td key={c.key} className={c.num ? "num" : undefined}>
                      {c.cell(p)}
                    </td>
                  ))}
                  <ActionCells canEdit={canEdit} onOpen={() => edit(p.id)} onDuplicate={() => edit(`copy-${p.id}`)} />
                </tr>
              ))}
              {data !== null && people.length === 0 && (
                <tr>
                  <td colSpan={shown.length + 2} className="small">
                    {filtered ? "No one matches." : 'No one yet. Click "Add person".'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Pager data={data} noun="people" onPage={turnPage}>
            <ShowInactive
              noun="People"
              on={inactive}
              onChange={(v) => {
                setInactive(v);
                turnPage(1);
              }}
            />
          </Pager>
        </div>
        <div className="side-col">
          <SidePanel title="Person Details">
            {current ? (
              <SideRows
                rows={[
                  ["Name", current.name],
                  ["Works As", worksAs(current)],
                  ["Mobile", current.mobile],
                  ["Email", current.email],
                  ["MyERP User", current.user_name || "None (no sign-in)"],
                  ["Parties", String(current.party_count)],
                  ["Disabled", current.is_active ? "No" : "Yes"],
                  ["Notes", current.notes],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="sales_person" id={current?.id} stamp={JSON.stringify(current ?? people.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one person, alone in its own tab: Save and Cancel close the tab. */
function PersonFormTab(props: { form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const [loaded, setLoaded] = useState(props.form === "new");
  const [target, setTarget] = useState<SalesPerson | null>(null);
  useEffect(() => {
    if (props.form === "new") return;
    api<SalesPerson>(`v1/sales-people/${key}/`)
      .then(setTarget, () => setTarget(null))
      .finally(() => setLoaded(true));
  }, [props.form, key]);
  const startName = useNewName();
  const toList = () => {
    window.location.hash = "#/sales-people";
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("sales_person_saved", saved);
    closeThisTab(toList);
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "Add person" : copy ? "Duplicate person" : readOnly ? "View person" : "Edit person";
  if (!loaded)
    return (
      <section className="page">
        <PageHeader title={title} />
      </section>
    );
  if (props.form !== "new" && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That person was not found.</p>
      </section>
    );
  if (readOnly && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view this list.</p>
      </section>
    );
  return (
    <PersonForm
      title={title}
      person={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      startAs={props.form === "new" ? hashParam("as") : null}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

type User = { id: number; name: string };

function PersonForm(props: {
  title: string;
  person: SalesPerson | null;
  copyOf?: SalesPerson | null;
  startName?: string;
  /** "salesman", "purchaser" or "stores": opened by "Create …" on a customer, supplier or goods receipt. */
  startAs?: string | null;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const p = props.person;
  const from = p ?? props.copyOf ?? null;
  const [name, setName] = useState(props.startName ?? (props.copyOf ? `${props.copyOf.name} (copy)` : (p?.name ?? "")));
  const [salesman, setSalesman] = useState(from ? from.is_salesman : props.startAs === "salesman");
  const [purchaser, setPurchaser] = useState(from ? from.is_purchaser : props.startAs === "purchaser");
  const [stores, setStores] = useState(from ? from.is_stores : props.startAs === "stores");
  const [mobile, setMobile] = useState(p?.mobile ?? "");
  const [email, setEmail] = useState(p?.email ?? "");
  const [user, setUser] = useState<number | null>(p?.user ?? null);
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [disabled, setDisabled] = useState(p ? !p.is_active : false);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<User[]>("v1/people/").then(setUsers);
  }, []);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = { name, is_salesman: salesman, is_purchaser: purchaser, is_stores: stores, mobile, email, user, notes };
    try {
      if (p) {
        await api(`v1/sales-people/${p.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: p.id, name });
      } else {
        const made = await api<{ id: number; name: string }>("v1/sales-people/", body);
        announceCreated("sales_person", made);
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
      sub={p ? p.name : undefined}
      formId="sales-person-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={p ? { value: disabled, set: setDisabled } : undefined}
      activity={p ? <ChangeLog type="sales_person" id={p.id} stamp={JSON.stringify(p)} /> : undefined}
    >
      <Section title="General">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Name</span>
            <input required autoFocus value={name} placeholder="e.g. Ramesh Kumar" onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Mobile
            <input value={mobile} inputMode="tel" maxLength={20} onChange={(e) => setMobile(e.target.value)} />
          </label>
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            MyERP User
            <Combobox
              value={user === null ? "" : String(user)}
              empty="None (no sign-in)"
              options={users.map((u) => ({ value: String(u.id), label: u.name }))}
              onChange={(v) => setUser(v ? Number(v) : null)}
            />
            <span className="small">Only if this person also signs in to MyERP</span>
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
        <fieldset className="item-checks">
          <legend>
            <span className="req">Works As</span>
          </legend>
          <label className="check">
            <input type="checkbox" checked={salesman} onChange={(e) => setSalesman(e.target.checked)} />
            Salesman
          </label>
          <label className="check">
            <input type="checkbox" checked={purchaser} onChange={(e) => setPurchaser(e.target.checked)} />
            Purchaser
          </label>
          <label className="check">
            <input type="checkbox" checked={stores} onChange={(e) => setStores(e.target.checked)} />
            Stores
          </label>
          <p className="small">
            Tick at least one. A Salesman is offered on customers, a Purchaser on suppliers, Stores as "Received By" and "QC By" on goods receipts.
          </p>
        </fieldset>
      </Section>
    </FormPage>
  );
}
