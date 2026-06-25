/** Portfolio dashboard — agency-first: every business with its real AI standing. */
import { useEffect, useState } from "react";
import { api, somPct, type Entity, type ProbeRun } from "../../lib/platformApi";
import { getWorkspace } from "../../lib/platformStore";
import { navigate } from "../router";
import { Button, Card, Chip, EmptyState, ErrorState, Gauge, LoadingState, PreviewBadge, fmtDate } from "../ui";

export function Dashboard() {
  const ws = getWorkspace();
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [latest, setLatest] = useState<Record<string, ProbeRun | null>>({});
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!ws) { navigate("#/onboarding"); return; }
    let alive = true;
    (async () => {
      const { data, error } = await api.listEntities();
      if (!alive) return;
      if (error) { setErr(error); setEntities([]); return; }
      const list = data ?? [];
      setEntities(list);
      // Pull each entity's most recent probe (honest: only what exists).
      const map: Record<string, ProbeRun | null> = {};
      await Promise.all(list.map(async (e) => {
        const runs = await api.listEntityProbes(e.id);
        map[e.id] = runs.data && runs.data.length ? runs.data[0] : null;
      }));
      if (alive) setLatest(map);
    })();
    return () => { alive = false; };
  }, []);

  if (!ws) return null;
  if (err) return <ErrorState detail={err} />;
  if (entities === null) return <LoadingState label="Loading your portfolio…" />;

  const withSom = entities.map((e) => latest[e.id]).filter((r): r is ProbeRun => !!r && r.share_of_model != null);
  const avgSom = withSom.length
    ? Math.round((withSom.reduce((s, r) => s + (r.share_of_model ?? 0), 0) / withSom.length) * 100)
    : null;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Portfolio</h1>
          <p className="mt-1 text-sm text-text-muted">How AI answer engines see each of your businesses.</p>
        </div>
        <Button onClick={() => navigate("#/onboarding")}>+ Add business</Button>
      </div>

      {/* Rollup */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Rollup label="Businesses" value={String(entities.length)} />
        <Rollup label="Avg Share-of-Model" value={avgSom == null ? "—" : `${avgSom}%`} hint={withSom.length ? `${withSom.length} measured` : "run a probe"} />
        <Rollup label="Agencies & teams" preview />
        <Rollup label="Scheduled monitoring" preview />
      </div>

      {entities.length === 0 ? (
        <EmptyState
          title="No businesses yet"
          body="Add your first business to see whether AI engines recommend it."
          action={<Button onClick={() => navigate("#/onboarding")}>Analyze my AI visibility</Button>}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {entities.map((e) => (
            <EntityCard key={e.id} entity={e} run={latest[e.id] ?? null} />
          ))}
        </div>
      )}
    </div>
  );
}

function Rollup({ label, value, hint, preview }: { label: string; value?: string; hint?: string; preview?: boolean }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-text-muted">{label}</p>
        {preview && <PreviewBadge />}
      </div>
      <p className="mt-2 font-mono text-2xl font-semibold text-text-primary">{preview ? "—" : value}</p>
      {hint && !preview && <p className="mt-0.5 text-[11px] text-text-muted">{hint}</p>}
    </Card>
  );
}

function EntityCard({ entity, run }: { entity: Entity; run: ProbeRun | null }) {
  const som = run ? somPct(run) : null;
  const flags = run?.flags?.length ?? 0;
  return (
    <Card className="p-5 transition-colors hover:border-accent-teal/40">
      <button onClick={() => navigate(`#/e/${entity.id}`)} className="block w-full text-left">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-medium text-text-primary">{entity.canonical_name}</p>
            <p className="truncate text-xs text-text-muted">{entity.website_url}</p>
          </div>
          {run && <Chip tone={run.status === "complete" ? "teal" : run.status === "failed" ? "red" : "violet"}>{run.status}</Chip>}
        </div>
        <div className="mt-4 flex items-center gap-4">
          <Gauge value={som} suffix="%" label="Discovery Visibility" size={96} tone={som != null && som >= 50 ? "teal" : "amber"} />
          <div className="text-sm">
            {run && run.status === "complete" ? (
              <>
                <p className="text-text-secondary"><span className="font-mono text-text-primary">{run.recommended_count}</span> discovery mention{run.recommended_count === 1 ? "" : "s"} <span className="text-text-muted">(no-name searches)</span></p>
                <p className="mt-1 text-text-muted">{flags > 0 ? `${flags} issue${flags > 1 ? "s" : ""} to review` : "No issues flagged"}</p>
                <p className="mt-1 text-[11px] text-text-muted">{fmtDate(run.completed_at)}</p>
              </>
            ) : run && run.status === "failed" ? (
              <p className="text-[#f87171]">Last probe failed — open to retry</p>
            ) : (
              <p className="text-text-muted">No probe yet — open to run one</p>
            )}
          </div>
        </div>
      </button>
    </Card>
  );
}
