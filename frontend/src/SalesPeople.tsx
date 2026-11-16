import { FormEvent, useCallback, useEffect, useState } from "react";
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

/** Salesmen and Purchasers (Sidharth, 2026-11-16, preview 83): the people who sell to
 * customers and buy from suppliers, with or without a MyERP sign-in. One list for every
 * company in the group; a customer picks a Salesman, a supplier a Purchaser. */
export type SalesPerson = {
  id: number;
  name: string;
  is_salesman: boolean;
  is_purchaser: boolean;
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
  return { people, reload, refresh };
}

export const worksAs = (p: SalesPerson) => [p.is_salesman && "Salesman", p.is_purchaser && "Purchaser"].filter(Boolean).join(", ");

const formParam = () => hashParam("form");

/** Masters > Salesmen and Purchasers. Add, Edit and Duplicate open in a new tab. */
export function SalesPeoplePage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { people, reload } = useSalesPeople();
  const form = formParam();
  if (form) return <PersonFormTab form={form} canEdit={canEdit} />;
  return <PeopleList session={session} canEdit={canEdit} people={people} reload={reload} />;
}

function PeopleList(props: { session: SignedIn; canEdit: boolean; people: SalesPerson[]; reload: () => void }) {
  const { people, canEdit, reload } = props;
  const [selectedId, setSelected] = useState<number | null>(null);
  useCreated("sales_person_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  const startAs = hashParam("as");
  useEffect(() => {
    // Opened by "Create …" in a dropdown: go straight to the Add page.
    if (startName && canEdit) window.location.hash = `#/sales-people?form=new&new=${encodeURIComponent(startName)}${startAs ? `&as=${startAs}` : ""}`;
  }, [startName, startAs, canEdit]);
  const io = useExchange({ master: "sales-people", noun: "people", session: props.session, onImported: reload });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && people.some((p) => p.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, people, opened]);
  const selected = people.find((p) => p.id === selectedId) ?? null;
  const edit = (what: number | string) => openTab(`#/sales-people?form=${what}`);
  return (
    <section className="page">
      <PageHeader
        title="Salesmen and Purchasers"
        sub="The people who sell to customers and buy from suppliers, with or without a MyERP sign-in. One list for every company in the group."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>Add person</button>}
          </>
        }
      />
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          <table className="pick">
            <thead>
              <tr>
                <th>Name</th>
                <th>Works As</th>
                <th>Mobile</th>
                <th>MyERP User</th>
                <th className="num">Parties</th>
                <ActionHeads />
              </tr>
              <ColumnSearch />
            </thead>
            <tbody>
              {people.map((p) => (
                <tr
                  key={p.id}
                  className={`${p.is_active ? "" : "off"}${selectedId === p.id ? " selected" : ""}`}
                  onClick={() => setSelected(p.id)}
                  onDoubleClick={() => edit(p.id)}
                >
                  <td>
                    {p.name}
                    {!p.is_active && <span className="pill">Disabled</span>}
                  </td>
                  <td>{worksAs(p)}</td>
                  <td>{p.mobile}</td>
                  <td>{p.user_name}</td>
                  <td className="num">{p.party_count > 0 ? p.party_count : <span className="small">—</span>}</td>
                  <ActionCells canEdit={canEdit} onOpen={() => edit(p.id)} onDuplicate={() => edit(`copy-${p.id}`)} />
                </tr>
              ))}
              {people.length === 0 && (
                <tr>
                  <td colSpan={7} className="small">
                    No one yet. Click "Add person".
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="side-col">
          <SidePanel title="Person Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.name],
                  ["Works As", worksAs(selected)],
                  ["Mobile", selected.mobile],
                  ["Email", selected.email],
                  ["MyERP User", selected.user_name || "None (no sign-in)"],
                  ["Parties", String(selected.party_count)],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                  ["Notes", selected.notes],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="sales_person" id={selected?.id} stamp={JSON.stringify(selected ?? people.length)} />
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
  const [people, setPeople] = useState<SalesPerson[]>([]);
  useEffect(() => {
    if (props.form === "new") return;
    api<SalesPerson[]>("v1/sales-people/").then((rows) => {
      setPeople(rows);
      setLoaded(true);
    });
  }, [props.form]);
  const startName = useNewName();
  const target = props.form === "new" ? null : (people.find((p) => p.id === key) ?? null);
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
  /** "salesman" or "purchaser": opened by "Create …" on a customer or supplier. */
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
    const body = { name, is_salesman: salesman, is_purchaser: purchaser, mobile, email, user, notes };
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
          <p className="small">Tick at least one. A Salesman is offered on customers, a Purchaser on suppliers.</p>
        </fieldset>
      </Section>
    </FormPage>
  );
}
