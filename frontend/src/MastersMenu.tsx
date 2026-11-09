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

/** "Masters" in the top menu: a dropdown of the master lists. Company-wise
 * masters open for the company on screen, else the last one used. */
export function MastersMenu(props: { active: boolean; routeCompany?: number; canSeeMasters: boolean; canManageUsers: boolean }) {
  const [open, setOpen] = useState(false);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [chosen, setChosen] = useState<number | null>(remembered);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (props.canSeeMasters) api<Company[]>("v1/companies/").then(setCompanies);
  }, [props.canSeeMasters]);
  useEffect(() => {
    if (props.routeCompany) {
      setChosen(props.routeCompany);
      remember(props.routeCompany);
    }
  }, [props.routeCompany]);
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

  const company = companies.find((c) => c.id === chosen) ?? companies[0];
  const items: [string, string, boolean][] = [
    ["Company", "#/companies", props.canSeeMasters],
    ["Ledger groups", company ? `#/companies/${company.id}/groups` : "", props.canSeeMasters && !!company],
    ["Ledgers", company ? `#/companies/${company.id}/ledgers` : "", props.canSeeMasters && !!company],
    ["Credit terms", company ? `#/companies/${company.id}/credit-terms` : "", props.canSeeMasters && !!company],
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
          {companies.length > 1 && (
            <label className="menu-company">
              Company
              <select
                value={company?.id}
                onChange={(e) => {
                  setChosen(Number(e.target.value));
                  remember(Number(e.target.value));
                }}
              >
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
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
