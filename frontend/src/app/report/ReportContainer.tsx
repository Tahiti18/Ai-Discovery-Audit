/**
 * Live report container: given a probe run id, polls the run to completion (so
 * a freshly-started check shows progress), then fetches the per-prompt answers
 * and entity and renders <ReportScreen> with real session data.
 */
import { useEffect, useRef, useState } from "react";
import {
  api, pollProbe, fetchTechnicalReportHtml, type Perception, type ProbeRun, type PollHandle,
} from "../../lib/platformApi";
import { ReportScreen, type ReportData, type Move } from "./ReportScreen";
import { navigate } from "../AppRoot";

type Phase = "loading" | "running" | "ready" | "failed" | "error";

export function ReportContainer({ runId }: { runId: string }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [run, setRun] = useState<ProbeRun | null>(null);
  const [data, setData] = useState<ReportData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<PollHandle | null>(null);

  useEffect(() => {
    setPhase("loading"); setData(null); setError(null);
    pollRef.current?.cancel();
    pollRef.current = pollProbe(runId, {
      onTick: (r) => { setRun(r); if (r.status === "running" || r.status === "queued") setPhase("running"); },
      onError: (m) => { setError(m); setPhase("error"); },
      onDone: async (r) => {
        setRun(r);
        if (r.status === "failed") { setPhase("failed"); return; }
        const [resp, ent] = await Promise.all([api.getProbeResponses(r.id), api.getEntity(r.entity_id)]);
        if (resp.error || !ent.data) { setError(resp.error || "Couldn't load the report details."); setPhase("error"); return; }
        setData({
          entity: ent.data,
          run: r,
          responses: resp.data ?? [],
          moves: computeMoves(r, resp.data ?? []),
          onDownloadTechnical: async (target: Window | null) => {
            const { html, error } = await fetchTechnicalReportHtml(r.entity_id);
            if (!html) throw new Error(error || "Could not generate the technical report.");
            if (target) {
              target.document.open();
              target.document.write(html);
              target.document.close();
            } else {
              // Popup was blocked despite the sync open — fall back to a blob tab.
              const blob = new Blob([html], { type: "text/html" });
              window.open(URL.createObjectURL(blob), "_blank");
            }
          },
        });
        setPhase("ready");
      },
    });
    return () => pollRef.current?.cancel();
  }, [runId]);

  if (phase === "ready" && data) return <ReportScreen data={data} />;

  return (
    <div className="vta">
      <div className="fixed inset-0 pointer-events-none v-glow" aria-hidden="true" />
      <div className="relative min-h-screen flex items-center justify-center px-6 text-center">
        <div className="max-w-md">
          {(phase === "loading" || phase === "running") && (
            <>
              <Spinner />
              <h1 className="v-display mt-5" style={{ fontSize: 24 }}>Asking AI about your business…</h1>
              <p className="v-text-secondary mt-2" style={{ fontSize: 14 }}>
                We're putting real buyer questions to live AI engines and reading every answer. This takes about a minute.
              </p>
              {run && run.prompt_count > 0 && (
                <p className="v-text-muted mt-3" style={{ fontSize: 13 }}>{run.answered_count}/{run.prompt_count} answered</p>
              )}
            </>
          )}
          {phase === "failed" && (
            <div className="v-card p-8">
              <h1 className="v-display" style={{ fontSize: 22 }}>This check didn't finish</h1>
              <p className="v-text-secondary mt-2" style={{ fontSize: 14 }}>{run?.error || "The AI provider couldn't be reached for this run."}</p>
              <a href="#/" className="v-btn v-btn-ghost mt-5">Back to my businesses</a>
            </div>
          )}
          {phase === "error" && (
            <div className="v-card p-8">
              <h1 className="v-display" style={{ fontSize: 22 }}>Couldn't load this report</h1>
              <p className="v-text-secondary mt-2" style={{ fontSize: 14 }}>{error}</p>
              <button onClick={() => navigate("")} className="v-btn v-btn-ghost mt-5">Back to my businesses</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const DISCOVERY = new Set(["category_recommendation", "problem_solution", "comparison"]);

/** Honest, data-driven next moves from the probe result (no fabrication). The
 *  richer audit-derived moves get layered in when the technical audit is wired. */
function computeMoves(run: ProbeRun, responses: Perception[]): Move[] {
  const moves: Move[] = [];
  const discovery = responses.filter((r) => DISCOVERY.has(r.prompt_category ?? ""));
  const discoveryHits = discovery.filter((r) => r.brand_mentioned).length;
  const brandChecks = responses.filter((r) => !DISCOVERY.has(r.prompt_category ?? ""));
  const brandHits = brandChecks.filter((r) => r.brand_mentioned).length;
  const brandStrong = brandChecks.length > 0 && brandHits >= Math.ceil(brandChecks.length / 2);

  if (discovery.length > 0 && discoveryHits < discovery.length) {
    moves.push({
      title: "Get AI to recommend you, not just recognise you",
      body: brandStrong
        ? "AI knows your business well when asked by name, but doesn't put you forward when buyers ask for a recommendation without naming you. Strengthen the signals AI uses to choose who to name — clear category + location, structured data, and consistent details across the web."
        : "AI rarely names you in no-name buyer searches. Make it unmistakable what you do and where, in language AI can read and trust.",
      why: `Why it matters: this is the visibility that reaches new customers. · You were named in ${discoveryHits} of ${discovery.length} discovery searches.`,
      impact: "high", impactLabel: "High impact",
    });
  }

  const flagTypes = new Set((run.flags ?? []).map((f) => f.type));
  if (flagTypes.has("claims_closed")) {
    moves.push({
      title: "Correct what AI believes about you",
      body: "AI suggested your business may be closed or gave wrong basic facts. Fix the source signals (Google Business Profile, your site's contact details, structured data) so AI stops repeating it.",
      why: "Why it matters: customers act on what AI tells them. · Effort: low.",
      impact: "high", impactLabel: "High impact",
    });
  }

  moves.push({
    title: "Run this check again after you make changes",
    body: "Live AI results vary run to run. Re-running over time is how you prove a fix actually moved the needle — and catch it when something on your site breaks your visibility.",
    why: "Why it matters: a trustworthy baseline you can measure improvement against. · Effort: one click.",
    impact: "medium", impactLabel: "Worth doing",
  });

  return moves;
}

function Spinner() {
  return (
    <svg className="mx-auto" width="40" height="40" viewBox="0 0 24 24" style={{ animation: "vtaspin 0.8s linear infinite" }}>
      <style>{"@keyframes vtaspin{to{transform:rotate(360deg)}}"}</style>
      <circle cx="12" cy="12" r="9" fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="var(--vta-accent)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
