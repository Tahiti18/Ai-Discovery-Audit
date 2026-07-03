/**
 * Visible to AI — the probe report screen (new design).
 *
 * Presentational and pure: it renders REAL backend data passed as props, plus a
 * small amount of honest interpretation (discovery vs brand, evidence tagging,
 * competitor bars). No fetching here — a container wires it to the API + auth
 * later. Every number is derived from the data; nothing is fabricated.
 */
import { useMemo, useState } from "react";
import type { Entity, ProbeRun, Perception } from "../../lib/platformApi";

/** A recommended next action — computed by the container from audit + probe. */
export interface Move {
  title: string;
  body: string;
  why: string;
  impact: "high" | "medium";
  impactLabel: string; // e.g. "High impact" / "Worth doing"
}

export interface ReportData {
  entity: Entity;
  run: ProbeRun;
  responses: Perception[];
  moves: Move[];
  /** Static link to the technical audit (used by the preview). */
  technicalReportHref?: string;
  /** Live: generate the technical report on demand (authed) and write it into
   *  the already-opened target window. The window is opened synchronously on
   *  click so the browser's popup blocker doesn't kill it. */
  onDownloadTechnical?: (target: Window | null) => Promise<void>;
  technicalScore?: number | null;
  /** Where "My businesses" / the logo lead. App: "/app/". Public sample: "/". */
  homeHref?: string;
  /** Start a fresh check for this business (app only). When absent — the public
   *  sample — run-again affordances become a "check my business" signup CTA. */
  onRunAgain?: () => void;
}

// Discovery = no-name buyer questions (Share-of-Model is computed from these).
// `comparison` embeds the brand name so it is NOT discovery, even though it
// used to be misclassified as one here — that caused the "2 of 5" vs "25%"
// math mismatch.
const DISCOVERY_CATEGORIES = new Set([
  "category_recommendation",
  "problem_solution",
]);

// Four semantic outcomes. Order matters for display: reds/ambers first (the
// actionable findings), greens last (the wins).
type Tag = "not-mentioned" | "wrong" | "brand-check" | "mentioned";

function tagOf(p: Perception): Tag {
  const discovery = DISCOVERY_CATEGORIES.has(p.prompt_category ?? "");
  if ((p.flags?.length ?? 0) > 0) return "wrong";
  if (discovery) return p.brand_mentioned ? "mentioned" : "not-mentioned";
  return "brand-check";
}

const TAG_STYLE: Record<Tag, { label: string; bg: string; fg: string }> = {
  "not-mentioned": { label: "Not mentioned", bg: "var(--vta-red-soft)", fg: "#FCA5A5" },
  "wrong":         { label: "Gets it wrong", bg: "var(--vta-amber-soft)", fg: "#FCD34D" },
  "mentioned":     { label: "You appeared",  bg: "var(--vta-green-soft)", fg: "#6EE7B7" },
  "brand-check":   { label: "Brand check",   bg: "var(--vta-accent-soft-bg)", fg: "var(--vta-accent-soft-text)" },
};

const TAG_ORDER: Tag[] = ["not-mentioned", "wrong", "mentioned", "brand-check"];

const TAG_GROUP_COPY: Record<Tag, { title: string; sub: string }> = {
  "not-mentioned": {
    title: "You weren't in the answer",
    sub: "Discovery questions where AI recommended other businesses — the visibility you're losing.",
  },
  "wrong": {
    title: "AI got something wrong",
    sub: "Answers where AI gave incorrect facts about your business — fix the source and the AI updates.",
  },
  "mentioned": {
    title: "You appeared in discovery",
    sub: "Discovery questions where AI named you unprompted — the visibility you're winning.",
  },
  "brand-check": {
    title: "What AI knows about you by name",
    sub: "Baseline check — what AI says when a buyer already knows your business name.",
  },
};

export function ReportScreen({ data }: { data: ReportData }) {
  const { entity, run, responses, moves, technicalReportHref, onDownloadTechnical, technicalScore, onRunAgain } = data;
  const home = data.homeHref ?? "/app/";

  // Strip parenthetical labels from the entity name for report copy — the owner
  // may have added "(new site)"/"(staging)" to distinguish it in the dashboard,
  // but that label makes the verdict text read weirdly ("never named Era More
  // Than Gold (new site)"). The dashboard list keeps the labelled name.
  const brandName = useMemo(
    () => (entity.canonical_name || "").replace(/\s*\([^)]*\)\s*/g, " ").replace(/\s+/g, " ").trim() || entity.canonical_name,
    [entity.canonical_name],
  );

  const derived = useMemo(() => {
    // Single source of truth = the responses actually rendered on this page.
    // Using run.share_of_model here caused the "25% vs 2 of 5" mismatch
    // because the backend and the frontend counted "discovery" differently.
    const discovery = responses.filter((r) => DISCOVERY_CATEGORIES.has(r.prompt_category ?? ""));
    const discoveryHits = discovery.filter((r) => r.brand_mentioned).length;
    const discoveryPct = discovery.length ? Math.round((discoveryHits / discovery.length) * 100) : 0;
    const brandChecks = responses.filter((r) => !DISCOVERY_CATEGORIES.has(r.prompt_category ?? ""));
    const brandHits = brandChecks.filter((r) => r.brand_mentioned).length;
    const brandStrong = brandChecks.length > 0 && brandHits >= Math.ceil(brandChecks.length / 2);
    const competitors = (run.competitors ?? []).slice(0, 10);
    const maxMentions = competitors.reduce((m, c) => Math.max(m, c.mentions), 1);
    // All responses grouped by outcome, red/amber first so the actionable
    // findings are at the top and greens are the "wins" tail.
    const tagged = responses.map((r) => ({ p: r, tag: tagOf(r) }));
    const evidenceGroups = TAG_ORDER
      .map((tag) => ({ tag, rows: tagged.filter((x) => x.tag === tag) }))
      .filter((g) => g.rows.length > 0);
    // Misinformation findings surfaced by the LLM fact-checker.
    const misinformation = (run.flags ?? []).filter((f) => f.source === "llm_misinformation");
    return { discoveryPct, brandStrong, competitors, maxMentions, evidenceGroups, discoveryHits, discoveryTotal: discovery.length, misinformation };
  }, [run, responses]);

  const cityCat = [entity.category, entity.geo].filter(Boolean).join(" · ");
  const checkedLine = [
    run.provider === "openrouter" ? "Perplexity (web-grounded)" : run.provider,
    `${run.answered_count} of ${run.prompt_count} questions answered`,
    run.completed_at ? fmtDate(run.completed_at) : "",
  ].filter(Boolean).join(" · ");

  return (
    <div className="vta">
      <div className="fixed inset-0 pointer-events-none v-glow" aria-hidden="true" />
      <div className="relative">
        {/* Top bar */}
        <nav className="border-b v-border-hair sticky top-0 z-50" style={{ background: "rgba(10,10,18,0.85)", backdropFilter: "blur(12px)" }}>
          <div className="max-w-5xl mx-auto px-6 py-3.5 flex items-center justify-between">
            <a href={home} className="flex items-center gap-2.5" style={{ textDecoration: "none", color: "inherit" }}>
              <svg width="24" height="18" viewBox="0 0 32 24" fill="none" aria-hidden="true" style={{ filter: "drop-shadow(0 0 10px rgba(167,139,250,0.25))" }}>
                <path d="M 2 12 Q 16 2, 30 12 Q 16 22, 2 12 Z" stroke="#A78BFA" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="16" cy="12" r="3.5" fill="#A78BFA" />
              </svg>
              <span style={{ fontFamily: "'Playfair Display Variable',Georgia,serif", fontWeight: 500, fontSize: 17 }}>
                Visible <em style={{ fontStyle: "italic" }}>to</em> <span style={{ color: "var(--vta-accent)" }}>AI</span>
              </span>
            </a>
            <div className="flex items-center gap-6">
              <a href={home} className="v-navlink hidden sm:block">{onRunAgain ? "My businesses" : "Home"}</a>
              {onRunAgain ? (
                <button onClick={onRunAgain} className="v-btn v-btn-ghost" style={{ padding: "7px 14px", fontSize: 13 }}>Run again</button>
              ) : (
                <a href="/login/" className="v-btn v-btn-ghost" style={{ padding: "7px 14px", fontSize: 13 }}>Check my business →</a>
              )}
            </div>
          </div>
        </nav>

        <main className="max-w-5xl mx-auto px-6 pb-24">
          {/* Business header */}
          <div className="pt-8">
            <a href={home} className="v-navlink" style={{ fontSize: 13 }}>← {onRunAgain ? "My businesses" : "Home"}</a>
            <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="v-display" style={{ fontSize: "clamp(28px,5vw,38px)" }}>{brandName}</h1>
                <p className="v-text-secondary mt-1" style={{ fontSize: 14 }}>
                  {hostOf(entity.website_url)}{cityCat ? ` · ${cityCat}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className="v-label mb-1.5">Checked</p>
                <p className="v-text-secondary" style={{ fontSize: 13 }}>{checkedLine}</p>
              </div>
            </div>
          </div>

          {/* THE VERDICT */}
          <section className="v-card mt-7 overflow-hidden">
            <div className="p-6 md:p-8 v-surface-2 border-b v-border-hair">
              <div className="grid md:grid-cols-[180px_1fr] gap-8 items-center">
                <Gauge pct={derived.discoveryPct} />
                <div>
                  {derived.discoveryPct === 0 ? (
                    <span className="v-pill" style={{ background: "var(--vta-red-soft)", color: "#FCA5A5" }}>
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--vta-red)" }} />Not getting recommended
                    </span>
                  ) : (
                    <span className="v-pill" style={{ background: "var(--vta-accent-soft-bg)", color: "var(--vta-accent-soft-text)" }}>
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--vta-accent)" }} />Discovery visibility
                    </span>
                  )}
                  <h2 className="v-display mt-4" style={{ fontSize: "clamp(22px,3.4vw,28px)" }}>
                    When customers ask AI for the best {entity.category} in {entity.geo || "your area"},{" "}
                    <span className="v-grad">{derived.discoveryPct === 0 ? "you're not in the answer." : `you appear ${derived.discoveryPct}% of the time.`}</span>
                  </h2>
                  <p className="v-text-secondary mt-3 leading-relaxed" style={{ fontSize: 15 }}>
                    {derived.discoveryHits === 0
                      ? `Across ${derived.discoveryTotal} "best ${entity.category} in ${entity.geo}"–style questions, AI named other businesses and never named ${brandName}. That's the visibility you're losing to competitors right now.`
                      : `You showed up in ${derived.discoveryHits} of ${derived.discoveryTotal} discovery questions${derived.discoveryPct < 50 ? ` — the other ${derived.discoveryTotal - derived.discoveryHits} handed a competitor to your customer instead.` : ` — a solid share, but there's still room to widen it.`}`}
                  </p>
                </div>
              </div>
            </div>

            {/* The gap */}
            <div className="p-6 md:p-8">
              <p className="v-label mb-4">The gap — and the opportunity</p>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="rounded-xl p-5" style={{ background: "var(--vta-bg-elevated)", border: "1px solid var(--vta-red-soft)" }}>
                  <div className="flex items-center justify-between mb-2">
                    <span style={{ fontSize: 14, fontWeight: 500 }}>When buyers <em>don't</em> name you</span>
                    <span className="v-tabular" style={{ fontSize: 22, fontWeight: 500, color: "var(--vta-red)" }}>{derived.discoveryPct}%</span>
                  </div>
                  <p className="v-text-secondary leading-relaxed" style={{ fontSize: 13 }}>
                    "Best {entity.category} in {entity.geo}?" — {derived.discoveryPct === 0
                      ? "AI names competitors instead. You're invisible to customers who don't already know you."
                      : derived.discoveryPct < 25
                        ? "AI rarely names you. Most customers who don't already know you never hear about you from AI."
                        : derived.discoveryPct < 50
                          ? "AI names you some of the time, competitors the rest. Plenty of room to widen your share."
                          : "AI names you often — you're already winning the majority of no-name buyer searches."}
                  </p>
                </div>
                <div className="rounded-xl p-5" style={{ background: "var(--vta-bg-elevated)", border: `1px solid ${derived.brandStrong ? "var(--vta-green-soft)" : "var(--vta-amber-soft)"}` }}>
                  <div className="flex items-center justify-between mb-2">
                    <span style={{ fontSize: 14, fontWeight: 500 }}>When buyers <em>do</em> name you</span>
                    <span style={{ fontSize: 15, fontWeight: 500, color: derived.brandStrong ? "var(--vta-green)" : "var(--vta-amber)" }}>{derived.brandStrong ? "Strong ✓" : "Mixed"}</span>
                  </div>
                  <p className="v-text-secondary leading-relaxed" style={{ fontSize: 13 }}>
                    "Is {brandName} reputable?" — AI {derived.brandStrong ? "describes you accurately and well. It knows you're a real, trusted business." : "has gaps in what it knows about you."}
                  </p>
                </div>
              </div>
              {derived.brandStrong && derived.discoveryPct < 50 && (
                <p className="v-text-secondary mt-4 leading-relaxed" style={{ fontSize: 14 }}>
                  <strong style={{ color: "var(--vta-text-primary)" }}>This is the whole story:</strong> AI rates you highly when someone already knows your name — but
                  {derived.discoveryPct === 0
                    ? " never puts you forward to someone who doesn't."
                    : ` only puts you forward ${derived.discoveryPct}% of the time to someone who doesn't.`}
                  {" "}That's a fixable visibility problem, not a reputation problem.
                </p>
              )}
            </div>
          </section>

          {/* WHAT AI IS GETTING WRONG — flag high-severity misinformation prominently */}
          {derived.misinformation.length > 0 && (
            <section className="v-card mt-6 overflow-hidden" style={{ borderColor: "var(--vta-amber-soft)" }}>
              <div className="p-6 md:p-7" style={{ background: "var(--vta-amber-soft)" }}>
                <div className="flex items-center gap-2 mb-1">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--vta-amber)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                  <h3 className="v-display" style={{ fontSize: "clamp(20px,2.6vw,24px)", color: "var(--vta-text-primary)" }}>
                    AI is telling buyers things about you that aren't true
                  </h3>
                </div>
                <p className="v-text-secondary" style={{ fontSize: 14 }}>
                  {derived.misinformation.length} misstatement{derived.misinformation.length === 1 ? "" : "s"} detected against your current homepage. Fix each source and AI's next crawl corrects itself.
                </p>
              </div>
              <div className="divide-y v-border-hair">
                {derived.misinformation.map((m, i) => (
                  <div key={i} className="p-5 md:p-6">
                    <div className="flex flex-wrap items-baseline gap-2 mb-2">
                      <span style={{ fontSize: 15, fontWeight: 500 }}>{m.description}</span>
                      <span className="v-pill" style={m.severity === "high" ? { background: "var(--vta-red-soft)", color: "#FCA5A5" } : m.severity === "medium" ? { background: "var(--vta-amber-soft)", color: "#FCD34D" } : { background: "var(--vta-surface-2)", color: "var(--vta-text-secondary)" }}>
                        {m.severity === "high" ? "High severity" : m.severity === "medium" ? "Worth fixing" : "Nice to fix"}
                      </span>
                    </div>
                    {m.evidence && (
                      <p className="v-text-muted italic mb-2" style={{ fontSize: 13 }}>
                        AI said: "{clip(m.evidence, 200)}"
                      </p>
                    )}
                    {m.fix && (
                      <p className="v-text-secondary" style={{ fontSize: 14 }}>
                        <strong style={{ color: "var(--vta-text-primary)" }}>Fix:</strong> {m.fix}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Next moves */}
          {moves.length > 0 && (
            <section className="mt-8">
              <h3 className="v-display mb-5" style={{ fontSize: "clamp(22px,3vw,26px)" }}>Your next {moves.length} moves</h3>
              <div className="space-y-3">
                {moves.map((m, i) => (
                  <div key={i} className="v-card p-5 md:p-6 flex gap-5">
                    <div className="v-move-num v-accent flex-shrink-0">{i + 1}</div>
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-1.5">
                        <span style={{ fontSize: 16, fontWeight: 500 }}>{m.title}</span>
                        <span className="v-pill" style={m.impact === "high" ? { background: "var(--vta-red-soft)", color: "#FCA5A5" } : { background: "var(--vta-amber-soft)", color: "#FCD34D" }}>{m.impactLabel}</span>
                      </div>
                      <p className="v-text-secondary leading-relaxed" style={{ fontSize: 14 }}>{m.body}</p>
                      <p className="v-text-muted mt-2" style={{ fontSize: 13 }}>{m.why}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Competitors */}
          {derived.competitors.length > 0 && (
            <section className="v-card mt-8 p-6 md:p-7">
              <div className="flex items-center justify-between mb-1">
                <h3 className="v-display" style={{ fontSize: "clamp(20px,2.6vw,24px)" }}>Who AI recommends instead</h3>
                <span className="v-pill" style={{ background: "var(--vta-surface-2)", color: "var(--vta-text-secondary)" }}>Your AI-era rivals</span>
              </div>
              <p className="v-text-secondary mb-5" style={{ fontSize: 14 }}>The businesses AI actually named when your customers asked — ranked by how often they came up.</p>
              <div className="space-y-2.5">
                {derived.competitors.map((c) => (
                  <div key={c.name} className="flex items-center gap-3">
                    <span className="w-48 truncate" style={{ fontSize: 14 }}>{c.name}</span>
                    <div className="flex-1 h-2 rounded-full" style={{ background: "var(--vta-surface-2)" }}>
                      <div className="h-full rounded-full" style={{ width: `${Math.max(8, (c.mentions / derived.maxMentions) * 100)}%`, background: "linear-gradient(90deg,var(--vta-accent),#E879F9)" }} />
                    </div>
                    <span className="v-text-muted w-20 text-right" style={{ fontSize: 13 }}>{c.mentions} mention{c.mentions === 1 ? "" : "s"}</span>
                  </div>
                ))}
              </div>
              <p className="v-text-muted mt-4" style={{ fontSize: 12 }}>Grouped from what AI said — observations, not verified competitive facts.</p>
            </section>
          )}

          {/* Evidence — every question, grouped by outcome, actionable groups first */}
          {derived.evidenceGroups.length > 0 && (
            <section className="mt-8">
              <h3 className="v-display mb-2" style={{ fontSize: "clamp(22px,3vw,26px)" }}>Every question we asked AI</h3>
              <p className="v-text-secondary mb-6" style={{ fontSize: 14 }}>
                No score to take on faith — every question and every answer, grouped by what happened. Click any row to read what AI actually said.
              </p>
              <div className="space-y-8">
                {derived.evidenceGroups.map(({ tag, rows }) => {
                  const s = TAG_STYLE[tag];
                  const copy = TAG_GROUP_COPY[tag];
                  return (
                    <div key={tag}>
                      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <h4 style={{ fontSize: 16, fontWeight: 500 }}>{copy.title}</h4>
                        <span className="v-pill" style={{ background: s.bg, color: s.fg }}>
                          {rows.length} {rows.length === 1 ? "question" : "questions"}
                        </span>
                      </div>
                      <p className="v-text-secondary mb-3" style={{ fontSize: 13 }}>{copy.sub}</p>
                      <div className="space-y-2">
                        {rows.map(({ p }) => (
                          <details key={p.id} className="v-card overflow-hidden">
                            <summary className="p-4 flex items-start gap-3">
                              <span className="v-tabular mt-0.5 v-text-muted" style={{ fontSize: 12, minWidth: 14 }}>›</span>
                              <span className="flex-1" style={{ fontSize: 14.5, fontWeight: 500 }}>"{p.prompt}"</span>
                              <svg className="v-chev mt-1 flex-shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--vta-text-muted)" strokeWidth="2"><polyline points="9 18 15 12 9 6" /></svg>
                            </summary>
                            <div className="px-4 pb-4 v-text-secondary leading-relaxed border-t v-border-hair pt-3" style={{ fontSize: 13.5 }}>
                              {clip(p.raw_response, 900)}
                            </div>
                          </details>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Technical report download */}
          {(technicalReportHref || onDownloadTechnical) && (
            <section className="v-card mt-8 p-6 md:p-7" style={{ borderColor: "var(--vta-border-accent)" }}>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex-1" style={{ minWidth: 260 }}>
                  <p className="v-label mb-2">For your developer</p>
                  <h3 className="v-display" style={{ fontSize: "clamp(20px,2.4vw,22px)" }}>The full technical audit{technicalScore != null ? ` — ${technicalScore}/100` : ""}</h3>
                  <p className="v-text-secondary mt-2 leading-relaxed" style={{ fontSize: 14 }}>A technical deep-dive your web person can act on directly: schema, llms.txt, crawler access, per-engine scores, and the exact fixes — all 19 sections.</p>
                </div>
                <DownloadButton href={technicalReportHref} onDownload={onDownloadTechnical} />
              </div>
            </section>
          )}

          {/* Methodology */}
          <section className="mt-8">
            <details style={{ fontSize: 13, color: "var(--vta-text-muted)" }}>
              <summary className="v-navlink inline-flex items-center gap-2">
                <svg className="v-chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6" /></svg> How we measured this
              </summary>
              <div className="mt-3 leading-relaxed max-w-2xl space-y-2">
                <p>We asked a live, web-grounded AI engine {run.answered_count} realistic buyer questions for your category and city — some "discovery" questions that don't name you, and some "brand-check" questions that do. <strong style={{ color: "var(--vta-text-secondary)" }}>Discovery Visibility</strong> is the share of no-name questions where AI independently named you.</p>
                <p>Results are a small, single-engine, point-in-time sample — directional, not a guarantee. Run it again over time to confirm a change is real. We never invent numbers or citations.</p>
              </div>
            </details>
          </section>

          <div className="mt-10 flex flex-wrap gap-3">
            {onRunAgain ? (
              <button onClick={onRunAgain} className="v-btn v-btn-primary">Run this check again</button>
            ) : (
              <a href="/login/" className="v-btn v-btn-primary">Run this check on my business →</a>
            )}
            <a href={home} className="v-btn v-btn-ghost">{onRunAgain ? "Back to my businesses" : "Back to the homepage"}</a>
          </div>
        </main>
      </div>
    </div>
  );
}

const LOADING_DOC =
  '<!doctype html><meta charset="utf-8"><title>Generating…</title>' +
  '<body style="background:#0A0A12;color:#A1A1AA;font-family:Inter,system-ui,sans-serif;' +
  'display:grid;place-items:center;height:100vh;margin:0">' +
  '<div>Generating your technical report… this takes about 15 seconds.</div></body>';

function DownloadButton({ href, onDownload }: { href?: string; onDownload?: (target: Window | null) => Promise<void> }) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (href) {
    return <a href={href} target="_blank" rel="noreferrer" className="v-btn v-btn-primary">Open technical report →</a>;
  }
  if (!onDownload) return null;
  return (
    <div className="text-right">
      <button
        className="v-btn v-btn-primary"
        disabled={loading}
        style={{ opacity: loading ? 0.7 : 1 }}
        onClick={async () => {
          // Open the tab synchronously (inside the click) so it isn't popup-blocked,
          // show a placeholder, then fill it with the generated report.
          const win = window.open("", "_blank");
          if (win) win.document.write(LOADING_DOC);
          setLoading(true); setErr(null);
          try {
            await onDownload(win);
          } catch (e) {
            if (win) win.close();
            setErr(e instanceof Error ? e.message : "Couldn't generate the report.");
          }
          setLoading(false);
        }}
      >
        {loading ? "Generating… (~15s)" : "Open technical report →"}
      </button>
      <p style={{ color: "var(--vta-text-muted)", fontSize: 12, marginTop: 6, maxWidth: 260 }}>
        Opens the full 19-section audit. Use “Save as PDF” on that page to download it.
      </p>
      {err && <p style={{ color: "var(--vta-red)", fontSize: 12, marginTop: 6, maxWidth: 260 }}>{err}</p>}
    </div>
  );
}

function Gauge({ pct }: { pct: number }) {
  const C = 2 * Math.PI * 52;
  const filled = (Math.max(0, Math.min(100, pct)) / 100) * C;
  const color = pct === 0 ? "var(--vta-red)" : pct < 50 ? "var(--vta-amber)" : "var(--vta-green)";
  return (
    <div className="text-center md:text-left">
      <div className="relative inline-flex items-center justify-center" style={{ width: 150, height: 150 }}>
        <svg viewBox="0 0 120 120" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
          <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="8" />
          <circle cx="60" cy="60" r="52" fill="none" stroke={color} strokeWidth="8" strokeDasharray={`${filled} ${C}`} strokeLinecap="round" />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="v-tabular" style={{ fontSize: 44, fontWeight: 500, lineHeight: 1, color }}>{pct}<span style={{ fontSize: 22 }}>%</span></span>
          <span className="v-label mt-1.5">Discovery</span>
        </div>
      </div>
    </div>
  );
}

// ─── helpers ─────────────────────────────────────────────────────────────────
function hostOf(url: string): string {
  try { return new URL(url.includes("://") ? url : `https://${url}`).hostname.replace(/^www\./, ""); }
  catch { return url; }
}
function clip(s: string | null, n: number): string {
  if (!s) return "(no answer returned)";
  return s.length > n ? s.slice(0, n).trimEnd() + " …" : s;
}
function fmtDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }); }
  catch { return iso; }
}
