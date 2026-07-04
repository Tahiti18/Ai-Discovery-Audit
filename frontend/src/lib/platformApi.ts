/**
 * Typed client for the AI Visibility OS platform API.
 *
 * - Talks to the platform via the Vite `/papi` proxy (no CORS dependency; the
 *   browser never sees the API origin or any provider key).
 * - Auth: `X-API-Key` from the local workspace (local-operator convenience).
 * - Every call returns `{ data, error }` — never throws to callers.
 * - Future-ready: probe results are normalized into a per-engine shape so adding
 *   ChatGPT/Claude later is additive, not a refactor.
 */

import { getApiKey } from "./platformStore";
import { getAccessToken } from "../app/session";

// Direct to the platform API (CORS-enabled for local dev). Override with
// PUBLIC_PLATFORM_API_BASE for other environments.
const BASE = (import.meta.env.PUBLIC_PLATFORM_API_BASE as string) || "https://geo-optimizer-web-production.up.railway.app";

// Per-endpoint timeout tiers. Health/entities should be snappy; probe reads
// (result + per-prompt answers) can legitimately be slower, so they get more
// headroom. A slow read must never be cut as aggressively as a liveness check.
const REQUEST_TIMEOUT_MS = 20_000; // default
const TIMEOUT = {
  health: 6_000,
  quick: 12_000,   // orgs, entities
  enqueue: 15_000, // returns 202 fast (probe runs in background)
  poll: 12_000,    // a single probe-status tick
  read: 45_000,    // probe result + per-prompt responses (can be larger)
} as const;

export interface ApiResult<T> {
  data: T | null;
  error: string | null;
  status?: number;
}

// ─── Backend response types (mirror platform schemas) ────────────────────────

export interface OrgCreated {
  org: { id: string; name: string; plan: string; created_at: string };
  api_key: string;
}
export interface Entity {
  id: string;
  org_id: string;
  canonical_name: string;
  website_url: string;
  category: string | null;
  geo: string | null;
  verified_at: string | null;
  created_at: string;
}
export interface ProbeEnqueued {
  probe_run_id: string;
  status: string;
}
export interface MagicLinkRequested {
  sent: boolean;
  dev_login_url?: string | null;
  dev_token?: string | null;
}
export interface VerifiedSession {
  access_token: string;
  token_type: string;
  user: { id: string; email: string; name: string | null };
  org: { id: string; name: string; plan: string; role: string };
}
export interface Competitor {
  name: string;
  mentions: number;
}
export interface ProbeFlag {
  type: string;
  severity?: string;
  evidence?: string;
  perception_index?: number;
  // Only present on LLM-misinformation flags (source === "llm_misinformation").
  source?: string;
  issue_type?: string;
  description?: string;
  fix?: string;
  confidence?: number;
}
export interface ProbeRun {
  id: string;
  entity_id: string;
  status: "queued" | "running" | "complete" | "failed" | string;
  provider: string | null;
  model: string | null;
  taxonomy_version: string | null;
  prompt_count: number;
  answered_count: number;
  share_of_model: number | null; // 0..1
  recommended_count: number;
  competitors: Competitor[] | null;
  flags: ProbeFlag[] | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
export interface Perception {
  id: string;
  probe_run_id: string | null;
  prompt_category: string | null;
  provider: string | null;
  model: string | null;
  taxonomy_version: string | null;
  prompt: string | null;
  raw_response: string | null;
  recommended: boolean | null;
  brand_mentioned: boolean | null;
  domain_cited: boolean | null;
  competitors_named: unknown[] | null;
  flags: unknown[] | null;
  details: {
    error?: string;
    /** Ranked business names extracted from the AI answer (top ≤10, in order). */
    ranked_names?: string[];
    /** 1-indexed position of the entity in ``ranked_names``, or null. */
    you_position?: number | null;
  } | null;
  probed_at: string;
}
export interface Signal {
  id: string;
  entity_id: string;
  source: string;
  signal_type: string;
  value: Record<string, unknown>;
  fetched_at: string;
}
export interface AuditJob {
  id: string;
  entity_id: string;
  status: string;
  triggered_by: string;
  score: number | null;
  band: string | null;
  score_breakdown: Record<string, unknown> | null;
  full_result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// ─── Core fetch ──────────────────────────────────────────────────────────────

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  withAuth = true,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (withAuth) {
    // Prefer the magic-link session JWT; fall back to a local API key if present.
    const token = getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    } else {
      const key = getApiKey();
      if (key) headers["X-API-Key"] = key;
    }
  }
  // Hard timeout so a hung request can never freeze the UI (e.g. a blocked
  // enqueue). The caller gets a friendly, actionable error instead of spinning.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    const text = await res.text();
    const json = text ? JSON.parse(text) : null;
    if (!res.ok) {
      // A 401 on a JWT-authed call means the session expired or was revoked.
      // Self-heal: clear the dead session and hand the user back to sign-in,
      // instead of surfacing "Invalid token" errors all over the app.
      if (res.status === 401 && withAuth && getAccessToken() && typeof window !== "undefined") {
        const { clearSession } = await import("../app/session");
        clearSession();
        window.location.href = "/login/?expired=1";
        return { data: null, error: "Your session expired — signing you back in.", status: 401 };
      }
      let detail = String((json && (json.detail || json.error || json.message)) || `HTTP ${res.status}`);
      // Friendlier local-dev message for the probe quota (it's just an env var).
      if (res.status === 429 && /quota/i.test(detail)) {
        detail =
          "Local development probe limit reached. Raise it by setting GR_FREE_PROBES_PER_DAY " +
          "higher in the API server environment and restarting the API. Your existing results " +
          "are still viewable — only “Run again” uses the quota.";
      }
      return { data: null, error: detail, status: res.status };
    }
    return { data: json as T, error: null, status: res.status };
  } catch (e) {
    // Network/connection failures get a human, actionable message (the API is
    // almost always just not running). Never surface a raw "Failed to fetch".
    if (e instanceof DOMException && e.name === "AbortError") {
      return { data: null, error: "The request timed out. The API may be busy or unreachable — please try again." };
    }
    const raw = e instanceof Error ? e.message : "Network error";
    const friendly = /failed to fetch|networkerror|load failed/i.test(raw)
      ? "Couldn't reach the analysis API. Make sure the API server is running on port 8001."
      : raw;
    return { data: null, error: friendly };
  } finally {
    clearTimeout(timer);
  }
}

// ─── Endpoints ───────────────────────────────────────────────────────────────

export const api = {
  health: () => request<{ status: string; db: boolean }>("GET", "/healthz", undefined, false, TIMEOUT.health),

  // ─── Magic-link auth (no credentials needed on these two) ───────────────────
  requestMagicLink: (email: string) =>
    request<MagicLinkRequested>("POST", "/v1/auth/request", { email }, false, TIMEOUT.quick),
  verifyMagicLink: (token: string) =>
    request<VerifiedSession>("POST", "/v1/auth/verify", { token }, false, TIMEOUT.quick),

  // ─── Billing: start a hosted Stripe Checkout ────────────────────────────────
  createCheckout: (plan: "pro" | "founding" | "business") =>
    request<{ url: string }>("POST", "/v1/billing/checkout", { plan }, true, TIMEOUT.quick),

  createOrg: (name: string, ownerEmail: string) =>
    request<OrgCreated>("POST", "/v1/orgs", { name, owner_email: ownerEmail }, false, TIMEOUT.quick),

  createEntity: (input: {
    canonical_name: string;
    website_url: string;
    category?: string | null;
    geo?: string | null;
  }) => request<Entity>("POST", "/v1/entities", input, true, TIMEOUT.quick),

  listEntities: () => request<Entity[]>("GET", "/v1/entities", undefined, true, TIMEOUT.quick),
  getEntity: (id: string) => request<Entity>("GET", `/v1/entities/${id}`, undefined, true, TIMEOUT.quick),

  enqueueProbe: (entityId: string) =>
    request<ProbeEnqueued>("POST", `/v1/entities/${entityId}/probes`, undefined, true, TIMEOUT.enqueue),
  getProbe: (runId: string) => request<ProbeRun>("GET", `/v1/probes/${runId}`, undefined, true, TIMEOUT.poll),
  getProbeResponses: (runId: string) =>
    request<Perception[]>("GET", `/v1/probes/${runId}/responses`, undefined, true, TIMEOUT.read),
  listEntityProbes: (entityId: string) =>
    request<ProbeRun[]>("GET", `/v1/entities/${entityId}/probes`, undefined, true, TIMEOUT.quick),

  getSignals: (entityId: string) => request<Signal[]>("GET", `/v1/entities/${entityId}/signals`),

  enqueueAudit: (entityId: string) =>
    request<{ audit_job_id: string; status: string }>("POST", `/v1/entities/${entityId}/audits`),
  getAudit: (jobId: string) => request<AuditJob>("GET", `/v1/audits/${jobId}`),
};

/** Fetch the complete technical-report HTML (authed). Returns raw HTML so the
 *  caller can open it as a blob — a plain <a> can't send the Bearer header. */
export async function fetchTechnicalReportHtml(
  entityId: string,
): Promise<{ html: string | null; error: string | null; status?: number }> {
  const token = getAccessToken();
  try {
    const res = await fetch(`${BASE}/v1/entities/${entityId}/technical-report`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { const j = await res.json(); detail = j.detail || detail; } catch { /* not json */ }
      return { html: null, error: detail, status: res.status };
    }
    return { html: await res.text(), error: null, status: res.status };
  } catch (e) {
    return { html: null, error: e instanceof Error ? e.message : "Network error" };
  }
}

// ─── Probe polling (backoff + cancel + timeout) ──────────────────────────────

export interface PollHandle {
  cancel: () => void;
}

export function pollProbe(
  runId: string,
  opts: {
    onTick?: (run: ProbeRun) => void;
    onDone: (run: ProbeRun) => void;
    onError: (msg: string) => void;
    onTransient?: (msg: string) => void; // a tolerated, recoverable hiccup
    timeoutMs?: number;
  },
): PollHandle {
  let cancelled = false;
  const started = Date.now();
  const timeoutMs = opts.timeoutMs ?? 180_000; // bounded: web-grounded probes can take a couple of minutes
  let delay = 1200;
  let consecutiveErrors = 0;
  const MAX_CONSECUTIVE_ERRORS = 5; // a single slow/failed tick must not kill the page

  const tick = async () => {
    if (cancelled) return;
    const { data, error } = await api.getProbe(runId);
    if (cancelled) return;
    if (error || !data) {
      // Tolerate transient failures (API briefly busy, one timed-out tick) and
      // keep polling; only give up after several in a row.
      consecutiveErrors += 1;
      if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS || Date.now() - started > timeoutMs) {
        opts.onError(error || "Lost contact with the analysis. It may still be running — try again.");
        return;
      }
      opts.onTransient?.(error || "Reconnecting…");
      delay = Math.min(delay * 1.5, 5000);
      setTimeout(tick, delay);
      return;
    }
    consecutiveErrors = 0;
    opts.onTick?.(data);
    if (data.status === "complete" || data.status === "failed") {
      opts.onDone(data);
      return;
    }
    if (Date.now() - started > timeoutMs) {
      opts.onError("The analysis is taking longer than expected. It may still finish — check back shortly.");
      return;
    }
    delay = Math.min(delay * 1.25, 4000); // gentle backoff
    setTimeout(tick, delay);
  };

  setTimeout(tick, 600);
  return { cancel: () => { cancelled = true; } };
}

// ─── Honest derived helpers (no fabrication) ─────────────────────────────────

/** Share-of-Model as a percentage 0..100, or null if not computed. */
export function somPct(run: Pick<ProbeRun, "share_of_model">): number | null {
  return run.share_of_model == null ? null : Math.round(run.share_of_model * 100);
}

// ─── Health: ONE shared poller for the whole app (prevents /healthz spam) ─────
// A single module-level interval, regardless of how many components subscribe or
// how often the shell re-renders. Checks once immediately, then every 60s.

type HealthState = boolean | null;
const HEALTH_INTERVAL_MS = 60_000;
let _healthStatus: HealthState = null;
let _healthTimer: ReturnType<typeof setInterval> | null = null;
const _healthSubs = new Set<(s: HealthState) => void>();

async function _runHealthCheck(): Promise<void> {
  const { data } = await api.health();
  _healthStatus = !!data && data.status === "ok";
  _healthSubs.forEach((fn) => fn(_healthStatus));
}

/** Subscribe to shared health status. Starts the single poller on first
 *  subscriber; stops it when the last unsubscribes. Returns an unsubscribe fn. */
export function subscribeHealth(cb: (s: HealthState) => void): () => void {
  _healthSubs.add(cb);
  cb(_healthStatus); // hand over the last known value immediately
  if (_healthTimer === null) {
    void _runHealthCheck(); // one check on start
    _healthTimer = setInterval(() => void _runHealthCheck(), HEALTH_INTERVAL_MS);
  }
  return () => {
    _healthSubs.delete(cb);
    if (_healthSubs.size === 0 && _healthTimer !== null) {
      clearInterval(_healthTimer);
      _healthTimer = null;
    }
  };
}

/** Manual one-off re-check (e.g. a "Retry" button). One extra call, no new loop. */
export function refreshHealth(): void {
  void _runHealthCheck();
}
