import { Combobox } from "./Combobox";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { useExchange } from "./Exchange";
import { Cells, useColumns, type Column } from "./Columns";
import { ActionCells, ActionHeads } from "./RowActions";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { ColumnSearch } from "./ColumnSearch";
import { useOnReturn } from "./Refresh";
import { useKept } from "./Keep";

/** Credit terms: how a party's bills are paid, split into parts. */
export type TermPart = { percent: string; event: string; days: number };
export type CreditTerm = {
  id: number;
  name: string;
  is_active: boolean;
  notes: string;
  parts: TermPart[];
  summary: string;
  party_count: number;
};

export const EVENTS: [string, string][] = [
  ["order", "With the order (advance)"],
  ["dispatch", "Before dispatch"],
  ["delivery", "On delivery"],
  ["bill", "After the bill date"],
];

export function useCreditTerms() {
  const [terms, setTerms] = useState<CreditTerm[]>([]);
  // refresh returns the request, so "Create …" can wait for the new record.
  const refresh = useCallback(() => api<CreditTerm[]>("v1/credit-terms/").then(setTerms), []);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { terms, reload, refresh };
}

/** `?form=new`, `?form=<id>` or `?form=copy-<id>`: this tab was opened to add, change,
 * view or duplicate one credit term (Sidharth, 2026-11-13). */
const formParam = () => hashParam("form");

// The list's columns; "Choose Columns…" in Actions ▾ picks and orders them for each person.
const TERM_COLUMNS: Column<CreditTerm>[] = [
  {
    key: "name",
    label: "Name",
    fixed: true,
    cell: (t) => (
      <>
        {t.name}
        {!t.is_active && <span className="pill">Inactive</span>}
      </>
    ),
  },
  { key: "summary", label: "When payment is due", standard: true, cell: (t) => t.summary },
  { key: "parties", label: "Parties", standard: true, num: true, cell: (t) => t.party_count || "" },
  { key: "notes", label: "Notes", cell: (t) => <span className="small">{t.notes}</span> },
];

/** Masters > Credit terms: one list for every company in the group. The details of the
 * clicked row are on the right; Add, Edit and Duplicate open in a new tab. */
export function CreditTermsPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const { terms, reload } = useCreditTerms();
  const form = formParam();
  if (form) return <TermFormTab form={form} canEdit={canEdit} terms={terms} />;
  return <TermList session={session} canEdit={canEdit} terms={terms} reload={reload} />;
}

function TermList(props: { session: SignedIn; canEdit: boolean; terms: CreditTerm[]; reload: () => void }) {
  const { terms, canEdit, reload } = props;
  const [selectedId, setSelected] = useKept<number | null>("CreditTerms.selectedId", null);
  useCreated("credit_term_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    // Opened by "Create …" in a dropdown: go straight to the Add page.
    if (startName && canEdit) window.location.hash = `#/credit-terms?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const columns = useColumns("credit-terms", TERM_COLUMNS, { sort: false });
  const io = useExchange({ master: "credit-terms", noun: "credit terms", session: props.session, onImported: reload, extra: [columns.item] });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    // Opened from a link (for example a duplicate-name refusal): select that row.
    if (openId && terms.some((t) => t.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, terms, opened]);
  const selected = terms.find((t) => t.id === selectedId) ?? null;
  return (
    <section className="page">
      <PageHeader
        title="Credit terms"
        sub="How customers pay and suppliers are paid. One list for every company in the group."
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => openTab("#/credit-terms?form=new")}>Add credit terms</button>}
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
              {terms.map((t) => (
                <tr
                  key={t.id}
                  className={`${t.is_active ? "" : "off"}${selectedId === t.id ? " selected" : ""}`}
                  onClick={() => setSelected(t.id)}
                  onDoubleClick={() => openTab(`#/credit-terms?form=${t.id}`)}
                >
                  <Cells shown={columns.shown} row={t} />
                  <ActionCells
                    canEdit={canEdit}
                    onOpen={() => openTab(`#/credit-terms?form=${t.id}`)}
                    onDuplicate={() => openTab(`#/credit-terms?form=copy-${t.id}`)}
                  />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="side-col">
          <SidePanel title="Credit Term Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.name],
                  ["Due", selected.summary],
                  ["Parties", String(selected.party_count)],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                  ["Notes", selected.notes],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="credit_term" id={selected?.id} stamp={JSON.stringify(selected ?? terms.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one credit term, alone in its own tab: Save and Cancel close the tab. */
function TermFormTab(props: { form: string; canEdit: boolean; terms: CreditTerm[] }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const [loaded, setLoaded] = useState(props.form === "new");
  const [terms, setTerms] = useState<CreditTerm[]>([]);
  useEffect(() => {
    if (props.form === "new") return;
    api<CreditTerm[]>("v1/credit-terms/").then((t) => {
      setTerms(t);
      setLoaded(true);
    });
  }, [props.form]);
  const startName = useNewName();
  const target = props.form === "new" ? null : (terms.find((t) => t.id === key) ?? null);
  const toList = () => {
    window.location.hash = "#/credit-terms";
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("credit_term_saved", saved);
    closeThisTab(toList);
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "Add credit terms" : copy ? "Duplicate credit terms" : readOnly ? "View credit terms" : "Edit credit terms";
  if (!loaded) return <section className="page"><PageHeader title={title} /></section>;
  if (props.form !== "new" && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">Those credit terms were not found.</p>
      </section>
    );
  if (!props.canEdit && !editing) return <section className="page"><PageHeader title={title} /><p className="error">You may only view credit terms.</p></section>;
  return (
    <TermForm
      title={title}
      term={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function TermForm(props: {
  title: string;
  term: CreditTerm | null;
  copyOf?: CreditTerm | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const t = props.term;
  const from = t ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const [name, setName] = useState(props.startName ?? (props.copyOf ? `${props.copyOf.name} (copy)` : (t?.name ?? "")));
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [parts, setParts] = useState<TermPart[]>(from?.parts ?? [{ percent: "100", event: "bill", days: 30 }]);
  const [disabled, setDisabled] = useState(t ? !t.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const total = parts.reduce((sum, p) => sum + (Number(p.percent) || 0), 0);
  const setPart = (i: number, change: Partial<TermPart>) =>
    setParts(parts.map((p, j) => (j === i ? { ...p, ...change } : p)));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (t) {
        await api(`v1/credit-terms/${t.id}/`, { name, notes, parts, is_active: !disabled }, "PATCH");
        props.onDone({ id: t.id, name });
      } else {
        const made = await api<{ id: number; name: string }>("v1/credit-terms/", { name, notes, parts });
        announceCreated("credit_term", made);
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
      sub={t ? t.name : undefined}
      formId="term-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={t ? { value: disabled, set: setDisabled } : undefined}
      tips={<p className="small">The shares must add up to 100%.</p>}
      activity={t ? <ChangeLog type="credit_term" id={t.id} stamp={JSON.stringify(t)} /> : undefined}
    >
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
              placeholder="e.g. 50% advance, 50% on delivery"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      </Section>
      <Section title="Payment Parts">
        <table className="grid">
          <thead>
            <tr>
              <th className="num">Share (%)</th>
              <th>Due</th>
              <th className="num">Plus days</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {parts.map((p, i) => (
              <tr key={i}>
                <td>
                  <input
                    required
                    className="num"
                    inputMode="decimal"
                    value={p.percent}
                    onChange={(e) => setPart(i, { percent: e.target.value })}
                  />
                </td>
                <td>
                  <Combobox
                    value={p.event}
                    onChange={(v) => setPart(i, { event: v })}
                    options={EVENTS.map(([value, label]) => ({ value, label }))}
                  />
                </td>
                <td>
                  <input
                    className="num"
                    inputMode="numeric"
                    value={p.days}
                    onChange={(e) => setPart(i, { days: Number(e.target.value) || 0 })}
                  />
                </td>
                <td>
                  {parts.length > 1 && (
                    <button type="button" className="link danger" onClick={() => setParts(parts.filter((_, j) => j !== i))}>
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className="num">
                <strong className={total === 100 ? "" : "error"}>{Number(total.toFixed(2))}%</strong>
              </td>
              <td colSpan={3}>
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    setParts([...parts, { percent: total < 100 ? String(Number((100 - total).toFixed(2))) : "", event: "bill", days: 0 }])
                  }
                >
                  Add part
                </button>
              </td>
            </tr>
          </tfoot>
        </table>
        <p className="small">
          The shares must add up to 100%. "Plus days" counts from the event: 30 days after the bill date, or 7 days after
          delivery.
        </p>
      </Section>
    </FormPage>
  );
}
