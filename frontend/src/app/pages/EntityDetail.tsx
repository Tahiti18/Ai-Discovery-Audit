/**
 * Business overview — outcome-first.
 * Leads with the product's signature insight: Reality (Share-of-Model, real) vs
 * Readiness (technical audit, ownership-gated → honest gate). History enables
 * the Prove stage; single runs are labeled directional.
 */
import { useEffect, useState } from "react";
import { api, somPct, type Entity, type ProbeRun, type Signal } from "../../lib/platformApi";
import { navigate } from "../router";
import {
  Button, Card, Caveat, Chip, EmptyState, ErrorState, Gauge, LoadingState,
  MethodologyNote, PreviewBadge, ProvenanceLine, fmtDate,
} from "../ui";

type Tab = "overview" | "history" | "signals";

export function EntityDetail({ id }: { id: string }) {
  const [entity, setEntity] = useState<Entity | null>(null);
  const [runs, setRuns] = useState<ProbeRun[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    let alive = true;
    // Reset so switching businesses never shows stale data/UI from the previous one.
    setEntity(null); setRuns(null); setErr(null); setTab("overview");
    (async () => {
      const e = await api.getEntity(id);
      if (!alive) return;
      if (e.error || !e.data) { setErr(e.error || "Business not found"); return; }
      setEntity(e.data);
      const r = await api.listEntityProbes(id);
      if (alive) setRuns(r.data ?? []);
    })();
    return () => { alive = false; };
  }, [id]);

  async function runProbe() {
    setStarting(true);
    const { data, error } = await api.enqueueProbe(id);
    setStarting(false);
    if (error || !data) { setErr(error || "Could not start probe"); return; }
    navigate(`#/probe/${data.probe_run_id}`);
  }

  if (err) return <ErrorState detail={err} action={<Button variant="ghost" onClick={() => navigate("#/dashboard")}>Back</Button>} />;
  if (!entity) return <LoadingState label="Loading business…" />;

  const latest = runs && runs.length ? runs[0] : null;
  const completed = runs?.filter((r) => r.status === "complete") ?? [];

  return (
    <div className="mx-auto max-w-4xl">
      <button onClick={() => navigate("#/dashboard")} className="mb-3 text-sm text-text-muted hover:text-text-secondary">← Portfolio</button>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{entity.canonical_name}</h1>
          <p className="text-sm text-text-muted">{entity.website_url}{entity.category ? ` · ${entity.category}` : ""}{entity.geo ? ` · ${entity.geo}` : ""}</p>
        </div>
        <Button onClick={runProbe} disabled={starting}>{starting ? "Starting…" : latest ? "Run probe again" : "Run AI Perception Probe"}</Button>
      </div>

      <div className="mb-5 flex gap-1 border-b border-border">
        {(["overview", "history", "signals"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm capitalize ${tab === t ? "border-accent-teal text-text-primary" : "border-transparent text-text-muted hover:text-text-secondary"}`}>
            {t}
          </button>
        ))}
      </div>

      {tab === "overview" && <Overview entity={entity} latest={latest} onRun={runProbe} />}
      {tab === "history" && <History runs={runs} completed={completed} />}
      {tab === "signals" && <Signals entityId={id} />}
    </div>
  );
}

function Overview({ entity, latest, onRun }: { entity: Entity; latest: ProbeRun | null; onRun: () => void }) {
  const som = latest && latest.status === "complete" ? somPct(latest) : null;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Reality */}
      <Card className="p-5">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-text-primary">Reality — does AI recommend you?</p>
          <Chip tone="teal">Live engine</Chip>
        </div>
        {latest && latest.status === "complete" ? (
          <div className="flex items-center gap-4">
            <Gauge value={som} suffix="%" label="Discovery Visibility" size={104} tone={som != null && som >= 50 ? "teal" : "amber"} />
            <div className="text-sm">
              <p className="text-text-secondary"><span className="font-mono text-text-primary">{latest.recommended_count}</span> discovery mention{latest.recommended_count === 1 ? "" : "s"} <span className="text-text-muted">(no-name searches)</span></p>
              <button onClick={() => navigate(`#/probe/${latest.id}`)} className="mt-2 text-accent-teal hover:underline">View full analysis →</button>
              <div className="mt-2"><ProvenanceLine provider={latest.provider} model={latest.model} date={latest.completed_at} sample={`${latest.answered_count}/${latest.prompt_count} prompts`} /></div>
            </div>
          </div>
        ) : (
          <EmptyState title="No probe yet" body="Run a probe to see whether AI recommends this business." action={<Button onClick={onRun}>Run AI Perception Probe</Button>} />
        )}
      </Card>

      {/* Readiness (honest gate) */}
      <Card className="p-5">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-text-primary">Readiness — is your site technically AI-ready?</p>
          {!entity.verified_at && <PreviewBadge label="Verify to unlock" />}
        </div>
        {entity.verified_at ? (
          <EmptyState title="Run a readiness audit" body="Your domain is verified — run the technical AI-readiness audit." />
        ) : (
          <div>
            <Gauge value={null} label="AI Readiness" size={104} tone="muted" />
            <Caveat>
              The technical audit crawls your site, so it requires verifying you own this domain
              (DNS or file). Until then we don’t show a readiness score — and we never invent one.
            </Caveat>
            <div className="mt-2">
              <MethodologyNote title="Readiness vs. Reality">
                <p><strong>Readiness</strong> measures the AI-facing technical signals on your site (crawler access, structured data, content). <strong>Reality</strong> measures what the AI engine actually says.</p>
                <p>They can diverge — a technically perfect site can still be ignored by AI. That gap is the most useful thing this product shows you.</p>
              </MethodologyNote>
            </div>
          </div>
        )}
      </Card>

      {/* Improve — honest about backend state */}
      <Card className="p-5 md:col-span-2">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-text-primary">Recommended fixes & one-click execution</p>
          <PreviewBadge label="Coming soon" />
        </div>
        <Caveat>
          Prioritized, impact-ranked fixes — and eventually one-click execution — are on the roadmap.
          We won’t show invented “impact” or “difficulty” numbers until the backend computes them.
        </Caveat>
      </Card>
    </div>
  );
}

function History({ runs, completed }: { runs: ProbeRun[] | null; completed: ProbeRun[] }) {
  if (runs === null) return <LoadingState />;
  if (runs.length === 0) return <EmptyState title="No runs yet" body="Run a probe to start building history." />;

  const trend =
    completed.length >= 2
      ? { first: somPct(completed[completed.length - 1]), last: somPct(completed[0]) }
      : null;

  return (
    <div>
      {trend ? (
        <Card className="mb-4 p-5">
          <p className="text-sm font-medium text-text-primary">Share-of-Model over time</p>
          <p className="mt-2 font-mono text-2xl text-text-primary">{trend.first ?? "—"}% → {trend.last ?? "—"}%</p>
          <Caveat>
            Based on {completed.length} completed runs. Share-of-Model varies run-to-run, so a small change may be
            normal variation rather than real improvement — confirm with repeated runs before reporting it as proof.
          </Caveat>
        </Card>
      ) : (
        <Card className="mb-4 p-5">
          <p className="text-sm text-text-secondary">Run at least twice to establish a trend.</p>
          <Caveat>We never interpolate fictional history — the trend appears once you have two or more real runs.</Caveat>
        </Card>
      )}
      <div className="space-y-2">
        {runs.map((r) => (
          <Card key={r.id} className="flex items-center justify-between p-3.5">
            <div className="flex items-center gap-3">
              <Chip tone={r.status === "complete" ? "teal" : r.status === "failed" ? "red" : "violet"}>{r.status}</Chip>
              <span className="text-sm text-text-secondary">{fmtDate(r.completed_at || r.created_at)}</span>
              {r.status === "complete" && <span className="font-mono text-sm text-text-primary">{somPct(r) ?? "—"}% · {r.recommended_count}/{r.answered_count}</span>}
            </div>
            <button onClick={() => navigate(`#/probe/${r.id}`)} className="text-sm text-accent-teal hover:underline">Open</button>
          </Card>
        ))}
      </div>
    </div>
  );
}

function Signals({ entityId }: { entityId: string }) {
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    api.getSignals(entityId).then((r) => { if (alive) { if (r.error) setErr(r.error); setSignals(r.data ?? []); } });
    return () => { alive = false; };
  }, [entityId]);
  if (err) return <ErrorState detail={err} />;
  if (signals === null) return <LoadingState />;
  if (signals.length === 0) return <EmptyState title="No signals yet" body="Signals are written by the audit pipeline once it runs for this business." />;
  return (
    <Card className="overflow-x-auto">
      <table className="w-full min-w-[34rem] text-sm">
        <thead className="border-b border-border text-left text-[11px] uppercase tracking-wider text-text-muted">
          <tr><th className="px-4 py-2 font-medium">Source</th><th className="px-4 py-2 font-medium">Type</th><th className="px-4 py-2 font-medium">Value</th><th className="px-4 py-2 font-medium">When</th></tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <tr key={s.id} className="border-b border-border/50 last:border-0">
              <td className="px-4 py-2.5 text-text-secondary">{s.source}</td>
              <td className="px-4 py-2.5 font-mono text-text-primary">{s.signal_type}</td>
              <td className="px-4 py-2.5 font-mono text-xs text-text-muted">{JSON.stringify(s.value)}</td>
              <td className="px-4 py-2.5 text-text-muted">{fmtDate(s.fetched_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
