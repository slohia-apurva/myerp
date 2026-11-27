import { FormEvent, useCallback, useEffect, useState } from "react";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { Cells, useColumns, type Column } from "./Columns";
import { ActionCells, ActionHeads } from "./RowActions";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { ColumnSearch } from "./ColumnSearch";
import { useOnReturn } from "./Refresh";
import { useKept } from "./Keep";

/** Mail Templates (Sidharth, 2026-11-27): the wording of the mails "Email Supplier"
 * sends, one list for every company in the group. */
export type MailTemplate = {
  id: number;
  name: string;
  used_for: string;
  used_for_label: string;
  subject: string;
  opening: string;
  closing: string;
  attach: boolean;
  attaches: string;
  is_default: boolean;
  is_active: boolean;
  notes: string;
};
export type MailUse = { value: string; label: string; fields: string[]; attaches: string };
type Listing = { templates: MailTemplate[]; uses: MailUse[] };

export function useMailTemplates() {
  const [data, setData] = useState<Listing>({ templates: [], uses: [] });
  const refresh = useCallback(() => api<Listing>("v1/mail-templates/").then(setData), []);
  const reload = useCallback(() => {
    refresh();
  }, [refresh]);
  useEffect(reload, [reload]);
  useOnReturn(reload);
  return { ...data, reload, refresh };
}

const COLUMNS: Column<MailTemplate>[] = [
  {
    key: "name",
    label: "Name",
    fixed: true,
    cell: (t) => (
      <>
        {t.name}
        {!t.is_active && <span className="pill">Disabled</span>}
      </>
    ),
  },
  { key: "used_for", label: "Used For", standard: true, cell: (t) => t.used_for_label },
  { key: "subject", label: "Subject", standard: true, cell: (t) => t.subject },
  { key: "attaches", label: "Attaches", standard: true, cell: (t) => (t.attach ? t.attaches : <span className="small">—</span>) },
  { key: "default", label: "Default", standard: true, cell: (t) => (t.is_default ? "✓" : "") },
];

/** Masters > Mail templates. */
export function MailTemplatesPage({ session }: { session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const all = useMailTemplates();
  const form = hashParam("form");
  if (form) return <TemplateFormTab form={form} canEdit={canEdit} />;
  return <TemplateList session={session} canEdit={canEdit} {...all} />;
}

function TemplateList(props: { session: SignedIn; canEdit: boolean; templates: MailTemplate[]; reload: () => void }) {
  const { templates, canEdit, reload } = props;
  const [selectedId, setSelected] = useKept<number | null>("MailTemplates.selectedId", null);
  useCreated("mail_template_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    if (startName && canEdit) window.location.hash = `#/mail-templates?form=new&new=${encodeURIComponent(startName)}`;
  }, [startName, canEdit]);
  const columns = useColumns("mail-templates", COLUMNS, { sort: false });
  const io = useExchange({ master: "mail_templates", noun: "mail templates", session: props.session, onImported: reload, extra: [columns.item] });
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    if (openId && templates.some((t) => t.id === openId)) {
      setSelected(openId);
      opened();
    }
  }, [openId, templates, opened]);
  const selected = templates.find((t) => t.id === selectedId) ?? null;
  const edit = (what: number | string) => openTab(`#/mail-templates?form=${what}`);
  return (
    <section className="page">
      <PageHeader
        title="Mail Templates"
        sub='The wording of the mails sent from "Email Supplier". One list for every company in the group.'
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>New Mail Template</button>}
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
              {templates.map((t) => (
                <tr
                  key={t.id}
                  className={`${t.is_active ? "" : "off"}${selectedId === t.id ? " selected" : ""}`}
                  onClick={() => setSelected(t.id)}
                  onDoubleClick={() => edit(t.id)}
                >
                  <Cells shown={columns.shown} row={t} />
                  <ActionCells canEdit={canEdit} onOpen={() => edit(t.id)} onDuplicate={() => edit(`copy-${t.id}`)} />
                </tr>
              ))}
              {templates.length === 0 && (
                <tr>
                  <td colSpan={columns.shown.length + 2} className="small">
                    No mail templates yet. Click "New Mail Template".
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p className="small">
            The "Template" picker in "Email Supplier" lists every active template that fits the order, the default first. Add more for the same use, such as a
            firmer second reminder.
          </p>
        </div>
        <div className="side-col">
          <SidePanel title="Mail Template Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.name],
                  ["Used For", selected.used_for_label],
                  ["Subject", selected.subject],
                  ["Attaches", selected.attach ? selected.attaches : "Nothing"],
                  ["Default", selected.is_default ? "Yes" : "No"],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="mail_template" id={selected?.id} stamp={JSON.stringify(selected ?? templates.length)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

function TemplateFormTab(props: { form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const [data, setData] = useState<Listing | null>(null);
  useEffect(() => {
    api<Listing>("v1/mail-templates/").then(setData);
  }, []);
  const startName = useNewName();
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("mail_template_saved", saved);
    closeThisTab(() => {
      window.location.hash = "#/mail-templates";
    });
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title = props.form === "new" ? "New Mail Template" : copy ? "Duplicate Mail Template" : readOnly ? "View Mail Template" : "Edit Mail Template";
  if (!data)
    return (
      <section className="page">
        <PageHeader title={title} />
      </section>
    );
  const target = props.form === "new" ? null : (data.templates.find((t) => t.id === key) ?? null);
  if (props.form !== "new" && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That mail template was not found.</p>
      </section>
    );
  if (readOnly && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view mail templates.</p>
      </section>
    );
  return (
    <TemplateForm
      title={title}
      uses={data.uses}
      template={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function TemplateForm(props: {
  title: string;
  uses: MailUse[];
  template: MailTemplate | null;
  copyOf: MailTemplate | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const t = props.template;
  const from = t ?? props.copyOf;
  const [name, setName] = useState(props.startName ?? (props.copyOf ? `${props.copyOf.name} (copy)` : (t?.name ?? "")));
  const [usedFor, setUsedFor] = useState(from?.used_for ?? "");
  const [subject, setSubject] = useState(from?.subject ?? "");
  const [opening, setOpening] = useState(from?.opening ?? "");
  const [closing, setClosing] = useState(from?.closing ?? "");
  const [attach, setAttach] = useState(from?.attach ?? true);
  const [isDefault, setDefault] = useState(t?.is_default ?? false);
  const [disabled, setDisabled] = useState(t ? !t.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const use = props.uses.find((u) => u.value === usedFor);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = { name, used_for: usedFor, subject, opening, closing, attach, is_default: isDefault && !disabled };
    try {
      if (t) {
        await api(`v1/mail-templates/${t.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: t.id, name });
      } else {
        const made = await api<{ id: number; name: string }>("v1/mail-templates/", body);
        announceCreated("mail_template", made);
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
      formId="mail-template-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={t ? { value: disabled, set: setDisabled } : undefined}
      switches={
        <label className="check">
          <input type="checkbox" disabled={props.readOnly || disabled} checked={isDefault && !disabled} onChange={(e) => setDefault(e.target.checked)} />
          Default for "{use?.label ?? "its use"}"
        </label>
      }
      tips={
        <>
          <p className="fact-label">Fields You Can Use</p>
          {use ? (
            <p className="mail-fields">
              {use.fields.map((f) => (
                <code key={f}>{`{${f}}`}</code>
              ))}
            </p>
          ) : (
            <p className="small">Pick "Used For" to see the fields.</p>
          )}
          <p className="small">Type them as shown; they are filled in when the mail is made. A field this template cannot use is refused on Save.</p>
        </>
      }
      activity={t ? <ChangeLog type="mail_template" id={t.id} stamp={JSON.stringify(t)} /> : undefined}
    >
      <Section title="General">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Name</span>
            <input required autoFocus value={name} placeholder="e.g. Second Reminder (firm)" onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            <span className="req">Used For</span>
            <Combobox
              ariaLabel="Used For"
              value={usedFor}
              onChange={setUsedFor}
              options={props.uses.map((u) => ({ value: u.value, label: u.label }))}
            />
            <span className="small">Decides which lines the mail's grid shows and when the template is offered.</span>
          </label>
          <label className="wide">
            <span className="req">Subject</span>
            <input required value={subject} placeholder="e.g. Reminder: Pending Supply against PO No : {PO No}" onChange={(e) => setSubject(e.target.value)} />
          </label>
          <div>
            <span className="fact-label">Attach</span>
            <label className="check">
              <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} />
              {use?.attaches ?? "The document"}
            </label>
            <span className="small">Ticked by default in the mail; can be unticked there.</span>
          </div>
        </div>
      </Section>
      <Section title="Mail Text">
        <label className="field">
          <span className="req">Opening</span>
          <textarea required rows={3} value={opening} onChange={(e) => setOpening(e.target.value)} />
        </label>
        <p className="mail-grid-slot small">The lines grid goes here.</p>
        <label className="field">
          Closing
          <textarea rows={3} value={closing} onChange={(e) => setClosing(e.target.value)} />
        </label>
        <p className="small">"Dear {"{Contact Name}"}," and the signature (your name, company, phone) are added by the mail itself.</p>
      </Section>
    </FormPage>
  );
}
