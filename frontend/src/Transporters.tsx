import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, type SignedIn } from "./api";
import { ChangeLog } from "./Audit";
import { PageHeader, Section } from "./Brand";
import { Combobox } from "./Combobox";
import { contactOf, ContactFields } from "./Companies";
import { announceCreated, announceSaved, closeThisTab, useCreated, useNewName } from "./Create";
import { useOpenParam } from "./ErrorNote";
import { useExchange } from "./Exchange";
import { InUseNote, isLocked, Locked, type LockInfo } from "./Lock";
import { FormPage, hashParam, openTab, SidePanel, SideRows } from "./Master";
import { ActionCells, ActionHeads } from "./RowActions";
import { type Carrier, type CourierAccount, NoSales, SERVICES, useCarriers, useCompany } from "./Shipments";
import { ColumnSearch } from "./ColumnSearch";
import { useColumns } from "./Columns";
import { Pager, ShowInactive, useShowInactive, type Paged } from "./Pager";
import { useOnReturn } from "./Refresh";
import { useKept } from "./Keep";

type Account = CourierAccount & { lock?: LockInfo; preferred_by?: number };

/** `?form=new`, `?form=<id>` or `?form=copy-<id>`: this tab was opened to add, change,
 * view or duplicate one transporter (Sidharth, 2026-11-13). */
const formParam = () => hashParam("form");

const pageHash = (company: number, query = "") => `#/companies/${company}/couriers${query}`;

/** Masters > Transporters: the company's couriers and transporters. The details of the
 * clicked row are on the right; Add, Edit and Duplicate open in a new tab. */
export function TransportersPage({ companyId, session }: { companyId: number; session: SignedIn }) {
  const canEdit = session.permissions.includes("masters.edit");
  const company = useCompany(companyId);
  const form = formParam();
  if (company && !company.modules.includes("sales")) return <NoSales company={company} />;
  if (form) return <AccountFormTab companyId={companyId} form={form} canEdit={canEdit} />;
  return <AccountList companyId={companyId} canEdit={canEdit} session={session} companyName={company?.name ?? ""} />;
}

function AccountList(props: { companyId: number; canEdit: boolean; session: SignedIn; companyName: string }) {
  const { companyId, canEdit } = props;
  // One page of 25 at a time, found on the server (Sidharth, 2026-11-24: large lists).
  const [data, setData] = useState<Paged<Account> | null>(null);
  const [page, setPage] = useKept("Transporters.page", 1);
  const [searches, setSearches] = useKept<Record<string, string>>("Transporters.searches", {});
  const [typed, setTyped] = useKept<Record<string, string>>("Transporters.typed", {});
  const [inactive, setInactive] = useShowInactive();
  const [selectedId, setSelected] = useKept<number | null>("Transporters.selectedId", null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (JSON.stringify(typed) === JSON.stringify(searches)) return;
    const wait = setTimeout(() => {
      setSearches(typed);
      setPage(1);
      setSelected(null);
    }, 300);
    return () => clearTimeout(wait);
  }, [typed, searches]);
  const turnPage = (p: number) => {
    setPage(p);
    setSelected(null);
  };
  const columns = useColumns<Account>("courier-accounts", [
    {
      key: "name",
      label: "Transporter",
      fixed: true,
      search: "name",
      cell: (a) => (
        <>
          {a.name}
          {!a.is_active && <span className="pill">Disabled</span>}
        </>
      ),
    },
    { key: "gstin", label: "GSTIN", standard: true, search: "gstin", cell: (a) => a.gstin || <span className="small">Missing: needed for e-way bills</span> },
    { key: "courier", label: "Courier in MyERP's list", standard: true, search: "courier", sort: false, cell: (a) => a.carrier_name },
    { key: "service", label: "Service", standard: true, search: "service", cell: (a) => a.service_label },
    { key: "code", label: "Account Code", standard: true, search: "code", cell: (a) => a.account_code },
    { key: "city", label: "City", search: "city", cell: (a) => a.city },
    { key: "phone", label: "Phone", search: "phone", cell: (a) => a.phone },
    { key: "contact", label: "Contact Person", search: "contact", cell: (a) => a.contact_person },
    { key: "email", label: "Email", search: "email", cell: (a) => a.email },
    { key: "notes", label: "Notes", search: "notes", cell: (a) => a.notes },
  ]);
  const sortKey = columns.sort;
  const reload = useCallback(() => {
    const q = new URLSearchParams({ page: String(page) });
    Object.entries(searches).forEach(([k, v]) => {
      if (v.trim()) q.set(k, v.trim());
    });
    if (inactive) q.set("inactive", "1");
    if (sortKey) q.set("sort", sortKey);
    return api<Paged<Account>>(`v1/companies/${companyId}/courier-accounts/?${q}`)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [companyId, page, searches, inactive, sortKey]);
  useEffect(() => {
    reload();
  }, [reload]);
  useOnReturn(reload);
  const shown = columns.shown;
  const onSearch = useCallback(
    (values: string[]) => {
      const next: Record<string, string> = {};
      shown.forEach((c, i) => {
        if (c.search && values[i]?.trim()) next[c.search] = values[i];
      });
      setTyped((was) => (JSON.stringify(was) === JSON.stringify(next) ? was : next));
    },
    [shown],
  );
  const accounts = useMemo(() => data?.results ?? [], [data]);
  useCreated("courier_account_saved", (c) => {
    reload();
    setSelected(c.id);
  });
  const startName = useNewName();
  useEffect(() => {
    // Opened by "Create …" in a dropdown: go straight to the Add page.
    if (startName && canEdit) window.location.hash = pageHash(companyId, `?form=new&new=${encodeURIComponent(startName)}`);
  }, [startName, canEdit, companyId]);
  const [openId, opened] = useOpenParam();
  useEffect(() => {
    // Opened from a link (for example a duplicate-name refusal): show that one, on this page or not.
    if (openId) {
      setSelected(openId);
      opened();
    }
  }, [openId, opened]);
  const io = useExchange({
    master: "courier-accounts",
    noun: "transporters",
    session: props.session,
    company: companyId,
    onImported: () => void reload(),
    printScreen: { title: "Transporters", scope: props.companyName },
    extra: [columns.item],
  });
  // The list's rows leave out the "in use" checks and the "Preferred By" count
  // (a dozen queries a row), so the clicked row is asked for on its own.
  const current = selectedId ?? accounts[0]?.id ?? null;
  const [full, setFull] = useState<Account | null>(null);
  useEffect(() => {
    if (current === null) return setFull(null);
    let live = true;
    api<Account>(`v1/courier-accounts/${current}/`).then(
      (one) => live && setFull(one),
      () => live && setFull(null),
    );
    return () => {
      live = false;
    };
  }, [current, data]);
  const row = accounts.find((a) => a.id === current) ?? null;
  // The row's own fields show at once; "Preferred By" and "In Use" join them.
  const selected = full?.id === current ? full : row;
  const edit = (id: number | string) => openTab(pageHash(companyId, `?form=${id}`));
  const filtered = Object.values(searches).some((v) => v.trim());
  const count = data?.count ?? 0;
  return (
    <section className="page">
      <PageHeader
        title="Transporters"
        crumbs={[{ label: "Shipments", href: `#/companies/${companyId}/shipments` }]}
        sub={`${data === null ? "" : `${count.toLocaleString("en-IN")}${inactive ? "" : " active"} ${count === 1 ? "transporter" : "transporters"}${filtered ? " match" : ""} · `}${props.companyName}: the couriers and transporters you send goods with, such as a B2C and a B2B account with the same courier.`}
        actions={
          <>
            {io.buttons}
            {canEdit && <button onClick={() => edit("new")}>Add transporter</button>}
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {io.panel}
      {columns.panel}
      <div className="side-layout">
        <div className="side-main">
          {data !== null && count === 0 && !filtered && !inactive ? (
            <p className="small">No transporters yet. Add one for each you ship with, for example "Delhivery B2C".</p>
          ) : (
            <>
              <table className="pick">
                <thead>
                  <tr>
                    {shown.map((c) => (
                      <th key={c.key} className={c.num ? "num" : undefined} data-no-search={c.search ? undefined : ""}>
                        {columns.heading(c)}
                      </th>
                    ))}
                    <ActionHeads />
                  </tr>
                  <ColumnSearch key={shown.map((c) => c.key).join(",")} onSearch={onSearch} />
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr
                      key={a.id}
                      className={`${a.is_active ? "" : "off"}${current === a.id ? " selected" : ""}`}
                      onClick={() => setSelected(a.id)}
                      onDoubleClick={() => edit(a.id)}
                    >
                      {shown.map((c) => (
                        <td key={c.key} className={c.num ? "num" : undefined}>
                          {c.cell(a)}
                        </td>
                      ))}
                      <ActionCells canEdit={canEdit} onOpen={() => edit(a.id)} onDuplicate={() => edit(`copy-${a.id}`)} />
                    </tr>
                  ))}
                  {data !== null && accounts.length === 0 && (
                    <tr>
                      <td colSpan={shown.length + 2} className="small">
                        No transporters match.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <Pager data={data} noun="transporters" onPage={turnPage}>
                <ShowInactive
                  noun="Transporters"
                  on={inactive}
                  onChange={(v) => {
                    setInactive(v);
                    turnPage(1);
                  }}
                />
              </Pager>
            </>
          )}
        </div>
        <div className="side-col">
          <SidePanel title="Transporter Details">
            {selected ? (
              <SideRows
                rows={[
                  ["Name", selected.name],
                  ["GSTIN", selected.gstin],
                  ["Courier", selected.carrier_name || "Not in MyERP's list"],
                  ["Service", selected.service_label],
                  ["Account Code", selected.account_code],
                  ["Contact Person", selected.contact_person],
                  ["Phone", selected.phone],
                  ["Email", selected.email],
                  ["Preferred By", selected.preferred_by ? `${selected.preferred_by} customer${selected.preferred_by === 1 ? "" : "s"}` : ""],
                  ["In Use", selected.lock?.in_use.join(", ") ?? ""],
                  ["Disabled", selected.is_active ? "No" : "Yes"],
                  ["Notes", selected.notes],
                ]}
              />
            ) : (
              <p className="small">Click a row to see its details here.</p>
            )}
          </SidePanel>
          <SidePanel title="Activity">
            <ChangeLog type="courier_account" id={selected?.id} stamp={JSON.stringify(selected ?? count)} />
          </SidePanel>
        </div>
      </div>
    </section>
  );
}

/** The form of one transporter, alone in its own tab: Save and Cancel close the tab. */
function AccountFormTab(props: { companyId: number; form: string; canEdit: boolean }) {
  const copy = props.form.startsWith("copy-");
  const key = Number(props.form.replace("copy-", ""));
  const carriers = useCarriers();
  const [loaded, setLoaded] = useState(props.form === "new");
  // One transporter, not the whole list: the form needs its "in use" checks.
  const [target, setTarget] = useState<Account | null>(null);
  useEffect(() => {
    if (props.form === "new") return;
    api<Account>(`v1/courier-accounts/${key}/`).then(
      (one) => {
        setTarget(one);
        setLoaded(true);
      },
      () => setLoaded(true),
    );
  }, [props.form, key]);
  const startName = useNewName();
  const toList = () => {
    window.location.hash = pageHash(props.companyId);
  };
  const finish = (saved?: { id: number; name: string }) => {
    if (saved) announceSaved("courier_account_saved", saved);
    closeThisTab(toList);
  };
  const editing = props.form !== "new" && !copy;
  const readOnly = !props.canEdit;
  const title =
    props.form === "new" ? "Add transporter" : copy ? "Duplicate transporter" : readOnly ? "View transporter" : "Edit transporter";
  if (!loaded)
    return (
      <section className="page">
        <PageHeader title={title} />
      </section>
    );
  if (props.form !== "new" && target === null)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">That transporter was not found.</p>
      </section>
    );
  if (readOnly && !editing)
    return (
      <section className="page">
        <PageHeader title={title} />
        <p className="error">You may only view transporters.</p>
      </section>
    );
  return (
    <AccountForm
      title={title}
      companyId={props.companyId}
      carriers={carriers}
      account={editing ? target : null}
      copyOf={copy ? target : null}
      startName={props.form === "new" ? (startName ?? undefined) : undefined}
      readOnly={readOnly}
      onDone={finish}
      onCancel={() => finish()}
    />
  );
}

function AccountForm(props: {
  title: string;
  companyId: number;
  carriers: Carrier[];
  account: Account | null;
  copyOf?: Account | null;
  startName?: string;
  readOnly?: boolean;
  onDone: (saved?: { id: number; name: string }) => void;
  onCancel: () => void;
}) {
  const a = props.account;
  const from = a ?? props.copyOf; // a duplicate starts as a copy but is saved as a new record
  const [carrierId, setCarrierId] = useState(from?.carrier_id ? String(from.carrier_id) : "");
  const [gstin, setGstin] = useState(props.copyOf ? "" : (a?.gstin ?? ""));
  const [contact, setContact] = useState(contactOf(from));
  const [name, setName] = useState(props.startName ?? (props.copyOf ? `${props.copyOf.name} (copy)` : (a?.name ?? "")));
  const [service, setService] = useState(from?.service ?? "b2c");
  const [code, setCode] = useState(props.copyOf ? "" : (a?.account_code ?? ""));
  const [notes, setNotes] = useState(from?.notes ?? "");
  const [forCentral, setForCentral] = useState("");
  // The company's own API login: plain values come back to edit; a secret is
  // only ever "saved", and is sent again only when someone presses Change.
  const [creds, setCreds] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      (props.copyOf ? [] : (a?.credential_fields ?? [])).filter((f) => !f.secret).map((f) => [f.key, f.value]),
    ),
  );
  const [changing, setChanging] = useState<string[]>([]);
  const [disabled, setDisabled] = useState(a ? !a.is_active : false);
  const [error, setError] = useState<unknown>("");
  const [busy, setBusy] = useState(false);
  const locked = (field: string) => isLocked(a?.lock, field);
  const pickedCarrier = props.carriers.find((c) => String(c.id) === carrierId);
  const credFields = pickedCarrier?.credential_fields ?? [];
  const savedSecret = (key: string) =>
    !props.copyOf && Number(carrierId) === a?.carrier_id && !!a?.credential_fields?.find((f) => f.key === key)?.saved;

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const body = {
      carrier_id: carrierId ? Number(carrierId) : null,
      name,
      gstin,
      service,
      account_code: code,
      notes,
      ...(carrierId ? {} : { note_for_central: forCentral }),
      ...(credFields.length
        ? {
            credentials: Object.fromEntries(
              credFields
                .filter((f) => !f.secret || changing.includes(f.key) || !savedSecret(f.key))
                .map((f) => [f.key, creds[f.key] ?? ""]),
            ),
          }
        : {}),
      ...contact,
    };
    try {
      if (a) {
        await api(`v1/courier-accounts/${a.id}/`, { ...body, is_active: !disabled }, "PATCH");
        props.onDone({ id: a.id, name });
      } else {
        const made = await api<{ id: number; name: string }>(`v1/companies/${props.companyId}/courier-accounts/`, body);
        announceCreated("courier_account", made);
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
      sub={a ? a.name : undefined}
      formId="transporter-form"
      onSubmit={save}
      onCancel={props.onCancel}
      busy={busy}
      error={error}
      readOnly={props.readOnly}
      disabled={a ? { value: disabled, set: setDisabled } : undefined}
      tips={
        <p className="small">
          API credentials appear when the courier in MyERP's list supports them. Secrets are kept locked and never shown again.
        </p>
      }
      activity={a ? <ChangeLog type="courier_account" id={a.id} stamp={JSON.stringify(a)} /> : undefined}
    >
      <InUseNote lock={a?.lock} />
      <Section title="Transporter">
        <p className="small">
          <span className="req-star">*</span> Required
        </p>
        <div className="item-fields">
          <label>
            <span className="req">Name</span>
            <input
              required
              autoFocus
              value={name}
              placeholder="e.g. Delhivery B2B or Shree Roadlines"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            <span className="req">GSTIN (the Transporter ID on an e-way bill)</span>
            <input
              required
              value={gstin}
              maxLength={15}
              placeholder="15 characters"
              onChange={(e) => setGstin(e.target.value.toUpperCase())}
            />
          </label>
          <label>
            Courier in MyERP's List
            <Locked on={locked("carrier_id")}>
              <Combobox
                value={carrierId}
                onChange={(v) => {
                  setCarrierId(v);
                  const c = props.carriers.find((x) => String(x.id) === v);
                  if (c && !name) setName(c.name);
                  if (c?.kind === "aggregator") setService("aggregator");
                }}
                empty="Not in the list"
                options={props.carriers
                  .filter((c) => c.is_active || String(c.id) === carrierId)
                  .map((c) => ({ value: String(c.id), label: c.name, hint: c.kind_label }))}
              />
            </Locked>
            <span className="small">Leave empty if it is not there.</span>
          </label>
          <label>
            Service
            <Locked on={locked("service")}>
              <Combobox
                value={service}
                onChange={setService}
                options={SERVICES.map(([value, label]) => ({ value, label }))}
              />
            </Locked>
          </label>
        </div>
        {!carrierId && (
          <label>
            Note for the MyERP Team
            <textarea
              rows={2}
              value={forCentral}
              placeholder="Anything that helps us add this transporter to the list, such as its website or the routes you use"
              onChange={(e) => setForCentral(e.target.value)}
            />
            <span className="small">The MyERP team sees this transporter and can add it to the list for everyone.</span>
          </label>
        )}
      </Section>
      <Section title="Contact">
        <ContactFields value={contact} onChange={setContact} noAddress />
      </Section>
      {credFields.length > 0 && (
        <Section title="API Credentials">
          <p className="small">
            Your own login with {pickedCarrier?.name}. It is kept for this transporter only; a secret is stored
            locked and never shown again.
          </p>
          <div className="item-fields">
            {credFields.map((f) => (
              <label key={f.key}>
                {f.label}
                {f.secret && savedSecret(f.key) && !changing.includes(f.key) ? (
                  <span className="saved-secret">
                    Saved · ●●●●●●●●{" "}
                    <button type="button" className="link" onClick={() => setChanging([...changing, f.key])}>
                      Change
                    </button>
                  </span>
                ) : (
                  <input
                    type={f.secret ? "password" : "text"}
                    autoComplete="off"
                    value={creds[f.key] ?? ""}
                    onChange={(e) => setCreds({ ...creds, [f.key]: e.target.value })}
                  />
                )}
              </label>
            ))}
          </div>
        </Section>
      )}
      <Section title="Booking and Tracking">
        <div className="item-fields">
          <label>
            Account or Customer Code
            <input
              value={code}
              placeholder="The code the transporter gave you"
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
      </Section>
    </FormPage>
  );
}
