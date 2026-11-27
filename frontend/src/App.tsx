import { lazy, type ReactNode, Suspense, useCallback, useEffect, useState } from "react";
import { api, ApiError, Session, SignedIn } from "./api";
import "./app.css";
import { Logo } from "./Brand";
import { AdminMenu, CompanyPicker, EntryMenu, MastersMenu, ReportsMenu, SalesMenu, useCurrentCompany } from "./MastersMenu";
import { NotificationBell } from "./Notifications";
import { SignIn } from "./Login";
import { helpTopicFor } from "./help/topic";

// Each screen is fetched when it is first opened, instead of everything in one
// file of 1.35 MB before anything shows (2026-11-25). The browser then keeps it.
const HelpPage = lazy(() => import("./help/Help").then((m) => ({ default: m.HelpPage })));
const CompaniesPage = lazy(() => import("./Companies").then((m) => ({ default: m.CompaniesPage })));
const CompanyPage = lazy(() => import("./Companies").then((m) => ({ default: m.CompanyPage })));
const LedgerGroupsPage = lazy(() => import("./LedgerGroups").then((m) => ({ default: m.LedgerGroupsPage })));
const CreditTermsPage = lazy(() => import("./CreditTerms").then((m) => ({ default: m.CreditTermsPage })));
const PriceListsPage = lazy(() => import("./PriceLists").then((m) => ({ default: m.PriceListsPage })));
const TermsPage = lazy(() => import("./Terms").then((m) => ({ default: m.TermsPage })));
const Dashboard = lazy(() => import("./Dashboard").then((m) => ({ default: m.Dashboard })));
const BomsPage = lazy(() => import("./Boms").then((m) => ({ default: m.BomsPage })));
const ItemsPage = lazy(() => import("./Items").then((m) => ({ default: m.ItemsPage })));
const LedgersPage = lazy(() => import("./Ledgers").then((m) => ({ default: m.LedgersPage })));
const BillReadingPage = lazy(() => import("./BillReading").then((m) => ({ default: m.BillReadingPage })));
const DataResetPage = lazy(() => import("./DataReset").then((m) => ({ default: m.DataResetPage })));
const MigrationToolsPage = lazy(() => import("./MigrationTools").then((m) => ({ default: m.MigrationToolsPage })));
const HsnPage = lazy(() => import("./Hsn").then((m) => ({ default: m.HsnPage })));
const UnitsPage = lazy(() => import("./Units").then((m) => ({ default: m.UnitsPage })));
const RolesPage = lazy(() => import("./Users").then((m) => ({ default: m.RolesPage })));
const UsersPage = lazy(() => import("./Users").then((m) => ({ default: m.UsersPage })));
const ShipmentsPage = lazy(() => import("./Shipments").then((m) => ({ default: m.ShipmentsPage })));
const TransportersPage = lazy(() => import("./Transporters").then((m) => ({ default: m.TransportersPage })));
const InsurancePage = lazy(() => import("./Insurance").then((m) => ({ default: m.InsurancePage })));
const WarehousesPage = lazy(() => import("./Warehouses").then((m) => ({ default: m.WarehousesPage })));
const BatchesPage = lazy(() => import("./Batches").then((m) => ({ default: m.BatchesPage })));
const ReminderSchedulePage = lazy(() => import("./ReminderSchedule").then((m) => ({ default: m.ReminderSchedulePage })));
const MailTemplatesPage = lazy(() => import("./MailTemplates").then((m) => ({ default: m.MailTemplatesPage })));
const BrandsPage = lazy(() => import("./Brands").then((m) => ({ default: m.BrandsPage })));
const SalesPeoplePage = lazy(() => import("./SalesPeople").then((m) => ({ default: m.SalesPeoplePage })));
const ItemGroupsPage = lazy(() => import("./ItemGroups").then((m) => ({ default: m.ItemGroupsPage })));
const CentralPage = lazy(() => import("./Central").then((m) => ({ default: m.CentralPage })));
const CountriesPage = lazy(() => import("./Countries").then((m) => ({ default: m.CountriesPage })));
const PinCodesPage = lazy(() => import("./PinCodes").then((m) => ({ default: m.PinCodesPage })));
const RequestAdditionPage = lazy(() => import("./RequestAddition").then((m) => ({ default: m.RequestAdditionPage })));
const StockCheckPage = lazy(() => import("./StockCheck").then((m) => ({ default: m.StockCheckPage })));
const StockTransfersPage = lazy(() => import("./StockTransfers").then((m) => ({ default: m.StockTransfersPage })));
const CustomerStockPage = lazy(() => import("./CustomerStock").then((m) => ({ default: m.CustomerStockPage })));
const OwnUsePage = lazy(() => import("./OwnUse").then((m) => ({ default: m.OwnUsePage })));
const ManufacturingOrdersPage = lazy(() => import("./ManufacturingOrders").then((m) => ({ default: m.ManufacturingOrdersPage })));
const StockLedgerPage = lazy(() => import("./Reports").then((m) => ({ default: m.StockLedgerPage })));
const ProcurementTrackerPage = lazy(() => import("./PurchaseReports").then((m) => ({ default: m.ProcurementTrackerPage })));
const PendingPurchaseOrdersPage = lazy(() => import("./PurchaseReports").then((m) => ({ default: m.PendingPurchaseOrdersPage })));
const StockSummaryPage = lazy(() => import("./Reports").then((m) => ({ default: m.StockSummaryPage })));
const LedgerStatementPage = lazy(() => import("./Books").then((m) => ({ default: m.LedgerStatementPage })));
const TrialBalancePage = lazy(() => import("./Books").then((m) => ({ default: m.TrialBalancePage })));
const PurchaseOrdersPage = lazy(() => import("./PurchaseOrders").then((m) => ({ default: m.PurchaseOrdersPage })));
const SalesOrdersPage = lazy(() => import("./SalesOrders").then((m) => ({ default: m.SalesOrdersPage })));
const ScanPickingPage = lazy(() => import("./ScanPicking").then((m) => ({ default: m.ScanPickingPage })));
const PickListsPage = lazy(() => import("./PickLists").then((m) => ({ default: m.PickListsPage })));
const DeliveryNotesPage = lazy(() => import("./DeliveryNotes").then((m) => ({ default: m.DeliveryNotesPage })));
const SalesInvoicesPage = lazy(() => import("./SalesInvoices").then((m) => ({ default: m.SalesInvoicesPage })));
const CreditNotesPage = lazy(() => import("./CreditNotes").then((m) => ({ default: m.CreditNotesPage })));
const BatchTracePage = lazy(() => import("./BatchTrace").then((m) => ({ default: m.BatchTracePage })));
const BinContentsPage = lazy(() => import("./BinContents").then((m) => ({ default: m.BinContentsPage })));
const GoodsReceiptsPage = lazy(() => import("./GoodsReceipts").then((m) => ({ default: m.GoodsReceiptsPage })));
const PurchaseInvoicesPage = lazy(() => import("./PurchaseInvoices").then((m) => ({ default: m.PurchaseInvoicesPage })));
const PurchaseReturnsPage = lazy(() => import("./PurchaseReturns").then((m) => ({ default: m.PurchaseReturnsPage })));
const DebitNotesPage = lazy(() => import("./DebitNotes").then((m) => ({ default: m.DebitNotesPage })));
const TdsAdjustmentsPage = lazy(() => import("./TdsAdjustments").then((m) => ({ default: m.TdsAdjustmentsPage })));
const TdsCheckPage = lazy(() => import("./TdsCheck").then((m) => ({ default: m.TdsCheckPage })));
const SupplierReplyPage = lazy(() => import("./SupplierReply").then((m) => ({ default: m.SupplierReplyPage })));

type Page = "home" | "users" | "roles" | "companies" | "credit-terms" | "price-lists" | "terms" | "mail-templates" | "reminder-schedule" | "units" | "item-groups" | "brands" | "sales-people" | "batches" | "items" | "boms" | "hsn" | "reset" | "bill-reading" | "migration" | "central" | "request-addition" | "countries" | "pin-codes" | "help" | "bins";
/** The screens under "Reports" in the top menu. */
const REPORTS = ["stock-summary", "stock-ledger", "trial-balance", "ledger-statement", "pending-purchase-orders", "procurement-tracker"];
type Route = { page: Page; id?: number; sub?: string; subId?: number; topic?: string };

function routeFromHash(): Route {
  const [page, id, sub, subId] = window.location.hash.replace(/^#\/?/, "").split("?")[0].split("/");
  if (page === "companies")
    return { page, id: id ? Number(id) : undefined, sub, subId: subId ? Number(subId) : undefined };
  if (page === "help") return { page, topic: id };
  if (page === "bins") return { page, id: Number(id) || undefined };
  // The retention sample label QR opens #/batches/<id>/trace: keep that address.
  if (page === "batches" && sub === "trace") return { page: "batches", id: Number(id) || undefined, sub };
  return { page: page === "users" || page === "roles" || page === "credit-terms" || page === "price-lists" || page === "terms" || page === "mail-templates" || page === "reminder-schedule" || page === "units" || page === "item-groups" || page === "brands" || page === "sales-people" || page === "batches" || page === "hsn" || page === "items" || page === "boms" || page === "reset" || page === "bill-reading" || page === "migration" || page === "central" || page === "request-addition" || page === "countries" || page === "pin-codes" ? page : "home" };
}

/** While a screen's own file is on its way: the page's empty band, so nothing jumps. */
function Opening({ children }: { children: ReactNode }) {
  return <Suspense fallback={<section className="page" aria-busy="true" />}>{children}</Suspense>;
}

export function App() {
  // The supplier's page from a mailed order: no sign-in (SupplierReply.tsx).
  const reply = window.location.hash.match(/^#\/po-reply\/([\w-]+)/);
  if (reply)
    return (
      <Opening>
        <SupplierReplyPage token={reply[1]} />
      </Opening>
    );
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
  const canMigrate = Boolean(session.migration_tools) && session.permissions.includes("masters.edit") && session.permissions.includes("masters.import");
  const canSeeMasters = session.permissions.includes("masters.view");
  const canSeeShipments = session.permissions.some((p) => p === "sales.view" || p === "stock.view");
  const canSeePurchase = session.permissions.includes("purchase.view");
  const canSeeSales = session.permissions.includes("sales.view");
  const canSeeStock = session.permissions.includes("stock.view");
  const canSeeProduction = session.permissions.includes("production.view");
  const canSeeBooks = session.permissions.includes("accounts.view");
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
              active={page === "credit-terms" || page === "price-lists" || page === "terms" || page === "mail-templates" || page === "reminder-schedule" || page === "units" || page === "item-groups" || page === "brands" || page === "sales-people" || page === "batches" || page === "items" || page === "boms" || (page === "companies" && (sub === "ledgers" || sub === "groups" || sub === "couriers" || sub === "insurance" || sub === "warehouses"))}
              company={current.company}
              canSeeMasters={canSeeMasters}
            />
          )}
          {((canReceive && current.company?.modules.includes("purchase")) || (canSeeSales && current.company?.modules.includes("sales")) || (canSeeStock && current.company?.modules.includes("stock"))) && current.company && (
            <EntryMenu purchase={canReceive && current.company.modules.includes("purchase")} sales={canSeeSales && current.company.modules.includes("sales")} stock={canSeeStock && current.company.modules.includes("stock")} production={canSeeProduction && current.company.modules.includes("production")} active={page === "companies" && (sub === "manufacturing-orders" || sub === "stock-transfers" || sub === "stock-receipts" || sub === "stock-deliveries" || sub === "own-use" || sub === "sales-orders" || sub === "pick-lists" || sub === "scan-picking" || sub === "delivery-notes" || sub === "sales-invoices" || sub === "credit-notes" || sub === "purchase-orders" || sub === "goods-receipts" || sub === "purchase-invoices" || sub === "purchase-returns" || sub === "debit-notes" || sub === "tds-adjustments" || sub === "tds-check" || sub === "stock-check")} company={current.company} orders={canSeePurchase} tds={canSeeBooks || session.user.is_owner} />
          )}
          {canSeeShipments && current.company?.modules.includes("sales") && (
            <SalesMenu active={page === "companies" && sub === "shipments"} company={current.company} />
          )}
          {(canSeeStock || canSeeBooks || (canSeePurchase && current.company?.modules.includes("purchase"))) && current.company && (
            <ReportsMenu active={page === "companies" && REPORTS.includes(sub ?? "")} company={current.company} stock={canSeeStock} books={canSeeBooks} purchase={canSeePurchase && current.company.modules.includes("purchase")} />
          )}
          {(session.user.is_owner || canMigrate) && (
            <AdminMenu
              active={page === "users" || page === "roles" || page === "reset" || page === "bill-reading" || page === "migration" || (page === "companies" && !["ledgers", "groups", "couriers", "insurance", "warehouses", "shipments", "sales-orders", "pick-lists", "scan-picking", "delivery-notes", "sales-invoices", "credit-notes", "purchase-orders", "goods-receipts", "purchase-invoices", "purchase-returns", "debit-notes", "tds-adjustments", "tds-check", "stock-check", "stock-transfers", "stock-receipts", "stock-deliveries", "own-use", "manufacturing-orders", ...REPORTS].includes(sub ?? ""))}
              canSeeMasters={canSeeMasters}
              canManageUsers={canManageUsers}
              canMigrate={canMigrate}
              isOwner={session.user.is_owner}
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
        <Opening>
          {page === "help" ? (
            <HelpPage topic={topic} />
          ) : page === "batches" && sub === "trace" && id && canSeeStock ? (
            <BatchTracePage key={id} id={id} />
          ) : page === "bins" && id && canSeeMasters ? (
            <BinContentsPage key={id} id={id} />
          ) : page === "companies" && id && sub === "pending-purchase-orders" && canSeePurchase ? (
            <PendingPurchaseOrdersPage key={id} companyId={id} />
          ) : page === "companies" && id && sub === "procurement-tracker" && canSeePurchase ? (
            <ProcurementTrackerPage key={id} companyId={id} />
          ) : page === "companies" && id && sub === "stock-summary" && canSeeStock ? (
            <StockSummaryPage key={id} companyId={id} />
          ) : page === "companies" && id && sub === "stock-ledger" && canSeeStock ? (
            <StockLedgerPage key={id} companyId={id} />
          ) : page === "companies" && id && sub === "trial-balance" && canSeeBooks ? (
            <TrialBalancePage key={id} companyId={id} />
          ) : page === "companies" && id && sub === "ledger-statement" && canSeeBooks ? (
            <LedgerStatementPage key={id} companyId={id} />
          ) : page === "companies" && id && sub === "pick-lists" && (canSeeSales || session.permissions.includes("stock.view")) ? (
            <PickListsPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "scan-picking" && (canSeeSales || session.permissions.includes("stock.view")) ? (
            <ScanPickingPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "delivery-notes" && (canSeeSales || session.permissions.includes("stock.view")) ? (
            <DeliveryNotesPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "sales-invoices" && canSeeSales ? (
            <SalesInvoicesPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "credit-notes" && canSeeSales ? (
            <CreditNotesPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "sales-orders" && canSeeSales ? (
            <SalesOrdersPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "stock-transfers" && canSeeStock ? (
            <StockTransfersPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "stock-receipts" && canSeeStock ? (
            <CustomerStockPage key={`${id}-receipt`} companyId={id} session={session} kind="receipt" />
          ) : page === "companies" && id && sub === "stock-deliveries" && canSeeStock ? (
            <CustomerStockPage key={`${id}-delivery`} companyId={id} session={session} kind="delivery" />
          ) : page === "companies" && id && sub === "manufacturing-orders" && canSeeProduction ? (
            <ManufacturingOrdersPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "own-use" && canSeeStock ? (
            <OwnUsePage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "stock-check" && canSeePurchase ? (
            <StockCheckPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "purchase-orders" && canSeePurchase ? (
            <PurchaseOrdersPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "purchase-invoices" && canSeePurchase ? (
            <PurchaseInvoicesPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "tds-check" && (canSeeBooks || session.user.is_owner) ? (
            <TdsCheckPage key={id} companyId={id} session={session} />
          ) : page === "companies" && id && sub === "tds-adjustments" && (canSeeBooks || session.user.is_owner) ? (
            <TdsAdjustmentsPage key={id} companyId={id} session={session} />
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
            ) : id && sub === "insurance" ? (
              <InsurancePage key={id} companyId={id} session={session} companyName={current.companies.find((c) => c.id === id)?.name ?? ""} />
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
            <ItemsPage session={session} company={current.company} />
          ) : page === "boms" && canSeeMasters ? (
            <BomsPage session={session} />
          ) : page === "reset" && session.user.is_owner ? (
            <DataResetPage session={session} />
          ) : page === "bill-reading" && session.user.is_owner ? (
            <BillReadingPage />
          ) : page === "migration" && canMigrate ? (
            <MigrationToolsPage session={session} />
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
          ) : page === "reminder-schedule" && canSeeMasters ? (
            <ReminderSchedulePage session={session} />
          ) : page === "mail-templates" && canSeeMasters ? (
            <MailTemplatesPage session={session} />
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
        </Opening>
      </main>
    </>
  );
}
