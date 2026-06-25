/**
 * Landing + first-run for AI Visibility OS.
 * Silent local workspace → real probe. Rich, targeted, honest content below the
 * fold (no fabricated claims; Preview labels on anything not yet backed).
 */
import { useState, type ReactNode } from "react";
import { api } from "../../lib/platformApi";
import { getWorkspace, setWorkspace, setLastEntityId } from "../../lib/platformStore";
import { navigate } from "../router";
import { Button, Card, Caveat, Chip, MethodologyNote, PreviewBadge } from "../ui";

export function Onboarding() {
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [category, setCategory] = useState("");
  const [city, setCity] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const existing = getWorkspace();

  async function run() {
    setErr(null);
    if (!name.trim() || !website.trim()) { setErr("Please enter at least your business name and website."); return; }
    setBusy(true);
    try {
      let ws = getWorkspace();
      if (!ws) {
        const email = `operator+${Date.now()}@local.workspace`;
        const { data, error } = await api.createOrg(name.trim() || "My workspace", email);
        if (error || !data) { setErr(error || "Could not create workspace"); setBusy(false); return; }
        ws = { orgId: data.org.id, orgName: data.org.name, apiKey: data.api_key, plan: data.org.plan };
        setWorkspace(ws);
      }
      const ent = await api.createEntity({
        canonical_name: name.trim(), website_url: website.trim(),
        category: category.trim() || null, geo: city.trim() || null,
      });
      if (ent.error || !ent.data) { setErr(ent.error || "Could not add business"); setBusy(false); return; }
      setLastEntityId(ent.data.id);
      const probe = await api.enqueueProbe(ent.data.id);
      if (probe.error || !probe.data) { navigate(`#/e/${ent.data.id}`); return; }
      navigate(`#/probe/${probe.data.probe_run_id}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      {/* Hero */}
      <div className="pt-4 text-center">
        <div className="mb-4 flex justify-center"><Chip tone="teal">Evidence-first AI visibility</Chip></div>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-[2.6rem] sm:leading-[1.1]">Will AI recommend your business?</h1>
        <p className="mx-auto mt-4 max-w-xl text-lg text-text-secondary">
          We ask a live AI answer engine the questions your buyers actually ask — and show you whether it
          names you, who it names instead, and exactly why.
        </p>
      </div>

      {/* First-run form */}
      <Card className="mt-8 p-6">
        <div className="grid gap-4">
          <Field label="Business name" value={name} onChange={setName} placeholder="Acme Plumbing" autoFocus />
          <Field label="Website" value={website} onChange={setWebsite} placeholder="acmeplumbing.com" />
          <div className="grid grid-cols-2 gap-4">
            <Field label="Category" value={category} onChange={setCategory} placeholder="plumber" />
            <Field label="City / area" value={city} onChange={setCity} placeholder="Austin" />
          </div>
        </div>
        {err && <p className="mt-4 rounded-lg border border-[#f87171]/30 bg-[#f87171]/10 px-3 py-2 text-sm text-[#fca5a5]">{err}</p>}
        <div className="mt-6 flex items-center justify-between gap-4">
          <Button onClick={run} disabled={busy} className="px-6">{busy ? "Starting analysis…" : "Analyze my AI visibility"}</Button>
          {existing && <button onClick={() => navigate("#/dashboard")} className="text-sm text-text-muted hover:text-text-secondary">Back to dashboard</button>}
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-border pt-4">
          <Chip tone="neutral">~30 seconds</Chip>
          <Chip tone="neutral">Live web-grounded engine</Chip>
          <MethodologyNote title="How this analysis works">
            <p>We generate buyer-intent questions for your category and location (e.g. “best {`{category}`} in {`{city}`}”) and ask a live, web-grounded AI engine, then measure whether your business is named, which competitors appear, and any factual issues.</p>
            <p><strong>Today this uses one engine.</strong> ChatGPT, Claude and Gemini are on the roadmap and clearly marked “Preview” until live.</p>
            <p>Results vary slightly run-to-run (it’s a live sample), so we treat a single run as directional and build confidence from repeated runs.</p>
          </MethodologyNote>
        </div>
      </Card>
      <Caveat><span className="mt-4 block text-center">A local workspace is created automatically to store results on this machine. No account or payment required.</span></Caveat>

      {/* The differentiator: Readiness vs Reality */}
      <Section title="Being findable isn’t being recommended" kicker="Why this is different from an SEO audit">
        <div className="grid gap-4 sm:grid-cols-2">
          <MiniCard title="Readiness" body="Whether your site is technically AI-ready — crawler access, structured data, content. An SEO-style checklist." tone="muted" />
          <MiniCard title="Reality" body="What the AI engine actually says when a buyer asks. You can be perfectly ‘ready’ and still never get named." tone="teal" />
        </div>
        <Caveat><span className="mt-3 block">The gap between the two is the most useful thing we show you — and the thing a normal audit tool can’t.</span></Caveat>
      </Section>

      {/* How it works */}
      <Section title="How it works" kicker="Four honest steps">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Step n={1} title="Analyze" body="We ask the engine real buyer questions about your category and city." />
          <Step n={2} title="See the answers" body="Read the exact AI responses — your mention highlighted, competitors named." />
          <Step n={3} title="Find the gap" body="Share-of-Model + who’s recommended instead, with the why." />
          <Step n={4} title="Prove it" body="Re-run over time to show whether your visibility actually improved." />
        </div>
      </Section>

      {/* What you get */}
      <Section title="What you get" kicker="All from real engine output">
        <div className="grid gap-3 sm:grid-cols-2">
          <Bullet>Share-of-Model — how often AI names you when buyers ask</Bullet>
          <Bullet>The actual AI answers, as inspectable evidence</Bullet>
          <Bullet>Competitors the engine recommends instead <Chip tone="amber">Directional</Chip></Bullet>
          <Bullet>Factual issues the AI states about you (e.g. wrong status)</Bullet>
          <Bullet>History &amp; trend once you run more than once</Bullet>
          <Bullet>Technical AI-readiness audit of your site</Bullet>
        </div>
      </Section>

      {/* Three pillars */}
      <Section title="The three things AI needs to recommend you" kicker="Access · Meaning · Recommendation">
        <div className="grid gap-3 sm:grid-cols-3">
          <Pillar title="Access" body="Can AI crawlers reach and read your site at all?" />
          <Pillar title="Meaning" body="Does your content clearly tell AI who you are and what you do?" />
          <Pillar title="Recommendation" body="When it matters, does AI actually put you in the answer?" />
        </div>
      </Section>

      {/* For agencies (honest preview) */}
      <Section title="Built for agencies" kicker="Roadmap">
        <div className="flex flex-wrap gap-2">
          <PreviewItem>Portfolio across all clients</PreviewItem>
          <PreviewItem>White-label proof reports</PreviewItem>
          <PreviewItem>Shareable client links</PreviewItem>
          <PreviewItem>Scheduled monitoring &amp; alerts</PreviewItem>
          <PreviewItem>One-click fixes</PreviewItem>
        </div>
        <Caveat><span className="mt-3 block">These are designed-for, not yet live. We label everything honestly and never show fabricated results.</span></Caveat>
      </Section>

      {/* FAQ */}
      <Section title="Questions" kicker="Straight answers">
        <Faq q="Is this an SEO tool?" a="No. SEO measures how you rank in search results. We measure whether AI answer engines actually recommend you — and we show the real answers as proof." />
        <Faq q="Which AI engines do you check?" a="Today, one live web-grounded engine. ChatGPT, Claude and Gemini comparisons are on the roadmap and clearly marked Preview until they’re genuinely live — we never show an engine’s results we didn’t query." />
        <Faq q="How is Share-of-Model measured?" a="The share of buyer-intent (no-name) questions where the engine independently names your business. It’s a live sample, so a single run is directional — confirm changes with repeated runs." />
        <Faq q="Are the competitor results facts?" a="They’re observations of what the AI said on a given date, not statements of fact about those businesses. Competitor precision is still improving, so we label it Directional." />
        <Faq q="Do you store my data?" a="A local workspace is created on this machine to hold your results. No account or payment is required to analyze." />
      </Section>

      <div className="my-10 text-center">
        <Button onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); }} variant="ghost">Back to top</Button>
      </div>
    </div>
  );
}

// ─── content primitives ──────────────────────────────────────────────────────

function Field({ label, value, onChange, placeholder, autoFocus }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; autoFocus?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm text-text-secondary">{label}</span>
      <input autoFocus={autoFocus} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full rounded-xl border border-border bg-bg-base px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-teal focus:outline-none" />
    </label>
  );
}
function Section({ title, kicker, children }: { title: string; kicker?: string; children: ReactNode }) {
  return (
    <section className="mt-14">
      {kicker && <p className="mb-1 text-[11px] uppercase tracking-[0.18em] text-accent-teal">{kicker}</p>}
      <h2 className="mb-4 text-xl font-semibold tracking-tight text-text-primary sm:text-2xl">{title}</h2>
      {children}
    </section>
  );
}
function MiniCard({ title, body, tone }: { title: string; body: string; tone: "teal" | "muted" }) {
  return (
    <Card className={`p-5 ${tone === "teal" ? "border-accent-teal/30" : ""}`}>
      <p className={`text-sm font-semibold ${tone === "teal" ? "text-accent-teal" : "text-text-secondary"}`}>{title}</p>
      <p className="mt-1.5 text-sm leading-relaxed text-text-muted">{body}</p>
    </Card>
  );
}
function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <Card className="p-4">
      <span className="font-mono text-xs text-accent-teal">0{n}</span>
      <p className="mt-1 font-medium text-text-primary">{title}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-text-muted">{body}</p>
    </Card>
  );
}
function Bullet({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-border bg-bg-surface p-3.5 text-sm text-text-secondary">
      <span className="mt-0.5 text-accent-teal">✓</span><span>{children}</span>
    </div>
  );
}
function Pillar({ title, body }: { title: string; body: string }) {
  return (
    <Card className="p-5">
      <p className="font-medium text-text-primary">{title}</p>
      <p className="mt-1.5 text-[13px] leading-relaxed text-text-muted">{body}</p>
    </Card>
  );
}
function PreviewItem({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-surface px-3 py-1.5 text-[13px] text-text-secondary">
      {children}<PreviewBadge />
    </span>
  );
}
function Faq({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-border py-3.5 last:border-0">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-3 text-left">
        <span className="text-sm font-medium text-text-primary">{q}</span>
        <span className="text-text-muted">{open ? "–" : "+"}</span>
      </button>
      {open && <p className="mt-2 text-sm leading-relaxed text-text-muted">{a}</p>}
    </div>
  );
}
