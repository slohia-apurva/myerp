import { useCallback, useEffect, useRef, useState } from "react";
import { api, upload } from "./api";
import { Section } from "./Brand";
import { Combobox } from "./Combobox";
import { renewalNote } from "./Companies";
import { ErrorNote } from "./ErrorNote";
import { ActionCells, ActionHeads, ActiveButton, FormBody } from "./RowActions";

type DocFile = { id: number; filename: string; size: number };
export type PartyDocument = {
  id: number;
  kind: string;
  kind_label: string;
  name: string;
  number: string;
  issued_by: string;
  address_label: string;
  valid_from: string | null;
  valid_until: string | null;
  notes: string;
  is_active: boolean;
  files: DocFile[];
};

/** Keep in step with PartyDocument.KINDS in core/models.py. */
const KINDS: [string, string][] = [
  ["gst", "GST registration certificate"],
  ["pan", "PAN card"],
  ["fssai", "FSSAI licence"],
  ["udyam", "MSME / Udyam registration"],
  ["agreement", "Agreement or contract"],
  ["bank", "Cancelled cheque or bank proof"],
  ["other", "Other"],
];
const MAX_SIZE = 10 * 1024 * 1024;
const ACCEPT = ".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx";

const sizeText = (n: number) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/** The "Documents" tab of a customer or supplier: papers with renewal dates and attached files. */
export function PartyDocuments(props: {
  partyId?: number;
  canEdit: boolean;
  onCount: (n: number) => void;
}) {
  const { partyId } = props;
  const countRef = useRef(props.onCount);
  countRef.current = props.onCount;
  const [docs, setDocs] = useState<PartyDocument[]>([]);
  const [editing, setEditing] = useState<PartyDocument | "new" | null>(null);
  const [showOff, setShowOff] = useState(false);
  const reload = useCallback(() => {
    if (!partyId) return;
    api<PartyDocument[]>(`v1/parties/${partyId}/documents/`).then((rows) => {
      setDocs(rows);
      countRef.current(rows.filter((d) => d.is_active).length);
    });
  }, [partyId]);
  useEffect(reload, [reload]);
  if (!partyId) return <p className="small">Save this first, then add its documents here.</p>;
  const shown = docs.filter((d) => d.is_active || showOff);
  return (
    <>
      <div className="page-head">
        <h3>Documents</h3>
        {props.canEdit && (
          <button type="button" className="link" onClick={() => setEditing("new")}>
            Add document
          </button>
        )}
      </div>
      {editing && (
        <DocumentForm
          key={editing === "new" ? "new" : editing.id}
          partyId={partyId}
          document={editing === "new" ? null : editing}
          readOnly={!props.canEdit}
          onDone={() => {
            setEditing(null);
            reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      {shown.length === 0 ? (
        <p className="small">None yet. Add the GST certificate, FSSAI licence, agreement or a cancelled cheque.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Document</th>
              <th>Number</th>
              <th>Renewal</th>
              <th>Attachments</th>
              <ActionHeads />
            </tr>
          </thead>
          <tbody>
            {shown.map((d) => {
              const note = renewalNote(d.valid_until);
              return (
                <tr key={d.id} className={d.is_active ? "" : "inactive"}>
                  <td>
                    {d.kind_label}
                    {d.name && <div className="small">{d.name}</div>}
                    {d.issued_by && <div className="small">{d.issued_by}</div>}
                    {d.address_label && <div className="small">{d.address_label}</div>}
                  </td>
                  <td>{d.number}</td>
                  <td className={note.cls}>{note.text}</td>
                  <td>
                    {d.files.length === 0 ? (
                      <span className="small">No file attached</span>
                    ) : (
                      d.files.map((f) => (
                        <div key={f.id}>
                          <a href={`/api/v1/party-document-files/${f.id}/`} target="_blank" rel="noreferrer">
                            {f.filename}
                          </a>{" "}
                          <span className="small">{sizeText(f.size)}</span>
                        </div>
                      ))
                    )}
                  </td>
                  <ActionCells canEdit={props.canEdit} onOpen={() => setEditing(d)} />
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {docs.some((d) => !d.is_active) && (
        <label className="small">
          <input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} /> Show disabled
          documents
        </label>
      )}
      <p className="small">
        A document is never deleted: use "Disable" to hide it. A renewed document is added as a new one, so the old one
        stays on record.
      </p>
    </>
  );
}

function DocumentForm(props: {
  partyId: number;
  document: PartyDocument | null;
  readOnly: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const x = props.document;
  const [kind, setKind] = useState(x?.kind ?? "gst");
  const [name, setName] = useState(x?.name ?? "");
  const [number, setNumber] = useState(x?.number ?? "");
  const [issuedBy, setIssuedBy] = useState(x?.issued_by ?? "");
  const [premises, setPremises] = useState(x?.address_label ?? "");
  const [validFrom, setValidFrom] = useState(x?.valid_from ?? "");
  const [validUntil, setValidUntil] = useState(x?.valid_until ?? "");
  const [notes, setNotes] = useState(x?.notes ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const [kept, setKept] = useState<DocFile[]>(x?.files ?? []);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const picked = Array.from(list);
    const big = picked.find((f) => f.size > MAX_SIZE);
    if (big) {
      setError(new Error(`${big.name} is over 10 MB.`));
      return;
    }
    setError("");
    setFiles((cur) => [...cur, ...picked]);
  };
  const removeKept = async (f: DocFile) => {
    if (!window.confirm(`Remove ${f.filename} from this document?`)) return;
    try {
      await api(`v1/party-document-files/${f.id}/`, undefined, "DELETE");
      setKept((cur) => cur.filter((k) => k.id !== f.id));
    } catch (err) {
      setError(err);
    }
  };
  const save = async () => {
    if (!number.trim() && kind !== "bank" && kind !== "other") {
      setError(new Error("Give the number of the document."));
      return;
    }
    setBusy(true);
    setError("");
    const body = {
      kind,
      name,
      number,
      issued_by: issuedBy,
      address_label: premises,
      valid_from: validFrom || null,
      valid_until: validUntil || null,
      notes,
    };
    try {
      const saved = x
        ? await api<PartyDocument>(`v1/party-documents/${x.id}/`, body, "PATCH")
        : await api<PartyDocument>(`v1/parties/${props.partyId}/documents/`, body);
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        await upload(`v1/party-documents/${saved.id}/files/`, form);
      }
      props.onDone();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <div
      className="card"
      onKeyDown={(e) => {
        // This sits inside the ledger form: Enter must not save the whole ledger.
        if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT") e.preventDefault();
      }}
    >
      <h4>{x ? `${props.readOnly ? "View" : "Edit"} ${x.kind_label}` : "Add document"}</h4>
      <FormBody readOnly={props.readOnly}>
        <Section title="Document">
          <div className="row">
            <label>
              <span className="req">Document type</span>
              <Combobox value={kind} onChange={setKind} options={KINDS.map(([value, label]) => ({ value, label }))} />
            </label>
            <label>
              {kind === "other" ? <span className="req">Name</span> : "Name (optional)"}
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
          </div>
          <div className="row">
            <label>
              {kind === "bank" || kind === "other" ? "Number" : <span className="req">Number</span>}
              <input value={number} onChange={(e) => setNumber(e.target.value)} />
            </label>
            <label>
              Issued by
              <input value={issuedBy} onChange={(e) => setIssuedBy(e.target.value)} />
            </label>
          </div>
          <label>
            Premises (for papers issued per address)
            <input value={premises} placeholder="Blank for the whole party" onChange={(e) => setPremises(e.target.value)} />
          </label>
        </Section>
        <Section title="Validity">
          <div className="row">
            <label>
              Valid from
              <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
            </label>
            <label>
              Renewal date (blank if it does not lapse)
              <input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </label>
          </div>
        </Section>
        <Section title="Attachments">
          {kept.map((f) => (
            <div key={f.id} className="row">
              <a href={`/api/v1/party-document-files/${f.id}/`} target="_blank" rel="noreferrer">
                {f.filename}
              </a>
              <span className="small">{sizeText(f.size)}</span>
              {!props.readOnly && (
                <button type="button" className="link danger" onClick={() => removeKept(f)}>
                  Remove
                </button>
              )}
            </div>
          ))}
          {files.map((f, i) => (
            <div key={`${f.name}-${i}`} className="row">
              <span>{f.name}</span>
              <span className="small">{sizeText(f.size)} (saved when you click Save)</span>
              <button type="button" className="link danger" onClick={() => setFiles((cur) => cur.filter((_, j) => j !== i))}>
                Remove
              </button>
            </div>
          ))}
          {!props.readOnly && (
            <label
              className="drop"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                addFiles(e.dataTransfer.files);
              }}
            >
              Choose files or drag them here
              <span className="small">PDF, images, Word or Excel. Up to 10 MB each; several files are allowed.</span>
              <input
                type="file"
                multiple
                accept={ACCEPT}
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
          )}
        </Section>
        <Section title="Notes">
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Section>
      </FormBody>
      <ErrorNote error={error} />
      <div className="buttons">
        {!props.readOnly && (
          <button type="button" disabled={busy} onClick={save}>
            {busy ? "Saving…" : "Save"}
          </button>
        )}
        <button type="button" className="secondary" onClick={props.onCancel}>
          {props.readOnly ? "Close" : "Cancel"}
        </button>
        {x && !props.readOnly && (
          <ActiveButton
            url={`v1/party-documents/${x.id}/`}
            active={x.is_active}
            what="this document"
            onDone={props.onDone}
            onError={(m) => setError(m ? new Error(m) : "")}
          />
        )}
      </div>
    </div>
  );
}
