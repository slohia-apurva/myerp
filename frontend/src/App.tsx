import { useCallback, useEffect, useState } from "react";
import { api, ApiError, Session } from "./api";
import { SignIn } from "./Login";
import "./app.css";

type WhoAmI = { tenant: string; name: string; companies: string[] };

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Session>("auth/session/")
      .then(setSession)
      .catch((err: ApiError) => setError(err.status === 404 ? "Unknown company group address." : err.message));
  }, []);
  const onChange = useCallback((s: Session) => setSession(s), []);

  return (
    <main>
      <h1>MyERP</h1>
      {error && <p className="error">{error}</p>}
      {session === null ? (
        !error && <p>Loading…</p>
      ) : session.signed_in ? (
        <Home session={session} onSignOut={onChange} />
      ) : (
        <SignIn clientId={session.google_client_id} onChange={onChange} />
      )}
    </main>
  );
}

function Home({
  session,
  onSignOut,
}: {
  session: Extract<Session, { signed_in: true }>;
  onSignOut: (s: Session) => void;
}) {
  const [who, setWho] = useState<WhoAmI | null>(null);
  useEffect(() => {
    api<WhoAmI>("whoami/").then(setWho);
  }, []);
  const signOut = () => {
    // Stop Google from signing the person straight back in on this browser.
    if ("google" in window) google.accounts.id.disableAutoSelect();
    api<Session>("auth/logout/", {}).then(onSignOut);
  };
  return (
    <div className="card">
      <p>
        Signed in as <strong>{session.user.name}</strong>
        <br />
        <span className="small">{session.user.email}</span>
      </p>
      {who && (
        <>
          <p>
            {who.name} ({who.tenant})
          </p>
          <ul>
            {who.companies.length === 0 && <li>No companies yet.</li>}
            {who.companies.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </>
      )}
      <button onClick={signOut}>Sign out</button>
    </div>
  );
}
