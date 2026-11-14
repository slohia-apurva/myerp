import { useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader } from "./Brand";
import { usePrintMenu } from "./Exchange";
import { SidePanel, SideRows } from "./Master";
import { openRequestAddition } from "./RequestAddition";

type Country = { code: string; name: string };

/** Masters > Countries: the central list a party's country is picked from. The details of
 * the clicked row are on the right. Nobody changes a country here: MyERP keeps the list. */
export function CountriesPage({ session }: { session: SignedIn }) {
  const [rows, setRows] = useState<Country[]>([]);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    api<Country[]>("v1/countries/").then(setRows, () => setRows([]));
  }, []);
  const printing = usePrintMenu({ title: "Countries", scope: q ? `Search: ${q}` : "" });
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = rows.filter((c) => words.every((w) => `${c.name} ${c.code}`.toLowerCase().includes(w)));
  const chosen = rows.find((c) => c.code === selected) ?? null;
  return (
    <section className="page">
      <PageHeader
        title="Countries"
        actions={
          <>
            {session.permissions.includes("masters.edit") && (
              <button type="button" onClick={() => openRequestAddition("country")}>
                Request Addition
              </button>
            )}
            {printing.buttons}
          </>
        }
        sub={`${rows.length} countr${rows.length === 1 ? "y" : "ies"} · kept centrally by MyERP, the same for every company. Picked on a customer's or supplier's address.`}
      />
      {printing.panel}
      <div className="side-layout">
        <div className="side-main">
          <input
            type="search"
            placeholder="Search by country name or code"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <table className="pick">
            <thead>
              <tr>
                <th>Country</th>
                <th>Code</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.code} className={selected === c.code ? "selected" : ""} onClick={() => setSelected(c.code)}>
                  <td>{c.name}</td>
                  <td>{c.code}</td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={2} className="small">
                    Nothing matches.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="side-col">
          <SidePanel title="Country Details">
            {chosen ? (
              <SideRows
                rows={[
                  ["Country", chosen.name],
                  ["Code", chosen.code],
                ]}
              />
            ) : (
              <p className="small">Click a country to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="About This List">
            <p className="small">
              MyERP keeps this list for every company, so countries cannot be added or changed here. If one is missing,
              click "Request Addition".
            </p>
          </SidePanel>
        </div>
      </div>
    </section>
  );
}
