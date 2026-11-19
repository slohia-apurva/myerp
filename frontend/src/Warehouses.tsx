import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { Chevron, PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { announceSaved, closeThisTab, useCreated } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { InUseNote, type LockInfo } from "./Lock";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { useOnReturn } from "./Refresh";

/** Masters > Warehouses: a company's warehouses (branches ticked "Warehouse") with their
 * racks, bins and areas. The details of the clicked row are on the right; Add and Edit open
 * in a new tab (Sidharth, 2026-11-13). */
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
  is_default: boolean;
  lock?: LockInfo;
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

/** `?form=new-rack-<warehouse id>`, `new-area-<warehouse id>`, `new-bin-<rack id>` or
 * `<id>` (change or view): this tab was opened to add or change one rack, bin or area. */
const formParam = () => hashParam("form");

const pageHash = (company: number, query = "") => `#/companies/${company}/warehouses${query}`;

function useWarehouses(companyId: number) {
  const [warehouses, setWarehouses] = useState<Warehouse[] | null>(null);
  const reload = useCallback(() => {
    api<Warehouse[]>(`v1/companies/${companyId}/warehouses/`).then(setWarehouses);
  }, [companyId]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { warehouses, reload };
}

export function WarehousesPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { warehouses, reload } = useWarehouses(companyId);
  const form = formParam();
  if (form) return <LocationFormTab companyId={companyId} form={form} canEdit={canEdit} warehouses={warehouses} />;
  return (
    <WarehouseList companyId={companyId} canEdit={canEdit} session={session} warehouses={warehouses ?? []} reload={reload} />
  );
}

function WarehouseList(props: {
  companyId: number;
  canEdit: boolean;
  session: SignedIn;
  warehouses: Warehouse[];
  reload: () => void;
}) {
  const { companyId, canEdit, warehouses, reload } = props;
  const [selectedId, setSelected] = useState<number | null>(null);
  const [shut, setShut] = useState<Set<number>>(new Set()); // racks folded closed
  useCreated("warehouse_location_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const io = useExchange({
    master: "warehouse-locations",
    noun: "racks, bins and areas",
    session: props.session,
    company: companyId,
    onImported: reload,
  });
  const all: { loc: Location; warehouse: Warehouse; rack?: Rack }[] = warehouses.flatMap((w) => [
    ...w.racks.flatMap((r) => [{ loc: r as Location, warehouse: w }, ...r.bins.map((b) => ({ loc: b, warehouse: w, rack: r }))]),
    ...w.areas.map((a) => ({ loc: a, warehouse: w })),
  ]);
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    // Opened from a link (for example a duplicate-name refusal): select that row.
    if (openId && all.some((x) => x.loc.id === openId)) {
      setSelected(openId);
      opened();
    }
  });
  const selected = all.find((x) => x.loc.id === selectedId) ?? null;
  const fold = (id: number) => {
    const next = new Set(shut);
    if (!next.delete(id)) next.add(id);
    setShut(next);
  };
  const add = (what: string) => openTab(pageHash(companyId, `?form=${what}`));
  /** A rack's row and, unless folded, its bins; `pad` indents racks standing in an area. */
  const rackRows = (r: Rack, pad: number) => [
    <tr
      key={`r${r.id}`}
      className={`${r.is_active ? "" : "off"}${selectedId === r.id ? " selected" : ""}`}
      onClick={() => setSelected(r.id)}
      onDoubleClick={() => add(String(r.id))}
    >
      <td style={{ paddingLeft: pad }}>
        <button
          type="button"
          className="fold"
          aria-expanded={!shut.has(r.id)}
          aria-label={shut.has(r.id) ? `Show bins of ${r.name}` : `Hide bins of ${r.name}`}
          onClick={(e) => {
            e.stopPropagation();
            fold(r.id);
          }}
        >
          <Chevron open={!shut.has(r.id)} />
        </button>{" "}
        <strong>{r.name}</strong>
        {!r.is_active && <span className="pill">Disabled</span>}
      </td>
      <td className="num">{r.bin_count}</td>
      <td>{r.notes}</td>
      <td className="row-actions">
        {canEdit && r.is_active && (
          <button
            type="button"
            className="link"
            onClick={(e) => {
              e.stopPropagation();
              add(`new-bin-${r.id}`);
            }}
          >
            Add bin
          </button>
        )}
        {canEdit && (
          <button
            type="button"
            className="link"
            onClick={(e) => {
              e.stopPropagation();
              add(String(r.id));
            }}
          >
            Edit
          </button>
        )}
      </td>
    </tr>,
    ...(shut.has(r.id)
      ? []
      : r.bins.map((b) => (
          <tr
            key={`b${b.id}`}
            className={`${b.is_active ? "" : "off"}${selectedId === b.id ? " selected" : ""}`}
            onClick={() => setSelected(b.id)}
            onDoubleClick={() => add(String(b.id))}
          >
            <td style={{ paddingLeft: pad + 36 }}>
              {b.name}
              {!b.is_active && <span className="pill">Disabled</span>}
            </td>
            <td />
            <td>{b.notes}</td>
            <td className="row-actions">
              {canEdit && (
                <button
                  type="button"
                  className="link"
                  onClick={(e) => {
                    e.stopPropagation();
                    add(String(b.id));
                  }}
                >
                  Edit
                </button>
              )}
            </td>
          </tr>
        ))),
  ];
  return (
    <section className="page">
      <PageHeader
        title="Warehouses"
        sub="Every branch not ticked No stock is a warehouse, with a default store. Areas are its named zones, such as finished goods, receiving and despatch; racks stand in an area (or straight in the warehouse) and hold bins."
        actions={io.buttons}
      />
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          {warehouses.length === 0 && (
            <p className="small">
              No warehouse yet. Under "Admin", "Company", "Branches", add or edit a branch and tick "This branch is a warehouse".
            </p>
          )}
          {warehouses.map((w) => (
            <Section key={w.id} title={`${w.name}${w.city ? `, ${w.city}` : ""}${w.is_active ? "" : " (closed)"}`}>
              <div className="page-head">
                <strong>Racks and bins</strong>
                {canEdit && w.is_active && (
                  <button type="button" className="secondary" onClick={() => add(`new-rack-${w.id}`)}>
                    Add rack
                  </button>
                )}
              </div>
              <table className="pick">
                <thead>
                  <tr>
                    <th>Rack or bin</th>
                    <th className="num">Bins</th>
                    <th>Notes</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {w.areas
                    .filter((a) => w.racks.some((r) => r.parent === a.id))
                    .flatMap((a) => [
                      <tr key={`a${a.id}`} className={selectedId === a.id ? "selected" : ""} onClick={() => setSelected(a.id)}>
                        <td>
                          <button
                            type="button"
                            className="fold"
                            aria-expanded={!shut.has(a.id)}
                            aria-label={shut.has(a.id) ? `Show racks in ${a.name}` : `Hide racks in ${a.name}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              fold(a.id);
                            }}
                          >
                            <Chevron open={!shut.has(a.id)} />
                          </button>{" "}
                          <strong>{a.name}</strong> <span className="small">area</span>
                        </td>
                        <td className="num">{w.racks.filter((r) => r.parent === a.id).length} racks</td>
                        <td>{a.notes}</td>
                        <td className="row-actions">
                          {canEdit && w.is_active && a.is_active && (
                            <button
                              type="button"
                              className="link"
                              onClick={(e) => {
                                e.stopPropagation();
                                add(`new-rack-${w.id}-${a.id}`);
                              }}
                            >
                              Add rack
                            </button>
                          )}
                        </td>
                      </tr>,
                      ...(shut.has(a.id) ? [] : w.racks.filter((r) => r.parent === a.id).flatMap((r) => rackRows(r, 28))),
                    ])}
                  {w.racks.some((r) => r.parent !== null) && w.racks.some((r) => r.parent === null) && (
                    <tr>
                      <td colSpan={4} className="small">
                        Not in an area
                      </td>
                    </tr>
                  )}
                  {w.racks.filter((r) => r.parent === null).flatMap((r) => rackRows(r, 0))}
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
                {canEdit && w.is_active && (
                  <button type="button" className="secondary" onClick={() => add(`new-area-${w.id}`)}>
                    Add area
                  </button>
                )}
              </div>
              <table className="pick">
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
                    <tr
                      key={a.id}
                      className={`${a.is_active ? "" : "off"}${selectedId === a.id ? " selected" : ""}`}
                      onClick={() => setSelected(a.id)}
                      onDoubleClick={() => add(String(a.id))}
                    >
                      <td>
                        {a.name}
                        {a.is_default && <span className="pill on">Default</span>}
                        {!a.is_active && <span className="pill">Disabled</span>}
                      </td>
                      <td>{a.purpose_label}</td>
                      <td>{a.notes}</td>
                      <td className="row-actions">
                        {canEdit && (
                          <button
                            type="button"
                            className="link"
                            onClick={(e) => {
                              e.stopPropagation();
                              add(String(a.id));
                            }}
                          >
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
        </div>
        <div className="side-col">
          <SidePanel title="Location Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.loc.name],
                  ["Kind", selected.loc.kind === "rack" ? "Rack" : selected.loc.kind === "bin" ? "Bin" : "Area"],
                  ["Warehouse", selected.warehouse.name],
                  ["Rack", selected.rack?.name ?? ""],
                  [
                    "In Area",
                    selected.loc.kind === "rack"
                      ? (selected.warehouse.areas.find((a) => a.id === selected.loc.parent)?.name ?? "Not in an area")
                      : "",
                  ],
                  ["Used For", selected.loc.purpose_label],
                  ["Bins", selected.loc.kind === "rack" ? String(selected.loc.bin_count) : ""],
                  ["In Use", selected.loc.lock?.in_use.join(", ") ?? ""],
                  ["Disabled", selected.loc.is_active ? "No" : "Yes"],
                  ["Notes", selected.loc.notes],
                ]}
              />
            ) : (
              <p className="small">Click a rack, bin or area to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog
              type="warehouse_location"
              id={selected?.loc.id}
              company={selected ? undefined : companyId}
              stamp={JSON.stringify(selected?.loc ?? warehouses.length)}
            />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one rack, bin or area, alone in its own tab: Save and Cancel close the tab. */
function LocationFormTab(props: { companyId: number; form: string; canEdit: boolean; warehouses: Warehouse[] | null }) {
  const startNew = props.form.startsWith("new-");
  const [, newKind, newOf, newArea] = startNew ? props.form.split("-") : [];
  const id = Number(props.form);
  const toList = () => {
    window.location.hash = pageHash(props.companyId);
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("warehouse_location_saved", saved);
    closeThisTab(toList);
  };
  const title = startNew ? `Add ${newKind}` : props.canEdit ? "Edit rack, bin or area" : "View rack, bin or area";
  const wait = (
    <section className="page">
      <PageHeader title={title} />
    </section>
  );
  if (props.warehouses === null) return wait;
  let warehouse: Warehouse | undefined;
  let rack: Rack | undefined;
  let location: Location | undefined;
  if (startNew) {
    if (newKind === "bin") {
      for (const w of props.warehouses) {
        const r = w.racks.find((x) => x.id === Number(newOf));
        if (r) [warehouse, rack] = [w, r];
      }
    } else warehouse = props.warehouses.find((w) => w.id === Number(newOf));
  } else {
    for (const w of props.warehouses) {
      for (const r of w.racks) {
        if (r.id === id) [warehouse, location] = [w, r];
        for (const b of r.bins) if (b.id === id) [warehouse, rack, location] = [w, r, b];
      }
      for (const a of w.areas) if (a.id === id) [warehouse, location] = [w, a];
    }
  }
  if (!warehouse || (!startNew && !location) || (startNew && !["rack", "bin", "area"].includes(newKind)))
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That rack, bin, area or warehouse was not found.</p>
      </section>
    );
  if (startNew && !props.canEdit)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view racks, bins and areas.</p>
      </section>
    );
  return (
    <LocationForm
      title={title}
      kind={location?.kind ?? (newKind as Location["kind"])}
      warehouse={warehouse}
      rack={rack}
      location={location}
      companyId={props.companyId}
      startArea={newArea ? Number(newArea) : null}
      readOnly={!props.canEdit}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function LocationForm(props: {
  title: string;
  kind: Location["kind"];
  warehouse: Warehouse;
  rack?: Rack;
  location?: Location;
  startArea?: number | null;
  companyId: number;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const { warehouse, kind, rack, location } = props;
  const [name, setName] = useState(location?.name ?? "");
  const [purpose, setPurpose] = useState(location?.purpose ?? "");
  const [notes, setNotes] = useState(location?.notes ?? "");
  // A rack stands in an area of the warehouse, or straight in it (Sidharth, 2026-11-19).
  const [area, setArea] = useState(String((kind === "rack" ? location?.parent : null) ?? props.startArea ?? ""));
  const [disabled, setDisabled] = useState(location ? !location.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body: Record<string, unknown> = { name, notes };
    if (kind === "area") body.purpose = purpose;
    if (kind === "rack") body.parent = area ? Number(area) : null;
    try {
      if (location) {
        await api(
          `v1/warehouse-locations/${location.id}/`,
          location.is_default ? body : { ...body, is_active: !disabled },
          "PATCH",
        );
        props.onDone({ id: location.id, name });
      } else {
        const made = await api<{ id: number; name: string }>(`v1/companies/${props.companyId}/warehouse-locations/`, {
          ...body,
          branch: warehouse.id,
          kind,
          parent: rack?.id ?? null,
          ...body,
        });
        props.onDone(made);
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };
  const heading = kind === "area" ? "Area" : kind === "rack" ? "Rack" : "Bin";
  return (
    <FormPage
      title={props.title}
      sub={`${warehouse.name}${rack ? ` · rack ${rack.name}` : ""}${location ? ` · ${location.name}` : ""}`}
      formId="location-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={location && !location.is_default ? { value: disabled, set: setDisabled } : undefined}
      tips={
        kind === "rack" ? <p className="small">A rack with open bins cannot be disabled; disable its bins first.</p> : undefined
      }
      activity={location ? <ChangeLog type="warehouse_location" id={location.id} stamp={JSON.stringify(location)} /> : undefined}
    >
      <InUseNote lock={location?.lock} />
      <Section title={heading}>
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Name</span>
            <input
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={kind === "area" ? "e.g. Despatch bay" : kind === "rack" ? "e.g. R1" : "e.g. A1"}
            />
          </label>
          {kind === "rack" && (
            <label>
              In Area
              <Combobox
                value={area}
                onChange={setArea}
                empty="Not in an area"
                options={warehouse.areas
                  .filter((a) => a.is_active || a.id === location?.parent)
                  .map((a) => ({ value: String(a.id), label: a.name }))}
              />
              <span className="small">
                Leave empty for a rack straight in the warehouse. You can give it an area at any time; its bins and their stock go
                with it.
              </span>
            </label>
          )}
          {kind === "area" && (
            <label>
              <span className="req">Used For</span>
              <Combobox
                required
                value={purpose}
                onChange={setPurpose}
                empty="Pick what it is for"
                options={PURPOSES.map(([value, label]) => ({ value, label }))}
              />
            </label>
          )}
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      </Section>
    </FormPage>
  );
}
