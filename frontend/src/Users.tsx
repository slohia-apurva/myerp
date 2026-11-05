import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, SignedIn } from "./api";

type Role = {
  id: number;
  code: string;
  name: string;
  description: string;
  permissions: string[];
  is_standard: boolean;
  user_count: number;
};
type Area = { code: string; label: string; permissions: { code: string; label: string }[] };
type User = {
  id: number;
  email: string;
  full_name: string;
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
  const roleName = (id: number) => roles.find((r) => r.id === id)?.name ?? "?";

  return (
    <section className="page">
      <div className="page-head">
        <h2>Users</h2>
        <button onClick={() => setEditing("new")}>Add user</button>
      </div>
      <p className="small">
        People sign in with the Google account for their email address. Add them here first; nobody else can sign in.
      </p>
      {error && <p className="error">{error}</p>}
      {editing && (
        <UserForm
          user={editing === "new" ? null : editing}
          roles={roles}
          companies={companies}
          isOwner={session.user.is_owner}
          onDone={() => {
            setEditing(null);
            reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Roles</th>
            <th>Status</th>
            <th />
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
              <td>
                <button className="link" onClick={() => setEditing(u)}>
                  Edit
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function UserForm(props: {
  user: User | null;
  roles: Role[];
  companies: Company[];
  isOwner: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { user } = props;
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [roleIds, setRoleIds] = useState<number[]>(user?.roles ?? []);
  const [companyIds, setCompanyIds] = useState<number[]>(user?.companies ?? []);
  const [active, setActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const body = { full_name: fullName, roles: roleIds, companies: companyIds, is_active: active };
    try {
      if (user) await api(`v1/users/${user.id}/`, body, "PATCH");
      else await api("v1/users/", { ...body, email });
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h3>{user ? `Edit ${user.email}` : "Add user"}</h3>
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
      <fieldset>
        <legend>Roles</legend>
        <Checks
          items={props.roles}
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
      {user && (
        <label className="check">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          Active (untick to stop this person signing in)
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button disabled={busy || (!user && !email)}>{user ? "Save" : "Add user"}</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function RolesPage({ session }: { session: SignedIn }) {
  const { roles, catalogue, error, reload } = useData();
  const [editing, setEditing] = useState<Role | "new" | null>(null);
  const owner = session.user.is_owner;

  return (
    <section className="page">
      <div className="page-head">
        <h2>Roles</h2>
        {owner && <button onClick={() => setEditing("new")}>New role</button>}
      </div>
      <p className="small">
        {owner
          ? "A role is a set of permissions. Owner can do everything and cannot be changed."
          : "Only an Owner can change roles."}
      </p>
      {error && <p className="error">{error}</p>}
      {editing && (
        <RoleForm
          role={editing === "new" ? null : editing}
          catalogue={catalogue}
          onDone={() => {
            setEditing(null);
            reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      <table>
        <thead>
          <tr>
            <th>Role</th>
            <th>Users</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {roles.map((r) => (
            <tr key={r.id}>
              <td>
                {r.name}
                <br />
                <span className="small">{r.description}</span>
              </td>
              <td>{r.user_count}</td>
              <td>
                {owner && r.code !== "owner" && (
                  <button className="link" onClick={() => setEditing(r)}>
                    Edit
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RoleForm(props: { role: Role | null; catalogue: Area[]; onDone: () => void; onCancel: () => void }) {
  const { role } = props;
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [perms, setPerms] = useState<string[]>(role?.permissions ?? []);
  const [error, setError] = useState("");

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
      setError((err as Error).message);
    }
  };
  const remove = async () => {
    if (!role || !window.confirm(`Delete the role ${role.name}?`)) return;
    try {
      await api(`v1/roles/${role.id}/`, undefined, "DELETE");
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h3>{role ? `Edit ${role.name}` : "New role"}</h3>
      <label>
        Name
        <input required value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Description
        <input value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
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
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {role && !role.is_standard && (
          <button type="button" className="link danger" onClick={remove}>
            Delete role
          </button>
        )}
      </div>
    </form>
  );
}
