import { useEffect, useRef, useState } from "react";
import { api, Session } from "./api";

const GSI_SRC = "https://accounts.google.com/gsi/client";

function loadGoogleScript(): Promise<void> {
  const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
  if (existing && "google" in window) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = existing ?? document.createElement("script");
    script.src = GSI_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not reach Google. Check the internet connection."));
    if (!existing) document.head.appendChild(script);
  });
}

// Sign-in screen: one "Sign in with Google" button. Google checks the person;
// the server checks they were added to this company group.
export function SignIn({ clientId, onChange }: { clientId: string; onChange: (s: Session) => void }) {
  const button = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clientId) return;
    let live = true;
    loadGoogleScript()
      .then(() => {
        if (!live || !button.current) return;
        google.accounts.id.initialize({
          client_id: clientId,
          ux_mode: "popup",
          callback: ({ credential }) => {
            setError("");
            api<Session>("auth/google/", { credential })
              .then(onChange)
              .catch((err: Error) => setError(err.message));
          },
        });
        google.accounts.id.renderButton(button.current, {
          theme: "outline",
          size: "large",
          text: "signin_with",
          shape: "rectangular",
          width: 280,
        });
      })
      .catch((err: Error) => live && setError(err.message));
    return () => {
      live = false;
    };
  }, [clientId, onChange]);

  return (
    <div className="card">
      <h2>Sign in</h2>
      {clientId ? (
        <>
          <p>Use the Google account your company added to MyERP.</p>
          <div ref={button} className="google-button" />
        </>
      ) : (
        <p className="error">Google sign-in is not set up for this address yet.</p>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
