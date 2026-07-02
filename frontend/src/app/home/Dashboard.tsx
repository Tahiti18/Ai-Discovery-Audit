/**
 * Visible to AI — dashboard: the signed-in home. Lists the user's businesses
 * (built as a list from day one, so multi-business is a later unlock, not a
 * rebuild) and links each to its latest report. All data is the session's real
 * data via the JWT.
 */
import { useEffect, useState } from "react";
import { api, somPct, type Entity, type ProbeRun } from "../../lib/platformApi";
import { getSession, clearSession } from "../session";
import { navigate } from "../AppRoot";

interface Row {
  entity: Entity;
  latest: ProbeRun | null;
}

export function Dashboard() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [limitMsg, setLimitMsg] = useState<string | null>(null); // plan limit → upsell, not error
  const [busy, setBusy] = useState<string | null>(null);
  const session = getSession();

  useEffect(() => {
    (async () => {
      const { data, error } = await api.listEntities();
      if (error) { setErr(error); return; }
      const entities = data ?? [];
      const withRuns = await Promise.all(
        entities.map(async (entity) => {
          const r = await api.listEntityProbes(entity.id);
          const runs = r.data ?? [];
          const latest = runs.find((x) => x.status === "complete") ?? runs[0] ?? null;
          return { entity, latest } as Row;
        }),
      );
      setRows(withRuns);
    })();
  }, []);

  async function runCheck(entityId: string) {
    setBusy(entityId); setErr(null); setLimitMsg(null);
    const res = await api.enqueueProbe(entityId);
    setBusy(null);
    if (res.error || !res.data) {
      // Plan limits are an upgrade moment, not a failure.
      if (res.status === 429 || res.status === 402) { setLimitMsg(res.error); return; }
      setErr(res.error || "Could not start the check");
      return;
    }
    navigate(`report/${res.data.probe_run_id}`);
  }

  async function upgrade() {
    setBusy("upgrade");
    const { data, error } = await api.createCheckout("founding");
    setBusy(null);
    if (data?.url) { window.location.href = data.url; return; }
    // Until Stripe keys are configured the API returns a friendly 503.
    setErr(error || "Upgrades open soon — hang tight.");
  }

  return (
    <div className="vta">
      <div className="fixed inset-0 pointer-events-none v-glow" aria-hidden="true" />
      <div className="relative">
        <nav className="border-b v-border-hair sticky top-0 z-50" style={{ background: "rgba(10,10,18,0.85)", backdropFilter: "blur(12px)" }}>
          <div className="max-w-5xl mx-auto px-6 py-3.5 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <svg width="24" height="18" viewBox="0 0 32 24" fill="none" aria-hidden="true" style={{ filter: "drop-shadow(0 0 10px rgba(167,139,250,0.25))" }}>
                <path d="M 2 12 Q 16 2, 30 12 Q 16 22, 2 12 Z" stroke="#A78BFA" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="16" cy="12" r="3.5" fill="#A78BFA" />
              </svg>
              <span style={{ fontFamily: "'Playfair Display Variable',Georgia,serif", fontWeight: 500, fontSize: 17 }}>
                Visible <em style={{ fontStyle: "italic" }}>to</em> <span style={{ color: "var(--vta-accent)" }}>AI</span>
              </span>
            </div>
            <div className="flex items-center gap-5">
              <span className="v-text-muted hidden sm:block" style={{ fontSize: 13 }}>{session?.user.email}</span>
              <button onClick={() => { clearSession(); window.location.href = "/login/"; }} className="v-navlink" style={{ fontSize: 13 }}>Sign out</button>
            </div>
          </div>
        </nav>

        <main className="max-w-5xl mx-auto px-6 py-10">
          <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
            <div>
              <h1 className="v-display" style={{ fontSize: "clamp(26px,4vw,34px)" }}>My businesses</h1>
              <p className="v-text-secondary mt-1" style={{ fontSize: 14 }}>{session?.org.name} · {session?.org.plan} plan</p>
            </div>
            <div className="flex items-center gap-2.5">
              {session?.org.plan === "free" && (
                <button onClick={upgrade} disabled={busy === "upgrade"} className="v-btn v-btn-ghost">
                  {busy === "upgrade" ? "…" : "Upgrade"}
                </button>
              )}
              <button onClick={() => navigate("new")} className="v-btn v-btn-primary">+ Add a business</button>
            </div>
          </div>

          {err && <div className="v-card p-5 mb-4" style={{ borderColor: "var(--vta-red-soft)" }}><p style={{ color: "var(--vta-red)", fontSize: 14 }}>{err}</p></div>}

          {limitMsg && (
            <div className="v-card p-5 mb-4 flex flex-wrap items-center justify-between gap-4" style={{ borderColor: "var(--vta-border-accent)" }}>
              <div className="flex-1" style={{ minWidth: 240 }}>
                <p style={{ fontSize: 15, fontWeight: 500 }}>You've hit your plan's limit</p>
                <p className="v-text-secondary mt-1" style={{ fontSize: 13 }}>{limitMsg}</p>
              </div>
              <button onClick={upgrade} disabled={busy === "upgrade"} className="v-btn v-btn-primary" style={{ padding: "9px 16px", fontSize: 14 }}>
                {busy === "upgrade" ? "…" : "Upgrade — founding price"}
              </button>
            </div>
          )}

          {rows === null ? (
            <p className="v-text-muted" style={{ fontSize: 14 }}>Loading your businesses…</p>
          ) : rows.length === 0 ? (
            <div className="v-card p-8 text-center">
              <h2 className="v-display" style={{ fontSize: 22 }}>Add your first business</h2>
              <p className="v-text-secondary mt-2" style={{ fontSize: 14 }}>Run your first AI visibility check and see what AI says about your business.</p>
              <button onClick={() => navigate("new")} className="v-btn v-btn-primary mt-5">+ Add a business</button>
            </div>
          ) : (
            <div className="space-y-3">
              {rows.map(({ entity, latest }) => {
                const pct = latest && latest.status === "complete" ? somPct(latest) : null;
                const running = latest && (latest.status === "queued" || latest.status === "running");
                return (
                  <div key={entity.id} className="v-card p-5 md:p-6 flex flex-wrap items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p style={{ fontSize: 17, fontWeight: 500 }}>{entity.canonical_name}</p>
                      <p className="v-text-muted truncate" style={{ fontSize: 13 }}>
                        {hostOf(entity.website_url)}{entity.category ? ` · ${entity.category}` : ""}{entity.geo ? ` · ${entity.geo}` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      {latest && latest.status === "complete" && (
                        <div className="text-right hidden sm:block">
                          <span className="v-tabular" style={{ fontSize: 22, fontWeight: 500, color: pct != null && pct > 0 ? "var(--vta-green)" : "var(--vta-red)" }}>{pct ?? 0}%</span>
                          <span className="v-label block">Discovery</span>
                        </div>
                      )}
                      {running && <span className="v-pill" style={{ background: "var(--vta-amber-soft)", color: "#FCD34D" }}>Running…</span>}
                      {latest && (
                        <button onClick={() => navigate(`report/${latest.id}`)} className="v-btn v-btn-ghost" style={{ padding: "8px 14px", fontSize: 14 }}>View report</button>
                      )}
                      <button onClick={() => runCheck(entity.id)} disabled={busy === entity.id} className="v-btn v-btn-primary" style={{ padding: "8px 14px", fontSize: 14 }}>
                        {busy === entity.id ? "Starting…" : latest ? "Run again" : "Run check"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function hostOf(url: string): string {
  try { return new URL(url.includes("://") ? url : `https://${url}`).hostname.replace(/^www\./, ""); }
  catch { return url; }
}
