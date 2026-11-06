import { useCallback, useEffect, useState } from "react";
import { api, ApiError, Session, SignedIn } from "./api";
import { CompaniesPage, CompanyPage, LedgerGroupsPage, type Company } from "./Companies";
import { LedgersPage } from "./Ledgers";
import { SignIn } from "./Login";
import { RolesPage, UsersPage } from "./Users";
import "./app.css";
import { Logo, PageHeader } from "./Brand";

type WhoAmI = { tenant: string; name: string; companies: string[] };
type Page = "home" | "users" | "roles" | "companies";
type Route = { page: Page; id?: number; sub?: string; subId?: number };

function routeFromHash(): Route {
  const [page, id, sub, subId] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (page === "companies")
    return { page, id: id ? Number(id) : undefined, sub, subId: subId ? Number(subId) : undefined };
  return { page: page === "users" || page === "roles" ? page : "home" };
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Session>("auth/session/")
      .then(setSession)
      .catch((err: ApiError) => setError(err.status === 404 ? "Unknown company group address." : err.message));
  }, []);
  const onChange = useCallback((s: Session) => setSession(s), []);

  if (session?.signed_in) return <Shell session={session} onSignOut={onChange} />;
  return (
    <main className="narrow">
      <h1 className="login-logo">
        <Logo size={40} />
      </h1>
      {error && <p className="error">{error}</p>}
      {session === null ? (
        !error && <p>Loading…</p>
      ) : (
        <SignIn clientId={session.google_client_id} onChange={onChange} />
      )}
    </main>
  );
}

function Shell({ session, onSignOut }: { session: SignedIn; onSignOut: (s: Session) => void }) {
  const [{ page, id, sub, subId }, setRoute] = useState<Route>(routeFromHash);
  useEffect(() => {
    const onHash = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const canManageUsers = session.permissions.includes("users.manage");
  const canSeeMasters = session.permissions.includes("masters.view");
  const signOut = () => {
    // Stop Google from signing the person straight back in on this browser.
    if ("google" in window) google.accounts.id.disableAutoSelect();
    api<Session>("auth/logout/", {}).then(onSignOut);
  };
  const link = (target: Page, label: string) => (
    <a href={`#/${target === "home" ? "" : target}`} className={page === target ? "active" : ""}>
      {label}
    </a>
  );

  return (
    <>
      <header className="topbar">
        <a href="#/" className="home-link" aria-label="MyERP home">
          <Logo />
        </a>
        <nav aria-label="Modules">
          {link("home", "Home")}
          {canSeeMasters && link("companies", "Masters")}
          {canManageUsers && link("users", "Users")}
          {canManageUsers && link("roles", "Roles")}
        </nav>
        <span className="who">
          <span className="avatar" aria-hidden="true">
            {session.user.name.trim().charAt(0).toUpperCase() || "?"}
          </span>
          <span className="who-name">{session.user.name}</span>
          <button className="link" onClick={signOut}>
            Sign out
          </button>
        </span>
      </header>
      <main>
        {page === "companies" && canSeeMasters ? (
          id && sub === "ledgers" ? (
            <LedgersPage key={`${id}-${subId}`} companyId={id} groupId={subId} session={session} />
          ) : id && sub === "groups" ? (
            <LedgerGroupsPage key={id} id={id} session={session} />
          ) : id ? (
            <CompanyPage key={id} id={id} session={session} />
          ) : (
            <CompaniesPage session={session} />
          )
        ) : page === "users" && canManageUsers ? (
          <UsersPage session={session} />
        ) : page === "roles" && canManageUsers ? (
          <RolesPage session={session} />
        ) : (
          <Home session={session} />
        )}
      </main>
    </>
  );
}

function Home({ session }: { session: SignedIn }) {
  const [who, setWho] = useState<WhoAmI | null>(null);
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const canSeeMasters = session.permissions.includes("masters.view");
  useEffect(() => {
    api<WhoAmI>("whoami/").then(setWho);
    if (canSeeMasters) api<Company[]>("v1/companies/").then(setCompanies);
  }, [canSeeMasters]);
  return (
    <section className="page">
      <PageHeader title={`Welcome, ${session.user.name}`} sub={who?.name} />
      {who && who.companies.length === 0 && <p>No companies yet.</p>}
      {companies && companies.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Company</th>
              <th>GSTIN</th>
              <th>State</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {companies.map((c) => (
              <tr key={c.id}>
                <td>
                  <a href={`#/companies/${c.id}`}>{c.name}</a>
                </td>
                <td>{c.gstin || <span className="small">Unregistered</span>}</td>
                <td>{c.state}</td>
                <td>
                  <a href={`#/companies/${c.id}/ledgers`}>Ledgers</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        who &&
        !canSeeMasters &&
        who.companies.length > 0 && (
          <table>
            <tbody>
              {who.companies.map((name) => (
                <tr key={name}>
                  <td>{name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
      {session.permissions.length === 0 && (
        <p className="small">You have no role yet. Ask your MyERP admin to give you one.</p>
      )}
    </section>
  );
}
