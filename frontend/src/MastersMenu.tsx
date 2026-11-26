import { Combobox } from "./Combobox";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Company } from "./Companies";

const KEY = "myerp.masters.company";

function remembered(): number | null {
  try {
    return Number(localStorage.getItem(KEY)) || null;
  } catch {
    return null;
  }
}

function remember(id: number) {
  try {
    localStorage.setItem(KEY, String(id));
  } catch {
    // Private window or blocked storage: the menu just uses the first company.
  }
}

/** The company being worked in: the one on screen, else the last one
 * picked, else the first. Shown at the top right of every screen. */
export function useCurrentCompany(routeCompany: number | undefined, canSeeMasters: boolean) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [chosen, setChosen] = useState<number | null>(remembered);
  useEffect(() => {
    if (canSeeMasters) api<Company[]>("v1/companies/").then(setCompanies);
  }, [canSeeMasters]);
  useEffect(() => {
    if (routeCompany) {
      setChosen(routeCompany);
      remember(routeCompany);
    }
  }, [routeCompany]);
  const company = companies.find((c) => c.id === chosen) ?? companies[0];
  const choose = (id: number) => {
    setChosen(id);
    remember(id);
    // On a company's screen, open the same screen for the company picked.
    const parts = window.location.hash.replace(/^#\/?/, "").split("/");
    if (parts[0] === "companies" && parts[1]) {
      const sub = parts[2] ?? ""; // a ledger group filter belongs to the old company, so drop it
      window.location.hash = `#/companies/${id}${sub ? `/${sub}` : ""}`;
    }
  };
  return { companies, company, choose };
}

/** The company picker at the top right. */
export function CompanyPicker(props: { companies: Company[]; company?: Company; onChoose: (id: number) => void }) {
  if (!props.company) return null;
  if (props.companies.length < 2)
    return (
      <span className="company-pick" title="Company">
        {props.company.name}
      </span>
    );
  return (
    <label className="company-pick" title="Company you are working in">
      <span className="sr-only">Company</span>
      <Combobox
        value={String(props.company.id)}
        onChange={(v) => props.onChoose(Number(v))}
        options={props.companies.map((c) => ({ value: String(c.id), label: c.name }))}
      />
    </label>
  );
}

type MenuItem = [label: string, href: string, show: boolean];

/** A dropdown in the top menu: a label and a list of links. */
function DropMenu(props: { label: string; active: boolean; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    const shut = () => setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    window.addEventListener("hashchange", shut);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
      window.removeEventListener("hashchange", shut);
    };
  }, [open]);

  return (
    <div className={`menu${props.active ? " active" : ""}`} ref={box}>
      <button type="button" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(!open)}>
        {props.label} <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="menu-panel" role="menu">
          {props.items
            .filter(([, , show]) => show)
            .map(([label, href]) => (
              <a key={label} role="menuitem" href={href} onClick={() => setOpen(false)}>
                {label}
              </a>
            ))}
        </div>
      )}
    </div>
  );
}

/** "Masters" in the top menu: the master lists. Company-wise masters open for
 * the company picked at the top right. */
export function MastersMenu(props: { active: boolean; company?: Company; canSeeMasters: boolean }) {
  const company = props.company;
  return (
    <DropMenu
      label="Masters"
      active={props.active}
      items={[
        ["Ledger groups", company ? `#/companies/${company.id}/groups` : "", props.canSeeMasters && !!company],
        ["Ledgers", company ? `#/companies/${company.id}/ledgers` : "", props.canSeeMasters && !!company],
        ["Credit terms", "#/credit-terms", props.canSeeMasters],
        ["People", "#/sales-people", props.canSeeMasters],
        [
          "Transporters",
          company ? `#/companies/${company.id}/couriers` : "",
          props.canSeeMasters && !!company?.modules.includes("sales"),
        ],
        ["Insurance policies", company ? `#/companies/${company.id}/insurance` : "", props.canSeeMasters && !!company],
        ["Warehouses", company ? `#/companies/${company.id}/warehouses` : "", props.canSeeMasters && !!company],
        ["Item groups", "#/item-groups", props.canSeeMasters],
        ["Items", "#/items", props.canSeeMasters],
        ["BOMs", "#/boms", props.canSeeMasters && !!company?.modules.includes("production")],
        ["Batches", "#/batches", props.canSeeMasters],
        ["Brands", "#/brands", props.canSeeMasters],
        ["Price lists", "#/price-lists", props.canSeeMasters],
        ["Terms and conditions", "#/terms", props.canSeeMasters],
        ["Units", "#/units", props.canSeeMasters],
        ["HSN codes", "#/hsn", props.canSeeMasters],
        ["Countries", "#/countries", props.canSeeMasters],
        ["PIN codes", "#/pin-codes", props.canSeeMasters],
      ]}
    />
  );
}

/** "Sales" in the top menu: for now the shipments sent by courier (spec 06).
 * Quotations, orders and invoices join it with Phase 4. */
export function SalesMenu(props: { active: boolean; company: Company }) {
  return (
    <DropMenu
      label="Sales"
      active={props.active}
      items={[["Shipments", `#/companies/${props.company.id}/shipments`, true]]}
    />
  );
}

/** "Reports" in the top menu (Sidharth, 2026-11-18): reports read straight from the
 * stock ledger and the books, for the company picked at the top right. */
export function ReportsMenu(props: { active: boolean; company: Company; stock: boolean; books: boolean }) {
  const id = props.company.id;
  return (
    <DropMenu
      label="Reports"
      active={props.active}
      items={[
        ["Stock Summary", `#/companies/${id}/stock-summary`, props.stock],
        ["Stock Ledger", `#/companies/${id}/stock-ledger`, props.stock],
        // Opens Batches, where "Trace" on a batch opens its Batch Trace (Sidharth, 2026-11-26).
        ["Batch Traceability", "#/batches", props.stock],
        ["Trial Balance", `#/companies/${id}/trial-balance`, props.books],
        ["Ledger Statement", `#/companies/${id}/ledger-statement`, props.books],
      ]}
    />
  );
}

/** "Admin" in the top menu, for Owners only: companies, users and roles. */
export function AdminMenu(props: { active: boolean; canSeeMasters: boolean; canManageUsers: boolean; canMigrate: boolean; isOwner: boolean }) {
  return (
    <DropMenu
      label="Admin"
      active={props.active}
      items={[
        ["Company", "#/companies", props.canSeeMasters],
        ["Users", "#/users", props.canManageUsers],
        ["User roles", "#/roles", props.canManageUsers],
        ["Bill Reading", "#/bill-reading", props.isOwner],
        ["Migration Tools", "#/migration", props.canMigrate],
        ["Reset data", "#/reset", props.isOwner],
      ]}
    />
  );
}

/** "Entry" in the top menu: the entry screens, grouped. "Purchase ▸" opens its own list
 * to the right on hover (or on a click, for touch screens). Purchase
 * Invoice and Purchase Return are shown as coming next until they are built. */
export function EntryMenu(props: { active: boolean; company: Company; orders: boolean; tds?: boolean; purchase?: boolean; sales?: boolean; stock?: boolean; production?: boolean }) {
  const [open, setOpen] = useState(false);
  const [sub, setSub] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    const shut = () => setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    window.addEventListener("hashchange", shut);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
      window.removeEventListener("hashchange", shut);
    };
  }, [open]);
  const id = props.company.id;
  return (
    <div className={`menu${props.active ? " active" : ""}`} ref={box}>
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          setSub("");
        }}
      >
        Entry <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="menu-panel" role="menu">
          {props.sales && (
            <div className={`menu-sub${sub === "sales" ? " open" : ""}`}>
              <button type="button" aria-haspopup="true" aria-expanded={sub === "sales"} onClick={() => setSub(sub === "sales" ? "" : "sales")}>
                Sales <span aria-hidden="true">▸</span>
              </button>
              <div className="menu-flyout" role="menu" aria-label="Sales">
                <a role="menuitem" href={`#/companies/${id}/sales-orders`} onClick={() => setOpen(false)}>
                  Sales Order
                </a>
                <a role="menuitem" href={`#/companies/${id}/pick-lists`} onClick={() => setOpen(false)}>
                  Pick List
                </a>
                <a role="menuitem" href={`#/companies/${id}/scan-picking`} onClick={() => setOpen(false)}>
                  Scan Picking
                </a>
                <a role="menuitem" href={`#/companies/${id}/delivery-notes`} onClick={() => setOpen(false)}>
                  Delivery Note
                </a>
                <a role="menuitem" href={`#/companies/${id}/sales-invoices`} onClick={() => setOpen(false)}>
                  Sales Invoice
                </a>
                <a role="menuitem" href={`#/companies/${id}/credit-notes`} onClick={() => setOpen(false)}>
                  Credit Note
                </a>
              </div>
            </div>
          )}
          {props.stock && (
            <div className={`menu-sub${sub === "stock" ? " open" : ""}`}>
              <button type="button" aria-haspopup="true" aria-expanded={sub === "stock"} onClick={() => setSub(sub === "stock" ? "" : "stock")}>
                Stock <span aria-hidden="true">▸</span>
              </button>
              <div className="menu-flyout" role="menu" aria-label="Stock">
                <a role="menuitem" href={`#/companies/${id}/stock-transfers`} onClick={() => setOpen(false)}>
                  Stock Transfer
                </a>
                <a role="menuitem" href={`#/companies/${id}/stock-receipts`} onClick={() => setOpen(false)}>
                  Stock Receipt
                </a>
                <a role="menuitem" href={`#/companies/${id}/stock-deliveries`} onClick={() => setOpen(false)}>
                  Stock Delivery
                </a>
                <a role="menuitem" href={`#/companies/${id}/own-use`} onClick={() => setOpen(false)}>
                  Own Use
                </a>
              </div>
            </div>
          )}
          {props.production && (
            <div className={`menu-sub${sub === "production" ? " open" : ""}`}>
              <button type="button" aria-haspopup="true" aria-expanded={sub === "production"} onClick={() => setSub(sub === "production" ? "" : "production")}>
                Production <span aria-hidden="true">▸</span>
              </button>
              <div className="menu-flyout" role="menu" aria-label="Production">
                <a role="menuitem" href={`#/companies/${id}/manufacturing-orders`} onClick={() => setOpen(false)}>
                  Manufacturing Order
                </a>
              </div>
            </div>
          )}
          {props.purchase !== false && props.orders && (
            <div className={`menu-sub${sub === "planning" ? " open" : ""}`}>
              <button type="button" aria-haspopup="true" aria-expanded={sub === "planning"} onClick={() => setSub(sub === "planning" ? "" : "planning")}>
                Planning <span aria-hidden="true">▸</span>
              </button>
              <div className="menu-flyout" role="menu" aria-label="Planning">
                <a role="menuitem" href={`#/companies/${id}/stock-check`} onClick={() => setOpen(false)}>
                  Stock Check
                </a>
              </div>
            </div>
          )}
          {props.purchase !== false && (
          <div className={`menu-sub${sub === "purchase" ? " open" : ""}`}>
            <button type="button" aria-haspopup="true" aria-expanded={sub === "purchase"} onClick={() => setSub(sub === "purchase" ? "" : "purchase")}>
              Purchase <span aria-hidden="true">▸</span>
            </button>
            <div className="menu-flyout" role="menu" aria-label="Purchase">
              {props.orders && (
                <a role="menuitem" href={`#/companies/${id}/purchase-orders`} onClick={() => setOpen(false)}>
                  Purchase Order
                </a>
              )}
              <a role="menuitem" href={`#/companies/${id}/goods-receipts`} onClick={() => setOpen(false)}>
                Goods Receipt
              </a>
              {props.orders && (
                <a role="menuitem" href={`#/companies/${id}/purchase-invoices`} onClick={() => setOpen(false)}>
                  Purchase Invoice
                </a>
              )}
              <a role="menuitem" href={`#/companies/${id}/purchase-returns`} onClick={() => setOpen(false)}>
                Purchase Return
              </a>
              {props.orders && (
                <a role="menuitem" href={`#/companies/${id}/debit-notes`} onClick={() => setOpen(false)}>
                  Debit Note
                </a>
              )}
            </div>
          </div>
          )}
          {props.tds && (
            <div className={`menu-sub${sub === "accounts" ? " open" : ""}`}>
              <button type="button" aria-haspopup="true" aria-expanded={sub === "accounts"} onClick={() => setSub(sub === "accounts" ? "" : "accounts")}>
                Accounts <span aria-hidden="true">▸</span>
              </button>
              <div className="menu-flyout" role="menu" aria-label="Accounts">
                <a role="menuitem" href={`#/companies/${id}/tds-check`} onClick={() => setOpen(false)}>
                  TDS Check
                </a>
                <a role="menuitem" href={`#/companies/${id}/tds-adjustments`} onClick={() => setOpen(false)}>
                  TDS Adjustment
                </a>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
