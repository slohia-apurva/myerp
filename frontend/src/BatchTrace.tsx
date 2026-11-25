import { useEffect, useState } from "react";
import { api } from "./api";
import { PageHeader } from "./Brand";
import { closeThisTab } from "./Create";
import { ErrorNote } from "./ErrorNote";
import { readTables, usePrintMenu } from "./Exchange";
import { Fold, openTab, SidePanel, SideRows } from "./Master";
import { showDate } from "./Batches";

/** Batch Trace: where one batch came from, where it is now and where it went, for recall
 * and audits (Sidharth, 2026-11-25, preview mockups/batch-trace/1-batch-trace-preview.png).
 * Read from the stock ledger, across every company of the group the person may see. The
 * retention sample label QR opens #/batches/<id>/trace, so that address must stay. */

type Ref = {
  type: string;
  type_label: string;
  id: number;
  number: string;
  page: string;
  company: number;
  extra?: string;
  qty?: string;
};
type Party = {
  id: number | null;
  name: string;
  number: string;
  contact: string;
} | null;
type Row = {
  date: string;
  entry: Ref;
  company_name: string;
  branch_name: string;
  party: Party;
  to: string;
  orders: Ref[];
  bills: Ref[];
  note: string;
  customer_goods: boolean;
  qty: string;
  back?: string;
  moved?: boolean;
};
type Place = {
  company_name: string;
  branch_name: string;
  location: number;
  location_name: string;
  owner_name: string;
  bags: string;
  qty: string;
  held: Ref[];
};
type Move = {
  date: string;
  entry: Ref;
  reversal: boolean;
  company_name: string;
  branch_name: string;
  location_name: string;
  qty: string;
  balance: string;
};
type Trace = {
  batch: {
    id: number;
    number: string;
    supplier_batch_no: string;
    mfg_date: string | null;
    expiry_date: string | null;
    status: string;
    status_label: string;
    notes: string;
    is_active: boolean;
    item: number;
    item_name: string;
    item_number: string;
  };
  unit: string;
  companies: number;
  came_from: Row[];
  now: Place[];
  went: Row[];
  customers: {
    id: number | null;
    name: string;
    number: string;
    contact: string;
    qty: string;
    entries: number;
  }[];
  moves: Move[];
  balance: {
    received: string;
    sent: string;
    back: string;
    moved: string;
    in_stock: string;
    held: string;
  };
};

const qty = (v: string) => (v === "" ? "" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 6 }));

/** An entry's number, opening it in this tab (Ctrl+click: a new one). */
function EntryLink({ r }: { r: Ref }) {
  if (!r.page) return <>{r.number}</>;
  const href = `#/companies/${r.company}/${r.page}?view=${r.id}`;
  return (
    <a
      href={href}
      title={`Open ${r.type_label} ${r.number}`}
      onClick={(e) => {
        if (e.ctrlKey || e.metaKey) return;
        e.preventDefault();
        openTab(href);
      }}
    >
      {r.number}
    </a>
  );
}

function Refs({ refs }: { refs: Ref[] }) {
  return (
    <>
      {refs.map((r, i) => (
        <div key={`${r.type}-${r.id}-${i}`}>
          <EntryLink r={r} />
          {r.extra && <span className="small"> Supplier bill {r.extra}</span>}
        </div>
      ))}
    </>
  );
}

function Who({ row }: { row: Row }) {
  // Our own goods moved between branches: neither out nor in.
  if (row.moved)
    return (
      <>
        {row.to}
        <span className="small">Moved {qty(row.qty)}, still ours</span>
      </>
    );
  if (!row.party) return <>{row.to}</>;
  return (
    <>
      {row.party.name}
      {(row.party.number || row.party.contact) && <span className="small">{[row.party.number, row.party.contact].filter(Boolean).join(" · ")}</span>}
    </>
  );
}

function What({ row }: { row: Row }) {
  return (
    <>
      <EntryLink r={row.entry} />
      <span className="small">{[row.entry.type_label, row.note].filter(Boolean).join(" · ")}</span>
    </>
  );
}

export function BatchTracePage({ id }: { id: number }) {
  const [t, setT] = useState<Trace | null>(null);
  const [error, setError] = useState<unknown>("");
  useEffect(() => {
    api<Trace>(`v1/batches/${id}/trace/`).then(setT, setError);
  }, [id]);
  const b = t?.batch;
  const unit = t?.unit ? ` (${t.unit})` : "";
  const several = (t?.companies ?? 0) > 1;
  const printing = usePrintMenu({
    title: b ? `Batch Trace ${b.number}` : "Batch Trace",
    scope: b ? `${b.item_number} ${b.item_name}` : "",
    read: () => {
      if (!t || !b) return [];
      const page = document.querySelector("section.batch-trace");
      return [
        {
          title: "Batch",
          columns: ["Item", "Item No", "Batch No", "Supplier's Batch No", "Mfg Date", "Expiry", "Quality"],
          rows: [[b.item_name, b.item_number, b.number, b.supplier_batch_no, showDate(b.mfg_date), showDate(b.expiry_date), b.status_label]],
        },
        {
          title: "Balance",
          columns: [`Received${unit}`, `Sent Out${unit}`, `Came Back${unit}`, `Moved Between Branches${unit}`, `In Stock Now${unit}`, `Held${unit}`],
          rows: [[t.balance.received, t.balance.sent, t.balance.back, t.balance.moved, t.balance.in_stock, t.balance.held].map(qty)],
          right: [true, true, true, true, true, true],
        },
        ...(page ? readTables(page, "Batch Trace") : []),
      ];
    },
  });
  if (!t || !b)
    return (
      <section className="page">
        <PageHeader title="Batch Trace" crumbs={[{ label: "Batches", href: "#/batches" }]} />
        <ErrorNote error={error} />
      </section>
    );
  const close = () =>
    closeThisTab(() => {
      window.location.hash = `#/batches?open=${b.id}`;
    });
  const bal = t.balance;
  const n = (v: string) => `${qty(v)} ${t.unit}`.trim();
  return (
    <section className="page batch-trace">
      <PageHeader
        title={`Batch ${b.number} · ${b.item_name}`}
        crumbs={[
          { label: "Batches", href: "#/batches" },
          { label: "Trace", href: `#/batches/${b.id}/trace` },
        ]}
        sub={[b.item_number, b.supplier_batch_no && `Supplier's Batch ${b.supplier_batch_no}`, b.status_label, !b.is_active && "Disabled"]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <>
            <button type="button" className="link" onClick={close}>
              Close
            </button>
            <button type="button" className="link" onClick={() => openTab(`#/batches?open=${b.id}`)}>
              Open Batch
            </button>
            {printing.buttons}
          </>
        }
      />
      {printing.panel}
      <div className="doc-page">
        <div className="side-main">
          <Fold title="Batch" open summary={b.status_label}>
            <dl className="kv">
              {(
                [
                  ["Item", b.item_name],
                  ["Item No", b.item_number],
                  ["Batch No", b.number],
                  ["Supplier's Batch No", b.supplier_batch_no],
                  ["Mfg Date", showDate(b.mfg_date)],
                  ["Expiry", showDate(b.expiry_date)],
                  ["Quality", b.status_label],
                  ["Notes", b.notes],
                ] as [string, string][]
              )
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
            </dl>
          </Fold>

          <Fold
            title="Where It Came From"
            open
            summary={
              t.came_from.length ? `${t.came_from.length} ${t.came_from.length === 1 ? "entry" : "entries"} · ${n(bal.received)}` : "Nothing received yet"
            }
          >
            {t.came_from.length ? (
              <div className="table-scroll">
                <table className="grid trace-table" data-title="Where It Came From">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Entry</th>
                      <th>From</th>
                      <th>Order</th>
                      <th>Bill</th>
                      {several && <th>Company</th>}
                      <th>Branch</th>
                      <th className="num">Qty{unit}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.came_from.map((r) => (
                      <tr key={`${r.entry.type}-${r.entry.id}`}>
                        <td>{showDate(r.date)}</td>
                        <td>
                          <What row={r} />
                        </td>
                        <td>
                          <Who row={r} />
                        </td>
                        <td>
                          <Refs refs={r.orders} />
                        </td>
                        <td>
                          <Refs refs={r.bills} />
                        </td>
                        {several && <td>{r.company_name}</td>}
                        <td>{r.branch_name}</td>
                        <td className="num">{qty(r.qty)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="small">No entry has brought this batch in yet.</p>
            )}
            <p className="small no-print">
              A batch we make ourselves will show its Production Entry and Manufacturing Order here, with the batches it was made from, once those entries are
              in use.
            </p>
          </Fold>

          <Fold
            title="Where It Is Now"
            open
            summary={
              t.now.length
                ? `${n(bal.in_stock)} in ${t.now.length} ${t.now.length === 1 ? "place" : "places"}${Number(bal.held) ? ` · ${n(bal.held)} held` : ""}`
                : "None in stock"
            }
          >
            {t.now.length ? (
              <div className="table-scroll">
                <table className="grid trace-table" data-title="Where It Is Now">
                  <thead>
                    <tr>
                      {several && <th>Company</th>}
                      <th>Branch</th>
                      <th>Bin</th>
                      <th>Bags</th>
                      <th className="num">Qty{unit}</th>
                      <th>Held For</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.now.map((p) => (
                      <tr key={`${p.location}-${p.owner_name}`}>
                        {several && <td>{p.company_name}</td>}
                        <td>{p.branch_name}</td>
                        <td>
                          <a
                            href={`#/bins/${p.location}`}
                            onClick={(e) => {
                              if (e.ctrlKey || e.metaKey) return;
                              e.preventDefault();
                              openTab(`#/bins/${p.location}`);
                            }}
                          >
                            {p.location_name}
                          </a>
                          {p.owner_name && <span className="small">{p.owner_name}'s goods</span>}
                        </td>
                        <td>{p.bags}</td>
                        <td className="num">{qty(p.qty)}</td>
                        <td>
                          {p.held.map((h) => (
                            <div key={`${h.type}-${h.id}`}>
                              <EntryLink r={h} /> <span className="small-inline">{qty(h.qty ?? "")}</span>
                            </div>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="small">None of this batch is in stock now.</p>
            )}
          </Fold>

          <Fold
            title="Where It Went"
            open
            summary={
              t.went.length
                ? [`${n(bal.sent)} out`, Number(bal.back) && `${n(bal.back)} back`, Number(bal.moved) && `${n(bal.moved)} moved`].filter(Boolean).join(" · ")
                : "Nothing has gone out"
            }
          >
            {t.went.length ? (
              <div className="table-scroll">
                <table className="grid trace-table" data-title="Where It Went">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Entry</th>
                      <th>To</th>
                      <th>Order</th>
                      <th>Invoice</th>
                      {several && <th>Company</th>}
                      <th className="num">Out{unit}</th>
                      <th className="num">Back{unit}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.went.map((r) => (
                      <tr key={`${r.entry.type}-${r.entry.id}`}>
                        <td>{showDate(r.date)}</td>
                        <td>
                          <What row={r} />
                        </td>
                        <td>
                          <Who row={r} />
                        </td>
                        <td>
                          <Refs refs={r.orders} />
                        </td>
                        <td>
                          <Refs refs={r.bills} />
                        </td>
                        {several && <td>{r.company_name}</td>}
                        <td className="num">{r.moved ? "" : qty(r.qty)}</td>
                        <td className="num">{qty(r.back ?? "")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="small">None of this batch has left our stock.</p>
            )}
            <p className="small no-print">
              Once Material Issue and Production Entry are in use, a batch issued to a Manufacturing Order shows here with the batches made from it, each
              opening its own trace.
            </p>
          </Fold>

          <Fold title="Every Move" summary={`${t.moves.length} ${t.moves.length === 1 ? "move" : "moves"}`}>
            <div className="table-scroll">
              <table className="grid trace-table" data-title="Every Move">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Entry</th>
                    {several && <th>Company</th>}
                    <th>Branch</th>
                    <th>Bin</th>
                    <th className="num">Qty{unit}</th>
                    <th className="num">Balance{unit}</th>
                  </tr>
                </thead>
                <tbody>
                  {t.moves.map((m, i) => (
                    <tr key={i}>
                      <td>{showDate(m.date)}</td>
                      <td>
                        <EntryLink r={m.entry} />
                        <span className="small">{m.entry.type_label + (m.reversal ? " · cancelled" : "")}</span>
                      </td>
                      {several && <td>{m.company_name}</td>}
                      <td>{m.branch_name}</td>
                      <td>{m.location_name}</td>
                      <td className="num">{qty(m.qty)}</td>
                      <td className="num">{qty(m.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Fold>
        </div>
        <div className="doc-side">
          <SidePanel title="Balance">
            <SideRows
              rows={[
                ["Received", n(bal.received)],
                ["Sent Out", n(bal.sent)],
                ["Came Back", Number(bal.back) ? n(bal.back) : ""],
                ["Moved Between Branches", Number(bal.moved) ? n(bal.moved) : ""],
                ["In Stock Now", n(bal.in_stock)],
                ["Held", Number(bal.held) ? n(bal.held) : ""],
              ]}
            />
          </SidePanel>
          <SidePanel title="Customers Who Got It">
            {t.customers.length ? (
              <table className="grid trace-table" data-title="Customers Who Got It">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th className="num">Net Qty{unit}</th>
                  </tr>
                </thead>
                <tbody>
                  {t.customers.map((c) => (
                    <tr key={`${c.id ?? c.name}`}>
                      <td>
                        {c.name}
                        {(c.number || c.contact) && <span className="small">{[c.number, c.contact].filter(Boolean).join(" · ")}</span>}
                      </td>
                      <td className="num">{qty(c.qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="small">No customer has had this batch.</p>
            )}
            <p className="small no-print">The recall list: who got this batch, less what came back, with their main contact.</p>
          </SidePanel>
        </div>
      </div>
    </section>
  );
}
