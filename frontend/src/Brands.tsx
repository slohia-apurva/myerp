import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { Activity, WithActivity } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { ActionCells, ActionHeads, ActiveButton, FormBody } from "./RowActions";

/** Brands: one list for every company in the group; an item picks its brand on the General tab. */
export type Brand = { id: number; name: string; notes: string; is_active: boolean; item_count: number };

export function useBrands() {
  const [brands, setBrands] = useState<Brand[]>([]);
  const reload = useCallback(() => {
    api<Brand[]>("v1/brands/").then(setBrands);
  }, []);
  useEffect(reload, [reload]);
  return { brands, reload };
}

/** Masters > Brands. */
export function BrandsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { brands, reload } = useBrands();
  const [editing, setEditing] = useState<Brand | "new" | null>(null);
  const [copyOf, setCopyOf] = useState<Brand | null>(null);
  const done = () => {
    setEditing(null);
    setCopyOf(null);
    reload();
  };
  const io = useExchange({ master: "brands", noun: "brands", session, onImported: reload });
  return (
    <section className="page">
      <PageHeader
        title="Brands"
        sub="The brand names items are sold under. One list for every company in the group."
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
                Add brand
              </button>
            )}
          </>
        }
      />
      <WithActivity activity={<Activity type="brand" stamp={JSON.stringify(brands)} />}>
        {io.panel}
        {editing && (
          <BrandForm
            key={editing === "new" ? `new-${copyOf?.id ?? ""}` : editing.id}
            brand={editing === "new" ? null : editing}
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
              <th>Brand</th>
              <th>Notes</th>
              <th className="num">Items</th>
              <ActionHeads />
            </tr>
          </thead>
          <tbody>
            {brands.map((b) => (
              <tr key={b.id} className={b.is_active ? "" : "off"}>
                <td>
                  {b.name}
                  {!b.is_active && <span className="pill">Inactive</span>}
                </td>
                <td className="small">{b.notes}</td>
                <td className="num">{b.item_count > 0 ? b.item_count : <span className="small">—</span>}</td>
                <ActionCells
                  canEdit={canEdit}
                  onOpen={() => {
                    setCopyOf(null);
                    setEditing(b);
                  }}
                  onDuplicate={() => {
                    setCopyOf(b);
                    setEditing("new");
                  }}
                />
              </tr>
            ))}
            {brands.length === 0 && (
              <tr>
                <td colSpan={5} className="small">
                  No brands yet. Click "Add brand".
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </WithActivity>
    </section>
  );
}

function BrandForm(props: {
  brand: Brand | null;
  copyOf?: Brand | null;
  readOnly?: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const b = props.brand;
  const [name, setName] = useState(props.copyOf ? `${props.copyOf.name} (copy)` : (b?.name ?? ""));
  const [notes, setNotes] = useState(props.copyOf?.notes ?? b?.notes ?? "");
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (b) await api(`v1/brands/${b.id}/`, { name, notes }, "PATCH");
      else await api("v1/brands/", { name, notes });
      props.onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form className="card" onSubmit={save}>
      <h4>{b ? `${props.readOnly ? "View" : "Edit"} ${b.name}` : props.copyOf ? `Duplicate ${props.copyOf.name}` : "Add brand"}</h4>
      <FormBody readOnly={props.readOnly}>
        <Section title="Brand">
          <div className="row">
            <label>
              Name
              <input required autoFocus value={name} placeholder="e.g. Apurvam" onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
              Notes
              <input value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
          </div>
        </Section>
      </FormBody>
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {!props.readOnly && <button>Save</button>}
        <button type="button" className="link" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
        {b && !props.readOnly && (
          <ActiveButton
            url={`v1/brands/${b.id}/`}
            active={b.is_active}
            what={`the brand ${b.name}`}
            onDone={props.onDone}
            onError={setError}
          />
        )}
      </div>
    </form>
  );
}
