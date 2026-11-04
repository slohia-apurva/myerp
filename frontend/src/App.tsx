import { useCallback, useEffect, useState } from "react";
import { api, ApiError, Session } from "./api";
import { Login, SetPassword } from "./Login";
import "./app.css";

type WhoAmI = { tenant: string; name: string; companies: string[] };

// A one-time password link looks like /#set-password/<uid>/<token>. The token
// sits after "#" so it never reaches the server or its logs.
function passwordLink(): { uid: string; token: string } | null {
  const match = window.location.hash.match(/^#set-password\/([^/]+)\/([^/]+)$/);
  return match ? { uid: match[1], token: match[2] } : null;
}

export function App() {
  const [link, setLink] = useState(passwordLink);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Session>("auth/session/")
      .then(setSession)
      .catch((err: ApiError) => setError(err.status === 404 ? "Unknown company group address." : err.message));
  }, []);
  useEffect(load, [load]);

  const leaveLink = () => {
    history.replaceState(null, "", "/");
    setLink(null);
    load();
  };

  return (
    <main>
      <h1>MyERP</h1>
      {error && <p className="error">{error}</p>}
      {link ? (
        <SetPassword uid={link.uid} token={link.token} onDone={leaveLink} />
      ) : session === null ? (
        !error && <p>Loading…</p>
      ) : session.step === "done" ? (
        <Home session={session} onLogout={setSession} />
      ) : (
        <Login session={session} onChange={setSession} />
      )}
    </main>
  );
}

function Home({
  session,
  onLogout,
}: {
  session: Extract<Session, { step: "done" }>;
  onLogout: (s: Session) => void;
}) {
  const [who, setWho] = useState<WhoAmI | null>(null);
  useEffect(() => {
    api<WhoAmI>("whoami/").then(setWho);
  }, []);
  return (
    <div className="card">
      <p>
        Logged in as <strong>{session.user.name}</strong>
        {who && (
          <>
            {" "}
            · {who.name} ({who.tenant})
          </>
        )}
      </p>
      {who && (
        <ul>
          {who.companies.length === 0 && <li>No companies yet.</li>}
          {who.companies.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
      <button onClick={() => api<Session>("auth/logout/", {}).then(onLogout)}>Log out</button>
    </div>
  );
}
