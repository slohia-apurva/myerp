import { FormEvent, useEffect, useState } from "react";
import { api, Session } from "./api";

type Props = { session: Session; onChange: (s: Session) => void };

// Shared wrapper for each step: a form with an error line and a busy state.
function useSubmit<T>(run: () => Promise<T>, done: (value: T) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      done(await run());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, submit };
}

export function Login({ session, onChange }: Props) {
  if (session.step === "totp_setup") return <TotpSetup onChange={onChange} />;
  if (session.step === "totp") return <TotpCode onChange={onChange} />;
  return <Password onChange={onChange} />;
}

function Password({ onChange }: Pick<Props, "onChange">) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, submit } = useSubmit(
    () => api<Session>("auth/login/", { username, password }),
    onChange,
  );
  return (
    <form onSubmit={submit} className="card">
      <h2>Log in</h2>
      <label>
        Username
        <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label>
        Password
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button disabled={busy || !username || !password}>Continue</button>
    </form>
  );
}

function CodeField({ code, setCode }: { code: string; setCode: (v: string) => void }) {
  return (
    <label>
      6-digit code
      <input
        autoFocus
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
      />
    </label>
  );
}

function TotpCode({ onChange }: Pick<Props, "onChange">) {
  const [code, setCode] = useState("");
  const { busy, error, submit } = useSubmit(() => api<Session>("auth/totp/verify/", { code }), onChange);
  return (
    <form onSubmit={submit} className="card">
      <h2>Enter your code</h2>
      <p>Open your authenticator app and enter the code shown for MyERP.</p>
      <CodeField code={code} setCode={setCode} />
      {error && <p className="error">{error}</p>}
      <button disabled={busy || code.length !== 6}>Log in</button>
      <BackToStart onChange={onChange} />
    </form>
  );
}

type Setup = { secret: string; uri: string; qr_svg: string };

function TotpSetup({ onChange }: Pick<Props, "onChange">) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [loadError, setLoadError] = useState("");
  const [code, setCode] = useState("");
  const { busy, error, submit } = useSubmit(() => api<Session>("auth/totp/verify/", { code }), onChange);

  useEffect(() => {
    let live = true;
    api<Setup>("auth/totp/setup/", {})
      .then((s) => live && setSetup(s))
      .catch((err: Error) => live && setLoadError(err.message));
    return () => {
      live = false;
    };
  }, []);

  return (
    <form onSubmit={submit} className="card">
      <h2>Set up two-factor login</h2>
      <p>
        Every MyERP user needs an authenticator app (Google Authenticator, Microsoft Authenticator, or similar).
        Scan this code with it, then enter the 6-digit code it shows.
      </p>
      {loadError && <p className="error">{loadError}</p>}
      {setup && (
        <>
          <div className="qr" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <p className="small">
            Can't scan? Enter this key in the app: <code>{setup.secret}</code>
          </p>
        </>
      )}
      <CodeField code={code} setCode={setCode} />
      {error && <p className="error">{error}</p>}
      <button disabled={busy || !setup || code.length !== 6}>Finish and log in</button>
      <BackToStart onChange={onChange} />
    </form>
  );
}

function BackToStart({ onChange }: Pick<Props, "onChange">) {
  return (
    <button type="button" className="link" onClick={() => api<Session>("auth/logout/", {}).then(onChange)}>
      Start again
    </button>
  );
}

export function SetPassword({ uid, token, onDone }: { uid: string; token: string; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [username, setUsername] = useState("");
  const { busy, error, submit } = useSubmit(
    () => api<{ username: string }>("auth/password-setup/", { uid, token, password }),
    (r) => setUsername(r.username),
  );

  if (username) {
    return (
      <div className="card">
        <h2>Password set</h2>
        <p>
          Your username is <strong>{username}</strong>. Log in now to set up two-factor login.
        </p>
        <button onClick={onDone}>Go to login</button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="card">
      <h2>Choose a password</h2>
      <p className="small">At least 10 characters, not all numbers, and not a common password.</p>
      <label>
        New password
        <input
          type="password"
          autoFocus
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label>
        Repeat it
        <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </label>
      {confirm && confirm !== password && <p className="error">The two passwords differ.</p>}
      {error && <p className="error">{error}</p>}
      <button disabled={busy || !password || password !== confirm}>Set password</button>
    </form>
  );
}
