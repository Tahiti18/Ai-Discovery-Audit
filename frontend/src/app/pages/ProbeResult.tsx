/**
 * The probe result, presented like a strategic advisor — interpretation BEFORE
 * data. Order: Executive Summary → What this means → Your next 3 actions →
 * Metrics → Domains (collapsed) → Raw answers → Methodology.
 *
 * Every word is derived from REAL backend data (prompt_category, brand_mentioned,
 * flags, citations). Nothing fabricated; unsupported actions are Preview.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api, pollProbe, type Entity, type Perception, type ProbeRun, type PollHandle,
} from "../../lib/platformApi";
import { navigate } from "../router";
import { promptType, domainBucket, DOMAIN_BUCKET_LABEL, type DomainBucket, type PromptGroup } from "../classify";
import {
  Button, Card, Caveat, Chip, ErrorState, ExplainButton, Gauge, LoadingState, MethodologyNote,
  PreviewBadge, ProvenanceLine, SeverityChip, downloadJson, fmtDate, type ChipTone,
} from "../ui";
import type { ReactNode } from "react";

export function ProbeResult({ runId }: { runId: string }) {
  const [run, setRun] = useState<ProbeRun | null>(null);
  const [responses, setResponses] = useState<Perception[] | null>(null);
  const [entity, setEntity] = useState<Entity | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsErr, setDetailsErr] = useState<string | null>(null);
  const pollRef = useRef<PollHandle | null>(null);

  // Per-prompt answers load SEPARATELY from the run status, so a slow or failed
  // /responses call degrades to a retryable detail-error instead of failing the
  // whole page.
  const loadDetails = useCallback(async (r: ProbeRun) => {
    setDetailsLoading(true); setDetailsErr(null);
    const [resp, ent] = await Promise.all([api.getProbeResponses(r.id), api.getEntity(r.entity_id)]);
    setDetailsLoading(false);
    if (resp.error) { setDetailsErr(resp.error); return; }
    setResponses(resp.data ?? []);
    if (!ent.error) setEntity(ent.data ?? null);
  }, []);

  const startPolling = useCallback(() => {
    setRun(null); setResponses(null); setEntity(null);
    setErr(null); setDetailsErr(null); setReconnecting(false);
    pollRef.current?.cancel();
    pollRef.current = pollProbe(runId, {
      onTick: (r) => { setRun(r); setReconnecting(false); },
      onTransient: () => setReconnecting(true),         // tolerated hiccup, keep the running page
      onError: (m) => setErr(m),                         // sustained failure only
      onDone: (r) => {
        setRun(r); setReconnecting(false);
        if (r.status === "complete" || r.status === "failed") void loadDetails(r);
      },
    });
  }, [runId, loadDetails]);

  useEffect(() => {
    startPolling();
    return () => pollRef.current?.cancel();
  }, [startPolling]);

  // Sustained failure reaching the run itself → recoverable with Retry / Back.
  if (err)
    return (
      <ErrorState
        title="Couldn't load this analysis"
        detail={err}
        action={
          <div className="flex flex-wrap gap-2">
            <Button onClick={startPolling}>Retry</Button>
            <Button variant="ghost" onClick={() => navigate("#/dashboard")}>Back to dashboard</Button>
          </div>
        }
      />
    );
  // Still working (or a brief reconnect) → the running page, never "couldn't load".
  if (!run || run.status === "queued" || run.status === "running") return <RunningState run={run} reconnecting={reconnecting} />;

  // Terminal run, but the per-prompt answers are still loading → finalizing, not an error.
  if (responses === null && detailsLoading) return <RunningState run={run} finalizing />;

  // The answers failed to load (e.g. a slow /responses). Don't fail the whole page —
  // offer a Retry that re-fetches only the details, plus Back to business.
  if (responses === null && detailsErr)
    return (
      <div className="mx-auto max-w-2xl">
        <button onClick={() => navigate(`#/e/${run.entity_id}`)} className="mb-4 text-sm text-text-muted hover:text-text-secondary">← Back to business</button>
        <ErrorState
          title="Couldn't load the detailed answers"
          detail={detailsErr}
          action={
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => loadDetails(run)}>Retry</Button>
              <Button variant="ghost" onClick={() => navigate(`#/e/${run.entity_id}`)}>Back to business</Button>
            </div>
          }
        />
      </div>
    );
  // Terminal but details not yet in flight (initial frame) → finalizing.
  if (responses === null) return <RunningState run={run} finalizing />;

  // A "readable answer" is a stored prompt that actually returned text. A run with
  // ZERO readable answers is a provider/auth failure, never a 0-visibility result —
  // whether the backend marked it `failed` (new runs) or `complete` (older runs
  // saved before this fix). Either way: show the error state, not metrics.
  const readable = (responses ?? []).filter((r) => (r.raw_response ?? "").trim().length > 0);
  const noReadable = responses !== null && responses.length > 0 && readable.length === 0;
  if (run.status === "failed" || noReadable) {
    return <ProviderErrorView run={run} responses={responses} />;
  }

  const name = entity?.canonical_name || "your business";
  const b = breakdown(responses, entity?.canonical_name ?? "", entity?.website_url);

  return (
    <div className="mx-auto max-w-4xl">
      <button onClick={() => navigate(`#/e/${run.entity_id}`)} className="mb-4 text-sm text-text-muted hover:text-text-secondary">← Back to business</button>

      {/* Partial-result warning: some prompts failed at the provider. */}
      {responses && readable.length < responses.length && (
        <Card className="mb-4 border-[#fbbf24]/30 bg-[#fbbf24]/5 p-4">
          <p className="text-sm font-medium text-[#fbbf24]">We collected {readable.length} of {responses.length} answers. Some prompts failed.</p>
          <Caveat><span className="mt-1 block">Metrics below are based only on the {readable.length} answers we could read. Run again to get the full set.</span></Caveat>
        </Card>
      )}

      {/* 1. Executive summary */}
      <Card className="border-accent-teal/30 p-6">
        <div className="mb-1 flex items-center justify-between gap-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-accent-teal">Executive summary</p>
          <ExplainButton title="What this result means" plain={explainPlain(name, entity, b, run)} raw={{ run, responses }} />
        </div>
        <p className="text-lg leading-relaxed text-text-primary">{execSummary(name, entity, b, run)}</p>
        <div className="mt-3"><ProvenanceLine provider={run.provider} model={run.model} date={run.completed_at} sample={b ? `${b.overall.total} prompts` : undefined} taxonomy={run.taxonomy_version} /></div>
      </Card>

      {/* 2. What this means */}
      {b && (
        <section className="mt-5">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-text-muted">What this means for you</h2>
          <div className="space-y-2">
            {whatThisMeans(b).map((line, i) => (
              <div key={i} className="flex items-start gap-2.5 text-sm text-text-secondary">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-teal" /><span>{line}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 3. Your next 3 actions */}
      <NextMove b={b} run={run} />

      {/* 4. Metrics (data AFTER interpretation) */}
      <MetricsSection run={run} b={b} />

      {/* 5. Domains, collapsed, businesses first */}
      <DomainsSection run={run} />

      {/* Flags */}
      {(run.flags ?? []).length > 0 && (
        <section className="mt-8">
          <h2 className="mb-2 text-lg font-semibold text-text-primary">Issues to review</h2>
          <div className="space-y-2">
            {(run.flags ?? []).map((f, i) => (
              <Card key={i} className="flex items-start justify-between gap-3 p-3.5">
                <div><p className="text-sm font-medium text-text-primary">{friendlyFlag(f.type)}</p>{f.evidence && <p className="mt-0.5 text-xs text-text-muted">“{f.evidence}”</p>}</div>
                <SeverityChip severity={f.severity} />
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* 6. Raw answers */}
      <section id="answers" className="mt-8">
        <h2 className="mb-2 text-lg font-semibold text-text-primary">The actual AI answers</h2>
        {responses === null ? <LoadingState label="Loading answers…" />
          : responses.length === 0 ? <Caveat>No per-answer records were returned for this run.</Caveat>
          : <div className="space-y-3">{responses.map((r) => <EvidenceCard key={r.id} p={r} />)}</div>}
      </section>

      {/* 7. Methodology / technical details (last) */}
      <MethodologyFooter run={run} b={b} responses={responses} />
    </div>
  );
}

// ─── Interpretation generators (real data only) ──────────────────────────────

function execSummary(name: string, entity: Entity | null, b: Breakdown | null, run: ProbeRun): string {
  const where = [entity?.category, entity?.geo].filter(Boolean).join(" in ");
  const forWhat = where ? ` searching for ${where}` : "";
  // Only a true zero-answer run (no records at all) is "couldn't read".
  if (!b || b.overall.total === 0) return `We queried a live AI engine about ${name} but no answers were returned to summarize. Try running the analysis again.`;
  // Answers exist but the business was never named — that's a real result, not a failure.
  if (b.overall.hit === 0)
    return `We found 0 mentions of ${name} across ${b.overall.total} AI answers. The engine answered every question${forWhat ? ` from people${forWhat}` : ""} — it just didn't name your business, even in the direct brand questions. The first priority is getting AI to recognize you at all.`;
  const d = b.discovery, brand = b.brand;
  const dStrong = d.total > 0 && d.hit / d.total >= 0.5;
  const knownDirect = brand.total > 0 && brand.hit / brand.total >= 0.5;
  if (d.total > 0 && d.hit === 0 && knownDirect)
    return `AI understands ${name} when asked directly, but it is not currently recommending you to new customers${forWhat}. Your biggest opportunity is Discovery Visibility — you appear in ${d.hit} of ${d.total} recommendation searches.`;
  if (dStrong)
    return `AI already recommends ${name} in ${d.hit} of ${d.total} discovery searches, so new customers asking AI${forWhat ? ` for help${forWhat}` : ""} are likely to find you. The priority now is defending that position and proving it holds over time.`;
  if (d.total > 0 && d.hit > 0)
    return `AI recommends ${name} in some discovery searches (${d.hit} of ${d.total}) but not consistently. There is clear room to become a default recommendation${forWhat}.`;
  return `AI shows limited awareness of ${name} in recommendation searches${knownDirect ? ", though it can answer questions about you when your name is provided" : ""}. The priority is making AI recognize and then recommend your business${forWhat}.`;
}

function whatThisMeans(b: Breakdown): string[] {
  const d = b.discovery, brand = b.brand;
  if (b.overall.hit === 0)
    return [
      `We found 0 mentions across ${b.overall.total} AI answers.`,
      "The AI did answer every question — it simply didn't name your business, even when asked about you directly.",
      "The first goal is recognition: getting AI to know your business exists for these searches, before it can recommend you.",
    ];
  const dStrong = d.total > 0 && d.hit / d.total >= 0.5;
  const knownDirect = brand.total > 0 && brand.hit / brand.total >= 0.5;
  if (d.total > 0 && d.hit === 0 && knownDirect)
    return [
      "Customers who already know your brand can find information about you through AI.",
      "Customers asking AI for a recommendation are currently being pointed to other businesses.",
      "This is a discovery and visibility gap — not a reputation problem.",
    ];
  if (dStrong)
    return [
      "When buyers ask AI for a recommendation, you're already in the answer.",
      "Your main risk is slipping over time, so repeated monitoring is what protects this.",
    ];
  return [
    "AI does not yet reliably surface or describe your business to new customers.",
    "Building consistent, recognizable signals is the first step before recommendation can follow.",
  ];
}

function explainPlain(name: string, entity: Entity | null, b: Breakdown | null, run: ProbeRun): ReactNode {
  if (!b) return <p>Not enough answers were returned to explain this result. Try running the analysis again.</p>;
  const where = [entity?.category, entity?.geo].filter(Boolean).join(" in ") || "your category";
  return (
    <>
      <p>We asked a live AI engine (<span className="font-mono text-text-secondary">{run.provider} · {run.model}</span>) {b.overall.total} buyer-style questions about <strong className="text-text-primary">{name}</strong> on {fmtDate(run.completed_at)}, in three groups:</p>
      <ul className="list-disc space-y-1 pl-5">
        <li><strong className="text-text-primary">Discovery</strong> — no-name searches like “best {where}”. AI named you in <strong className="text-text-primary">{b.discovery.hit} of {b.discovery.total}</strong>. This is the headline: it's whether AI recommends you to people who don't know you yet.</li>
        <li><strong className="text-text-primary">Brand check</strong> — questions that already include your name. AI included you in {b.brand.hit} of {b.brand.total}. Easy, and it doesn't prove you'll be recommended.</li>
        <li><strong className="text-text-primary">Alternatives</strong> — comparison questions: {b.alternative.hit} of {b.alternative.total}.</li>
      </ul>
      <p><strong className="text-text-primary">Why the headline isn't your overall number:</strong> AI mentioned you in {b.overall.hit} of {b.overall.total} questions overall, but most of those were brand-check questions where we handed it your name. Discovery — the real test — is {b.discovery.hit}/{b.discovery.total}.</p>
      <p>Results vary slightly each run because it's a live sample, so treat one run as directional and use “Run again” to confirm a change is real.</p>
    </>
  );
}

function metricsExplain(b: Breakdown | null): ReactNode {
  if (!b) return <p>No metrics to explain yet.</p>;
  return (
    <>
      <p>Each metric is a simple ratio from the real answers — “named / answered” for that group of questions:</p>
      <ul className="list-disc space-y-1 pl-5">
        <li><strong className="text-text-primary">Discovery Visibility</strong> {b.discovery.hit}/{b.discovery.total} — the commercial KPI. Were you recommended without your name being given?</li>
        <li><strong className="text-text-primary">Brand Knowledge</strong> {b.brand.hit}/{b.brand.total} — can AI answer when your name is supplied?</li>
        <li><strong className="text-text-primary">Alternative / vs</strong> {b.alternative.hit}/{b.alternative.total} — comparison prompts.</li>
        <li><strong className="text-text-primary">Overall mentions</strong> {b.overall.hit}/{b.overall.total} — all groups combined; shown for context only, never the headline.</li>
      </ul>
      <p>“View raw data” below shows the exact run record these numbers came from.</p>
    </>
  );
}

// ─── Your next 3 actions (advisor-grade) ─────────────────────────────────────

interface Move {
  priority: "high" | "medium" | "low";
  title: string; why: string; benefit: string; effort: "Low" | "Medium" | "High";
  success: string; action?: { label: string; onClick: () => void }; preview?: boolean;
}

function NextMove({ b, run }: { b: Breakdown | null; run: ProbeRun }) {
  const moves: Move[] = [];
  const flagTypes = new Set((run.flags ?? []).map((f) => f.type));
  const scrollAnswers = () => document.getElementById("answers")?.scrollIntoView({ behavior: "smooth" });
  const goBusiness = () => navigate(`#/e/${run.entity_id}`);

  if (b && b.discovery.total > 0 && b.discovery.hit < b.discovery.total) {
    moves.push({
      priority: "high",
      title: "Win the discovery searches you're losing",
      why: `AI recommended you in ${b.discovery.hit} of ${b.discovery.total} no-name buyer searches — the rest went to other businesses.`,
      benefit: "Reach customers who don't know you yet — the largest source of new demand.",
      effort: "Medium",
      success: `Future probes show a higher Discovery Visibility than ${b.discovery.hit}/${b.discovery.total}.`,
      action: { label: "Read the answers", onClick: scrollAnswers },
    });
  }
  if (flagTypes.has("claims_closed")) {
    moves.push({
      priority: "high", title: "Correct what AI believes about you",
      why: "AI suggested your business may be closed.",
      benefit: "Stop losing customers who are told you're unavailable.",
      effort: "Low",
      success: "The “may be closed” flag disappears on the next probe.",
      action: { label: "See the flagged answer", onClick: scrollAnswers },
    });
  }
  if (flagTypes.has("brand_not_recognized")) {
    moves.push({
      priority: "high", title: "Make AI recognize your business",
      why: "AI couldn't reliably identify you from buyer questions.",
      benefit: "A recognized business can be recommended; an unknown one can't.",
      effort: "Medium",
      success: "Brand Knowledge rises and AI starts describing you accurately.",
      action: { label: "See the evidence", onClick: scrollAnswers },
    });
  }
  moves.push({
    priority: "medium", title: "Confirm it's real, then prove it",
    why: "Live AI results vary slightly run-to-run.",
    benefit: "A trustworthy baseline you can measure real improvement against.",
    effort: "Low", success: "A second run confirms what's signal vs. normal variation.",
    action: { label: "Run again", onClick: goBusiness },
  });
  moves.push({ priority: "low", title: "Confirm your identity & competitors", why: "Give us your exact name, aliases and real competitors.", benefit: "Sharper, more accurate analysis tailored to you.", effort: "Low", success: "Matching and competitor detection improve.", preview: true });
  moves.push({ priority: "low", title: "Generate a shareable proof report", why: "Package a client-ready before/after.", benefit: "Demonstrate measurable results to clients or stakeholders.", effort: "Low", success: "An exportable proof link is produced.", preview: true });

  const rank = { high: 0, medium: 1, low: 2 };
  moves.sort((a, c) => rank[a.priority] - rank[c.priority]);
  const top = moves.slice(0, 3);

  return (
    <section className="mt-6">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-lg font-semibold text-text-primary">Your next 3 actions</h2>
        <Chip tone="teal">Decide → Execute → Prove</Chip>
      </div>
      <div className="space-y-3">
        {top.map((m, i) => (
          <Card key={i} className="p-4">
            <div className="flex items-start gap-3">
              <PriorityDot priority={m.priority} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-text-primary">{m.title}</p>
                  {m.preview && <PreviewBadge label="Coming soon" />}
                  <Chip tone="neutral">Effort: {m.effort}</Chip>
                </div>
                <p className="mt-1 text-[13px] leading-relaxed text-text-muted"><span className="text-text-secondary">Why:</span> {m.why}</p>
                <p className="mt-0.5 text-[13px] leading-relaxed text-text-muted"><span className="text-text-secondary">Benefit:</span> {m.benefit}</p>
                <p className="mt-0.5 text-[13px] leading-relaxed text-text-muted"><span className="text-text-secondary">How you'll know it worked:</span> {m.success}</p>
              </div>
              {m.action && !m.preview && <Button variant="ghost" onClick={m.action.onClick} className="shrink-0 px-3 py-1.5 text-xs">{m.action.label}</Button>}
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
}

function PriorityDot({ priority }: { priority: "high" | "medium" | "low" }) {
  const color = priority === "high" ? "#f87171" : priority === "medium" ? "#FBBF24" : "#475569";
  return <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: color }} title={`${priority} priority`} />;
}

// ─── Metrics (after interpretation) ──────────────────────────────────────────

function MetricsSection({ run, b }: { run: ProbeRun; b: Breakdown | null }) {
  const discoveryPct = b ? pct(b.discovery) : (run.share_of_model != null ? Math.round(run.share_of_model * 100) : null);
  return (
    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-text-primary">AI visibility metrics</h2>
        <ExplainButton title="How these metrics are calculated" plain={metricsExplain(b)} raw={run} />
      </div>
      <Card className="p-6">
        <div className="flex flex-col items-center gap-6 sm:flex-row">
          <Gauge value={discoveryPct} suffix="%" label="Discovery Visibility" tone={discoveryPct != null && discoveryPct >= 50 ? "teal" : "amber"} />
          <div className="flex-1">
            <p className="text-sm leading-relaxed text-text-secondary">
              <strong className="text-text-primary">Discovery Visibility</strong> is the real commercial number — whether AI recommends you when buyers <em>don't</em> name you.
              Brand-check prompts (“is X reputable?”) don't count toward it.
            </p>
            <div className="mt-3"><MethodologyNote title="Discovery vs. brand-check">
              <p><strong>Discovery Visibility</strong> = share of no-name buyer questions where AI independently names you.</p>
              <p><strong>Brand Knowledge</strong> = whether AI can answer when your name is given (easier; doesn't prove recommendation).</p>
              <p>Single engine, point-in-time, small sample — directional. Run again to confirm a change is real.</p>
            </MethodologyNote></div>
          </div>
        </div>
        {b && (
          <div className="mt-6 grid grid-cols-2 gap-3 border-t border-border pt-5 sm:grid-cols-4">
            <Stat label="Discovery Visibility" v={b.discovery} primary />
            <Stat label="Brand Knowledge" v={b.brand} />
            <Stat label="Alternative / vs" v={b.alternative} />
            <Stat label="Overall mentions" v={b.overall} muted />
          </div>
        )}
      </Card>
      <button onClick={() => navigate("#/soon/engines")} className="mt-3 block w-full text-left">
        <Card className="flex items-center justify-between p-4 transition-colors hover:border-accent-teal/40">
          <p className="text-sm text-text-secondary">Compare across ChatGPT, Claude & Gemini — see how</p>
          <PreviewBadge label="Coming soon" />
        </Card>
      </button>
    </section>
  );
}

// ─── Domains (collapsed, businesses first) ───────────────────────────────────

function DomainsSection({ run }: { run: ProbeRun }) {
  const [showAll, setShowAll] = useState(false);
  const domains = run.competitors ?? [];
  if (domains.length === 0) return null;

  const buckets: Record<DomainBucket, { name: string; mentions: number }[]> = {
    business: [], directory: [], manufacturer: [], citation: [], unclassified: [],
  };
  for (const d of domains) buckets[domainBucket(d.name)].push(d);
  const sortB = (arr: { name: string; mentions: number }[]) => arr.sort((a, z) => z.mentions - a.mentions);
  const businesses = sortB(buckets.business);
  const others: DomainBucket[] = ["directory", "manufacturer", "citation", "unclassified"];
  const otherCount = others.reduce((n, k) => n + buckets[k].length, 0);

  return (
    <section className="mt-8">
      <div className="mb-1 flex items-center gap-2">
        <h2 className="text-lg font-semibold text-text-primary">Who AI named instead</h2>
        <Chip tone="amber">Possible competitors</Chip>
      </div>
      <Caveat><span className="mb-3 block">Businesses the engine surfaced for the same searches, on {fmtDate(run.completed_at)}. Heuristic grouping — observations of what AI said, not verified competitive facts.</span></Caveat>

      <DomainChips items={businesses.slice(0, 10)} />
      {businesses.length > 10 && !showAll && (
        <button onClick={() => setShowAll(true)} className="mt-3 text-sm text-accent-teal hover:underline">Show {businesses.length - 10} more businesses</button>
      )}

      {!showAll ? (
        otherCount > 0 && (
          <button onClick={() => setShowAll(true)} className="mt-4 block text-sm text-accent-teal hover:underline">
            Show full evidence — {otherCount} directories, citation sources & other mentions
          </button>
        )
      ) : (
        <div className="mt-5 space-y-4">
          {businesses.length > 10 && <div><GroupHead label={DOMAIN_BUCKET_LABEL.business} n={businesses.length} /><DomainChips items={businesses} /></div>}
          {others.filter((k) => buckets[k].length).map((k) => (
            <div key={k}><GroupHead label={DOMAIN_BUCKET_LABEL[k]} n={buckets[k].length} /><DomainChips items={sortB(buckets[k])} /></div>
          ))}
          <button onClick={() => setShowAll(false)} className="text-sm text-text-muted hover:text-text-secondary">Show less</button>
        </div>
      )}
    </section>
  );
}
function GroupHead({ label, n }: { label: string; n: number }) {
  return <div className="mb-1.5 flex items-center gap-2"><p className="text-sm font-medium text-text-primary">{label}</p><span className="text-xs text-text-muted">{n}</span></div>;
}
function DomainChips({ items }: { items: { name: string; mentions: number }[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((d) => (
        <span key={d.name} className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-border bg-bg-surface px-2.5 py-1 text-[12px]">
          <span className="break-all font-mono text-text-secondary">{d.name}</span><span className="shrink-0 text-text-muted">×{d.mentions}</span>
        </span>
      ))}
    </div>
  );
}

// ─── breakdown ───────────────────────────────────────────────────────────────

interface Tally { hit: number; total: number }
interface Breakdown { discovery: Tally; brand: Tally; alternative: Tally; overall: Tally }

/** Case-insensitive name/alias candidates for mention detection. Built from the
 *  business name (with legal suffixes stripped) and its domain label, so we can
 *  re-detect mentions in the frontend even if the stored flag is missing/wrong. */
function nameCandidates(name: string, websiteUrl?: string | null): string[] {
  const out = new Set<string>();
  const add = (s: string) => { const t = s.toLowerCase().trim(); if (t.length >= 3) out.add(t); };
  if (name) {
    add(name);
    add(name.replace(/[.,]/g, ""));
    add(name.replace(/\b(inc|llc|ltd|co|corp|company|gmbh|plc|sa|srl)\b\.?/gi, "").replace(/\s{2,}/g, " ").trim());
  }
  if (websiteUrl) {
    const m = websiteUrl.replace(/^https?:\/\//, "").replace(/^www\./, "").split(/[/?#]/)[0];
    const label = m.split(".")[0];
    if (label) add(label);
  }
  return [...out];
}

/** True if any candidate appears in the answer text (case-insensitive). */
function mentionsName(text: string | null | undefined, candidates: string[]): boolean {
  if (!text) return false;
  const hay = text.toLowerCase();
  return candidates.some((c) => hay.includes(c));
}

function breakdown(responses: Perception[] | null, name: string, websiteUrl?: string | null): Breakdown | null {
  if (!responses || responses.length === 0) return null;
  const cands = nameCandidates(name, websiteUrl);
  const z = (): Tally => ({ hit: 0, total: 0 });
  const b: Breakdown = { discovery: z(), brand: z(), alternative: z(), overall: z() };
  for (const r of responses) {
    // Only READABLE answers count (denominator = answers that actually returned
    // text). Prompts that failed at the provider are excluded here and surfaced
    // separately as a provider-error / partial state — never as "not named".
    if (!(r.raw_response ?? "").trim()) continue;
    const g: PromptGroup = promptType(r.prompt_category).group;
    // Re-interpret the mention here: backend flag OR own-domain citation OR a
    // case-insensitive name/alias match in the answer text. Never weaker than
    // the stored flag, so old saved results only get *more* accurate.
    const named = !!r.brand_mentioned || !!r.domain_cited || mentionsName(r.raw_response, cands);
    b.overall.total++; if (named) b.overall.hit++;
    b[g].total++; if (named) b[g].hit++;
  }
  return b;
}
function pct(t: Tally): number | null { return t.total ? Math.round((t.hit / t.total) * 100) : null; }

function Stat({ label, v, primary, muted }: { label: string; v: Tally; primary?: boolean; muted?: boolean }) {
  const p = pct(v);
  return (
    <div className={`rounded-xl border p-3 ${primary ? "border-accent-teal/30 bg-accent-teal/5" : "border-border bg-bg-base"}`}>
      <p className="text-[10px] uppercase tracking-wider text-text-muted">{label}</p>
      <p className={`mt-1 font-mono text-lg font-semibold ${muted ? "text-text-secondary" : primary ? "text-accent-teal" : "text-text-primary"}`}>
        {v.total === 0 ? "—" : `${v.hit}/${v.total}`}{p != null && v.total > 0 ? ` · ${p}%` : ""}
      </p>
    </div>
  );
}

// ─── Provider / auth failure (no readable answers) ───────────────────────────

/** Safe, user-facing reason derived from saved per-prompt errors (for older runs
 *  stored "complete" with no run.error). Never dumps the raw stack/key. */
function safeProviderReason(responses: Perception[] | null): string {
  const errs = (responses ?? []).map((r) => r.details?.error || "").join(" ").toLowerCase();
  if (errs.includes("401") || errs.includes("unauthorized"))
    return "The AI provider returned 401 Unauthorized — the API key is missing, invalid, or expired. Check OPENROUTER_API_KEY in the API server environment.";
  if (errs.includes("403") || errs.includes("forbidden"))
    return "The AI provider returned 403 Forbidden — the API key lacks access to this model.";
  if (errs.includes("429") || errs.includes("rate limit"))
    return "The AI provider rate-limited the request (429). Try again shortly.";
  if (errs.includes("timeout") || errs.includes("timed out"))
    return "The AI provider did not respond in time (timeout).";
  return "The AI provider could not be reached or returned an error for every prompt.";
}

function ProviderErrorView({ run, responses }: { run: ProbeRun; responses: Perception[] | null }) {
  const reason = run.error || safeProviderReason(responses);
  const attempted = responses?.length ?? run.prompt_count ?? 0;
  // A run reaped as stale (worker stopped / server restarted) is a different
  // story from a provider/auth failure — title and copy adapt accordingly.
  const isStale = /did not finish|worker stopped|server was restarted/i.test(run.error ?? "");
  const [starting, setStarting] = useState(false);

  async function runAgain() {
    setStarting(true);
    const { data, error } = await api.enqueueProbe(run.entity_id);
    setStarting(false);
    if (error || !data) { navigate(`#/e/${run.entity_id}`); return; }
    navigate(`#/probe/${data.probe_run_id}`);
  }

  return (
    <div className="mx-auto max-w-2xl">
      <ErrorState
        title={isStale ? "This analysis didn’t finish" : "The AI provider could not be reached for this run"}
        detail={reason}
        action={
          <div className="flex flex-wrap gap-2">
            <Button onClick={runAgain} disabled={starting}>{starting ? "Starting…" : "Run again"}</Button>
            <Button variant="ghost" onClick={() => navigate(`#/e/${run.entity_id}`)}>Back to business</Button>
          </div>
        }
      />
      <Card className="mt-4 p-5">
        <p className="text-sm font-medium text-text-primary">What this means</p>
        <Caveat>
          <span className="mt-1 block">
            {isStale ? (
              <>This run was interrupted before it could finish, so it has <strong className="text-text-primary">no visibility result</strong>. Any
              answers collected before it stopped are kept below as a record. Run it again to get a complete result.</>
            ) : (
              <>No readable AI answers were returned, so this run has <strong className="text-text-primary">no visibility result</strong> — the Discovery
              and Brand numbers are intentionally not shown. It’s kept as a diagnostic record. Fix the provider key on the API
              server and run again to get a real result.</>
            )}
          </span>
        </Caveat>
      </Card>
      {responses && responses.length > 0 && <DiagnosticPrompts responses={responses} attempted={attempted} />}
    </div>
  );
}

function DiagnosticPrompts({ responses, attempted }: { responses: Perception[]; attempted: number }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="mt-4">
      <button onClick={() => setOpen((o) => !o)} className="text-sm text-accent-teal hover:underline">
        {open ? "Hide" : "Show"} diagnostic detail ({attempted} prompts attempted)
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {responses.map((r) => (
            <Card key={r.id} className="p-3">
              <p className="text-sm text-text-secondary">{r.prompt}</p>
              {r.details?.error && <p className="mt-1 break-words font-mono text-[11px] text-[#f87171]">{r.details.error}</p>}
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}

// ─── misc ────────────────────────────────────────────────────────────────────

function RunningState({ run, reconnecting, finalizing }: { run: ProbeRun | null; reconnecting?: boolean; finalizing?: boolean }) {
  const answered = run?.answered_count ?? 0;
  const total = run?.prompt_count || 8;
  const heading = finalizing ? "Finalizing your results…" : "Asking a live AI engine about your business…";
  const sub = finalizing
    ? "The analysis is done — loading the detailed answers."
    : "Putting buyer-intent questions to the engine and reading the answers. ~30 seconds.";
  return (
    <div className="mx-auto max-w-2xl pt-10">
      <Card className="p-8 text-center">
        <div className="mx-auto mb-5 h-10 w-10 animate-spin rounded-full border-2 border-accent-teal border-t-transparent" />
        <h1 className="text-xl font-semibold text-text-primary">{heading}</h1>
        <p className="mt-2 text-sm text-text-secondary">{sub}</p>
        {run && !finalizing && <p className="mt-4 font-mono text-sm text-text-muted">{answered}/{total} answered</p>}
        {reconnecting && <p className="mt-3 text-[12px] text-[#fbbf24]">Reconnecting to the analysis API… still working.</p>}
        <p className="mt-4 text-[12px] text-text-muted">You can leave this page — the result is saved to your business.</p>
      </Card>
    </div>
  );
}

function EvidenceCard({ p }: { p: Perception }) {
  const [open, setOpen] = useState(false);
  const t = promptType(p.prompt_category);
  const toneByGroup: Record<PromptGroup, ChipTone> = { discovery: "teal", alternative: "violet", brand: "neutral" };
  const mentioned = ((p.competitors_named ?? []) as string[]);
  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-2">
        <Chip tone={toneByGroup[t.group]}>{t.label}</Chip>
        {p.brand_mentioned ? <Chip tone="teal">Named you</Chip> : <Chip tone="neutral">Not named</Chip>}
        {p.domain_cited && <Chip tone="teal">Cited site</Chip>}
      </div>
      <p className="text-sm font-medium text-text-primary">{p.prompt}</p>
      {open && <div className="mt-3 rounded-xl border border-border bg-bg-base p-3"><p className="whitespace-pre-wrap text-sm leading-relaxed text-text-secondary">{p.raw_response || "(no answer text)"}</p></div>}
      <div className="mt-3 flex items-center justify-between">
        <ProvenanceLine provider={p.provider} model={p.model} date={p.probed_at} />
        <button onClick={() => setOpen((o) => !o)} className="text-[12px] text-accent-teal hover:underline">{open ? "Hide answer" : "Show the answer"}</button>
      </div>
      {mentioned.length > 0 && <p className="mt-2 text-[12px] text-text-muted">Also mentioned: {mentioned.slice(0, 8).join(", ")}{mentioned.length > 8 ? ` +${mentioned.length - 8} more` : ""}</p>}
    </Card>
  );
}

function MethodologyFooter({ run, b, responses }: { run: ProbeRun; b: Breakdown | null; responses: Perception[] | null }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="mt-8 border-t border-border pt-5">
      <div className="flex items-center justify-between gap-3">
        <button onClick={() => setOpen((o) => !o)} className="flex flex-1 items-center justify-between text-left">
          <span className="text-sm font-medium text-text-secondary">Methodology & limitations</span>
        </button>
        <Button variant="ghost" className="px-3 py-1.5 text-xs"
          onClick={() => downloadJson(`ai-visibility-${run.id}.json`, { run, responses })}>
          Download raw data (JSON)
        </Button>
        <button onClick={() => setOpen((o) => !o)} className="text-text-muted">{open ? "–" : "+"}</button>
      </div>
      {open && (
        <div className="mt-3 space-y-2 text-[13px] leading-relaxed text-text-muted">
          <p><span className="text-text-secondary">Engine / model:</span> {run.provider ?? "—"} · {run.model ?? "—"}</p>
          <p><span className="text-text-secondary">Date:</span> {fmtDate(run.completed_at)} · <span className="text-text-secondary">Sample:</span> {b ? `${b.overall.total} prompts` : `${run.answered_count}/${run.prompt_count}`} · <span className="text-text-secondary">Taxonomy:</span> {run.taxonomy_version ?? "—"}</p>
          <p><span className="text-text-secondary">Limitations:</span> single engine, point-in-time, small sample. Share-of-Model is a mention-based proxy; competitor/domain grouping is a presentation-layer heuristic. Multi-engine comparison is in development. Nothing here is fabricated — every figure derives from the live answers above.</p>
        </div>
      )}
    </section>
  );
}

function friendlyFlag(type: string): string {
  const map: Record<string, string> = {
    claims_closed: "AI suggested the business may be closed",
    brand_not_recognized: "AI doesn’t recognize this business yet",
  };
  return map[type] ?? type.replace(/_/g, " ");
}
