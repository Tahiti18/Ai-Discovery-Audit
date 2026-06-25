/** Learn & Coming-Soon pages. Educational keys render real content; unbuilt
 *  features render an honest 4-part explainer (what it does / why it matters /
 *  what's needed / how it connects). Every nav item lands somewhere useful. */
import type { ReactNode } from "react";
import { navigate } from "../router";
import { Button, Card, Chip, PreviewBadge } from "../ui";

interface Entry { title: string; kind: "learn" | "soon"; body: ReactNode }

const P = ({ children }: { children: ReactNode }) => <p className="text-sm leading-relaxed text-text-secondary">{children}</p>;
const L = ({ children }: { children: ReactNode }) => <li className="text-sm leading-relaxed text-text-secondary">{children}</li>;

function Field({ h, children }: { h: string; children: ReactNode }) {
  return <div><p className="text-[11px] uppercase tracking-wider text-accent-teal">{h}</p><p className="mt-0.5 text-sm leading-relaxed text-text-secondary">{children}</p></div>;
}
/** Honest 4-part "coming soon" explainer. */
function soon(title: string, parts: { does: string; matters: string; needed: string; connects: string }): Entry {
  return {
    title, kind: "soon",
    body: (
      <div className="space-y-4">
        <Field h="What it will do">{parts.does}</Field>
        <Field h="Why it matters">{parts.matters}</Field>
        <Field h="What's needed to ship it">{parts.needed}</Field>
        <Field h="How it connects to AI Visibility OS">{parts.connects}</Field>
      </div>
    ),
  };
}

const CONTENT: Record<string, Entry> = {
  // ── Educational (real content) ──────────────────────────────────────────
  discovery: { title: "Discovery Visibility", kind: "learn", body: <><P><strong className="text-text-primary">Discovery Visibility</strong> is the headline and the real commercial question: when a buyer asks AI for a recommendation <em>without naming you</em> ("best jeweller in Limassol"), does AI put you in the answer?</P><P>It's measured only from no-name discovery prompts. Being mentioned when your name is already given does not count — that would make almost everyone look 100%.</P></> },
  brand: { title: "Brand Knowledge", kind: "learn", body: <><P><strong className="text-text-primary">Brand Knowledge</strong> measures whether AI answers correctly when the buyer already knows your name ("is X reputable?").</P><P>Useful — wrong facts cost customers — but far easier than Discovery, and it doesn't prove you'll be recommended to new customers.</P></> },
  "ai-answers": { title: "AI Answers (the evidence)", kind: "learn", body: <><P>Every analysis stores the <strong className="text-text-primary">actual answers</strong> the engine gave — exact prompt, response, whether you were named, cited domains, provider, model, timestamp.</P><P>Open any result and expand "The actual AI answers", or download the raw JSON.</P></> },
  "next-moves": { title: "Your Next Moves", kind: "learn", body: <><P>After each analysis we turn the result into the <strong className="text-text-primary">top 3 actions</strong> a strategist would take first — each with why, expected benefit, effort, and how a future check confirms it worked.</P><P>Find them at the top of any result, under "Your next 3 actions".</P></> },
  readiness: { title: "Website Readiness", kind: "learn", body: <><P><strong className="text-text-primary">Readiness</strong> is the technical side: can AI crawlers reach and understand your site? It differs from <strong className="text-text-primary">Reality</strong> — what AI actually says.</P><P>The gap is the insight: a technically perfect site can still be ignored. Readiness requires verifying you own the domain; find it on each business page.</P></> },
  "how-it-works": { title: "How It Works", kind: "learn", body: <ol className="list-decimal space-y-1.5 pl-5"><L>We generate realistic buyer questions for your category and location.</L><L>We ask a live, web-grounded AI engine and read every answer.</L><L>We separate <strong className="text-text-primary">discovery</strong> (no-name) from <strong className="text-text-primary">brand-check</strong> questions.</L><L>We show whether AI named you, and which other businesses it named.</L><L>We turn that into your top 3 actions.</L><L>You re-run later to prove whether visibility improved.</L></ol> },
  methodology: { title: "Methodology", kind: "learn", body: <ul className="list-disc space-y-1.5 pl-5"><L><strong className="text-text-primary">Discovery Visibility</strong> = share of no-name questions where AI independently names you.</L><L><strong className="text-text-primary">Brand Knowledge</strong> = share of name-given questions answered with you.</L><L>Provider/model and timestamp are recorded on every answer.</L><L>Sample is small and single-engine today — directional, not guarantees.</L><L>Results vary run-to-run; repeated runs and trends matter.</L><L>Competitor/domain grouping is a labeled presentation-layer heuristic.</L></ul> },
  research: { title: "Research Notes", kind: "learn", body: <ul className="list-disc space-y-1.5 pl-5"><L>Buyers increasingly ask AI assistants for recommendations.</L><L>AI answers lean on retrievable evidence — citations, entities, trusted sources.</L><L>Technical readiness alone doesn't guarantee actual recommendation behavior.</L><L>The only reliable way to know is to inspect real AI outputs.</L><L>We don't invent citations or overclaim.</L></ul> },
  faq: { title: "FAQ", kind: "learn", body: <div className="space-y-3">{[
    ["Is this SEO?", "No. SEO is about ranking in search. This measures whether AI engines actually recommend you — and shows the real answers."],
    ["Does it guarantee AI recommendations?", "No. It measures and guides; results are directional samples."],
    ["Which engines are tested?", "One live web-grounded engine today (via OpenRouter). ChatGPT/Claude/Gemini comparison is on the roadmap, labelled Preview."],
    ["Why do results vary?", "It's a live AI sample. Run again to confirm a change is real."],
    ["Why was a competitor or directory mentioned?", "Those are domains the AI cited. We group them conservatively, never asserting they're 'beating you'."],
    ["Can I export this for my developer?", "Yes — download the raw JSON from any result's methodology section."],
    ["Can agencies use this for clients?", "That's the direction — portfolio, white-label and shareable proof are on the roadmap."],
  ].map(([q, a]) => <div key={q}><p className="text-sm font-medium text-text-primary">{q}</p><p className="mt-0.5 text-sm leading-relaxed text-text-muted">{a}</p></div>)}</div> },
  limitations: { title: "Limitations (read this)", kind: "learn", body: <ul className="list-disc space-y-1.5 pl-5"><L>Single engine, small sample, point-in-time — directional, not definitive.</L><L>Discovery Visibility is a mention-based proxy for "recommended".</L><L>Competitor/domain classification is a heuristic with edge cases.</L><L>Readiness requires domain verification; multi-engine isn't live yet.</L><L>We never fabricate — every figure derives from a real, inspectable answer.</L></ul> },
  "raw-download": { title: "Raw Data Download", kind: "learn", body: <><P>Available now. Open any analysis result, scroll to <strong className="text-text-primary">Methodology &amp; limitations</strong>, and click <strong className="text-text-primary">Download raw data (JSON)</strong> — the full run plus every AI answer.</P><P>CSV and a full evidence bundle are on the way.</P></> },
  history: { title: "Progress History", kind: "learn", body: <><P>Every business keeps all its past runs. Open a business and use the <strong className="text-text-primary">History</strong> tab to see runs over time.</P><P>A two-run trend appears once you've run at least twice — richer charts and before/after are expanding.</P></> },
  roadmap: { title: "Roadmap", kind: "learn", body: <div className="space-y-4">
    <RoadGroup tone="teal" title="Available now" items={["Discovery Visibility", "Brand Knowledge", "Real AI-answer evidence", "Prompt-type breakdown", "Your next 3 actions", "Explain-this panels", "Raw JSON export"]} />
    <RoadGroup tone="amber" title="In progress" items={["Proof reports", "Readiness-vs-reality view", "Progress history & trends", "CSV / evidence-bundle export"]} />
    <RoadGroup tone="violet" title="Planned" items={["Multi-engine comparison (ChatGPT/Claude/Gemini)", "Scheduled monitoring & alerts", "Agency portfolio dashboard", "White-label & shareable links"]} />
    <RoadGroup tone="neutral" title="Exploring" items={["One-click fixes", "Automated execution", "Integrations", "Team accounts, billing & plans"]} />
  </div> },

  // ── Feature explainers (honest "coming soon", no dead ends) ─────────────
  engines: soon("Multi-engine comparison", {
    does: "Run the same buyer questions across ChatGPT, Claude, Gemini and Perplexity and compare where each recommends you.",
    matters: "Your customers don't all use one assistant. Visibility in one engine doesn't mean visibility in another.",
    needed: "Per-engine provider connections and a per-engine results view (the data model already supports multiple engines).",
    connects: "Each engine becomes another column next to today's Discovery Visibility — same evidence-first approach, more coverage.",
  }),
  scheduled: soon("Scheduled monitoring", {
    does: "Automatically re-run your AI Visibility Checks on a schedule (e.g. weekly) without you lifting a finger.",
    matters: "AI answers drift. Monitoring catches a drop before it costs you customers, and builds the trend that proves improvement.",
    needed: "A background scheduler and per-plan run budgets (live checks cost money, so this is usage-controlled).",
    connects: "Feeds the same history and proof views you already see on each business — just kept current automatically.",
  }),
  alerts: soon("Alerts", {
    does: "Notify you when your Discovery Visibility drops, a competitor overtakes you, or AI states something wrong about you.",
    matters: "You find out the moment your AI standing changes, instead of discovering it months later.",
    needed: "Monitoring (above) plus notification channels (email/Slack) and thresholds.",
    connects: "Built on the flags and metrics already produced by every analysis.",
  }),
  trends: soon("Trend tracking", {
    does: "Chart Discovery Visibility and Brand Knowledge over time, with real-vs-noise bands so you trust the movement.",
    matters: "One number is a snapshot; the trend is the proof a client or executive actually wants.",
    needed: "Multiple stored runs (you build these by re-running) and an aggregation layer over them.",
    connects: "Uses the run history already saved per business; the History tab is the first version.",
  }),
  "proof-report": soon("Proof report", {
    does: "Generate a clean, client-ready before/after report showing measurable AI-visibility improvement.",
    matters: "It's the deliverable that justifies an agency retainer or proves ROI to a stakeholder.",
    needed: "A report renderer/export and at least two real runs to compare.",
    connects: "Packages your real metrics, evidence and trend into a shareable artifact — no fabricated numbers.",
  }),
  "before-after": soon("Before / After", {
    does: "Compare two analyses side by side and highlight exactly what changed and whether it's real.",
    matters: "Shows your work paid off — the core of the Prove stage.",
    needed: "Two stored runs and a diff view with noise-aware comparison.",
    connects: "Reads the same run records the History tab already lists.",
  }),
  export: soon("Export evidence", {
    does: "Export full evidence bundles (JSON, CSV, and a packaged report) for developers, agencies and technical reviewers.",
    matters: "Lets technical users and clients audit everything without losing fidelity.",
    needed: "CSV/bundle generators (raw JSON download already works on each result).",
    connects: "Extends today's 'Download raw data (JSON)' into multiple formats.",
  }),
  "action-plan": soon("90-day action plan", {
    does: "Synthesize a prioritized plan — Week 1 highest-impact fixes, Weeks 2–4 trust-building, Months 2–3 monitoring and proof — with how each will be measured.",
    matters: "Turns a result into a roadmap a business owner can actually execute, not just a score.",
    needed: "A planning layer over your findings (today's 'Your next 3 actions' is the seed).",
    connects: "Expands the action panel already on every result into a time-phased plan.",
  }),
  "trust-signals": soon("Trust signals", {
    does: "Check the trust signals AI looks for — consistent listings, reviews, citations, entity links — and what's missing.",
    matters: "These signals are often the difference between being recognized and recommended, or ignored.",
    needed: "Readiness audit data (requires domain verification) plus entity-signal analysis.",
    connects: "Sits alongside Website Readiness to explain the readiness-vs-reality gap.",
  }),
  "content-signals": soon("Content & entity signals", {
    does: "Analyze whether your content and structured data clearly tell AI who you are, what you do, and where.",
    matters: "Unclear entity signals make AI uncertain — and uncertain AI doesn't recommend you.",
    needed: "Readiness/audit pipeline wired into this view (the engine already computes these signals).",
    connects: "Turns the technical signals behind Readiness into plain-English fixes.",
  }),
  "what-changed": soon("What changed", {
    does: "A feed of what's new since your last visit — new results, visibility movement, new issues or opportunities.",
    matters: "Tells you where to focus the moment you log in, instead of hunting.",
    needed: "Change detection across stored runs.",
    connects: "Summarizes movements from the same run history other views use.",
  }),
  portfolio: soon("Client portfolio", {
    does: "Manage many businesses at once with a portfolio view — visibility, issues and trends across every client.",
    matters: "Agencies live in a portfolio, not a single business. This is the agency home screen.",
    needed: "Multi-business rollups and team scoping (the dashboard is the single-tenant seed today).",
    connects: "Aggregates the per-business results you already produce.",
  }),
  "white-label": soon("White-label reports", {
    does: "Produce proof reports under your own brand to hand to clients.",
    matters: "Agencies need client-facing deliverables that look like theirs, not ours.",
    needed: "Report export plus branding controls.",
    connects: "A branded skin over the proof report, using your real client data.",
  }),
  shareable: soon("Shareable links", {
    does: "Share a read-only result or proof page via a link — no login required for the recipient.",
    matters: "Lets clients and stakeholders see the evidence without an account.",
    needed: "Public read-only sharing with safe, scoped access.",
    connects: "Exposes an existing result as a clean, client-safe view.",
  }),
  team: soon("Team access", {
    does: "Invite teammates with roles, so a team can manage businesses together.",
    matters: "Real agencies and companies have more than one person.",
    needed: "Authentication, accounts and role management (today uses a local workspace key).",
    connects: "Wraps the current workspace in real multi-user accounts.",
  }),
  integrations: soon("Integrations", {
    does: "Connect AI Visibility OS to the tools you already use — CMS, Google Business Profile, Slack, Zapier and more.",
    matters: "Less manual work, and a path toward applying fixes and alerts where you already work.",
    needed: "A connector framework and per-integration APIs.",
    connects: "Becomes the bridge between insight here and execution in your stack.",
  }),
  diagnostics: soon("Technical diagnostics", {
    does: "Operator-grade view of latency, cost, failures and engine health for power users and developers.",
    matters: "Trust and debuggability — see exactly what the system did and what it cost.",
    needed: "A read endpoint exposing the internal diagnostics already captured.",
    connects: "Surfaces the technical receipts behind every run, separate from the business view.",
  }),
};

function RoadGroup({ title, items, tone }: { title: string; items: string[]; tone: "teal" | "amber" | "violet" | "neutral" }) {
  return (
    <div>
      <div className="mb-1.5"><Chip tone={tone as never}>{title}</Chip></div>
      <ul className="list-disc space-y-1 pl-5">{items.map((i) => <L key={i}>{i}</L>)}</ul>
    </div>
  );
}

function fallback(key: string): Entry {
  const title = key.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return soon(title, {
    does: "This capability is planned as part of AI Visibility OS.",
    matters: "We're building it so it's genuinely useful to business owners and agencies.",
    needed: "Backend support is still being finalized — and we won't show fabricated data before it's real.",
    connects: "It will build on the real analysis, evidence and history the product already produces.",
  });
}

export function Learn({ contentKey }: { contentKey: string }) {
  const e = CONTENT[contentKey] ?? fallback(contentKey);
  return (
    <div className="mx-auto max-w-2xl">
      <button onClick={() => navigate("#/dashboard")} className="mb-3 text-sm text-text-muted hover:text-text-secondary">← Dashboard</button>
      <div className="mb-4 flex items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight text-text-primary">{e.title}</h1>
        {e.kind === "soon" && <PreviewBadge label="Coming soon" />}
      </div>
      <Card className="p-6">{e.body}</Card>
      <div className="mt-4 flex gap-3">
        {e.kind === "soon" && <Button onClick={() => navigate("#/onboarding")}>Run an AI Visibility Check now</Button>}
        <Button variant="ghost" onClick={() => navigate("#/soon/roadmap")}>See the full roadmap</Button>
      </div>
    </div>
  );
}
