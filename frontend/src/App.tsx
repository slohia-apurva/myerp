import { useEffect, useState } from "react";

type WhoAmI = { tenant: string; name: string; companies: string[] };

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: WhoAmI }
  | { kind: "error"; message: string };

// Phase 0 placeholder: shows which tenant this subdomain reaches.
export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    fetch("/api/whoami/")
      .then(async (res) => {
        if (!res.ok) throw new Error(res.status === 404 ? "Unknown tenant" : `HTTP ${res.status}`);
        setState({ kind: "ready", data: (await res.json()) as WhoAmI });
      })
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: 24 }}>
      <h1>MyERP</h1>
      {state.kind === "loading" && <p>Loading…</p>}
      {state.kind === "error" && <p>Could not load: {state.message}</p>}
      {state.kind === "ready" && (
        <>
          <p>
            Tenant: <strong>{state.data.name}</strong> ({state.data.tenant})
          </p>
          <ul>
            {state.data.companies.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
