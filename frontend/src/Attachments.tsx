import { useCallback, useEffect, useState } from "react";
import { api, upload } from "./api";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { Fold } from "./Master";

/** The "Attachments" box every entry screen carries (Sidharth, 2026-11-15): the supplier's
 * challan, LR, photos of the truck… Files stay with the entry after Submit and can still be
 * added later. Served by core/attachments.py; each entry type registers there. */

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
const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx,.xls,.xlsx";
const sizeText = (n: number) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

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
  return (
    <Fold title="Attachments" open={rows.length > 0} summary={id === null ? "" : rows.length ? `${rows.length} file${rows.length > 1 ? "s" : ""}` : "None"}>
      {id === null ? (
        <p className="small">Save the entry first, then add the supplier's challan, LR, photos and other papers here.</p>
      ) : (
        <>
          {rows.length > 0 && (
            <div className="table-wrap">
              <table className="list attach-list">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Type</th>
                    <th>Added By</th>
                    <th>Added On</th>
                    <th className="no-print" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        {row.filename} <span className="small">{sizeText(row.size)}</span>
                      </td>
                      <td className="attach-kind">
                        {canChange ? (
                          <Combobox value={row.kind} onChange={(k) => k && k !== row.kind && retype(row, k)} options={kinds} ariaLabel={`Type of ${row.filename}`} />
                        ) : (
                          row.kind_label
                        )}
                      </td>
                      <td>{row.added_by_name}</td>
                      <td>{when(row.added_at)}</td>
                      <td className="no-print attach-acts">
                        <a className="link" href={`/api/v1/attachments/${row.id}/`} target="_blank" rel="noreferrer">
                          Open
                        </a>
                        {canChange && (
                          <button type="button" className="link danger" title={`Remove ${row.filename}`} onClick={() => remove(row)}>
                            ×
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
    </Fold>
  );
}
