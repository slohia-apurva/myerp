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
      <select value={props.company.id} onChange={(e) => props.onChoose(Number(e.target.value))}>
        {props.companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}

/** "Masters" in the top menu: a dropdown of the master lists. Company-wise
 * masters open for the company picked at the top right. */
export function MastersMenu(props: { active: boolean; company?: Company; canSeeMasters: boolean; canManageUsers: boolean }) {
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

  const company = props.company;
  const items: [string, string, boolean][] = [
    ["Company", "#/companies", props.canSeeMasters],
    ["Ledger groups", company ? `#/companies/${company.id}/groups` : "", props.canSeeMasters && !!company],
    ["Ledgers", company ? `#/companies/${company.id}/ledgers` : "", props.canSeeMasters && !!company],
    ["Credit terms", "#/credit-terms", props.canSeeMasters],
    ["Items", "#/items", props.canSeeMasters],
    ["Units", "#/units", props.canSeeMasters],
    ["Users", "#/users", props.canManageUsers],
    ["User roles", "#/roles", props.canManageUsers],
  ];

  return (
    <div className={`menu${props.active ? " active" : ""}`} ref={box}>
      <button type="button" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(!open)}>
        Masters <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="menu-panel" role="menu">
          {items
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
