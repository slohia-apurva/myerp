import { useCallback, useEffect, useState } from "react";
import { api, ApiError, Session, SignedIn } from "./api";
import { CompaniesPage, CompanyPage, LedgerGroupsPage } from "./Companies";
import { CreditTermsPage } from "./CreditTerms";
import { Dashboard } from "./Dashboard";
import { ItemsPage } from "./Items";
import { LedgersPage } from "./Ledgers";
import { SignIn } from "./Login";
import { DataResetPage } from "./DataReset";
import { HsnPage } from "./Hsn";
import { UnitsPage } from "./Units";
import { RolesPage, UsersPage } from "./Users";
import { CourierAccountsPage, ShipmentsPage } from "./Shipments";
import "./app.css";
import { Logo } from "./Brand";
import { ItemGroupsPage } from "./ItemGroups";
import { CentralPage } from "./Central";
import { HelpPage, helpTopicFor } from "./help/Help";
import { AdminMenu, CompanyPicker, MastersMenu, SalesMenu, useCurrentCompany } from "./MastersMenu";

type Page = "home" | "users" | "roles" | "companies" | "credit-terms" | "units" | "item-groups" | "items" | "hsn" | "reset" | "central" | "help";
type Route = { page: Page; id?: number; sub?: string; subId?: number; topic?: string };

function routeFromHash(): Route {
  const [page, id, sub, subId] = window.location.hash.replace(/^#\/?/, "").split("?")[0].split("/");
  if (page === "companies")
    return { page, id: id ? Number(id) : undefined, sub, subId: subId ? Number(subId) : undefined };
  if (page === "help") return { page, topic: id };
  return { page: page === "users" || page === "roles" || page === "credit-terms" || page === "units" || page === "item-groups" || page === "hsn" || page === "items" || page === "reset" || page === "central" ? page : "home" };
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Session>("auth/session/")
      .then(setSession)
      .catch((err: ApiError) => setError(err.status === 404 ? "Unknown company group address." : err.message));
  }, []);
  const onChange = useCallback((s: Session) => {
    // Signing in always starts at the dashboard, not wherever the address bar was left.
    if (s.signed_in) window.location.hash = "#/";
    setSession(s);
  }, []);

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
  const [{ page, id, sub, subId, topic }, setRoute] = useState<Route>(routeFromHash);
  useEffect(() => {
    const onHash = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const canManageUsers = session.permissions.includes("users.manage");
  const canSeeMasters = session.permissions.includes("masters.view");
  const canSeeShipments = session.permissions.some((p) => p === "sales.view" || p === "stock.view");
  const current = useCurrentCompany(page === "companies" ? id : undefined, canSeeMasters);
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
          {link("home", "Dashboard")}
          {canSeeMasters && (
            <MastersMenu
              active={page === "credit-terms" || page === "units" || page === "item-groups" || page === "items" || (page === "companies" && (sub === "ledgers" || sub === "groups" || sub === "couriers"))}
              company={current.company}
              canSeeMasters={canSeeMasters}
            />
          )}
          {canSeeShipments && current.company?.modules.includes("sales") && (
            <SalesMenu active={page === "companies" && sub === "shipments"} company={current.company} />
          )}
          {session.user.is_owner && (
            <AdminMenu
              active={page === "users" || page === "roles" || page === "reset" || (page === "companies" && !["ledgers", "groups", "couriers", "shipments"].includes(sub ?? ""))}
              canSeeMasters={canSeeMasters}
              canManageUsers={canManageUsers}
            />
          )}
          {session.user.is_platform_admin && link("central", "Central")}
        </nav>
        <span className="who">
          <CompanyPicker companies={current.companies} company={current.company} onChoose={current.choose} />
          <a
            href={page === "help" ? "#/help" : `#/help/${helpTopicFor(window.location.hash)}`}
            className={`help-link${page === "help" ? " active" : ""}`}
            title="Help for this screen"
          >
            Help
          </a>
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
        {page === "help" ? (
          <HelpPage topic={topic} />
        ) : page === "companies" && canSeeMasters ? (
          id && sub === "shipments" && canSeeShipments ? (
            <ShipmentsPage key={id} companyId={id} session={session} />
          ) : id && sub === "couriers" ? (
            <CourierAccountsPage key={id} companyId={id} session={session} />
          ) : id && sub === "ledgers" ? (
            <LedgersPage key={`${id}-${subId}`} companyId={id} groupId={subId} session={session} />
          ) : id && sub === "groups" ? (
            <LedgerGroupsPage key={id} id={id} session={session} />
          ) : id ? (
            <CompanyPage key={id} id={id} session={session} tab={sub} />
          ) : (
            <CompaniesPage session={session} />
          )
        ) : page === "credit-terms" && canSeeMasters ? (
          <CreditTermsPage session={session} />
        ) : page === "items" && canSeeMasters ? (
          <ItemsPage session={session} />
        ) : page === "reset" && session.user.is_owner ? (
          <DataResetPage session={session} />
        ) : page === "central" && session.user.is_platform_admin ? (
          <CentralPage />
        ) : page === "hsn" && canSeeMasters ? (
          <HsnPage session={session} />
        ) : page === "item-groups" && canSeeMasters ? (
          <ItemGroupsPage session={session} />
        ) : page === "units" && canSeeMasters ? (
          <UnitsPage session={session} />
        ) : page === "users" && canManageUsers ? (
          <UsersPage session={session} />
        ) : page === "roles" && canManageUsers ? (
          <RolesPage session={session} />
        ) : (
          <Dashboard session={session} company={current.company} />
        )}
      </main>
    </>
  );
}
