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
}

// Discovery = no-name buyer questions (the commercially important ones).
const DISCOVERY_CATEGORIES = new Set([
  "category_recommendation",
  "problem_solution",
  "comparison",
]);

type Tag = "not-mentioned" | "accurate" | "wrong";

function tagOf(p: Perception): Tag {
  const discovery = DISCOVERY_CATEGORIES.has(p.prompt_category ?? "");
  if (discovery && !p.brand_mentioned) return "not-mentioned";
  if ((p.flags?.length ?? 0) > 0) return "wrong";
  return "accurate";
}

const TAG_STYLE: Record<Tag, { label: string; bg: string; fg: string }> = {
  "not-mentioned": { label: "Not mentioned", bg: "var(--vta-red-soft)", fg: "#FCA5A5" },
  accurate: { label: "Accurate", bg: "var(--vta-green-soft)", fg: "#6EE7B7" },
  wrong: { label: "Gets it wrong", bg: "var(--vta-amber-soft)", fg: "#FCD34D" },
};

export function ReportScreen({ data }: { data: ReportData }) {
  const { entity, run, responses, moves, technicalReportHref, onDownloadTechnical, technicalScore } = data;

  const derived = useMemo(() => {
    const discovery = responses.filter((r) => DISCOVERY_CATEGORIES.has(r.prompt_category ?? ""));
    const discoveryHits = discovery.filter((r) => r.brand_mentioned).length;
    const discoveryPct =
      run.share_of_model != null
        ? Math.round(run.share_of_model * 100)
        : discovery.length
          ? Math.round((discoveryHits / discovery.length) * 100)
          : 0;
    const brandChecks = responses.filter((r) => !DISCOVERY_CATEGORIES.has(r.prompt_category ?? ""));
    const brandHits = brandChecks.filter((r) => r.brand_mentioned).length;
    const brandStrong = brandChecks.length > 0 && brandHits >= Math.ceil(brandChecks.length / 2);
    const competitors = (run.competitors ?? []).slice(0, 5);
    const maxMentions = competitors.reduce((m, c) => Math.max(m, c.mentions), 1);
    // Evidence: prefer a spread — a couple of "not mentioned", one accurate, one wrong.
    const tagged = responses.map((r) => ({ p: r, tag: tagOf(r) }));
    const pick = (t: Tag, n: number) => tagged.filter((x) => x.tag === t).slice(0, n);
    const evidence = [...pick("not-mentioned", 2), ...pick("accurate", 1), ...pick("wrong", 1)];
    return { discoveryPct, brandStrong, competitors, maxMentions, evidence, discoveryHits, discoveryTotal: discovery.length };
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
            <div className="flex items-center gap-2.5">
              <svg width="24" height="18" viewBox="0 0 32 24" fill="none" aria-hidden="true" style={{ filter: "drop-shadow(0 0 10px rgba(167,139,250,0.25))" }}>
                <path d="M 2 12 Q 16 2, 30 12 Q 16 22, 2 12 Z" stroke="#A78BFA" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="16" cy="12" r="3.5" fill="#A78BFA" />
              </svg>
              <span style={{ fontFamily: "'Playfair Display Variable',Georgia,serif", fontWeight: 500, fontSize: 17 }}>
                Visible <em style={{ fontStyle: "italic" }}>to</em> <span style={{ color: "var(--vta-accent)" }}>AI</span>
              </span>
            </div>
            <div className="flex items-center gap-6">
              <a href="#" className="v-navlink hidden sm:block">My businesses</a>
              <a href="#" className="v-btn v-btn-ghost" style={{ padding: "7px 14px", fontSize: 13 }}>Run again</a>
            </div>
          </div>
        </nav>

        <main className="max-w-5xl mx-auto px-6 pb-24">
          {/* Business header */}
          <div className="pt-8">
            <a href="#" className="v-navlink" style={{ fontSize: 13 }}>← My businesses</a>
            <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="v-display" style={{ fontSize: "clamp(28px,5vw,38px)" }}>{entity.canonical_name}</h1>
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
                    Across the "best {entity.category} in {entity.geo}" style questions, AI named{" "}
                    {derived.discoveryHits === 0 ? "other businesses — never " : "you in some answers and competitors in others, including "}
                    {entity.canonical_name}{derived.discoveryHits === 0 ? "." : "."} That's the visibility you're {derived.discoveryPct < 50 ? "losing to competitors" : "building"} right now.
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
                    "Best {entity.category} in {entity.geo}?" — AI {derived.discoveryPct === 0 ? "names competitors" : "sometimes names you"}. You're {derived.discoveryPct < 50 ? "largely invisible" : "partly visible"} to customers who don't already know you.
                  </p>
                </div>
                <div className="rounded-xl p-5" style={{ background: "var(--vta-bg-elevated)", border: `1px solid ${derived.brandStrong ? "var(--vta-green-soft)" : "var(--vta-amber-soft)"}` }}>
                  <div className="flex items-center justify-between mb-2">
                    <span style={{ fontSize: 14, fontWeight: 500 }}>When buyers <em>do</em> name you</span>
                    <span style={{ fontSize: 15, fontWeight: 500, color: derived.brandStrong ? "var(--vta-green)" : "var(--vta-amber)" }}>{derived.brandStrong ? "Strong ✓" : "Mixed"}</span>
                  </div>
                  <p className="v-text-secondary leading-relaxed" style={{ fontSize: 13 }}>
                    "Is {entity.canonical_name} reputable?" — AI {derived.brandStrong ? "describes you accurately and well. It knows you're a real, trusted business." : "has gaps in what it knows about you."}
                  </p>
                </div>
              </div>
              {derived.brandStrong && derived.discoveryPct < 50 && (
                <p className="v-text-secondary mt-4 leading-relaxed" style={{ fontSize: 14 }}>
                  <strong style={{ color: "var(--vta-text-primary)" }}>This is the whole story:</strong> AI rates you highly when someone already knows your name — but never puts you forward to someone who doesn't. That's a fixable visibility problem, not a reputation problem.
                </p>
              )}
            </div>
          </section>

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

          {/* Evidence */}
          {derived.evidence.length > 0 && (
            <section className="mt-8">
              <h3 className="v-display mb-2" style={{ fontSize: "clamp(22px,3vw,26px)" }}>The actual AI answers</h3>
              <p className="v-text-secondary mb-5" style={{ fontSize: 14 }}>No score to take on faith — here's exactly what AI said when asked about businesses like yours.</p>
              <div className="space-y-3">
                {derived.evidence.map(({ p, tag }) => {
                  const s = TAG_STYLE[tag];
                  return (
                    <details key={p.id} className="v-card overflow-hidden">
                      <summary className="p-5 flex items-start gap-3">
                        <span className="v-pill mt-0.5" style={{ background: s.bg, color: s.fg }}>{s.label}</span>
                        <span className="flex-1" style={{ fontSize: 15, fontWeight: 500 }}>"{p.prompt}"</span>
                        <svg className="v-chev mt-1 flex-shrink-0" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--vta-text-muted)" strokeWidth="2"><polyline points="9 18 15 12 9 6" /></svg>
                      </summary>
                      <div className="px-5 pb-5 v-text-secondary leading-relaxed border-t v-border-hair pt-4" style={{ fontSize: 14 }}>
                        {clip(p.raw_response, 460)}
                      </div>
                    </details>
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
            <a href="#" className="v-btn v-btn-primary">Run this check again</a>
            <a href="#" className="v-btn v-btn-ghost">Back to my businesses</a>
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
