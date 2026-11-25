import { useEffect, useState } from "react";
import { api, type SignedIn } from "./api";
import { PageHeader } from "./Brand";
import type { AdditionRequest } from "./RequestAddition";
import { money, renewalNote, type Company } from "./Companies";

/** What the dashboard reads of a company and its ledgers. */
type Overview = {
  company: Company;
  branches: { id: number; is_active: boolean }[];
  certificates: { id: number; kind_label: string; name: string; valid_until: string | null }[];
  opening: { dr: string; cr: string; difference: string };
};
type PartyRenewal = {
  id: number;
  party: string;
  kind_label: string;
  name: string;
  valid_until: string;
};
type LedgerRow = { id: number; nature: string; party: { id?: number } | null; is_active: boolean };

/** The first screen after signing in: the company being worked in, at a glance. */
export function Dashboard({ session, company }: { session: SignedIn; company?: Company }) {
  const canSeeMasters = session.permissions.includes("masters.view");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [ledgers, setLedgers] = useState<LedgerRow[]>([]);
  const [partyRenewals, setPartyRenewals] = useState<PartyRenewal[]>([]);
  const [noBrand, setNoBrand] = useState(0);
  const [decided, setDecided] = useState<AdditionRequest[]>([]);
  const loadDecided = () =>
    api<AdditionRequest[]>("v1/central-requests/").then(
      (rows) => setDecided(rows.filter((r) => r.status !== "open" && !r.seen)),
      () => setDecided([]),
    );
  useEffect(() => {
    if (canSeeMasters) loadDecided();
  }, [canSeeMasters]);
  const id = company?.id;
  useEffect(() => {
    if (!id) return;
    setOverview(null);
    api<Overview>(`v1/companies/${id}/`).then(setOverview);
    api<LedgerRow[]>(`v1/companies/${id}/ledgers/`).then(setLedgers);
    api<PartyRenewal[]>("v1/party-documents/renewals/").then(setPartyRenewals, () => setPartyRenewals([]));
  }, [id]);
  useEffect(() => {
    // Items from before the brand became required: counted on the server, not by
    // reading the whole item list (16 MB with 12,457 items, 2026-11-25).
    api<{ without_brand: number }>("v1/items/counts/").then(
      (counts) => setNoBrand(counts.without_brand),
      () => setNoBrand(0),
    );
  }, []);

  const hello = `Welcome, ${session.user.name}`;
  if (!canSeeMasters || !company)
    return (
      <section className="page">
        <PageHeader title={hello} />
        {session.permissions.length === 0 ? (
          <p className="small">You have no role yet. Ask your MyERP admin to give you one.</p>
        ) : (
          <p className="small">Nothing to show here yet. Your screens are in the top menu.</p>
        )}
      </section>
    );

  const customers = ledgers.filter((l) => l.party && l.nature === "asset").length;
  const suppliers = ledgers.filter((l) => l.party && l.nature === "liability").length;
  const diff = overview ? Number(overview.opening.difference) : 0;
  const renewals = (overview?.certificates ?? [])
    .filter((x) => x.valid_until)
    .map((x) => ({ x, note: renewalNote(x.valid_until) }))
    .filter(({ note }) => note.cls === "warn" || note.cls === "error")
    .sort((a, b) => (a.x.valid_until! < b.x.valid_until! ? -1 : 1));
  const partyDue = partyRenewals.map((x) => ({ x, note: renewalNote(x.valid_until) }));
  const base = `#/companies/${company.id}`;

  return (
    <section className="page">
      <PageHeader title={hello} sub={company.name} />
      <div className="main-col">
        <div className="stats">
          <div className="stat">
            <span className="stat-label">Ledgers</span>
            <span className="stat-value">{ledgers.length}</span>
            <a className="stat-note" href={`${base}/ledgers`}>
              Open ledgers
            </a>
          </div>
          <div className="stat">
            <span className="stat-label">Customers</span>
            <span className="stat-value">{customers}</span>
            <span className="stat-note">Under Sundry Debtors</span>
          </div>
          <div className="stat">
            <span className="stat-label">Suppliers</span>
            <span className="stat-value">{suppliers}</span>
            <span className="stat-note">Under Sundry Creditors</span>
          </div>
          <div className="stat">
            <span className="stat-label">Branches</span>
            <span className="stat-value">{overview ? overview.branches.filter((b) => b.is_active).length : "…"}</span>
            <a className="stat-note" href={`${base}/branches`}>
              Open branches
            </a>
          </div>
        </div>

        <h3>Needs your attention</h3>
        {overview && diff === 0 && renewals.length === 0 && partyDue.length === 0 && noBrand === 0 && decided.length === 0 && <p className="small">Nothing needs attention.</p>}
        <ul className="attention">
          {diff !== 0 && (
            <li>
              <span className="error">Opening balances do not balance:</span> {money(Math.abs(diff))} {diff > 0 ? "Dr" : "Cr"}{" "}
              more. <a href={`${base}/ledgers`}>Fix in ledgers</a>
            </li>
          )}
          {decided.map((r) => (
            <li key={r.id}>
              <span className={r.status === "added" ? "" : "warn"}>
                {r.status === "added"
                  ? `${r.kind_label} ${r.entry} was added to the list.`
                  : `${r.kind_label} ${r.entry} was not added (the MyERP team says it is not needed).`}
              </span>{" "}
              <button
                type="button"
                className="link"
                onClick={() => api(`v1/central-requests/${r.id}/seen/`, {}).then(loadDecided)}
              >
                OK
              </button>
            </li>
          ))}
          {noBrand > 0 && (
            <li>
              <span className="warn">
                {noBrand} item{noBrand === 1 ? " has" : "s have"} no brand.
              </span>{" "}
              A brand is now required: <a href="#/items">pick one in Items</a>.
            </li>
          )}
          {renewals.map(({ x, note }) => (
            <li key={x.id}>
              <span className={note.cls}>{x.kind_label}</span>
              {x.name ? ` (${x.name})` : ""}: {note.text}. <a href={`${base}/certificates`}>Licences and certificates</a>
            </li>
          ))}
          {partyDue.map(({ x, note }) => (
            <li key={`party-${x.id}`}>
              <span className={note.cls}>{x.kind_label}</span>
              {x.name ? ` (${x.name})` : ""} of {x.party}: {note.text}. <a href={`${base}/ledgers`}>Ledgers</a>
            </li>
          ))}
        </ul>

        <h3>Go to</h3>
        <div className="buttons">
          <a className="button" href={`${base}/ledgers`}>
            Ledgers
          </a>
          <a className="button" href={`${base}/groups`}>
            Ledger groups
          </a>
          <a className="button" href="#/credit-terms">
            Credit terms
          </a>
          <a className="button" href="#/companies">
            All companies
          </a>
        </div>
      </div>
    </section>
  );
}
