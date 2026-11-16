import { useCallback, useEffect, useState } from "react";
import { api, ApiError, Session, SignedIn } from "./api";
import { CompaniesPage, CompanyPage } from "./Companies";
import { LedgerGroupsPage } from "./LedgerGroups";
import { CreditTermsPage } from "./CreditTerms";
import { PriceListsPage } from "./PriceLists";
import { TermsPage } from "./Terms";
import { Dashboard } from "./Dashboard";
import { ItemsPage } from "./Items";
import { LedgersPage } from "./Ledgers";
import { SignIn } from "./Login";
import { DataResetPage } from "./DataReset";
import { HsnPage } from "./Hsn";
import { UnitsPage } from "./Units";
import { RolesPage, UsersPage } from "./Users";
import { ShipmentsPage } from "./Shipments";
import { TransportersPage } from "./Transporters";
import { WarehousesPage } from "./Warehouses";
import "./app.css";
import { Logo } from "./Brand";
import { BatchesPage } from "./Batches";
import { BrandsPage } from "./Brands";
import { SalesPeoplePage } from "./SalesPeople";
import { ItemGroupsPage } from "./ItemGroups";
import { CentralPage } from "./Central";
import { CountriesPage } from "./Countries";
import { PinCodesPage } from "./PinCodes";
import { RequestAdditionPage } from "./RequestAddition";
import { HelpPage, helpTopicFor } from "./help/Help";
import { AdminMenu, CompanyPicker, EntryMenu, MastersMenu, SalesMenu, useCurrentCompany } from "./MastersMenu";
import { PurchaseOrdersPage } from "./PurchaseOrders";
import { BinContentsPage } from "./BinContents";
import { GoodsReceiptsPage } from "./GoodsReceipts";
import { PurchaseInvoicesPage } from "./PurchaseInvoices";
import { PurchaseReturnsPage } from "./PurchaseReturns";
import { DebitNotesPage } from "./DebitNotes";
import { NotificationBell } from "./Notifications";
import { SupplierReplyPage } from "./SupplierReply";

type Page = "home" | "users" | "roles" | "companies" | "credit-terms" | "price-lists" | "terms" | "units" | "item-groups" | "brands" | "sales-people" | "batches" | "items" | "hsn" | "reset" | "central" | "request-addition" | "countries" | "pin-codes" | "help" | "bins";
type Route = { page: Page; id?: number; sub?: string; subId?: number; topic?: string };

function routeFromHash(): Route {
  const [page, id, sub, subId] = window.location.hash.replace(/^#\/?/, "").split("?")[0].split("/");
  if (page === "companies")
    return { page, id: id ? Number(id) : undefined, sub, subId: subId ? Number(subId) : undefined };
  if (page === "help") return { page, topic: id };
  if (page === "bins") return { page, id: Number(id) || undefined };
  return { page: page === "users" || page === "roles" || page === "credit-terms" || page === "price-lists" || page === "terms" || page === "units" || page === "item-groups" || page === "brands" || page === "sales-people" || page === "batches" || page === "hsn" || page === "items" || page === "reset" || page === "central" || page === "request-addition" || page === "countries" || page === "pin-codes" ? page : "home" };
}

export function App() {
  // The supplier's page from a mailed order: no sign-in (SupplierReply.tsx).
  const reply = window.location.hash.match(/^#\/po-reply\/([\w-]+)/);
  if (reply) return <SupplierReplyPage token={reply[1]} />;
  return <Signed />;
}

function Signed() {
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
  const canSeePurchase = session.permissions.includes("purchase.view");
  // Goods are received by purchase or by the stores (stock rights).
  const canReceive = canSeePurchase || session.permissions.includes("stock.view");
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
              active={page === "credit-terms" || page === "price-lists" || page === "terms" || page === "units" || page === "item-groups" || page === "brands" || page === "sales-people" || page === "batches" || page === "items" || (page === "companies" && (sub === "ledgers" || sub === "groups" || sub === "couriers" || sub === "warehouses"))}
              company={current.company}
              canSeeMasters={canSeeMasters}
            />
          )}
          {canReceive && current.company?.modules.includes("purchase") && (
            <EntryMenu active={page === "companies" && (sub === "purchase-orders" || sub === "goods-receipts" || sub === "purchase-invoices" || sub === "purchase-returns" || sub === "debit-notes")} company={current.company} orders={canSeePurchase} />
          )}
          {canSeeShipments && current.company?.modules.includes("sales") && (
            <SalesMenu active={page === "companies" && sub === "shipments"} company={current.company} />
          )}
          {session.user.is_owner && (
            <AdminMenu
              active={page === "users" || page === "roles" || page === "reset" || (page === "companies" && !["ledgers", "groups", "couriers", "warehouses", "shipments", "purchase-orders", "goods-receipts", "purchase-invoices", "purchase-returns", "debit-notes"].includes(sub ?? ""))}
              canSeeMasters={canSeeMasters}
              canManageUsers={canManageUsers}
            />
          )}
          {session.user.is_platform_admin && link("central", "Central")}
        </nav>
        <span className="who">
          <CompanyPicker companies={current.companies} company={current.company} onChoose={current.choose} />
          <NotificationBell />
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
        ) : page === "bins" && id && canSeeMasters ? (
          <BinContentsPage key={id} id={id} />
        ) : page === "companies" && id && sub === "purchase-orders" && canSeePurchase ? (
          <PurchaseOrdersPage key={id} companyId={id} session={session} />
        ) : page === "companies" && id && sub === "purchase-invoices" && canSeePurchase ? (
          <PurchaseInvoicesPage key={id} companyId={id} session={session} />
        ) : page === "companies" && id && sub === "debit-notes" && canSeePurchase ? (
          <DebitNotesPage key={id} companyId={id} session={session} />
        ) : page === "companies" && id && sub === "purchase-returns" && canReceive ? (
          <PurchaseReturnsPage key={id} companyId={id} session={session} />
        ) : page === "companies" && id && sub === "goods-receipts" && canReceive ? (
          <GoodsReceiptsPage key={id} companyId={id} session={session} />
        ) : page === "companies" && canSeeMasters ? (
          id && sub === "shipments" && canSeeShipments ? (
            <ShipmentsPage key={id} companyId={id} session={session} />
          ) : id && sub === "couriers" ? (
            <TransportersPage key={id} companyId={id} session={session} />
          ) : id && sub === "warehouses" ? (
            <WarehousesPage key={id} companyId={id} session={session} />
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
        ) : page === "price-lists" && canSeeMasters ? (
          <PriceListsPage session={session} />
        ) : page === "terms" && canSeeMasters ? (
          <TermsPage session={session} />
        ) : page === "items" && canSeeMasters ? (
          <ItemsPage session={session} />
        ) : page === "reset" && session.user.is_owner ? (
          <DataResetPage session={session} />
        ) : page === "central" && session.user.is_platform_admin ? (
          <CentralPage />
        ) : page === "request-addition" && canSeeMasters ? (
          <RequestAdditionPage />
        ) : page === "countries" && canSeeMasters ? (
          <CountriesPage session={session} />
        ) : page === "pin-codes" && canSeeMasters ? (
          <PinCodesPage session={session} />
        ) : page === "hsn" && canSeeMasters ? (
          <HsnPage session={session} />
        ) : page === "batches" && canSeeMasters ? (
          <BatchesPage session={session} />
        ) : page === "brands" && canSeeMasters ? (
          <BrandsPage session={session} />
        ) : page === "sales-people" && canSeeMasters ? (
          <SalesPeoplePage session={session} />
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
