import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import type { Item } from "./Items";
import { ActionCells, ActionHeads } from "./RowActions";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { ColumnSearch } from "./ColumnSearch";
import { useOnReturn, useReturns } from "./Refresh";
import { useItemSearch } from "./ItemSearch";

/** Batches (lots) of batch-tracked items. A batch number is unique within its
 * item only: two items may both have batch 1234 (Sidharth, 2026-11-15). */
export type Batch = {
  id: number;
  item: number;
  item_name: string;
  item_number: string;
  number: string;
  supplier_batch_no: string;
  mfg_date: string | null;
  expiry_date: string | null;
  status: string;
  status_label: string;
  notes: string;
  is_active: boolean;
};

export const BATCH_STATUSES = [
  { value: "quarantine", label: "Quarantine" },
  { value: "released", label: "Released" },
  { value: "rejected", label: "Rejected" },
];

export const showDate = (iso: string | null) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "";

export function useBatches() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const refresh = useCallback(() => api<Batch[]>("v1/batches/").then(setBatches), []);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { batches, reload, refresh };
}

/** The items that keep batches, for the item picker. */
function useBatchItems(chosen: number | string | null) {
  // Asked from the server as the person types, never the whole catalogue
  // (12,457 items on staging): ItemSearch.ts, as on the entry screens.
  const visits = useReturns(); // lists load again on coming back to this tab (Refresh.ts)
  return useItemSearch<Item>("v1/items/?batch_tracked=1", [chosen], visits);
}

const formParam = () => hashParam("form");

/** Masters > Batches. The details of the clicked row are on the right; Add, Edit and
 * Duplicate open in a new tab. */
export function BatchesPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { batches, reload } = useBatches();
  const form = formParam();
  if (form) return <BatchFormTab form={form} canEdit={canEdit} />;
  return <BatchList session={session} canEdit={canEdit} batches={batches} reload={reload} />;
}

function BatchList(props: { session: SignedIn; canEdit: boolean; batches: Batch[]; reload: () => void }) {
  const { batches, canEdit, reload } = props;
  const [selectedId, setSelected] = useState<number | null>(null);
  const [itemFilter, setItemFilter] = useState("");
  useCreated("batch_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    if (startName && canEdit) window.location.hash = `#/batches?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const io = useExchange({ master: "batches", noun: "batches", session: props.session, onImported: reload });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && batches.some((b) => b.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, batches, opened]);
  const itemOptions = useMemo(() => {
    const seen = new Map<number, string>();
    batches.forEach((b) => seen.set(b.item, `${b.item_number} ${b.item_name}`));
    return [...seen].map(([id, name]) => ({ value: String(id), label: name }));
  }, [batches]);
  const shown = itemFilter ? batches.filter((b) => String(b.item) === itemFilter) : batches;
  const selected = batches.find((b) => b.id === selectedId) ?? null;
  const edit = (what: number | string) => openTab(`#/batches?form=${what}`);
  return (
    <section className="page">
      <PageHeader
        title="Batches"
        sub="The batches (lots) of batch-tracked items, with their dates and quality status. A batch number is unique within its item."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>Add batch</button>}
          </>
        }
      />
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          <div className="filter-row" style={{ maxWidth: 360, marginBottom: 8 }}>
            <Combobox options={itemOptions} value={itemFilter} onChange={setItemFilter} empty="All items" ariaLabel="Item" />
          </div>
          <table className="pick">
            <thead>
              <tr>
                <th>Batch No</th>
                <th>Item No</th>
                <th>Item</th>
                <th>Mfg Date</th>
                <th>Expiry</th>
                <th>Status</th>
                <ActionHeads />
              </tr>
              <ColumnSearch />
            </thead>
            <tbody>
              {shown.map((b) => (
                <tr
                  key={b.id}
                  className={`${b.is_active ? "" : "off"}${selectedId === b.id ? " selected" : ""}`}
                  onClick={() => setSelected(b.id)}
                  onDoubleClick={() => edit(b.id)}
                >
                  <td>
                    {b.number}
                    {!b.is_active && <span className="pill">Disabled</span>}
                  </td>
                  <td>{b.item_number}</td>
                  <td>{b.item_name}</td>
                  <td>{showDate(b.mfg_date)}</td>
                  <td>{showDate(b.expiry_date)}</td>
                  <td>{b.status_label}</td>
                  <ActionCells canEdit={canEdit} onOpen={() => edit(b.id)} onDuplicate={() => edit(`copy-${b.id}`)} />
                </tr>
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={8} className="small">
                    No batches yet. Click "Add batch", or receive goods of a batch-tracked item.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="side-col">
          <SidePanel title="Batch Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Batch No", selected.number],
                  ["Item No", selected.item_number],
                  ["Item", selected.item_name],
                  ["Supplier's Batch No", selected.supplier_batch_no],
                  ["Mfg Date", showDate(selected.mfg_date)],
                  ["Expiry", showDate(selected.expiry_date)],
                  ["Status", selected.status_label],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                  ["Notes", selected.notes],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="batch" id={selected?.id} stamp={JSON.stringify(selected ?? batches.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

function BatchFormTab(props: { form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const [loaded, setLoaded] = useState(props.form === "new");
  const [batches, setBatches] = useState<Batch[]>([]);
  useEffect(() => {
    if (props.form === "new") return;
    api<Batch[]>("v1/batches/").then((rows) => {
      setBatches(rows);
      setLoaded(true);
    });
  }, [props.form]);
  const startName = useNewName();
  const target = props.form === "new" ? null : (batches.find((b) => b.id === key) ?? null);
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("batch_saved", saved);
    closeThisTab(() => {
      window.location.hash = "#/batches";
    });
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "Add batch" : copy ? "Duplicate batch" : readOnly ? "View batch" : "Edit batch";
  const shell = (note?: string) => (
    <section className="page">
      <PageHeader title={title} />
      {note && <p className="error">{note}</p>}
    </section>
  );
  if (!loaded) return shell();
  if (props.form !== "new" && target === null) return shell("That batch was not found.");
  if (readOnly && !editing) return shell("You may only view batches.");
  return (
    <BatchForm
      title={title}
      batch={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function bestBefore(item: Item | undefined) {
  if (!item?.best_before_value) return "";
  return `${item.best_before_value} ${item.best_before_unit === "months" ? "months" : "days"}`;
}

function BatchForm(props: {
  title: string;
  batch: Batch | null;
  copyOf?: Batch | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const b = props.batch;
  const from = b ?? props.copyOf ?? null;
  const [item, setItem] = useState(from ? String(from.item) : "");
  const { items, onType } = useBatchItems(item);
  const [number, setNumber] = useState(props.startName ?? b?.number ?? "");
  const [supplierNo, setSupplierNo] = useState(b?.supplier_batch_no ?? "");
  const [mfg, setMfg] = useState(b?.mfg_date ?? "");
  const [expiry, setExpiry] = useState(b?.expiry_date ?? "");
  const [status, setStatus] = useState(from?.status ?? "released");
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [disabled, setDisabled] = useState(b ? !b.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const picked = items.find((i) => String(i.id) === item);
  const period = bestBefore(picked);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = {
      item: item ? Number(item) : null,
      number,
      supplier_batch_no: supplierNo,
      mfg_date: mfg || null,
      expiry_date: expiry || null,
      status,
      notes,
    };
    try {
      if (b) {
        const saved = await api<Batch>(`v1/batches/${b.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: saved.id, name: saved.number });
      } else {
        const made = await api<Batch>("v1/batches/", body);
        announceCreated("batch", { id: made.id, name: made.number });
        props.onDone({ id: made.id, name: made.number });
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <FormPage
      title={props.title}
      sub={b ? `${b.number} · ${b.item_number} ${b.item_name}` : undefined}
      formId="batch-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={b ? { value: disabled, set: setDisabled } : undefined}
      activity={b ? <ChangeLog type="batch" id={b.id} stamp={JSON.stringify(b)} /> : undefined}
    >
      <Section title="General">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Item</span>
            <Combobox
              options={items.map((i) => ({ value: String(i.id), label: `${i.item_number} ${i.name}` }))}
              value={item}
              onChange={setItem}
              onType={onType}
              required
              placeholder="Only items that track batches"
              ariaLabel="Item"
            />
          </label>
          <label>
            <span className="req">Batch No</span>
            <input required autoFocus value={number} placeholder="e.g. 26K09D" onChange={(e) => setNumber(e.target.value)} />
          </label>
          <label>
            Supplier's Batch No
            <input value={supplierNo} onChange={(e) => setSupplierNo(e.target.value)} />
          </label>
          <label>
            Status
            <Combobox options={BATCH_STATUSES} value={status} onChange={setStatus} ariaLabel="Status" />
          </label>
          <label>
            Mfg Date
            <input type="date" value={mfg} onChange={(e) => setMfg(e.target.value)} />
          </label>
          <label>
            Expiry
            <input type="date" value={expiry} min={mfg || undefined} onChange={(e) => setExpiry(e.target.value)} />
            {!expiry && period && <span className="small">Left blank, it is the mfg date plus {period}.</span>}
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
