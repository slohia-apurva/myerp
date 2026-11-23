import { useState } from "react";
import { api } from "./api";
import { Combobox } from "./Combobox";
import { ErrorNote } from "./ErrorNote";
import { Fold } from "./Master";

/** "Pick Materials" on a submitted Manufacturing Order (Sidharth, 2026-11-23, preview 17): the order is
 * its own pick list. One row per material with what is picked and from where, a green ✓ or a red ✕ with
 * what is short; "Edit picks" opens one material at a time with the same Area › Bin › Batch › Package
 * chooser as the sales Pick List, and "Done" saves it. Quantities are in the stock unit. */

export type Pick = {
  id: number;
  location: number;
  location_name: string;
  area: number | null;
  area_name: string;
  batch: number | null;
  batch_number: string;
  expiry: string | null;
  package: number | null;
  package_number: string;
  qty: string;
};
export type PickLine = {
  position: number;
  item: number;
  item_name: string;
  from_bom: boolean;
  required: string;
  issued: string;
  unit_name: string;
  factor: string;
  stock_unit_name: string;
  picks: Pick[];
  picked_stock: string;
  pick_short: string;
};
type Spot = Omit<Pick, "id" | "qty"> & { free: string };
type DraftRow = { key: number; area: string; bin: string; batch: string; pkg: string; qty: string };

let nextKey = 1;
const idOr = (n: number | null | undefined) => (n == null ? "none" : String(n));
const plain = (n: number) => String(Number(n.toFixed(3)));
const shortDate = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const uniq = (list: { value: string; label: string; hint?: string }[]) => list.filter((o, n) => list.findIndex((x) => x.value === o.value) === n);

/** "RM-R1-B2 · B2611-03 (60) · PK-000120"; several places joined with "; ". */
export const picksText = (picks: Pick[]) =>
  picks.map((p) => `${[p.location_name, p.batch_number].filter(Boolean).join(" · ")} (${plain(Number(p.qty))})${p.package_number ? ` · ${p.package_number}` : ""}`).join("; ");

export function MoPicks<T>(props: { orderId: number; lines: PickLine[]; mayEdit: boolean; onSaved: (order: T) => void }) {
  const [open, setOpen] = useState<number | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [spots, setSpots] = useState<Spot[]>([]);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const lines = props.lines.filter((l, n) => props.lines.findIndex((x) => x.item === l.item) === n);
  const full = lines.filter((l) => Number(l.pick_short) === 0).length;
  const edit = (l: PickLine) => {
    setError("");
    setOpen(l.item);
    setRows(l.picks.map((p) => ({ key: nextKey++, area: idOr(p.area), bin: String(p.location), batch: idOr(p.batch), pkg: idOr(p.package), qty: p.qty })));
    setSpots([]);
    api<Spot[]>(`v1/manufacturing-orders/${props.orderId}/places/?item=${l.item}`).then(setSpots, (err) => setError(err));
  };
  const call = async (path: string, body: object, method?: "PATCH") => {
    setError("");
    setBusy(true);
    try {
      props.onSaved(await api<T>(`v1/manufacturing-orders/${props.orderId}/${path}/`, body, method));
      setOpen(null);
    } catch (err) {
      setError(err);
    }
    setBusy(false);
  };
  const done = (item: number) =>
    call(
      "picks",
      {
        item,
        rows: rows
          .filter((r) => r.bin)
          .map((r) => ({ location: Number(r.bin), batch: r.batch && r.batch !== "none" ? Number(r.batch) : null, package: r.pkg && r.pkg !== "none" ? Number(r.pkg) : null, qty: r.qty || "0" })),
      },
      "PATCH",
    );
  const set = (key: number, patch: Partial<DraftRow>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  return (
    <Fold title="Pick Materials" open summary={`${lines.length} materials · ${full} fully picked${full < lines.length ? ` · ${lines.length - full} short` : ""}`}>
      <ErrorNote error={error} />
      <div className="table-scroll">
        <table className="grid po-lines">
          <thead>
            <tr>
              <th>#</th>
              <th>Material</th>
              <th className="num">Still to Issue</th>
              <th className="num">Picked</th>
              <th>Picked From (bin · batch · package)</th>
              <th />
              <th />
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => {
              const need = (Number(l.required) - Number(l.issued)) * Number(l.factor);
              const short = Number(l.pick_short);
              const editing = open === l.item;
              const got = editing ? rows.reduce((t, r) => t + (Number(r.qty) || 0), 0) : Number(l.picked_stock);
              return [
                <tr key={l.item} id={`pick-${l.item}`}>
                  <td>{l.position}</td>
                  <td>
                    <b>{l.item_name}</b> {l.from_bom ? <span className="pill">BOM</span> : <span className="pill warn">Added</span>}
                  </td>
                  <td className="num nowrap">
                    {plain(need)} {l.stock_unit_name}
                  </td>
                  <td className="num nowrap">{short > 0 && !editing ? <b className="error">{l.picked_stock}</b> : plain(got)}</td>
                  <td className="small">{editing ? "Being changed below" : picksText(l.picks) || <span className="error">Nothing free yet</span>}</td>
                  <td className="nowrap">{short > 0 ? <b className="error">✕ {l.pick_short} short</b> : <b className="ok-note">✓</b>}</td>
                  <td className="nowrap">
                    {props.mayEdit &&
                      (editing ? (
                        <button type="button" disabled={busy} onClick={() => done(l.item)}>
                          Done
                        </button>
                      ) : (
                        open === null && (
                          <button type="button" className="link" onClick={() => edit(l)}>
                            Edit picks
                          </button>
                        )
                      ))}
                  </td>
                </tr>,
                editing && (
                  <tr key={`${l.item}-edit`}>
                    <td />
                    <td colSpan={6}>
                      <table className="grid">
                        <thead>
                          <tr>
                            <th>Area</th>
                            <th>Bin</th>
                            <th>Batch</th>
                            <th>Package</th>
                            <th className="num">Qty ({l.stock_unit_name})</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((r) => {
                            const inArea = spots.filter((s) => idOr(s.area) === r.area);
                            const inBin = inArea.filter((s) => String(s.location) === r.bin);
                            const inBatch = inBin.filter((s) => idOr(s.batch) === r.batch);
                            const free = (list: Spot[]) => `${plain(list.reduce((t, s) => t + Number(s.free), 0))} ${l.stock_unit_name} free`;
                            const areas = uniq(spots.map((s) => ({ value: idOr(s.area), label: s.area_name || s.location_name, hint: free(spots.filter((x) => x.area === s.area)) })));
                            const bins = uniq(inArea.map((s) => ({ value: String(s.location), label: s.location_name, hint: free(inArea.filter((x) => x.location === s.location)) })));
                            const batches = uniq(
                              inBin.map((s) => ({
                                value: idOr(s.batch),
                                label: s.batch_number || "No batch",
                                hint: [s.expiry && `exp ${shortDate(s.expiry)}`, free(inBin.filter((x) => x.batch === s.batch))].filter(Boolean).join(" · "),
                              })),
                            );
                            const packages = uniq(inBatch.map((s) => ({ value: idOr(s.package), label: s.package_number || "No package", hint: free([s]) })));
                            const cell = (value: string, options: { value: string; label: string; hint?: string }[], label: string, patch: (v: string) => Partial<DraftRow>) => (
                              <Combobox value={value} onChange={(v) => set(r.key, patch(v))} ariaLabel={`${label} for ${l.item_name}`} placeholder="Type to search…" options={options} />
                            );
                            return (
                              <tr key={r.key}>
                                <td>{cell(r.area, areas, "Area", (v) => ({ area: v, bin: "", batch: "", pkg: "" }))}</td>
                                <td>{cell(r.bin, bins, "Bin", (v) => ({ bin: v, batch: "", pkg: "" }))}</td>
                                <td>{cell(r.batch, batches, "Batch", (v) => ({ batch: v, pkg: "" }))}</td>
                                <td>{cell(r.pkg, packages, "Package", (v) => ({ pkg: v }))}</td>
                                <td className="num">
                                  <input className="num" inputMode="decimal" aria-label={`Pick qty for ${l.item_name}`} value={r.qty} onChange={(e) => set(r.key, { qty: e.target.value })} />
                                </td>
                                <td>
                                  <button type="button" className="link danger" aria-label="Remove row" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}>
                                    ✕
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                      <div className="buttons">
                        <button type="button" className="link" onClick={() => setRows((rs) => [...rs, { key: nextKey++, area: "", bin: "", batch: "", pkg: "", qty: plain(Math.max(need - got, 0)) }])}>
                          + Add package
                        </button>
                        <button type="button" className="link" disabled={busy} onClick={() => call("pick-again", { item: l.item })}>
                          Pick again
                        </button>
                        <button type="button" className="link" onClick={() => setOpen(null)}>
                          Cancel
                        </button>
                      </div>
                      <p className="small">
                        Area, Bin, Batch and Package each offer only what is free in the one before (stock less what other orders and pick lists hold), earliest expiry first. "Pick again" proposes this material
                        afresh by the rule.
                      </p>
                    </td>
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>
      {props.mayEdit && (
        <div className="buttons">
          <button type="button" className="link" disabled={busy || open !== null} onClick={() => call("pick-again", {})}>
            Pick again (all materials)
          </button>
        </div>
      )}
      <p className="small">
        Picked on Submit by the pick list rule (earliest expiry first, then oldest received; Quarantine and Rejected batches never) from "Materials From". The picked stock is held for this order: other orders,
        pick lists and Own Use see it as not free. Short stock is not an error: "Pick again" fills the rest once stock comes in. Cancel or "Close MO" lets the stock go.
      </p>
    </Fold>
  );
}
