import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, upload } from "./api";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { SidePanel } from "./Master";

/** The "Attachments" box every entry screen carries (Sidharth, 2026-11-15): the supplier's
 * challan, LR, photos of the truck… Files stay with the entry after Submit and can still be
 * added later. Served by core/attachments.py; each entry type registers there.
 *
 * Since 2026-11-20 (Sidharth, like Odoo) it sits at the top of the entry's right-hand column
 * (`DocSide`) and shows the chosen file in the page, beside the form. */

type Row = {
  id: number;
  kind: string;
  kind_label: string;
  filename: string;
  size: number;
  added_by_name: string;
  added_at: string;
};
type Listing = { can_change: boolean; kinds: [string, string][]; rows: Row[] };

const MAX_SIZE = 10 * 1024 * 1024;
const SHOWN_IMAGES = [".jpg", ".jpeg", ".png", ".webp"];
const fileUrl = (row: Row) => `/api/v1/attachments/${row.id}/`;
const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx,.xls,.xlsx";
const sizeText = (n: number) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** The draft the server kept when Submit was refused for want of a file (the
 * company's "Attachment Needed to Submit" setting): a new form then edits it,
 * so files can be added straight away. */
export function keptDraft(err: unknown): number | null {
  return err instanceof ApiError && err.keptDraft ? err.keptDraft : null;
}

export function Attachments(props: {
  /** The entry type as registered on the server, e.g. "purchase_order". */
  type: string;
  /** Null for a new entry not saved yet. */
  id: number | null;
  /** Called after a file is added, retyped or removed (to refresh the Activity). */
  onChange?: () => void;
}) {
  const { type, id, onChange } = props;
  const [data, setData] = useState<Listing | null>(null);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState("");
  // The file shown in the viewer; the first one until another is clicked.
  const [picked, setPicked] = useState<number | null>(null);

  const load = useCallback(() => {
    if (id === null) return;
    api<Listing>(`v1/attachments/?type=${type}&id=${id}`).then(setData, setError);
  }, [type, id]);
  useEffect(load, [load]);

  const changed = () => {
    load();
    onChange?.();
  };
  const add = async (list: FileList | null) => {
    if (!list || id === null) return;
    setError("");
    for (const file of Array.from(list)) {
      if (file.size > MAX_SIZE) {
        setError(new Error(`${file.name} is over 10 MB.`));
        continue;
      }
      setBusy(`Adding ${file.name}…`);
      const form = new FormData();
      form.append("type", type);
      form.append("id", String(id));
      form.append("file", file);
      try {
        await upload(`v1/attachments/`, form);
      } catch (err) {
        setError(err);
      }
    }
    setBusy("");
    changed();
  };
  const retype = async (row: Row, kind: string) => {
    try {
      await api(`v1/attachments/${row.id}/`, { kind }, "PATCH");
      changed();
    } catch (err) {
      setError(err);
    }
  };
  const remove = async (row: Row) => {
    if (!window.confirm(`Remove ${row.filename} from this entry?`)) return;
    try {
      await api(`v1/attachments/${row.id}/`, undefined, "DELETE");
      changed();
    } catch (err) {
      setError(err);
    }
  };

  const rows = data?.rows ?? [];
  const kinds = (data?.kinds ?? []).map(([value, label]) => ({ value, label }));
  const canChange = !!data?.can_change;
  const shown = rows.find((r) => r.id === picked) ?? rows[0];
  return (
    <SidePanel title="Attachments" tag={id === null ? "" : rows.length ? `${rows.length} file${rows.length > 1 ? "s" : ""}` : "None"}>
      {id === null ? (
        <p className="small">Save the entry first, then add the supplier's challan, LR, photos and other papers here.</p>
      ) : (
        <>
          {rows.length > 0 && (
            <div className="attach-files" role="tablist" aria-label="Attached files">
              {rows.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  role="tab"
                  aria-selected={row === shown}
                  className={row === shown ? "attach-file on" : "attach-file"}
                  onClick={() => setPicked(row.id)}
                >
                  {row.filename}
                  <span className="small">· {row.kind_label}</span>
                </button>
              ))}
            </div>
          )}
          {shown && <Preview row={shown} />}
          {shown && (
            <div className="attach-bar">
              <span className="small">
                Added by {shown.added_by_name} · {when(shown.added_at)} · {sizeText(shown.size)}
              </span>
              <span className="attach-acts no-print">
                <a className="button" href={fileUrl(shown)} target="_blank" rel="noreferrer">
                  Open in New Tab
                </a>
                {canChange && (
                  <button type="button" className="link danger" onClick={() => remove(shown)}>
                    Remove
                  </button>
                )}
              </span>
            </div>
          )}
          {shown && canChange && (
            <label className="attach-kind no-print">
              Type
              <Combobox value={shown.kind} onChange={(k) => k && k !== shown.kind && retype(shown, k)} options={kinds} ariaLabel={`Type of ${shown.filename}`} />
            </label>
          )}
          {canChange && (
            <div
              className="drop no-print"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                add(e.dataTransfer.files);
              }}
            >
              <span>
                Drop files here, or{" "}
                <label className="attach-pick">
                  choose files
                  <input className="sr-only" type="file" multiple accept={ACCEPT} onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
                </label>{" "}
                /{" "}
                <label className="attach-pick">
                  take a photo
                  <input className="sr-only" type="file" accept="image/*" capture="environment" onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
                </label>
              </span>
              <span className="small">{busy || "PDF, images, Word or Excel, up to 10 MB each"}</span>
            </div>
          )}
          {data && !canChange && !rows.length && <p className="small">No files attached.</p>}
          <p className="small no-print">Files stay with the entry after Submit and can still be added later.</p>
        </>
      )}
      <ErrorNote error={error} />
    </SidePanel>
  );
}

/** The chosen file shown in the page: a PDF in the browser's own viewer, a photo as a
 * picture. Word, Excel and HEIC photos cannot be shown inside a page, so they get a note. */
function Preview({ row }: { row: Row }) {
  const ext = row.filename.slice(row.filename.lastIndexOf(".")).toLowerCase();
  if (ext === ".pdf")
    return (
      <>
        <iframe className="attach-view no-print" src={fileUrl(row)} title={row.filename} />
        <p className="attach-none attach-phone small">On a phone the PDF opens on its own: tap "Open in New Tab".</p>
      </>
    );
  if (SHOWN_IMAGES.includes(ext))
    return (
      <div className="attach-view attach-image no-print">
        <img src={fileUrl(row)} alt={row.filename} />
      </div>
    );
  return <p className="attach-none small">This kind of file cannot be shown here. Use "Open in New Tab" to open or download it.</p>;
}

/** The right-hand column of an entry screen (Sidharth, 2026-11-20): the Attachments box
 * with the file shown, then the screen's own panels (totals, details, Activity). On a
 * narrow screen it drops below the form. */
export function DocSide(props: { type: string; id: number | null; onChange?: () => void; children?: ReactNode }) {
  return (
    <div className="doc-side">
      <Attachments type={props.type} id={props.id} onChange={props.onChange} />
      {props.children}
    </div>
  );
}
