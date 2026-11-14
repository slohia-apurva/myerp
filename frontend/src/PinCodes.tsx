import { useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader } from "./Brand";
import { usePrintMenu } from "./Exchange";
import { SidePanel, SideRows } from "./Master";
import { type PinInfo, type PinRow, searchPins } from "./Pin";
import { openRequestAddition } from "./RequestAddition";

/** Masters > PIN codes: the central list of PIN, city and state that an Indian address is
 * picked from. The details of the clicked row, with the couriers that deliver there, are on
 * the right. Nobody changes a PIN here: MyERP keeps the list. */
export function PinCodesPage({ session }: { session: SignedIn }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<{ total: number; results: PinRow[] }>({ total: 0, results: [] });
  const [selectedId, setSelected] = useState<number | null>(null);
  const [info, setInfo] = useState<PinInfo | null>(null);
  useEffect(() => {
    const t = setTimeout(() => searchPins(q, false).then(setFound), 200);
    return () => clearTimeout(t);
  }, [q]);
  const selected = found.results.find((r) => r.id === selectedId) ?? null;
  const pin = selected?.pin;
  useEffect(() => {
    setInfo(null);
    if (pin) api<PinInfo>(`v1/pin/${pin}/`).then(setInfo, () => setInfo(null));
  }, [pin]);
  const printing = usePrintMenu({ title: "PIN codes", scope: q ? `Search: ${q}` : "" });
  const couriers = info?.couriers.map((c) => `${c.courier}${c.oda ? " (out of delivery area)" : ""}`).join(", ");
  return (
    <section className="page">
      <PageHeader
        title="PIN codes"
        actions={
          <>
            {session.permissions.includes("masters.edit") && (
              <button type="button" onClick={() => openRequestAddition("pin", q.replace(/\D/g, ""))}>
                Request Addition
              </button>
            )}
            {printing.buttons}
          </>
        }
        sub={`${found.total} PIN code${found.total === 1 ? "" : "s"} · kept centrally by MyERP, the same for every company. Picked on an Indian address, which fills its city and state.`}
      />
      {printing.panel}
      <div className="side-layout">
        <div className="side-main">
          <input
            type="search"
            placeholder="Search by PIN, city or state"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <table className="pick">
            <thead>
              <tr>
                <th>PIN Code</th>
                <th>City</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {found.results.map((r) => (
                <tr
                  key={r.id}
                  className={`${r.is_active ? "" : "off"}${selectedId === r.id ? " selected" : ""}`}
                  onClick={() => setSelected(r.id)}
                >
                  <td>
                    {r.pin}
                    {!r.is_active && <span className="pill">Inactive</span>}
                  </td>
                  <td>{r.city}</td>
                  <td>{r.state_name}</td>
                </tr>
              ))}
              {found.results.length === 0 && (
                <tr>
                  <td colSpan={3} className="small">
                    {found.total === 0 && q === "" ? "The list has not been loaded yet." : "Nothing matches."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {found.total > found.results.length && q === "" && (
            <p className="small">Showing the first {found.results.length}. Type in the search box to find others.</p>
          )}
        </div>
        <div className="side-col">
          <SidePanel title="PIN Code Details">
            {selected ? (
              <SideRows
                rows={[
                  ["PIN Code", selected.pin],
                  ["City", selected.city],
                  ["State", selected.state_name],
                  ["Delivered By", info ? couriers || "No courier list covers this PIN" : ""],
                ]}
              />
            ) : (
              <p className="small">Click a PIN code to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="About This List">
            <p className="small">
              MyERP keeps this list for every company, so PIN codes cannot be added or changed here. The city is the
              main one for the PIN. If a PIN is missing, click "Request Addition".
            </p>
          </SidePanel>
        </div>
      </div>
    </section>
  );
}
