/**
 * Visible to AI — add a business and run its first AI visibility check.
 * Creates the entity via the session, then starts a probe and goes to the live
 * report. Plain-English fields only — a business owner fills this in 20 seconds.
 */
import { useState } from "react";
import { api } from "../../lib/platformApi";
import { navigate } from "../AppRoot";

export function AddBusiness() {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [category, setCategory] = useState("");
  const [city, setCity] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [limitMsg, setLimitMsg] = useState<string | null>(null);

  async function upgrade() {
    const { data, error } = await api.createCheckout("business");
    if (data?.url) { window.location.href = data.url; return; }
    setErr(error || "Upgrades open soon — hang tight.");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !url.trim()) return;
    setBusy(true); setErr(null); setLimitMsg(null);
    const ent = await api.createEntity({
      canonical_name: name.trim(),
      website_url: normalizeUrl(url.trim()),
      category: category.trim() || null,
      geo: city.trim() || null,
    });
    if (ent.error || !ent.data) {
      setBusy(false);
      if (ent.status === 402) { setLimitMsg(ent.error); return; } // plan limit → upsell
      setErr(ent.error || "Couldn't add the business.");
      return;
    }
    const probe = await api.enqueueProbe(ent.data.id);
    setBusy(false);
    if (probe.error || !probe.data) { setErr(probe.error || "Business added, but the check didn't start. Try Run check from your dashboard."); return; }
    navigate(`report/${probe.data.probe_run_id}`);
  }

  return (
    <div className="vta">
      <div className="fixed inset-0 pointer-events-none v-glow" aria-hidden="true" />
      <div className="relative min-h-screen px-6 py-12">
        <div className="max-w-xl mx-auto">
          <button onClick={() => navigate("")} className="v-navlink" style={{ fontSize: 13 }}>← My businesses</button>
          <h1 className="v-display mt-4" style={{ fontSize: "clamp(26px,4vw,32px)" }}>Add a business</h1>
          <p className="v-text-secondary mt-2" style={{ fontSize: 15 }}>
            Tell us about your business and we'll check what AI says about it — about 60 seconds.
          </p>

          <form onSubmit={submit} className="v-card p-6 md:p-7 mt-6 flex flex-col gap-5">
            <Field label="Business name" hint="The name customers know you by.">
              <input required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Era More Than Gold" style={inputStyle} />
            </Field>
            <Field label="Website" hint="Your homepage — we work it out from there.">
              <input required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="eramorethangold.com" style={inputStyle} />
            </Field>
            <div className="grid sm:grid-cols-2 gap-5">
              <Field label="What you do" hint="e.g. jeweller, dentist, bakery.">
                <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="jeweller" style={inputStyle} />
              </Field>
              <Field label="City" hint="Where your customers are.">
                <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Limassol" style={inputStyle} />
              </Field>
            </div>
            {err && <p style={{ color: "var(--vta-red)", fontSize: 13 }}>{err}</p>}
            {limitMsg && (
              <div className="rounded-xl p-4 flex flex-wrap items-center justify-between gap-3" style={{ background: "var(--vta-accent-soft-bg)", border: "1px solid var(--vta-border-accent)" }}>
                <p className="v-text-secondary" style={{ fontSize: 13, flex: 1, minWidth: 200 }}>{limitMsg}</p>
                <button type="button" onClick={upgrade} className="v-btn v-btn-primary" style={{ padding: "8px 14px", fontSize: 13 }}>See upgrade options</button>
              </div>
            )}
            <button type="submit" disabled={busy} className="v-btn v-btn-primary" style={{ opacity: busy ? 0.7 : 1 }}>
              {busy ? "Starting your first check…" : "Add & run my first check"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "12px 14px", borderRadius: 10, background: "var(--vta-surface-1)",
  border: "1px solid var(--vta-border-strong)", color: "var(--vta-text-primary)",
  fontSize: 15, fontFamily: "inherit", width: "100%",
};

function Field({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span style={{ fontSize: 14, fontWeight: 500 }}>{label}</span>
      <span className="v-text-muted block" style={{ fontSize: 12, marginBottom: 7 }}>{hint}</span>
      {children}
    </label>
  );
}

function normalizeUrl(u: string): string {
  return u.includes("://") ? u : `https://${u}`;
}
