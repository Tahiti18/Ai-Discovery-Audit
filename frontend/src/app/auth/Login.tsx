/**
 * Visible to AI — passwordless login. Enter email → we email a sign-in link.
 * In local dev (no email backend) the API returns the link and we show it so the
 * flow is clickable end to end.
 */
import "../visibletoai.css";
import { useState } from "react";
import { api } from "../../lib/platformApi";

export default function Login() {
  // Prefill the email if the landing page passed it through (?email=…), and
  // show a gentle note when the app bounced us here after a session expiry.
  const [email, setEmail] = useState(() => {
    try { return new URLSearchParams(window.location.search).get("email") || ""; }
    catch { return ""; }
  });
  const [expired] = useState(() => {
    try { return new URLSearchParams(window.location.search).get("expired") === "1"; }
    catch { return false; }
  });
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [devUrl, setDevUrl] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("sending");
    setError(null);
    const { data, error } = await api.requestMagicLink(email.trim());
    if (error || !data) {
      setStatus("error");
      setError(error || "Something went wrong. Please try again.");
      return;
    }
    setDevUrl(data.dev_login_url ?? null);
    setStatus("sent");
  }

  return (
    <div className="vta">
      <div className="fixed inset-0 pointer-events-none v-glow" aria-hidden="true" />
      <div className="relative min-h-screen flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-[440px]">
          {/* Logo */}
          <a href="/" className="flex items-center justify-center gap-2.5 mb-8" style={{ textDecoration: "none", color: "inherit" }}>
            <svg width="26" height="20" viewBox="0 0 32 24" fill="none" aria-hidden="true" style={{ filter: "drop-shadow(0 0 10px rgba(167,139,250,0.25))" }}>
              <path d="M 2 12 Q 16 2, 30 12 Q 16 22, 2 12 Z" stroke="#A78BFA" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="16" cy="12" r="3.5" fill="#A78BFA" />
            </svg>
            <span style={{ fontFamily: "'Playfair Display Variable',Georgia,serif", fontWeight: 500, fontSize: 19 }}>
              Visible <em style={{ fontStyle: "italic" }}>to</em> <span style={{ color: "var(--vta-accent)" }}>AI</span>
            </span>
          </a>

          <div className="v-card p-7 md:p-8">
            {status === "sent" ? (
              <div className="text-center">
                <div className="mx-auto mb-4 flex items-center justify-center" style={{ width: 48, height: 48, borderRadius: 12, background: "var(--vta-accent-soft-bg)", border: "1px solid var(--vta-border-accent)" }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--vta-accent)" strokeWidth="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" /></svg>
                </div>
                <h1 className="v-display" style={{ fontSize: 24 }}>Check your email</h1>
                <p className="v-text-secondary mt-2 leading-relaxed" style={{ fontSize: 14 }}>
                  We sent a sign-in link to <strong style={{ color: "var(--vta-text-primary)" }}>{email}</strong>. Click it to sign in — no password needed.
                </p>
                {devUrl && (
                  <div className="mt-5 rounded-xl p-3" style={{ background: "var(--vta-bg-elevated)", border: "1px dashed var(--vta-border-strong)" }}>
                    <p className="v-label mb-2">Dev mode — no email sent</p>
                    <a href={devUrl} className="v-accent" style={{ fontSize: 13, wordBreak: "break-all" }}>Open sign-in link →</a>
                  </div>
                )}
                <button onClick={() => { setStatus("idle"); setDevUrl(null); }} className="v-navlink mt-5" style={{ fontSize: 13 }}>← Use a different email</button>
              </div>
            ) : (
              <>
                {expired && (
                  <p className="text-center mb-4 rounded-lg px-3 py-2" style={{ fontSize: 13, background: "var(--vta-amber-soft)", color: "#FCD34D" }}>
                    Your session expired — sign in again to pick up where you left off.
                  </p>
                )}
                <h1 className="v-display text-center" style={{ fontSize: 24 }}>Sign in to Visible to AI</h1>
                <p className="v-text-secondary text-center mt-2 leading-relaxed" style={{ fontSize: 14 }}>
                  Enter your email and we'll send you a secure sign-in link. No passwords.
                </p>
                <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
                  <input
                    type="email" required autoFocus value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@yourbusiness.com" autoComplete="email"
                    style={{ padding: "13px 16px", borderRadius: 10, background: "var(--vta-surface-1)", border: "1px solid var(--vta-border-strong)", color: "var(--vta-text-primary)", fontSize: 15, fontFamily: "inherit" }}
                  />
                  <button type="submit" disabled={status === "sending"} className="v-btn v-btn-primary" style={{ opacity: status === "sending" ? 0.7 : 1 }}>
                    {status === "sending" ? "Sending…" : "Email me a sign-in link"}
                  </button>
                </form>
                {error && <p className="mt-3 text-center" style={{ fontSize: 13, color: "var(--vta-red)" }}>{error}</p>}
              </>
            )}
          </div>

          <p className="v-text-muted text-center mt-5 leading-relaxed" style={{ fontSize: 12 }}>
            By signing in you agree to check what AI says about your business. We never store passwords.
          </p>
        </div>
      </div>
    </div>
  );
}
