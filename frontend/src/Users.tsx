import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ErrorNote, useOpenParam } from "./ErrorNote";
import { api, upload, SignedIn } from "./api";
import { Activity, WithActivity } from "./Audit";
import { ActionCells, ActionHeads, ActiveButton, FormBody } from "./RowActions";
import { PageHeader, Section } from "./Brand";
import { usePrintMenu } from "./Exchange";

type Role = {
  id: number;
  code: string;
  name: string;
  description: string;
  permissions: string[];
  is_standard: boolean;
  is_active: boolean;
  user_count: number;
};
type Area = { code: string; label: string; permissions: { code: string; label: string }[] };
type User = {
  id: number;
  email: string;
  full_name: string;
  phone: string;
  signature: string;
  is_active: boolean;
  roles: number[];
  companies: number[];
  last_login: string | null;
  signed_in_before: boolean;
};
type Company = { id: number; name: string };

function useData() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [catalogue, setCatalogue] = useState<Area[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState("");
  const reload = useCallback(() => {
    Promise.all([
      api<{ roles: Role[]; catalogue: Area[] }>("v1/roles/"),
      api<User[]>("v1/users/"),
      api<Company[]>("v1/companies/"),
    ])
      .then(([r, u, c]) => {
        setRoles(r.roles);
        setCatalogue(r.catalogue);
        setUsers(u);
        setCompanies(c);
      })
      .catch((err: Error) => setError(err.message));
  }, []);
  useEffect(reload, [reload]);
  return { roles, catalogue, users, companies, error, reload };
}

function Checks<T extends { id: number; name: string }>(props: {
  items: T[];
  selected: number[];
  onChange: (ids: number[]) => void;
  disabled?: (item: T) => boolean;
}) {
  return (
    <div className="checks">
      {props.items.map((item) => (
        <label key={item.id} className="check">
          <input
            type="checkbox"
            checked={props.selected.includes(item.id)}
            disabled={props.disabled?.(item)}
            onChange={(e) =>
              props.onChange(
                e.target.checked ? [...props.selected, item.id] : props.selected.filter((id) => id !== item.id),
              )
            }
          />
          {item.name}
        </label>
      ))}
    </div>
  );
}

export function UsersPage({ session }: { session: SignedIn }) {
  const { roles, users, companies, error, reload } = useData();
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<User | null>(null);
  const edit = (value: User | "new" | null, copy: User | null = null) => {
    setCopyOf(copy);
    setEditing(value);
  };
  const roleName = (id: number) => roles.find((r) => r.id === id)?.name ?? "?";
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    const found = openId && users.find((u) => u.id === openId);
    if (found) {
      edit(found);
      opened();
    }
  }, [openId, users, opened]);

  const printing = usePrintMenu({ title: "Users" });

  return (
    <section className="page">
      <PageHeader
        title="Users"
        crumbs={[{ label: "Settings", href: "#/users" }]}
        actions={
          <>
            {printing.buttons}
            <button onClick={() => edit("new")}>Add user</button>
          </>
        }
      />
      {printing.panel}
      <WithActivity activity={<Activity type="user" stamp={JSON.stringify(users)} />}>
        <p className="small">
          People sign in with the Google account for their email address. Add them here first; nobody else can sign in.
        </p>
        {error && <p className="error">{error}</p>}
        {editing && (
          <UserForm
            key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
            user={editing === "new" ? null : editing}
            copyOf={copyOf}
            roles={roles}
            companies={companies}
            isOwner={session.user.is_owner}
            myEmail={session.user.email}
            onDone={() => {
              edit(null);
              reload();
            }}
            onCancel={() => edit(null)}
          />
        )}
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Roles</th>
              <th>Status</th>
              <ActionHeads />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className={u.is_active ? "" : "inactive"}>
                <td>
                  {u.full_name || u.email}
                  <br />
                  <span className="small">{u.email}</span>
                </td>
                <td>{u.roles.map(roleName).join(", ") || <span className="small">No role</span>}</td>
                <td>{!u.is_active ? "Deactivated" : u.signed_in_before ? "Active" : "Not signed in yet"}</td>
                <ActionCells canEdit onOpen={() => edit(u)} onDuplicate={() => edit("new", u)} />
              </tr>
            ))}
          </tbody>
        </table>
      </WithActivity>
    </section>
  );
}

function UserForm(props: {
  user: User | null;
  copyOf?: User | null;
  roles: Role[];
  companies: Company[];
  isOwner: boolean;
  myEmail: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { user } = props;
  const from = user ?? props.copyOf; // a duplicate keeps the roles and companies, not the person
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [roleIds, setRoleIds] = useState<number[]>(from?.roles ?? []);
  const [companyIds, setCompanyIds] = useState<number[]>(from?.companies ?? []);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const body = { full_name: fullName, phone, roles: roleIds, companies: companyIds };
    try {
      if (user) await api(`v1/users/${user.id}/`, body, "PATCH");
      else await api("v1/users/", { ...body, email });
      props.onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h3>{user ? `Edit ${user.email}` : props.copyOf ? `Duplicate ${props.copyOf.full_name || props.copyOf.email}` : "Add user"}</h3>
      <FormBody>
      <Section title="User">
      {!user && (
        <label>
          Email (their Google account)
          <input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
      )}
      <label>
        Full name
        <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </label>
      <label>
        Mobile
        <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98300 22222" />
      </label>
      </Section>
      <Section title="Signature">
        {user ? (
          <SignatureBox
            user={user}
            canChange={props.isOwner || user.email === props.myEmail}
            onError={setError}
          />
        ) : (
          <p className="small">Save the user first; then their signature can be added here.</p>
        )}
      </Section>
      <fieldset>
        <legend>Roles</legend>
        <Checks
          items={props.roles.filter((r) => r.is_active || roleIds.includes(r.id))}
          selected={roleIds}
          onChange={setRoleIds}
          disabled={(r) => r.code === "owner" && !props.isOwner}
        />
      </fieldset>
      {props.companies.length > 0 && (
        <fieldset>
          <legend>Companies (none ticked = all)</legend>
          <Checks items={props.companies} selected={companyIds} onChange={setCompanyIds} />
        </fieldset>
      )}
      </FormBody>
      <ErrorNote error={error} />
      <div className="buttons">
        <button disabled={busy || (!user && !email)}>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {user && (
          <ActiveButton
            url={`v1/users/${user.id}/`}
            active={user.is_active}
            what={`${user.full_name || user.email}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}

/** The signature printed on documents the person submits. It is saved at once,
 * apart from the form's Save, and only the person or an Owner may change it. */
function SignatureBox(props: { user: User; canChange: boolean; onError: (e: unknown) => void }) {
  const [image, setImage] = useState(props.user.signature);
  const [busy, setBusy] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const url = `v1/users/${props.user.id}/signature/`;
  const run = async (work: () => Promise<User>) => {
    setBusy(true);
    props.onError("");
    try {
      setImage((await work()).signature);
    } catch (err) {
      props.onError(err);
    } finally {
      setBusy(false);
    }
  };
  const choose = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    run(() => upload<User>(url, form));
  };
  return (
    <>
      <div className="image-row">
        <div className="image-box">{image ? <img src={image} alt="Signature" /> : <span className="small">No signature</span>}</div>
        {props.canChange && (
          <div>
            <button type="button" className="link" disabled={busy} onClick={() => picker.current?.click()}>
              {image ? "Change image…" : "Upload image…"}
            </button>{" "}
            <input ref={picker} type="file" accept="image/png,image/jpeg" hidden onChange={choose} />
            {image && (
              <button type="button" className="link danger" disabled={busy} onClick={() => run(() => api<User>(url, undefined, "DELETE"))}>
                Remove
              </button>
            )}
          </div>
        )}
      </div>
      <p className="small">
        A PNG or JPG of the signature on a white or clear background, up to 300 KB. It is printed on purchase orders this
        person submits, above "Authorised Signatory". Only the person or an Owner can change it.
      </p>
    </>
  );
}

export function RolesPage({ session }: { session: SignedIn }) {
  const { roles, catalogue, error, reload } = useData();
  const [editing, setEditing] = useState<Role | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<Role | null>(null);
  const edit = (value: Role | "new" | null, copy: Role | null = null) => {
    setCopyOf(copy);
    setEditing(value);
  };
  const owner = session.user.is_owner;
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    const found = openId && roles.find((r) => r.id === openId);
    if (found) {
      edit(found);
      opened();
    }
  }, [openId, roles, opened]);

  const printing = usePrintMenu({ title: "Roles" });

  return (
    <section className="page">
      <PageHeader
        title="Roles"
        crumbs={[{ label: "Settings", href: "#/users" }]}
        actions={
          <>
            {printing.buttons}
            {owner && <button onClick={() => edit("new")}>New role</button>}
          </>
        }
      />
      {printing.panel}
      <WithActivity activity={<Activity type="role" stamp={JSON.stringify(roles)} />}>
        <p className="small">
          {owner
            ? "A role is a set of permissions. Owner can do everything and cannot be changed."
            : "Only an Owner can change roles."}
        </p>
        {error && <p className="error">{error}</p>}
        {editing && (
          <RoleForm
            key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
            role={editing === "new" ? null : editing}
            copyOf={copyOf}
            readOnly={editing !== "new" && !(owner && editing.code !== "owner")}
            catalogue={catalogue}
            onDone={() => {
              edit(null);
              reload();
            }}
            onCancel={() => edit(null)}
          />
        )}
        <table>
          <thead>
            <tr>
              <th>Role</th>
              <th>Users</th>
              <ActionHeads />
            </tr>
          </thead>
          <tbody>
            {roles.map((r) => (
              <tr key={r.id} className={r.is_active ? "" : "inactive"}>
                <td>
                  {r.name}
                  {!r.is_active && <span className="pill">Disabled</span>}
                  <br />
                  <span className="small">{r.description}</span>
                </td>
                <td>{r.user_count}</td>
                <ActionCells
                  canEdit={owner && r.code !== "owner"}
                  canDuplicate={owner}
                  onOpen={() => edit(r)}
                  onDuplicate={() => edit("new", r)}
                />
              </tr>
            ))}
          </tbody>
        </table>
      </WithActivity>
    </section>
  );
}

function RoleForm(props: {
  role: Role | null;
  copyOf?: Role | null;
  readOnly?: boolean;
  catalogue: Area[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const { role } = props;
  const from = role ?? props.copyOf;
  const [name, setName] = useState(role?.name ?? (props.copyOf ? `${props.copyOf.name} (copy)` : ""));
  const [description, setDescription] = useState(from?.description ?? "");
  const [perms, setPerms] = useState<string[]>(from?.permissions ?? []);
  const [error, setError] = useState<unknown>("");

  const toggle = (code: string, on: boolean) => setPerms(on ? [...perms, code] : perms.filter((p) => p !== code));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = { name, description, permissions: perms };
    try {
      if (role) await api(`v1/roles/${role.id}/`, body, "PATCH");
      else await api("v1/roles/", body);
      props.onDone();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <form className="card" onSubmit={save}>
      <h3>{role ? `${props.readOnly ? "View" : "Edit"} ${role.name}` : props.copyOf ? `Duplicate ${props.copyOf.name}` : "New role"}</h3>
      <FormBody readOnly={props.readOnly}>
      <Section title="Role">
      <label>
        Name
        <input required value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Description
        <input value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      </Section>
      {props.catalogue.map((area) => (
        <fieldset key={area.code}>
          <legend>{area.label}</legend>
          <div className="checks">
            {area.permissions.map((p) => (
              <label key={p.code} className="check">
                <input type="checkbox" checked={perms.includes(p.code)} onChange={(e) => toggle(p.code, e.target.checked)} />
                {p.label}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      </FormBody>
      <ErrorNote error={error} />
      <div className="buttons">
        {!props.readOnly && <button>Save</button>}
        <button type="button" className="link" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
        {role && !role.is_standard && !props.readOnly && (
          <ActiveButton
            url={`v1/roles/${role.id}/`}
            active={role.is_active}
            what={`the role ${role.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}
