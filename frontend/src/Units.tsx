import { Combobox } from "./Combobox";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { Activity, WithActivity } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { ActionCells, ActionHeads, ActiveButton, FormBody } from "./RowActions";

/** Units of measure: one list for every company in the group. */
export type Unit = {
  id: number;
  name: string;
  short_name: string;
  gst_code: string;
  whole_numbers: boolean;
  is_active: boolean;
};

export function useUnits() {
  const [units, setUnits] = useState<Unit[]>([]);
  const reload = useCallback(() => {
    api<Unit[]>("v1/units/").then(setUnits);
  }, []);
  useEffect(reload, [reload]);
  return { units, reload };
}

export type GstCode = { code: string; name: string };

/** The official GST unit quantity codes. */
export function useGstCodes() {
  const [codes, setCodes] = useState<GstCode[]>([]);
  useEffect(() => {
    api<GstCode[]>("v1/units/gst-codes/").then(setCodes);
  }, []);
  return codes;
}

/** Masters > Units. */
export function UnitsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { units, reload } = useUnits();
  const [editing, setEditing] = useState<Unit | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<Unit | null>(null);
  const done = () => {
    setEditing(null);
    setCopyOf(null);
    reload();
  };
  const io = useExchange({ master: "units", noun: "units", session, onImported: reload });
  return (
    <section className="page">
      <PageHeader
        title="Units"
        sub="Units of measure such as Packet, Carton and Kilogram. One list for every company in the group."
        actions={
          <>
            {io.buttons}
            {canEdit && (
              <button
                onClick={() => {
                  setCopyOf(null);
                  setEditing("new");
                }}
              >
                Add unit
              </button>
            )}
          </>
        }
      />
      <WithActivity activity={<Activity type="unit" stamp={JSON.stringify(units)} />}>
        {io.panel}
        {editing && (
          <UnitForm
            key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
            unit={editing === "new" ? null : editing}
            copyOf={copyOf}
            readOnly={!canEdit}
            onDone={done}
            onCancel={() => {
              setEditing(null);
              setCopyOf(null);
            }}
          />
        )}
        <table>
          <thead>
            <tr>
              <th>Unit</th>
              <th>Short name</th>
              <th>GST unit code</th>
              <th>Whole numbers only</th>
              <ActionHeads />
            </tr>
          </thead>
          <tbody>
            {units.map((u) => (
              <tr key={u.id} className={u.is_active ? "" : "off"}>
                <td>
                  {u.name}
                  {!u.is_active && <span className="pill">Inactive</span>}
                </td>
                <td>{u.short_name}</td>
                <td>{u.gst_code}</td>
                <td>{u.whole_numbers ? "Yes" : "No"}</td>
                <ActionCells
                  canEdit={canEdit}
                  onOpen={() => {
                    setCopyOf(null);
                    setEditing(u);
                  }}
                  onDuplicate={() => {
                    setCopyOf(u);
                    setEditing("new");
                  }}
                />
              </tr>
            ))}
          </tbody>
        </table>
      </WithActivity>
    </section>
  );
}

function UnitForm(props: {
  unit: Unit | null;
  copyOf?: Unit | null;
  readOnly?: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const u = props.unit;
  const from = u ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const [name, setName] = useState(props.copyOf ? `${props.copyOf.name} (copy)` : (u?.name ?? ""));
  const [shortName, setShortName] = useState(props.copyOf ? "" : (u?.short_name ?? ""));
  const codes = useGstCodes();
  const [gstCode, setGstCode] = useState(props.copyOf ? props.copyOf.gst_code : (u?.gst_code ?? ""));
  const [whole, setWhole] = useState(from?.whole_numbers ?? false);
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const body = { name, short_name: shortName, gst_code: gstCode, whole_numbers: whole };
    try {
      if (u) await api(`v1/units/${u.id}/`, body, "PATCH");
      else await api("v1/units/", body);
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h4>{u ? `${props.readOnly ? "View" : "Edit"} ${u.name}` : props.copyOf ? `Duplicate ${props.copyOf.name}` : "Add unit"}</h4>
      <FormBody readOnly={props.readOnly}>
        <Section title="Unit">
          <div className="row">
            <label>
              Name
              <input required autoFocus value={name} placeholder="e.g. Carton" onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
              Short name
              <input required value={shortName} maxLength={10} placeholder="e.g. ctn" onChange={(e) => setShortName(e.target.value)} />
            </label>
            <label>
              GST unit code
              <Combobox
                required
                value={gstCode}
                onChange={setGstCode}
                empty="Pick a code"
                options={codes.map((c) => ({ value: c.code, label: `${c.code} - ${c.name}` }))}
              />
            </label>
          </div>
          <label className="check">
            <input type="checkbox" checked={whole} onChange={(e) => setWhole(e.target.checked)} />
            Whole numbers only (2.5 cartons is not allowed)
          </label>
        </Section>
      </FormBody>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {!props.readOnly && <button>Save</button>}
        <button type="button" className="link" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
        {u && !props.readOnly && (
          <ActiveButton
            url={`v1/units/${u.id}/`}
            active={u.is_active}
            what={`the unit ${u.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}
