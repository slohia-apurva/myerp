import { Combobox } from "./Combobox";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { Cells, useColumns, type Column } from "./Columns";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { ActionCells, ActionHeads } from "./RowActions";
import { ColumnSearch } from "./ColumnSearch";
import { useOnReturn } from "./Refresh";
import { useKept } from "./Keep";

/** Units of measure: one list for every company in the group. */
export type Unit = {
  id: number;
  name: string;
  short_name: string;
  gst_code: string;
  whole_numbers: boolean;
  is_active: boolean;
  lock?: LockInfo;
};

/** How a unit reads in the masters: "Kilogram (Kg)". Entry screens and reports use
 * the short name alone (Sidharth, 2026-11-13). */
export const unitLabel = (u: { name: string; short_name: string }) => `${u.name} (${u.short_name})`;

/** The master label of unit `id`, or `fallback` (its plain name) while the list loads. */
export const labelFor = (units: Unit[], id: number | string | null, fallback: string | null = "") => {
  const u = id === null ? undefined : units.find((x) => String(x.id) === String(id));
  return u ? unitLabel(u) : (fallback ?? "");
};

export function useUnits(full = false) {
  const [units, setUnits] = useState<Unit[]>([]);
  // refresh returns the request, so "Create …" can wait for the new record. Only the Units
  // screen asks for `full` (each unit's "in use" check); pickers skip it, so screens open fast.
  const refresh = useCallback(() => api<Unit[]>(`v1/units/${full ? "?full=1" : ""}`).then(setUnits), [full]);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { units, reload, refresh };
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

/** `?form=new`, `?form=<id>` or `?form=copy-<id>`: this tab was opened to add, change,
 * view or duplicate one unit (Sidharth, 2026-11-13). */
const formParam = () => hashParam("form");

// The list's columns; "Choose Columns…" in Actions ▾ picks and orders them for each person.
const UNIT_COLUMNS: Column<Unit>[] = [
  {
    key: "name",
    label: "Unit",
    fixed: true,
    cell: (u) => (
      <>
        {u.name}
        {!u.is_active && <span className="pill">Disabled</span>}
      </>
    ),
  },
  { key: "short", label: "Short name", standard: true, cell: (u) => u.short_name },
  { key: "gst", label: "GST unit code", standard: true, cell: (u) => u.gst_code },
  { key: "whole", label: "Whole numbers only", standard: true, cell: (u) => (u.whole_numbers ? "Yes" : "No") },
];

/** Masters > Units. The details of the clicked row are on the right; Add, Edit and
 * Duplicate open in a new tab. */
export function UnitsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { units, reload } = useUnits(true);
  const form = formParam();
  if (form) return <UnitFormTab form={form} canEdit={canEdit} />;
  return <UnitList session={session} canEdit={canEdit} units={units} reload={reload} />;
}

function UnitList(props: { session: SignedIn; canEdit: boolean; units: Unit[]; reload: () => void }) {
  const { units, canEdit, reload } = props;
  const [selectedId, setSelected] = useKept<number | null>("Units.selectedId", null);
  useCreated("unit_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    // Opened by "Create …" in a dropdown: go straight to the Add page.
    if (startName && canEdit) window.location.hash = `#/units?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const columns = useColumns("units", UNIT_COLUMNS, { sort: false });
  const io = useExchange({ master: "units", noun: "units", session: props.session, onImported: reload, extra: [columns.item] });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    // Opened from a link (for example a duplicate-name refusal): select that row.
    if (openId && units.some((u) => u.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, units, opened]);
  const codes = useGstCodes();
  const selected = units.find((u) => u.id === selectedId) ?? null;
  const edit = (what: number | string) => openTab(`#/units?form=${what}`);
  return (
    <section className="page">
      <PageHeader
        title="Units"
        sub="Units of measure such as Packet, Carton and Kilogram. One list for every company in the group."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>Add unit</button>}
          </>
        }
      />
      {io.panel}
      {columns.panel}
      <div className="side-layout">
        <div className="side-main">
          <table className="pick">
            <thead>
              <tr>
                {columns.shown.map((c) => (
                  <th key={c.key} className={c.num ? "num" : undefined}>
                    {c.label}
                  </th>
                ))}
                <ActionHeads />
              </tr>
              <ColumnSearch key={columns.shown.map((c) => c.key).join(",")} />
            </thead>
            <tbody>
              {units.map((u) => (
                <tr
                  key={u.id}
                  className={`${u.is_active ? "" : "off"}${selectedId === u.id ? " selected" : ""}`}
                  onClick={() => setSelected(u.id)}
                  onDoubleClick={() => edit(u.id)}
                >
                  <Cells shown={columns.shown} row={u} />
                  <ActionCells canEdit={canEdit} onOpen={() => edit(u.id)} onDuplicate={() => edit(`copy-${u.id}`)} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="side-col">
          <SidePanel title="Unit Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Unit", unitLabel(selected)],
                  [
                    "GST Unit Code",
                    selected.gst_code
                      ? `${selected.gst_code}${codes.find((c) => c.code === selected.gst_code) ? ` - ${codes.find((c) => c.code === selected.gst_code)!.name}` : ""}`
                      : "",
                  ],
                  ["Whole Numbers Only", selected.whole_numbers ? "Yes" : "No"],
                  ["In Use", selected.lock?.in_use.join(", ") ?? ""],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="unit" id={selected?.id} stamp={JSON.stringify(selected ?? units.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one unit, alone in its own tab: Save and Cancel close the tab. */
function UnitFormTab(props: { form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const [loaded, setLoaded] = useState(props.form === "new");
  const [units, setUnits] = useState<Unit[]>([]);
  useEffect(() => {
    if (props.form === "new") return;
    api<Unit[]>("v1/units/?full=1").then((rows) => {
      setUnits(rows);
      setLoaded(true);
    });
  }, [props.form]);
  const startName = useNewName();
  const target = props.form === "new" ? null : (units.find((u) => u.id === key) ?? null);
  const toList = () => {
    window.location.hash = "#/units";
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("unit_saved", saved);
    closeThisTab(toList);
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "Add unit" : copy ? "Duplicate unit" : readOnly ? "View unit" : "Edit unit";
  if (!loaded)
    return (
      <section className="page">
        <PageHeader title={title} />
      </section>
    );
  if (props.form !== "new" && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That unit was not found.</p>
      </section>
    );
  if (readOnly && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view units.</p>
      </section>
    );
  return (
    <UnitForm
      title={title}
      unit={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function UnitForm(props: {
  title: string;
  unit: Unit | null;
  copyOf?: Unit | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const u = props.unit;
  const from = u ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const [name, setName] = useState(props.startName ?? (props.copyOf ? `${props.copyOf.name} (copy)` : (u?.name ?? "")));
  const [shortName, setShortName] = useState(props.copyOf ? "" : (u?.short_name ?? ""));
  const codes = useGstCodes();
  const [gstCode, setGstCode] = useState(props.copyOf ? props.copyOf.gst_code : (u?.gst_code ?? ""));
  const [whole, setWhole] = useState(from?.whole_numbers ?? false);
  const [disabled, setDisabled] = useState(u ? !u.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const locked = (field: string) => isLocked(u?.lock, field);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = { name, short_name: shortName, gst_code: gstCode, whole_numbers: whole };
    try {
      if (u) {
        await api(`v1/units/${u.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: u.id, name });
      } else {
        const made = await api<{ id: number; name: string }>("v1/units/", body);
        announceCreated("unit", made);
        props.onDone(made);
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <FormPage
      title={props.title}
      sub={u ? unitLabel(u) : undefined}
      formId="unit-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={u ? { value: disabled, set: setDisabled } : undefined}
      activity={u ? <ChangeLog type="unit" id={u.id} stamp={JSON.stringify(u)} /> : undefined}
    >
      <InUseNote lock={u?.lock} />
      <Section title="General">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Name</span>
            <input required autoFocus value={name} placeholder="e.g. Carton" onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            <span className="req">Short Name</span>
            <input required value={shortName} maxLength={10} placeholder="e.g. ctn" onChange={(e) => setShortName(e.target.value)} />
          </label>
          <label>
            <span className="req">GST Unit Code</span>
            <Locked on={locked("gst_code")}>
              <Combobox
                required
                value={gstCode}
                onChange={setGstCode}
                empty="Pick a code"
                options={codes.map((c) => ({ value: c.code, label: `${c.code} - ${c.name}` }))}
              />
            </Locked>
          </label>
        </div>
        <Locked on={locked("whole_numbers")}>
          <label className="check">
            <input type="checkbox" checked={whole} onChange={(e) => setWhole(e.target.checked)} />
            Whole numbers only (2.5 cartons is not allowed)
          </label>
        </Locked>
      </Section>
    </FormPage>
  );
}
