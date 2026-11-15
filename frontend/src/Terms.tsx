import { Combobox } from "./Combobox";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { ActionCells, ActionHeads } from "./RowActions";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";

/** Terms and conditions: named sets of the terms printed on orders, for purchase or sales. */
export type TermsSet = {
  id: number;
  name: string;
  kind: string;
  kind_label: string;
  text: string;
  is_active: boolean;
  notes: string;
  default_companies: { id: number; name: string }[];
  party_count: number;
  lock?: LockInfo;
};

export const TERMS_KINDS: [string, string][] = [
  ["purchase", "Purchase"],
  ["sales", "Sales"],
];

type CompanyRow = { id: number; name: string };

export function useTermsSets() {
  const [sets, setSets] = useState<TermsSet[]>([]);
  // refresh returns the request, so "Create …" can wait for the new record.
  const refresh = useCallback(() => api<TermsSet[]>("v1/terms/").then(setSets), []);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  return { sets, reload, refresh };
}

/** The text as printed: a line ending in ":" is a heading, the rest are terms. */
export function TermsText({ text }: { text: string }) {
  const lines = text.split("\n").filter((l) => l.trim());
  if (!lines.length) return <p className="small">No terms.</p>;
  return (
    <div className="terms-text">
      {lines.map((l, i) => (l.trim().endsWith(":") ? <b key={i}>{l.trim().slice(0, -1)}</b> : <div key={i}>{l}</div>))}
    </div>
  );
}

const formParam = () => hashParam("form");

/** Masters > Terms and conditions: the clicked set is shown on the right; Add, Edit and
 * Duplicate open in a new tab. */
export function TermsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { sets, reload } = useTermsSets();
  const form = formParam();
  if (form) return <TermsFormTab form={form} canEdit={canEdit} />;
  return <ListPage session={session} canEdit={canEdit} sets={sets} reload={reload} />;
}

function ListPage(props: { session: SignedIn; canEdit: boolean; sets: TermsSet[]; reload: () => void }) {
  const { sets, canEdit, reload } = props;
  const [selectedId, setSelected] = useState<number | null>(null);
  useCreated("terms_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    if (startName && canEdit) window.location.hash = `#/terms?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const io = useExchange({ master: "terms", noun: "terms and conditions", session: props.session, onImported: reload });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && sets.some((s) => s.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, sets, opened]);
  const selected = sets.find((s) => s.id === selectedId) ?? null;
  return (
    <section className="page">
      <PageHeader
        title="Terms and conditions"
        sub="Sets of terms printed on purchase orders (and, later, sales documents)."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => openTab("#/terms?form=new")}>Add terms</button>}
          </>
        }
      />
      {io.panel}
      <div className="side-layout">
        <div className="side-main">
          <table className="pick">
            <thead>
              <tr>
                <th>Terms</th>
                <th>Type</th>
                <th>Default For</th>
                <th className="num">Used By</th>
                <ActionHeads />
              </tr>
            </thead>
            <tbody>
              {sets.map((s) => (
                <tr
                  key={s.id}
                  className={`${s.is_active ? "" : "off"}${selectedId === s.id ? " selected" : ""}`}
                  onClick={() => setSelected(s.id)}
                  onDoubleClick={() => openTab(`#/terms?form=${s.id}`)}
                >
                  <td>
                    {s.name}
                    {!s.is_active && <span className="pill">Disabled</span>}
                  </td>
                  <td>{s.kind_label}</td>
                  <td>{s.default_companies.map((c) => c.name).join(", ")}</td>
                  <td className="num">{s.party_count || ""}</td>
                  <ActionCells
                    canEdit={canEdit}
                    onOpen={() => openTab(`#/terms?form=${s.id}`)}
                    onDuplicate={() => openTab(`#/terms?form=copy-${s.id}`)}
                  />
                </tr>
              ))}
            </tbody>
          </table>
          {sets.length === 0 && <p className="small">No terms yet. Click "Add terms" to write the first set.</p>}
        </div>
        <div className="side-col">
          <SidePanel title="Terms Details">
            {selected ? (
              <>
                <SideRows
                  rows={[
                    ["Name", selected.name],
                    ["Type", selected.kind_label],
                    ["Default For", selected.default_companies.map((c) => c.name).join(", ") || "None"],
                    ["Used By", String(selected.party_count)],
                    ["Disabled", selected.is_active ? "No" : "Yes"],
                    ["Notes", selected.notes],
                  ]}
                />
                <TermsText text={selected.text} />
              </>
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="terms" id={selected?.id} stamp={JSON.stringify(selected ?? sets.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one set, alone in its own tab: Save and Cancel close the tab. */
function TermsFormTab(props: { form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const [loaded, setLoaded] = useState(props.form === "new");
  const [sets, setSets] = useState<TermsSet[]>([]);
  useEffect(() => {
    if (props.form === "new") return;
    api<TermsSet[]>("v1/terms/").then((s) => {
      setSets(s);
      setLoaded(true);
    });
  }, [props.form]);
  const startName = useNewName();
  const target = props.form === "new" ? null : (sets.find((s) => s.id === key) ?? null);
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("terms_saved", saved);
    closeThisTab(() => {
      window.location.hash = "#/terms";
    });
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "Add terms" : copy ? "Duplicate terms" : readOnly ? "View terms" : "Edit terms";
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
        <p className="error">Those terms were not found.</p>
      </section>
    );
  if (!props.canEdit && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view terms and conditions.</p>
      </section>
    );
  return (
    <TermsForm
      title={title}
      terms={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function TermsForm(props: {
  title: string;
  terms: TermsSet | null;
  copyOf?: TermsSet | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const t = props.terms;
  const from = t ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const [name, setName] = useState(props.startName ?? (props.copyOf ? `${props.copyOf.name} (copy)` : (t?.name ?? "")));
  const [kind, setKind] = useState(from?.kind ?? "purchase");
  const [text, setText] = useState(from?.text ?? "");
  const [notes, setNotes] = useState(from?.notes ?? "");
  // A duplicate is not a default until ticked: a company has one default of each type.
  const [defaults, setDefaults] = useState<number[]>((t?.default_companies ?? []).map((c) => c.id));
  const [companies, setCompanies] = useState<CompanyRow[]>([]);
  useEffect(() => {
    api<CompanyRow[]>("v1/companies/").then(setCompanies, () => setCompanies([]));
  }, []);
  const [disabled, setDisabled] = useState(t ? !t.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const locked = (field: string) => isLocked(t?.lock, field);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = { name, kind, text, notes, default_for: disabled ? [] : defaults };
    try {
      if (t) {
        await api(`v1/terms/${t.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: t.id, name });
      } else {
        const made = await api<{ id: number; name: string }>("v1/terms/", body);
        announceCreated("terms", made);
        props.onDone(made);
      }
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };
  const kindWord = kind === "sales" ? "sales" : "purchase";

  return (
    <FormPage
      title={props.title}
      sub={t ? t.name : undefined}
      formId="terms-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={t ? { value: disabled, set: setDisabled } : undefined}
      tips={
        <p className="small">
          A new order starts with the supplier's own set, else the company's default. The order keeps its own copy of the
          text, which can be changed for that one order.
        </p>
      }
      activity={t ? <ChangeLog type="terms" id={t.id} stamp={JSON.stringify(t)} /> : undefined}
    >
      <InUseNote lock={t?.lock} />
      <Section title="General">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Name</span>
            <input required autoFocus value={name} placeholder="e.g. Purchase - tea" onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            <span className="req">Type</span>
            <Locked on={locked("kind")}>
              <Combobox
                value={kind}
                onChange={(v) => {
                  setKind(v);
                  setDefaults([]);
                }}
                options={TERMS_KINDS.map(([value, label]) => ({ value, label }))}
              />
            </Locked>
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      </Section>
      <Section title="Terms">
        <label className="wide">
          <span className="req">Terms</span>
          <textarea
            required
            rows={14}
            value={text}
            placeholder={"Delivery:\nGoods to reach our store within the delivery date.\nInvoices:\nOriginal bills to come with the material."}
            onChange={(e) => setText(e.target.value)}
          />
          <span className="small">One term per line. A line ending in ":" prints as a heading over the terms below it.</span>
        </label>
      </Section>
      <Section title="Default For">
        <p className="small">
          Tick the companies whose new {kindWord} documents start with these terms when the party has no set of its own. A
          company has one default {kindWord} set: ticking it here takes it off its old one.
        </p>
        <div className="checks">
        {companies.map((c) => (
          <label key={c.id} className="check">
            <input
              type="checkbox"
              disabled={props.readOnly || disabled}
              checked={defaults.includes(c.id)}
              onChange={(e) => setDefaults((d) => (e.target.checked ? [...d, c.id] : d.filter((x) => x !== c.id)))}
            />
            {c.name}
          </label>
        ))}
        </div>
      </Section>
    </FormPage>
  );
}
