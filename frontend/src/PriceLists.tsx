import { Combobox } from "./Combobox";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { Cells, useColumns, type Column } from "./Columns";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { ActionCells, ActionHeads } from "./RowActions";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { PriceTable, priceBody, rowFromServer, type PriceRow } from "./PriceLines";
import { ColumnSearch } from "./ColumnSearch";
import { useOnReturn } from "./Refresh";
import { useKept } from "./Keep";

/** Price lists: named sets of rates for selling or buying, each rate from a date and a quantity. */
export type PriceList = {
  id: number;
  name: string;
  kind: string;
  kind_label: string;
  currency: string | null;
  is_active: boolean;
  notes: string;
  lines: (PriceRow & { id: number })[];
  price_count: number;
  party_count: number;
  lock?: LockInfo;
};

export const KINDS: [string, string][] = [
  ["selling", "Selling"],
  ["buying", "Buying"],
];

type Currency = { code: string; name: string };
const currencyLabel = (code: string | null, all: Currency[]) => {
  const c = all.find((x) => x.code === (code || "INR"));
  return c ? `${c.name} (${c.code})` : "Rupee (INR)";
};

export function usePriceLists() {
  const [lists, setLists] = useState<PriceList[]>([]);
  // refresh returns the request, so "Create …" can wait for the new record.
  const refresh = useCallback(() => api<PriceList[]>("v1/price-lists/").then(setLists), []);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { lists, reload, refresh };
}

const formParam = () => hashParam("form");

/** Masters > Price lists: the details of the clicked row are on the right; Add, Edit and
 * Duplicate open in a new tab. */
export function PriceListsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { lists, reload } = usePriceLists();
  const form = formParam();
  if (form) return <ListFormTab form={form} canEdit={canEdit} />;
  return <ListPage session={session} canEdit={canEdit} lists={lists} reload={reload} />;
}

// The list's columns; "Choose Columns…" in Actions ▾ picks and orders them for each person.
function priceListColumns(currencies: Currency[]): Column<PriceList>[] {
  return [
    {
      key: "name",
      label: "Price List",
      fixed: true,
      cell: (l) => (
        <>
          {l.name}
          {!l.is_active && <span className="pill">Disabled</span>}
        </>
      ),
    },
    { key: "kind", label: "Type", standard: true, cell: (l) => l.kind_label },
    { key: "currency", label: "Currency", standard: true, cell: (l) => currencyLabel(l.currency, currencies) },
    { key: "prices", label: "Prices", standard: true, num: true, cell: (l) => l.price_count || "" },
    { key: "used", label: "Used By", standard: true, num: true, cell: (l) => l.party_count || "" },
    { key: "notes", label: "Notes", cell: (l) => <span className="small">{l.notes}</span> },
  ];
}

function ListPage(props: { session: SignedIn; canEdit: boolean; lists: PriceList[]; reload: () => void }) {
  const { lists, canEdit, reload } = props;
  const [selectedId, setSelected] = useKept<number | null>("PriceLists.selectedId", null);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  useEffect(() => {
    api<Currency[]>("v1/currencies/").then(setCurrencies, () => setCurrencies([]));
  }, []);
  useCreated("price_list_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    if (startName && canEdit) window.location.hash = `#/price-lists?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const columns = useColumns("price-lists", useMemo(() => priceListColumns(currencies), [currencies]), { sort: false });
  const io = useExchange({ master: "price-lists", noun: "price lists", session: props.session, onImported: reload, extra: [columns.item] });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && lists.some((l) => l.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, lists, opened]);
  const selected = lists.find((l) => l.id === selectedId) ?? null;
  return (
    <section className="page">
      <PageHeader
        title="Price lists"
        sub="Rates for selling and buying, with start dates and quantity slabs."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => openTab("#/price-lists?form=new")}>Add price list</button>}
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
              {lists.map((l) => (
                <tr
                  key={l.id}
                  className={`${l.is_active ? "" : "off"}${selectedId === l.id ? " selected" : ""}`}
                  onClick={() => setSelected(l.id)}
                  onDoubleClick={() => openTab(`#/price-lists?form=${l.id}`)}
                >
                  <Cells shown={columns.shown} row={l} />
                  <ActionCells
                    canEdit={canEdit}
                    onOpen={() => openTab(`#/price-lists?form=${l.id}`)}
                    onDuplicate={() => openTab(`#/price-lists?form=copy-${l.id}`)}
                  />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="side-col">
          <SidePanel title="Price List Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.name],
                  ["Type", selected.kind_label],
                  ["Currency", currencyLabel(selected.currency, currencies)],
                  ["Prices", String(selected.price_count)],
                  ["Used By", String(selected.party_count)],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                  ["Notes", selected.notes],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="price_list" id={selected?.id} stamp={JSON.stringify(selected ?? lists.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one price list, alone in its own tab: Save and Cancel close the tab. */
function ListFormTab(props: { form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const [loaded, setLoaded] = useState(props.form === "new");
  const [lists, setLists] = useState<PriceList[]>([]);
  useEffect(() => {
    if (props.form === "new") return;
    api<PriceList[]>("v1/price-lists/").then((l) => {
      setLists(l);
      setLoaded(true);
    });
  }, [props.form]);
  const startName = useNewName();
  const target = props.form === "new" ? null : (lists.find((l) => l.id === key) ?? null);
  const toList = () => {
    window.location.hash = "#/price-lists";
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("price_list_saved", saved);
    closeThisTab(toList);
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "Add price list" : copy ? "Duplicate price list" : readOnly ? "View price list" : "Edit price list";
  if (!loaded) return <section className="page"><PageHeader title={title} /></section>;
  if (props.form !== "new" && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That price list was not found.</p>
      </section>
    );
  if (!props.canEdit && !editing) return <section className="page"><PageHeader title={title} /><p className="error">You may only view price lists.</p></section>;
  return (
    <ListForm
      title={title}
      list={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function ListForm(props: {
  title: string;
  list: PriceList | null;
  copyOf?: PriceList | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const l = props.list;
  const from = l ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const [name, setName] = useState(props.startName ?? (props.copyOf ? `${props.copyOf.name} (copy)` : (l?.name ?? "")));
  const [kind, setKind] = useState(from?.kind ?? "selling");
  const [currency, setCurrency] = useState(from?.currency ?? "");
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [rows, setRows] = useState<PriceRow[]>(
    (from?.lines ?? []).map((r) => ({ ...rowFromServer(r), party: undefined })),
  );
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  useEffect(() => {
    api<Currency[]>("v1/currencies/").then(setCurrencies, () => setCurrencies([]));
  }, []);
  const [disabled, setDisabled] = useState(l ? !l.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const locked = (field: string) => isLocked(l?.lock, field);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = {
      name,
      kind,
      currency: currency && currency !== "INR" ? currency : null,
      notes,
      lines: priceBody(rows),
    };
    try {
      if (l) {
        await api(`v1/price-lists/${l.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: l.id, name });
      } else {
        const made = await api<{ id: number; name: string }>("v1/price-lists/", body);
        announceCreated("price_list", made);
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
      sub={l ? l.name : undefined}
      formId="price-list-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={l ? { value: disabled, set: setDisabled } : undefined}
      tips={
        <p className="small">
          Rates are before GST. A new rate is a new line with a later date: old lines stay as history. A customer's own
          Item Prices win over its price list.
        </p>
      }
      activity={l ? <ChangeLog type="price_list" id={l.id} stamp={JSON.stringify(l)} /> : undefined}
    >
      <InUseNote lock={l?.lock} />
      <Section title="General">
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
              placeholder="e.g. Retail 2026"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            <span className="req">Type</span>
            <Locked on={locked("kind")}>
              <Combobox value={kind} onChange={setKind} options={KINDS.map(([value, label]) => ({ value, label }))} />
            </Locked>
          </label>
          <label>
            Currency
            <Locked on={locked("currency")}>
              <Combobox
                value={currency}
                onChange={setCurrency}
                empty="Rupee (INR)"
                options={currencies
                  .filter((c) => c.code !== "INR")
                  .map((c) => ({ value: c.code, label: `${c.name} (${c.code})` }))}
              />
            </Locked>
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      </Section>
      <Section title="Prices">
        <PriceTable rows={rows} onChange={setRows} by="item" readOnly={props.readOnly} />
        <p className="small">
          Rates are before GST, as GST is added from the item's own rate on the bill date. The rate in force is the latest
          one that has started, for the biggest "From Qty" not above the quantity ordered. A rate is for the unit shown;
          there is no conversion between units.
        </p>
      </Section>
    </FormPage>
  );
}
