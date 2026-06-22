# Project Checkpoint — Current State & Next Priorities

_Last updated: 2026-06-22 · Canonical repo: Tahiti18/geo-optimizer-skill_

## 1. Repo status

- **Tahiti18 is the canonical home.** `origin` → `github.com/Tahiti18/geo-optimizer-skill`; `upstream` → `github.com/Auriti-Labs/geo-optimizer-skill` (read-only reference, untouched).
- **No open Tahiti18 PRs.** PRs #1 (rebrand), #2 (LIVE_ONLY runner), #3 (diagnostics history) merged; all feature branches deleted.
- **`main` contains:** the platform stack (Phase 0 foundation + Phase 1 Perception Probe), the Tahiti18 rebrand, the LIVE_ONLY demo-readiness runner, and the diagnostics-history tool.
- **Engine frozen.** `src/geo_optimizer/` is the OSS audit engine; the platform wraps it via adapters only. The sole `src/` deltas vs upstream are rebrand text (URLs, one docstring example).
- **Layout:** `src/geo_optimizer/` (engine), `platform/geoready_platform/` (platform: API, services, workers, db), `platform/probe_eval/` (internal, non-shipping eval/diagnostics tooling).

## 2. What is currently working

- **Audit-as-signal pipeline:** ownership-gated, tenant-scoped audit jobs that write results as signals on a business entity (Phase 0).
- **AI Perception Probe (core logic):** discovery-only Share-of-Model (taxonomy v3), canonical brand matching, competitor filtering (denylist), advisory hallucination flags — all with full provenance (provider, model, taxonomy_version, prompt, raw_response, timestamp).
- **Live validation:** LIVE_ONLY runner against `perplexity/sonar` via the eval-only OpenRouter client. Latest internal run: would_fallback_rate 0.0, citation_gap_run_rate 0.0, ~3.9s median latency, ~$0.064/batch; SoM cleanly separates real brands (Slack/Notion 1.0) from a fictional business (0.0).
- **Diagnostics history:** each live run's summary persisted to a gitignored folder; `_diagnostics_history --last N` reports the reliability trend + a fallback recommendation.
- **Quality gate:** 93 platform tests passing, ruff clean, idempotent Alembic migrations, internal eval framework (benchmark + thresholds).

## 3. What is still NOT production-ready

- **No UI / no self-serve.** Operator-run only; demos are controlled, not public.
- **Competitor intelligence is directional only** — citation-domain extraction is noisy; not safe to present as polished output.
- **Tenant isolation rests on app-layer scoping** — Postgres RLS is scaffolded but not enforced end-to-end.
- **Single-provider, mention-proxy SoM** — Perplexity only; "recommended" ≈ "independently mentioned in a discovery answer," not ranked endorsement.
- **Live diagnostics are demo-scoped** — small curated business set, no golden fallback, no SLA/observability for real traffic.
- **No attribution / no execution (auto-fix)** — the "prove business impact" and "fix" stages of the loop are unbuilt.

## 4. Highest-risk technical issues

1. **Noisy citation-domain competitor extraction** — biggest demo-credibility risk; denylist filtering helps but reference/aggregator noise remains. Do not surface as competitor intelligence.
2. **RLS not fully enforced** — must be closed before any real multi-tenant data lands (connect as non-owner role + `SET app.current_org` per request).
3. **Migration baseline cleanup** — `0001` uses `metadata.create_all`, forcing `0002` to be idempotent; pin `0001` to explicit Phase-0 DDL before further schema work.
4. **Single-provider / mention-proxy limitations** — SoM is not yet cross-engine and mention ≠ endorsement; a negative discovery mention still counts.
5. **LIVE_ONLY diagnostics are demo-only** — useful for reliability tracking, not production monitoring; no fallback, bounded scope.

## 5. Recommended next 3 engineering moves (in order)

1. **Harden tenant isolation (RLS) + pin the migration baseline.** Foundational safety/hygiene; unblocks real data. Enforce RLS end-to-end and convert `0001` to explicit DDL, simplifying `0002`.
2. **Improve competitor extraction quality.** Move from "directional" to "trustworthy": entity-aware competitor identification (category/geo-scoped allowlist + cross-probe co-occurrence), so the competitor panel is demo-safe.
3. **Close the proof loop, Stage 1 (measured citation/recommendation lift over time).** Use the existing provenance + diagnostics history to show before/after Share-of-Model movement per entity — the first credible "business impact" signal.

## 6. What NOT to build yet

- No public UI / self-serve dashboard.
- No golden fallback implementation (keep LIVE_ONLY measuring real failure rate first).
- No new AI providers / cross-engine SoM until competitor quality + RLS are done.
- No auto-fix/execution or revenue attribution (Stages 2–3) yet.
- No changes to the frozen `src/geo_optimizer/` engine.

---
_This is a documentation checkpoint only — no product code changes._
