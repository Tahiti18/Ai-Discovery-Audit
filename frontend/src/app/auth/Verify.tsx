/**
 * Visible to AI — magic-link verification. Reads the `token` from the URL,
 * exchanges it for a session, stores it, and continues into the app.
 */
import "../visibletoai.css";
import { useEffect, useState } from "react";
import { api } from "../../lib/platformApi";
import { setSession, type Session } from "../session";

const CONTINUE_TO = "/app/"; // where to land after a successful sign-in

export default function Verify() {
  const [state, setState] = useState<"verifying" | "ok" | "error">("verifying");
  const [error, setError] = useState<string | null>(null);
  const [session, setSess] = useState<Session | null>(null);

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      setState("error");
      setError("This sign-in link is missing its token. Request a new one.");
      return;
    }
    (async () => {
      const { data, error } = await api.verifyMagicLink(token);
      if (error || !data) {
        setState("error");
        setError(error || "This sign-in link is invalid or has expired.");
        return;
      }
      const s: Session = { accessToken: data.access_token, user: data.user, org: data.org };
      setSession(s);
      setSess(s);
      setState("ok");
    })();
  }, []);

  return (
    <div className="vta">
      <div className="fixed inset-0 pointer-events-none v-glow" aria-hidden="true" />
      <div className="relative min-h-screen flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-[440px] text-center">
          {state === "verifying" && (
            <>
              <Spinner />
              <p className="v-text-secondary mt-4" style={{ fontSize: 15 }}>Signing you in…</p>
            </>
          )}

          {state === "ok" && session && (
            <div className="v-card p-8">
              <div className="mx-auto mb-4 flex items-center justify-center" style={{ width: 48, height: 48, borderRadius: 12, background: "var(--vta-green-soft)", border: "1px solid var(--vta-green-soft)" }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--vta-green)" strokeWidth="2.5"><polyline points="20 6 9 17 4 12" /></svg>
              </div>
              <h1 className="v-display" style={{ fontSize: 24 }}>You're signed in</h1>
              <p className="v-text-secondary mt-2" style={{ fontSize: 14 }}>
                {session.user.email} · <span className="v-text-primary" style={{ color: "var(--vta-text-primary)" }}>{session.org.name}</span>
              </p>
              <a href={CONTINUE_TO} className="v-btn v-btn-primary mt-6">Continue →</a>
            </div>
          )}

          {state === "error" && (
            <div className="v-card p-8">
              <div className="mx-auto mb-4 flex items-center justify-center" style={{ width: 48, height: 48, borderRadius: 12, background: "var(--vta-red-soft)", border: "1px solid var(--vta-red-soft)" }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--vta-red)" strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
              </div>
              <h1 className="v-display" style={{ fontSize: 22 }}>Sign-in failed</h1>
              <p className="v-text-secondary mt-2 leading-relaxed" style={{ fontSize: 14 }}>{error}</p>
              <a href="/login/" className="v-btn v-btn-ghost mt-6">Back to sign in</a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="mx-auto" width="36" height="36" viewBox="0 0 24 24" style={{ animation: "vtaspin 0.8s linear infinite" }}>
      <style>{"@keyframes vtaspin{to{transform:rotate(360deg)}}"}</style>
      <circle cx="12" cy="12" r="9" fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="var(--vta-accent)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
