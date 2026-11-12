import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import { Chevron, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { ErrorNote, useOpenParam } from "./ErrorNote";
import { ActiveButton } from "./RowActions";

/** A company's warehouses (branches ticked "Warehouse") with their racks, bins and areas,
 * on the company's "Warehouses" tab. */
export type Location = {
  id: number;
  branch: number;
  kind: "rack" | "bin" | "area";
  parent: number | null;
  name: string;
  purpose: string;
  purpose_label: string;
  notes: string;
  is_active: boolean;
  bin_count: number;
};
export type Rack = Location & { bins: Location[] };
export type Warehouse = {
  id: number;
  name: string;
  city: string;
  is_active: boolean;
  racks: Rack[];
  areas: Location[];
};

const PURPOSES: [string, string][] = [
  ["receiving", "Receiving"],
  ["storage", "Storage"],
  ["production", "Production"],
  ["quality", "Quality check"],
  ["quarantine", "Quarantine"],
  ["packing", "Packing"],
  ["despatch", "Despatch"],
  ["other", "Other"],
];

const WHAT = { rack: "rack", bin: "bin", area: "area" };

/** What the form is adding or changing. */
type Editing = { warehouse: Warehouse; kind: Location["kind"]; rack?: Rack; location?: Location };

export function Warehouses(props: { warehouses: Warehouse[]; companyId: number; canEdit: boolean; reload: () => void }) {
  const [editing, setEditing] = useState<Editing | null>(null);
  const [shut, setShut] = useState<Set<number>>(new Set()); // racks folded closed
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (!openId) return;
    for (const w of props.warehouses) {
      for (const r of w.racks) {
        if (r.id === openId) setEditing({ warehouse: w, kind: "rack", location: r });
        for (const b of r.bins) if (b.id === openId) setEditing({ warehouse: w, kind: "bin", rack: r, location: b });
      }
      for (const a of w.areas) if (a.id === openId) setEditing({ warehouse: w, kind: "area", location: a });
    }
    opened();
  }, [openId, props.warehouses, opened]);
  const done = () => {
    setEditing(null);
    props.reload();
  };
  const fold = (id: number) => {
    const next = new Set(shut);
    if (!next.delete(id)) next.add(id);
    setShut(next);
  };
  return (
    <>
      <p className="small">
        A warehouse is a branch ticked "Warehouse" on the "Branches" tab. Racks stand in the warehouse and hold bins, and
        a bin is a physical storage location. Areas are the named zones of the warehouse, such as receiving, production
        and despatch.
      </p>
      {editing && (
        <LocationForm
          key={`${editing.kind}-${editing.location?.id ?? "new"}-${editing.rack?.id ?? ""}-${editing.warehouse.id}`}
          editing={editing}
          companyId={props.companyId}
          onDone={done}
          onCancel={() => setEditing(null)}
        />
      )}
      {props.warehouses.length === 0 && (
        <p className="small">
          No warehouse yet. Open the "Branches" tab, edit or add a branch, and tick "This branch is a warehouse".
        </p>
      )}
      {props.warehouses.map((w) => (
        <Section key={w.id} title={`${w.name}${w.city ? `, ${w.city}` : ""}${w.is_active ? "" : " (closed)"}`}>
          <div className="page-head">
            <strong>Racks and bins</strong>
            {props.canEdit && w.is_active && (
              <button type="button" className="secondary" onClick={() => setEditing({ warehouse: w, kind: "rack" })}>
                Add rack
              </button>
            )}
          </div>
          <table>
            <thead>
              <tr>
                <th>Rack or bin</th>
                <th className="num">Bins</th>
                <th>Notes</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {w.racks.flatMap((r) => [
                <tr key={`r${r.id}`} className={r.is_active ? "" : "off"}>
                  <td>
                    <button
                      type="button"
                      className="fold"
                      aria-expanded={!shut.has(r.id)}
                      aria-label={shut.has(r.id) ? `Show bins of ${r.name}` : `Hide bins of ${r.name}`}
                      onClick={() => fold(r.id)}
                    >
                      <Chevron open={!shut.has(r.id)} />
                    </button>{" "}
                    <strong>{r.name}</strong>
                    {!r.is_active && <span className="pill">Disabled</span>}
                  </td>
                  <td className="num">{r.bin_count}</td>
                  <td>{r.notes}</td>
                  <td className="row-actions">
                    {props.canEdit && r.is_active && (
                      <button type="button" className="link" onClick={() => setEditing({ warehouse: w, kind: "bin", rack: r })}>
                        Add bin
                      </button>
                    )}
                    {props.canEdit && (
                      <button type="button" className="link" onClick={() => setEditing({ warehouse: w, kind: "rack", location: r })}>
                        Edit
                      </button>
                    )}
                  </td>
                </tr>,
                ...(shut.has(r.id)
                  ? []
                  : r.bins.map((b) => (
                      <tr key={`b${b.id}`} className={b.is_active ? "" : "off"}>
                        <td style={{ paddingLeft: 36 }}>
                          {b.name}
                          {!b.is_active && <span className="pill">Disabled</span>}
                        </td>
                        <td />
                        <td>{b.notes}</td>
                        <td className="row-actions">
                          {props.canEdit && (
                            <button
                              type="button"
                              className="link"
                              onClick={() => setEditing({ warehouse: w, kind: "bin", rack: r, location: b })}
                            >
                              Edit
                            </button>
                          )}
                        </td>
                      </tr>
                    ))),
              ])}
              {w.racks.length === 0 && (
                <tr>
                  <td colSpan={4} className="small">
                    No racks yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="page-head">
            <strong>Areas</strong>
            {props.canEdit && w.is_active && (
              <button type="button" className="secondary" onClick={() => setEditing({ warehouse: w, kind: "area" })}>
                Add area
              </button>
            )}
          </div>
          <table>
            <thead>
              <tr>
                <th>Area</th>
                <th>Used for</th>
                <th>Notes</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {w.areas.map((a) => (
                <tr key={a.id} className={a.is_active ? "" : "off"}>
                  <td>
                    {a.name}
                    {!a.is_active && <span className="pill">Disabled</span>}
                  </td>
                  <td>{a.purpose_label}</td>
                  <td>{a.notes}</td>
                  <td className="row-actions">
                    {props.canEdit && (
                      <button type="button" className="link" onClick={() => setEditing({ warehouse: w, kind: "area", location: a })}>
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {w.areas.length === 0 && (
                <tr>
                  <td colSpan={4} className="small">
                    No areas yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Section>
      ))}
    </>
  );
}

function LocationForm(props: { editing: Editing; companyId: number; onDone: () => void; onCancel: () => void }) {
  const { warehouse, kind, rack, location } = props.editing;
  const [name, setName] = useState(location?.name ?? "");
  const [purpose, setPurpose] = useState(location?.purpose ?? "");
  const [notes, setNotes] = useState(location?.notes ?? "");
  const [error, setError] = useState<unknown>("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body: Record<string, unknown> = { name, notes };
    if (kind === "area") body.purpose = purpose;
    try {
      if (location) await api(`v1/warehouse-locations/${location.id}/`, body, "PATCH");
      else {
        await api(`v1/companies/${props.companyId}/warehouse-locations/`, {
          ...body,
          branch: warehouse.id,
          kind,
          parent: rack?.id ?? null,
        });
      }
      props.onDone();
    } catch (err) {
      setError(err);
    }
  };
  const title = `${location ? "Edit" : "Add"} ${WHAT[kind]}`;
  return (
    <form className="card" onSubmit={save}>
      <h4>
        {title} · {warehouse.name}
        {rack ? ` · rack ${rack.name}` : ""}
      </h4>
      <Section title={kind === "area" ? "Area" : kind === "rack" ? "Rack" : "Bin"}>
        <div className="row">
          <label>
            Name
            <input
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={kind === "area" ? "e.g. Despatch bay" : kind === "rack" ? "e.g. R1" : "e.g. A1"}
            />
          </label>
          {kind === "area" && (
            <label>
              Used for
              <Combobox
                required
                value={purpose}
                onChange={setPurpose}
                empty="Pick what it is for"
                options={PURPOSES.map(([value, label]) => ({ value, label }))}
              />
            </label>
          )}
        </div>
        <label>
          Notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
      </Section>
      <ErrorNote error={error} />
      <div className="buttons">
        <button>Save</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
        {location && (
          <ActiveButton
            url={`v1/warehouse-locations/${location.id}/`}
            active={location.is_active}
            what={`the ${WHAT[kind]} ${location.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}
