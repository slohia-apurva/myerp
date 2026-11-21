import { useState } from "react";
import { type SignedIn } from "./api";
import { PageHeader, Section } from "./Brand";
import { ImportForm } from "./Exchange";

/** One import from another program's own export file. */
type Tool = {
  key: string;
  what: string;
  /** The MyERP master the file goes into (core/exchange.py key). */
  master: string;
  noun: string;
  source: string;
  file: string;
  help: string;
};

const ERPNEXT: Tool[] = [
  {
    key: "erpnext-items",
    what: "Items",
    master: "items",
    noun: "items",
    source: "erpnext",
    file: 'Item list › Menu › Export: "Select All" and the child tables "UOMs" and "Taxes", Excel',
    help:
      "Upload ERPNext's Item export as it is. Each item keeps its ERPNext code as its item number, and new items " +
      "made in MyERP carry on after the highest. Item groups and brands must already be in MyERP (matched by name); " +
      "HSN codes are checked against the HSN list. Description and safety stock, lead time and minimum order are left out.",
  },
];

/**
 * Admin › Migration Tools (Sidharth, 2026-11-21): imports from the program a
 * customer is leaving, kept apart from the everyday screens. Shown while the
 * customer's "Migration Tools" switch is on (Central › Customers); platform
 * admins untick it after the cutover. More tools join the list as they are built.
 */
export function MigrationToolsPage(_props: { session: SignedIn }) {
  const [open, setOpen] = useState<Tool | null>(null);
  const [done, setDone] = useState("");
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
            {ERPNEXT.map((t) => (
              <tr key={t.key}>
                <td>{t.what}</td>
                <td>{t.file}</td>
                <td>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(t);
                      setDone("");
                    }}
                  >
                    Import {t.what}…
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small">
          More tools (customers and suppliers, ledgers with opening balances, opening stock) join this list as they are
          built.
        </p>
      </Section>
      {done && <p className="small">{done}</p>}
      {open && (
        <ImportForm
          key={open.key}
          master={open.master}
          noun={open.noun}
          source={open.source}
          title={`Import ${open.what} From ERPNext`}
          help={open.help}
          onImported={() => setDone(`${open.what} imported. Open Masters › ${open.what} to see them.`)}
          onClose={() => setOpen(null)}
        />
      )}
    </section>
  );
}
