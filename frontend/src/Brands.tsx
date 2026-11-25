import { FormEvent, useCallback, useEffect, useState } from "react";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { ActionCells, ActionHeads } from "./RowActions";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { ColumnSearch } from "./ColumnSearch";
import { useOnReturn } from "./Refresh";
import { useKept } from "./Keep";

/** Brands: one list for every company in the group; an item picks its brand on the General section. */
export type Brand = { id: number; name: string; notes: string; is_active: boolean; item_count: number };

export function useBrands() {
  const [brands, setBrands] = useState<Brand[]>([]);
  // refresh returns the request, so "Create …" can wait for the new record.
  const refresh = useCallback(() => api<Brand[]>("v1/brands/").then(setBrands), []);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { brands, reload, refresh };
}

/** `?form=new`, `?form=<id>` or `?form=copy-<id>`: this tab was opened to add, change,
 * view or duplicate one brand (Sidharth, 2026-11-13). */
const formParam = () => hashParam("form");

/** Masters > Brands. The details of the clicked row are on the right; Add, Edit and
 * Duplicate open in a new tab. */
export function BrandsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { brands, reload } = useBrands();
  const form = formParam();
  if (form) return <BrandFormTab form={form} canEdit={canEdit} />;
  return <BrandList session={session} canEdit={canEdit} brands={brands} reload={reload} />;
}

function BrandList(props: { session: SignedIn; canEdit: boolean; brands: Brand[]; reload: () => void }) {
  const { brands, canEdit, reload } = props;
  const [selectedId, setSelected] = useKept<number | null>("Brands.selectedId", null);
  useCreated("brand_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    // Opened by "Create …" in a dropdown: go straight to the Add page.
    if (startName && canEdit) window.location.hash = `#/brands?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const io = useExchange({ master: "brands", noun: "brands", session: props.session, onImported: reload });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    // Opened from a link (for example a duplicate-name refusal): select that row.
    if (openId && brands.some((b) => b.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, brands, opened]);
  const selected = brands.find((b) => b.id === selectedId) ?? null;
  const edit = (what: number | string) => openTab(`#/brands?form=${what}`);
  return (
    <section className="page">
      <PageHeader
        title="Brands"
        sub="The brand names items are sold under. One list for every company in the group."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>Add brand</button>}
          </>
        }
      />
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          <table className="pick">
            <thead>
              <tr>
                <th>Brand</th>
                <th>Notes</th>
                <th className="num">Items</th>
                <ActionHeads />
              </tr>
              <ColumnSearch />
            </thead>
            <tbody>
              {brands.map((b) => (
                <tr
                  key={b.id}
                  className={`${b.is_active ? "" : "off"}${selectedId === b.id ? " selected" : ""}`}
                  onClick={() => setSelected(b.id)}
                  onDoubleClick={() => edit(b.id)}
                >
                  <td>
                    {b.name}
                    {!b.is_active && <span className="pill">Disabled</span>}
                  </td>
                  <td className="small">{b.notes}</td>
                  <td className="num">{b.item_count > 0 ? b.item_count : <span className="small">—</span>}</td>
                  <ActionCells canEdit={canEdit} onOpen={() => edit(b.id)} onDuplicate={() => edit(`copy-${b.id}`)} />
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
        </div>
        <div className="side-col">
          <SidePanel title="Brand Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.name],
                  ["Items", String(selected.item_count)],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                  ["Notes", selected.notes],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="brand" id={selected?.id} stamp={JSON.stringify(selected ?? brands.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one brand, alone in its own tab: Save and Cancel close the tab. */
function BrandFormTab(props: { form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const [loaded, setLoaded] = useState(props.form === "new");
  const [brands, setBrands] = useState<Brand[]>([]);
  useEffect(() => {
    if (props.form === "new") return;
    api<Brand[]>("v1/brands/").then((rows) => {
      setBrands(rows);
      setLoaded(true);
    });
  }, [props.form]);
  const startName = useNewName();
  const target = props.form === "new" ? null : (brands.find((b) => b.id === key) ?? null);
  const toList = () => {
    window.location.hash = "#/brands";
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("brand_saved", saved);
    closeThisTab(toList);
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "Add brand" : copy ? "Duplicate brand" : readOnly ? "View brand" : "Edit brand";
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
        <p className="error">That brand was not found.</p>
      </section>
    );
  if (readOnly && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view brands.</p>
      </section>
    );
  return (
    <BrandForm
      title={title}
      brand={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function BrandForm(props: {
  title: string;
  brand: Brand | null;
  copyOf?: Brand | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const b = props.brand;
  const [name, setName] = useState(props.startName ?? (props.copyOf ? `${props.copyOf.name} (copy)` : (b?.name ?? "")));
  const [notes, setNotes] = useState(props.copyOf?.notes ?? b?.notes ?? "");
  const [disabled, setDisabled] = useState(b ? !b.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (b) {
        await api(`v1/brands/${b.id}/`, { name, notes, is_active: !disabled }, "PATCH");
        props.onDone({ id: b.id, name });
      } else {
        const made = await api<{ id: number; name: string }>("v1/brands/", { name, notes });
        announceCreated("brand", made);
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
      sub={b ? b.name : undefined}
      formId="brand-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={b ? { value: disabled, set: setDisabled } : undefined}
      activity={b ? <ChangeLog type="brand" id={b.id} stamp={JSON.stringify(b)} /> : undefined}
    >
      <Section title="General">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Name</span>
            <input required autoFocus value={name} placeholder="e.g. Apurvam" onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      </Section>
    </FormPage>
  );
}
