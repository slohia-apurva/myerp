import { useEffect, useState } from "react";
import { api } from "./api";
import { PageHeader, Section } from "./Brand";
import { usePrintMenu } from "./Exchange";

type Info = {
  tables: { key: string; label: string; about: string; count: number; open: string }[];
  tenants: { slug: string; name: string; status: string; created: string }[];
};

/** Central: for MyERP platform admins. The tables kept once for every customer, and the customers. */
export function CentralPage() {
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState("");
  const printing = usePrintMenu({ title: "Central tables" });
  useEffect(() => {
    api<Info>("v1/central/").then(setInfo, (e) => setError(String(e.message ?? e)));
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!info) return <p>Loading…</p>;
  return (
    <section className="page">
      <PageHeader
        title="Central tables"
        sub="Kept once by MyERP for every customer. Customers can read these lists but not change them."
        actions={printing.buttons}
      />
      {printing.panel}
      <Section title="Central tables">
        <table>
          <thead>
            <tr>
              <th>Table</th>
              <th>What it is for</th>
              <th>Rows</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {info.tables.map((t) => (
              <tr key={t.key}>
                <td>{t.label}</td>
                <td>{t.about}</td>
                <td>{t.count}</td>
                <td>{t.open && <a href={t.open}>Open</a>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      <Section title="Customers">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Short name</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {info.tenants.map((t) => (
              <tr key={t.slug}>
                <td>{t.name}</td>
                <td>{t.slug}</td>
                <td>{t.status}</td>
                <td>{t.created}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </section>
  );
}
