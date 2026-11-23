import { FormEvent, useState } from "react";
import { type SignedIn, upload } from "./api";
import { PageHeader, Section } from "./Brand";

/**
 * Admin › Migration Tools (Sidharth, 2026-11-21): imports from the program a
 * customer is leaving, kept apart from the everyday screens. Shown while the
 * customer's "Migration Tools" switch is on (Central › Customers); platform
 * admins untick it after the cutover. More tools join the list as they are built.
 */
export function MigrationToolsPage(_props: { session: SignedIn }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="page">
      <PageHeader
        title="Migration Tools"
        sub="Bring your masters across from the program you are leaving. Every file is checked first, row by row, and nothing is saved until every row is right."
      />
      <Section title="From ERPNext">
        <table>
          <thead>
            <tr>
              <th>What</th>
              <th>File From ERPNext</th>
              <th className="no-print" />
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Items</td>
              <td>Item list › Menu › Export: "Select All" and the child tables "UOMs" and "Taxes", Excel</td>
              <td>
                <button type="button" onClick={() => setOpen(true)}>
                  Import Items…
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p className="small">
          More tools (customers and suppliers, ledgers with opening balances, opening stock) join this list as they are
          built.
        </p>
      </Section>
      {open && <ErpnextItems onClose={() => setOpen(false)} />}
    </section>
  );
}

type Part = {
  rows: number;
  new: number;
  changed: number;
  same: number;
  errors: { sheet: string; row: number; messages: string[] }[];
  saved: boolean;
  notes?: string[];
  part: number;
  parts: number;
  items: number;
};

type Totals = { items: number; new: number; changed: number; same: number; errors: Part["errors"]; notes: string[] };

function plural(n: number, word: string) {
  return `${n.toLocaleString("en-IN")} ${word}${n === 1 ? "" : "s"}`;
}

/** ERPNext's Item export, read as it is, with a name map for groups and units,
 * checked and then imported a part at a time (the server reads 500 items per call). */
function ErpnextItems(props: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [nameMap, setNameMap] = useState<File | null>(null);
  const [skipDisabled, setSkipDisabled] = useState(true);
  const [deliveryHsn, setDeliveryHsn] = useState("");
  const [checked, setChecked] = useState<Totals | null>(null);
  const [imported, setImported] = useState<Totals | null>(null);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  const changed = () => {
    setChecked(null);
    setImported(null);
  };

  const run = async (commit: boolean) => {
    if (!file) return;
    setError("");
    const totals: Totals = { items: 0, new: 0, changed: 0, same: 0, errors: [], notes: [] };
    let parts = 1;
    try {
      for (let part = 0; part < parts; part++) {
        setProgress(`${commit ? "Importing" : "Checking"} part ${part + 1}${parts > 1 ? ` of ${parts}` : ""}…`);
        const form = new FormData();
        form.append("file", file);
        if (nameMap) form.append("map", nameMap);
        form.append("source", "erpnext");
        form.append("commit", commit ? "1" : "0");
        form.append("part", String(part));
        if (skipDisabled) form.append("skip_disabled", "1");
        if (deliveryHsn.trim()) form.append("delivery_hsn", deliveryHsn.trim());
        const out = await upload<Part>("v1/exchange/items/import/", form);
        parts = out.parts;
        totals.items = out.items;
        totals.new += out.new;
        totals.changed += out.changed;
        totals.same += out.same;
        totals.errors.push(...out.errors);
        for (const n of out.notes ?? []) if (!totals.notes.includes(n)) totals.notes.push(n);
        if (commit && !out.saved) break; // a part that no longer passes: stop here, say so
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setProgress("");
    }
    if (commit) setImported(totals);
    else setChecked(totals);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    run(false);
  };

  const ready = checked && checked.errors.length === 0 && !imported;
  const shown = imported ?? checked;
  const summary = shown && (
    <p>
      {plural(shown.items, "item")}: {shown.new.toLocaleString("en-IN")} new, {shown.changed.toLocaleString("en-IN")}{" "}
      changed, {shown.same.toLocaleString("en-IN")} with no change
      {shown.errors.length > 0 && `, ${plural(new Set(shown.errors.map((e) => e.row)).size, "row")} with problems`}.
    </p>
  );

  return (
    <form className="card" onSubmit={submit}>
      <h4>Import Items From ERPNext</h4>
      <Section title="Files">
        <p className="small">
          Upload ERPNext's Item export as it is. Each item keeps its ERPNext code as its item number, and new items made
          in MyERP carry on after the highest. Item groups, brands and units must already be in MyERP: names that differ
          go in the name map. Description and safety stock, lead time and minimum order are left out.
        </p>
        <label>
          ERPNext Item Export
          <input
            type="file"
            required
            accept=".xlsx,.csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              changed();
            }}
          />
        </label>
        <label>
          Name Map (optional)
          <input
            type="file"
            accept=".xlsx"
            onChange={(e) => {
              setNameMap(e.target.files?.[0] ?? null);
              changed();
            }}
          />
        </label>
        <p className="small">
          An Excel file with a sheet "Item groups" and a sheet "Units": the ERPNext name in the first column and the
          MyERP name in the column headed "MyERP …". Names not in the map are matched as they are. Nothing is created:
          every group and unit must already be in MyERP.
        </p>
      </Section>
      <Section title="Choices">
        <label className="check">
          <input
            type="checkbox"
            checked={skipDisabled}
            onChange={(e) => {
              setSkipDisabled(e.target.checked);
              changed();
            }}
          />
          Leave Out Disabled Items
        </label>
        <label>
          Delivery HSN For Job-Work Items
          <input
            value={deliveryHsn}
            inputMode="numeric"
            placeholder="e.g. 09024040"
            onChange={(e) => {
              setDeliveryHsn(e.target.value.replace(/\D/g, ""));
              changed();
            }}
          />
        </label>
        <p className="small">
          Given to every item with a service code (starting 99) that keeps stock. It must be in the HSN list.
        </p>
      </Section>
      {shown && (
        <Section title={imported ? "Imported" : checked!.errors.length ? "Fix these rows, then check again" : "Ready to import"}>
          {summary}
          {shown.errors.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Sheet</th>
                  <th>Row</th>
                  <th>Problem</th>
                </tr>
              </thead>
              <tbody>
                {shown.errors.slice(0, 500).map((e) => (
                  <tr key={`${e.sheet}-${e.row}`}>
                    <td>{e.sheet}</td>
                    <td>{e.row}</td>
                    <td>
                      {e.messages.map((m) => (
                        <div key={m}>{m}</div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {shown.errors.length > 500 && <p className="small">The first 500 problems are shown.</p>}
          {ready && <p className="small">Nothing is saved yet. Press "Import" to save the items, a part at a time.</p>}
          {shown.notes.map((n) => (
            <p key={n} className="small warn">
              ⚠ {n}
            </p>
          ))}
        </Section>
      )}
      {progress && <p className="small">{progress}</p>}
      {error && <p className="error">{error}</p>}
      <div className="buttons">
        {ready ? (
          <button type="button" disabled={!!progress} onClick={() => run(true)}>
            Import
          </button>
        ) : (
          !imported && <button disabled={!!progress || !file}>Check file</button>
        )}
        <button type="button" className="link" onClick={props.onClose}>
          {imported ? "Close" : "Cancel"}
        </button>
      </div>
    </form>
  );
}
