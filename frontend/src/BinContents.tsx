import { useEffect, useState } from "react";
import { api } from "./api";
import { PageHeader } from "./Brand";
import { ErrorNote } from "./ErrorNote";
import { Fold } from "./Master";

/** What is in a bin, rack or area now: opened by scanning the QR code on a bin sheet
 * (Sidharth, 2026-11-15). Read only; works on a phone. */

type Contents = {
  id: number;
  code: string;
  name: string;
  kind_label: string;
  purpose_label: string;
  branch_name: string;
  company_name: string;
  stock: { location_name: string; item_name: string; item_number: string; batch: string; expiry_date: string | null; batch_status: string; qty: string; unit_name: string }[];
  packages: { number: string; kind_label: string; location_name: string; item_name: string; batch: string; left_qty: string; unit_name: string; status_label: string; voucher_number: string }[];
};

const dmy = (iso: string | null) => (iso ? iso.split("-").reverse().join("-") : "");
const qty = (v: string) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: 6 });
const STATUS: Record<string, string> = { quarantine: "Quarantine", released: "Released", rejected: "Rejected" };

export function BinContentsPage({ id }: { id: number }) {
  const [c, setC] = useState<Contents | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    api<Contents>(`v1/bins/${id}/`).then(setC, setError);
  }, [id]);
  if (!c)
    return (
      <section className="page">
        <ErrorNote error={error} />
      </section>
    );
  const several = new Set(c.stock.map((s) => s.location_name)).size > 1;
  return (
    <section className="page doc-page">
      <PageHeader title={c.name} crumbs={[{ label: "Bin contents", href: `#/bins/${c.id}` }]} sub={[c.code, c.kind_label, c.purpose_label, c.branch_name, c.company_name].filter(Boolean).join(" · ")} />
      <Fold title="In This Bin Now" open summary={c.stock.length ? `${c.stock.length} item${c.stock.length === 1 ? "" : "s"}` : "Empty"}>
        {c.stock.length ? (
          <div className="table-scroll">
            <table className="grid">
              <thead>
                <tr>
                  {several && <th>Bin</th>}
                  <th>Item</th>
                  <th>Batch</th>
                  <th>Expiry</th>
                  <th>Batch Status</th>
                  <th className="num">Qty</th>
                  <th>Unit</th>
                </tr>
              </thead>
              <tbody>
                {c.stock.map((s, i) => (
                  <tr key={i}>
                    {several && <td>{s.location_name}</td>}
                    <td>
                      <b>{s.item_name}</b> <span className="small-inline">{s.item_number}</span>
                    </td>
                    <td>{s.batch || "–"}</td>
                    <td>{dmy(s.expiry_date)}</td>
                    <td>{STATUS[s.batch_status] ?? ""}</td>
                    <td className="num">{qty(s.qty)}</td>
                    <td>{s.unit_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="small">Nothing is kept here now.</p>
        )}
      </Fold>
      <Fold title="Bags And Boxes Here" open={c.packages.length > 0} summary={c.packages.length ? `${c.packages.length}` : "None"}>
        {c.packages.length ? (
          <div className="table-scroll">
            <table className="grid">
              <thead>
                <tr>
                  <th>Package No</th>
                  <th>Type</th>
                  {several && <th>Bin</th>}
                  <th>Item</th>
                  <th>Batch</th>
                  <th className="num">Left</th>
                  <th>Unit</th>
                  <th>Status</th>
                  <th>Received On</th>
                </tr>
              </thead>
              <tbody>
                {c.packages.map((k) => (
                  <tr key={k.number}>
                    <td>
                      <b>{k.number}</b>
                    </td>
                    <td>{k.kind_label}</td>
                    {several && <td>{k.location_name}</td>}
                    <td>{k.item_name}</td>
                    <td>{k.batch || "–"}</td>
                    <td className="num">{qty(k.left_qty)}</td>
                    <td>{k.unit_name}</td>
                    <td>{k.status_label}</td>
                    <td>{k.voucher_number}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="small">No numbered bags or boxes here.</p>
        )}
      </Fold>
    </section>
  );
}
