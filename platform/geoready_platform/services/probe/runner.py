"""Probe orchestrator: enqueue + execute.

Mirrors services/audits.py, with two deliberate differences:
- Probes query AI engines ABOUT the business and never crawl the entity site,
  so there is **no ownership-verification gate** (approved decision). Auth +
  per-org daily quota still apply.
- Every persisted Perception row records full provenance (provider, model,
  taxonomy_version, prompt, raw_response, timestamp) so historical comparisons
  stay valid as scoring/taxonomy evolve.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from geoready_platform.config import get_settings
from geoready_platform.core_bridge.probe_adapter import resolve_probe_provider, run_prompt
from geoready_platform.db.base import session_scope
from geoready_platform.db.models import AuditStatus, BusinessEntity, Perception, ProbeRun
from geoready_platform.services.entities import get_entity
from geoready_platform.services.probe import hallucination, prompt_generator, share_of_model
from geoready_platform.services.probe.analysis import analyze_response
from geoready_platform.services.probe.share_of_model import AnalyzedResponse
from geoready_platform.services.probe.taxonomy import CATEGORY_BY_KEY

logger = logging.getLogger(__name__)


STALE_RUN_MINUTES = 10
STALE_RUN_MESSAGE = (
    "This analysis did not finish because the worker stopped or the server was "
    "restarted. Please run it again."
)


class ProbeQuotaExceededError(Exception):
    pass


class ProbeRunNotFoundError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _domain_of(website_url: str) -> str:
    parsed = urlparse(website_url if "://" in website_url else f"https://{website_url}")
    return (parsed.netloc or parsed.path).split("/")[0].lower()


def _provider_error_summary(provider: str, errors: list[str]) -> str:
    """Safe, user-facing reason for a run where every prompt failed at the
    provider. Never leaks keys or full stack traces — just the actionable cause."""
    blob = " ".join(errors).lower()
    if "401" in blob or "unauthorized" in blob:
        detail = "The provider returned 401 Unauthorized — the API key is missing, invalid, or expired."
        if provider == "openrouter":
            detail += " Check OPENROUTER_API_KEY in the API server environment."
    elif "403" in blob or "forbidden" in blob:
        detail = "The provider returned 403 Forbidden — the API key lacks access to this model."
    elif "429" in blob or "rate limit" in blob:
        detail = "The provider rate-limited the request (429). Try again shortly."
    elif "timeout" in blob or "timed out" in blob:
        detail = "The provider did not respond in time (timeout)."
    else:
        detail = "The provider could not be reached or returned an error."
    return f"The AI provider ({provider}) could not be reached for this run. {detail}"


def _resolve_prompts(*, entity_id: str, entity_facts: dict, max_prompts: int, api_key: str) -> list:
    """Return the prompts for this run. Order of preference:
    1. Cached custom prompts on the entity, if version matches (fastest, keeps
       trend runs comparable across the same generator).
    2. Freshly LLM-generated + cached back onto the entity (one-time cost).
    3. Static templates (always works, no LLM needed).
    """
    from geoready_platform.services.probe import prompt_extraction as pe
    from geoready_platform.services.probe.prompt_generator import GeneratedPrompt as StaticPrompt

    static_fallback = prompt_generator.generate_prompts(
        name=entity_facts["name"], category=entity_facts["category"],
        city=entity_facts["city"], country=None, max_prompts=max_prompts,
    )

    # Step 1: try the cache.
    with session_scope() as session:
        ent = session.get(BusinessEntity, entity_id)
        cached = pe.from_json(getattr(ent, "custom_prompts", None) or [])
        cached_ver = getattr(ent, "custom_prompts_version", None)
        if cached and cached_ver == pe.GENERATOR_VERSION and len(cached) >= max(4, min(4, max_prompts)):
            logger.info("Probe: using %d cached custom prompts for entity %s", len(cached), entity_id)
            return [StaticPrompt(category=p.category, text=p.text) for p in cached[:max_prompts]]

    # Step 2: generate now and cache. Fetch the homepage snippet so the LLM
    # writes long-tail queries around actual products/brands. Snippet fetch
    # failures are non-fatal — the generator still runs from category alone.
    from geoready_platform.services.probe.website_snippet import fetch_snippet

    snippet = fetch_snippet(entity_facts.get("website_url") or "")
    if snippet:
        logger.info("Probe: fetched %d chars of homepage text for %s", len(snippet), entity_id)
    else:
        logger.info("Probe: no homepage snippet available for %s (generator uses category only)", entity_id)

    try:
        generated = pe.generate_prompts_for_entity(
            name=entity_facts["name"], category=entity_facts["category"],
            city=entity_facts["city"], domain=entity_facts["domain"],
            website_snippet=snippet, target_count=max(max_prompts, pe.DEFAULT_TARGET_COUNT),
            api_key=api_key,
        )
    except pe.PromptGenerationError as exc:
        logger.warning("Prompt generator failed, falling back to static templates: %s", exc)
        return static_fallback

    if not generated:
        return static_fallback

    with session_scope() as session:
        ent = session.get(BusinessEntity, entity_id)
        if ent is not None:
            ent.custom_prompts = pe.to_json(generated)
            ent.custom_prompts_version = pe.GENERATOR_VERSION
    logger.info("Probe: generated + cached %d custom prompts for entity %s", len(generated), entity_id)
    return [StaticPrompt(category=p.category, text=p.text) for p in generated[:max_prompts]]


def _build_perception_details(row: dict) -> dict | None:
    """Bundle the per-response extras onto ``Perception.details`` so the frontend
    can render the ranking view without re-parsing the raw text."""
    payload: dict = {}
    if row.get("error"):
        payload["error"] = row["error"]
    if row.get("ranked_names"):
        payload["ranked_names"] = row["ranked_names"]
    if row.get("you_position") is not None:
        payload["you_position"] = row["you_position"]
    return payload or None


def _brand_name(canonical_name: str) -> str:
    """Return the AI-facing brand name — parenthetical labels stripped.

    Owners often add labels to disambiguate entities in their dashboard
    ("Era More Than Gold (new site)", "Acme Ltd (staging)"). Those labels are
    fine for the UI but MUST NOT reach AI-facing prompts or fact-check inputs,
    or every AI question becomes "Is Acme (staging) reputable?" — unusable."""
    from geoready_platform.services.probe.prompt_extraction import _strip_labels
    return _strip_labels(canonical_name)


def _detect_misinformation_or_empty(
    *, name: str, domain: str | None, website_url: str, answers: list[str], api_key: str,
) -> list[dict]:
    """Fetch the homepage snippet, run the misinformation detector, return the
    findings serialised for storage on ProbeRun.flags. Any failure returns an
    empty list — never blocks a run."""
    from geoready_platform.services.probe.misinformation import (
        MisinformationError, detect_misinformation, to_json,
    )
    from geoready_platform.services.probe.website_snippet import fetch_snippet

    snippet = fetch_snippet(website_url)
    if not snippet:
        logger.info("Misinformation detector: no homepage snippet, skipping")
        return []
    try:
        findings = detect_misinformation(
            name=name, domain=domain, website_snippet=snippet,
            answers=answers, api_key=api_key,
        )
    except MisinformationError as exc:
        logger.warning("Misinformation detector failed: %s", exc)
        return []
    if findings:
        logger.info("Misinformation detector found %d issues", len(findings))
    return to_json(findings)


def _extract_competitors_or_fallback(
    *, name: str, category: str | None, city: str | None, domain: str | None,
    rows: list[dict], fallback: list[dict], api_key: str,
) -> list[dict]:
    """Run the LLM competitor classifier over Phase B's answers. Any failure
    (network, malformed JSON, empty output) logs a warning and returns the
    legacy URL+denylist ``fallback`` list, so a probe run is never blocked by
    this enrichment step."""
    from geoready_platform.services.probe.competitor_extraction import (
        CompetitorExtractionError,
        classify_competitors,
        filter_for_report,
    )

    answers = [(r["prompt"], r["raw_response"] or "") for r in rows if r.get("raw_response")]
    if not answers:
        return fallback
    candidate_domains = sorted({d.get("name") for d in (fallback or []) if isinstance(d, dict) and d.get("name")})

    try:
        classified = classify_competitors(
            name=name, category=category, city=city, domain=domain,
            answers=answers,
            candidate_domains=[d for d in candidate_domains if isinstance(d, str)],
            api_key=api_key,
        )
    except CompetitorExtractionError as exc:
        logger.warning("Competitor classifier failed, using legacy list: %s", exc)
        return fallback

    surfaced = filter_for_report(classified)
    if not surfaced:
        # Classifier ran but returned no confident businesses. Prefer the legacy
        # list over showing nothing at all.
        logger.info("Classifier returned no confident businesses; using legacy list")
        return fallback
    # Log dropped candidates so we can eyeball what was filtered.
    dropped = [(c.name, c.type, c.confidence) for c in classified if c.type != "business" or c.confidence < 0.7]
    if dropped:
        logger.info("Classifier dropped %d non-competitor candidates: %s", len(dropped), dropped[:10])
    return surfaced


def _check_quota(session: Session, org_id: str) -> None:
    """Enforce the org's plan check allowance. Paid plans are unlimited
    (``checks_per_day is None``); free is capped."""
    from geoready_platform.db.models import Org
    from geoready_platform.services.plans import limits_for

    org = session.get(Org, org_id)
    limits = limits_for(org.plan if org else None)
    if limits.checks_per_day is None:
        return  # unlimited

    since = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count = session.execute(
        select(func.count(ProbeRun.id)).where(ProbeRun.org_id == org_id, ProbeRun.created_at >= since)
    ).scalar_one()
    if count >= limits.checks_per_day:
        raise ProbeQuotaExceededError(
            f"You've used all {limits.checks_per_day} of today's free checks. "
            "Upgrade for unlimited checks, or try again tomorrow."
        )


def _mark_dispatch_failure(run_id: str, exc: BaseException) -> None:
    """Mark a `queued` run as `failed` after a dispatch-layer crash.

    Called from both the synchronous inline path and the background thread guard
    so that NO probe row can ever stay stuck in `queued` because the task
    framework (Celery broker, thread machinery) blew up between commit and
    execution. Idempotent: a run already `complete`/`failed` is left alone.
    """
    try:
        with session_scope() as session:
            run = session.get(ProbeRun, run_id)
            if run is not None and run.status not in (
                AuditStatus.complete.value,
                AuditStatus.failed.value,
            ):
                run.status = AuditStatus.failed.value
                run.error = f"Worker crashed: {type(exc).__name__}: {exc}"
                run.completed_at = _utcnow()
    except Exception:  # noqa: BLE001
        logger.exception("Could not mark run %s failed after dispatch crash", run_id)


def _run_probe_in_thread(run_id: str) -> None:
    """Thread target: execute the probe job and mark failed on ANY crash."""
    try:
        from geoready_platform.workers.probe_task import run_probe_job

        run_probe_job.apply(args=[run_id])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Probe thread crashed for run %s", run_id)
        _mark_dispatch_failure(run_id, exc)


def enqueue_probe(session: Session, *, org_id: str, entity_id: str) -> ProbeRun:
    """Create a queued probe run. Auth + quota only — NO ownership gate.

    Every created run is guaranteed to reach `running` / `complete` / `failed`:
    each dispatch branch either succeeds, or marks the run failed before
    returning. A row can never be left orphaned in `queued` by this path.
    """
    entity = get_entity(session, org_id=org_id, entity_id=entity_id)
    _check_quota(session, org_id)

    run = ProbeRun(
        entity_id=entity.id,
        org_id=org_id,
        status=AuditStatus.queued.value,
        taxonomy_version=prompt_generator.current_taxonomy_version(),
    )
    session.add(run)
    session.flush()
    run_id = run.id
    logger.info("Created probe run %s for entity %s", run_id, entity_id)

    # Commit before dispatch so the worker (eager or remote) can read the run.
    session.commit()

    from geoready_platform.workers.probe_task import run_probe_job

    settings = get_settings()
    if settings.celery_eager:
        if settings.probe_eager_background:
            import threading

            logger.info("Dispatching probe %s on background thread (eager)", run_id)
            threading.Thread(target=_run_probe_in_thread, args=(run_id,), daemon=True).start()
        else:
            logger.info("Running probe %s inline (eager, blocking)", run_id)
            try:
                run_probe_job.apply(args=[run_id])
            except Exception as exc:  # noqa: BLE001 — never leave the run queued
                logger.exception("Inline probe dispatch crashed for run %s", run_id)
                _mark_dispatch_failure(run_id, exc)
                raise
    else:
        try:
            logger.info("Dispatching probe %s to Celery broker", run_id)
            run_probe_job.delay(run_id)
        except Exception as exc:  # noqa: BLE001 — broker down
            logger.exception("Failed to dispatch probe %s to broker, falling back to thread", run_id)
            import threading

            threading.Thread(target=_run_probe_in_thread, args=(run_id,), daemon=True).start()

    return run


def reap_stale_runs(
    session: Session, *, org_id: str | None = None, older_than_minutes: int = STALE_RUN_MINUTES
) -> int:
    """Mark queued/running runs older than the threshold as failed.

    Such runs are orphans from a crashed/restarted worker — they will never
    complete on their own and otherwise show as perpetually "active" on the
    portfolio/result pages. Only the run row is touched, so any Perception rows
    already collected are preserved. Recent (still-plausibly-active) runs are
    left alone. Idempotent; returns the number reaped.
    """
    cutoff = _utcnow() - timedelta(minutes=older_than_minutes)
    stmt = select(ProbeRun).where(
        ProbeRun.status.in_((AuditStatus.queued.value, AuditStatus.running.value)),
        func.coalesce(ProbeRun.started_at, ProbeRun.created_at) < cutoff,
    )
    if org_id is not None:
        stmt = stmt.where(ProbeRun.org_id == org_id)
    stale = session.execute(stmt).scalars().all()
    for run in stale:
        run.status = AuditStatus.failed.value
        run.error = STALE_RUN_MESSAGE
        run.completed_at = _utcnow()
    if stale:
        session.flush()
    return len(stale)


def get_probe(session: Session, *, org_id: str, run_id: str) -> ProbeRun:
    run = session.execute(
        select(ProbeRun).where(ProbeRun.id == run_id, ProbeRun.org_id == org_id)
    ).scalar_one_or_none()
    if run is None:
        raise ProbeRunNotFoundError(run_id)
    return run


def execute_probe_run(run_id: str) -> None:
    """Run all prompts for a probe, persist per-prompt Perceptions + run metrics."""
    logger.info("Running probe job %s", run_id)
    settings = get_settings()

    # Phase A: load run + entity facts, mark running.
    with session_scope() as session:
        run = session.get(ProbeRun, run_id)
        if run is None:
            raise ProbeRunNotFoundError(run_id)
        entity = session.get(BusinessEntity, run.entity_id)
        if entity is None:
            run.status = AuditStatus.failed.value
            run.error = "Entity missing at execution time"
            run.completed_at = _utcnow()
            return
        run.status = AuditStatus.running.value
        run.started_at = _utcnow()
        facts = {
            # Strip any parenthetical labels the owner used to disambiguate the
            # business in their dashboard — those must never leak into AI
            # questions (e.g. "Is Era (new site) reputable?" is unusable).
            "name": _brand_name(entity.canonical_name),
            "category": entity.category,
            "city": entity.geo,
            "domain": _domain_of(entity.website_url),
            "website_url": entity.website_url,
        }
        org_id = entity.org_id
        entity_id = entity.id
        taxonomy_version = run.taxonomy_version
        session.flush()

    # Resolve provider once.
    provider, api_key = resolve_probe_provider(settings.probe_provider)
    logger.info("Probe %s: provider=%s, key_set=%s", run_id, provider, bool(api_key))
    if not provider or not api_key:
        with session_scope() as session:
            run = session.get(ProbeRun, run_id)
            if run is not None:
                run.status = AuditStatus.failed.value
                run.error = (
                    "No AI provider configured. Set OPENROUTER_API_KEY (recommended: one key, 400+ "
                    "models incl. web-grounded Perplexity) or PERPLEXITY_API_KEY / OPENAI_API_KEY / "
                    "ANTHROPIC_API_KEY in the API server environment."
                )
                run.completed_at = _utcnow()
        return

    # Buyer questions: prefer LLM-tailored ones cached on the entity (so trend
    # runs stay comparable), else generate them now and cache, else fall back
    # to the static templates so a probe is never blocked by generator issues.
    prompts = _resolve_prompts(
        entity_id=entity_id, entity_facts=facts,
        max_prompts=settings.probe_max_prompts, api_key=api_key,
    )

    # Phases B + C run under a failure guard: any unexpected error (provider
    # library, analysis edge case, DB write) marks the run failed instead of
    # leaving it stuck in `running` or propagating a 500 in eager mode. Mirrors
    # the audit service's contract.
    try:
        # Phase B: run prompts OUTSIDE any DB transaction (network I/O).
        rows: list[dict] = []
        analyzed: list[AnalyzedResponse] = []
        model_seen = ""
        answered = 0

        for gp in prompts:
            resp = run_prompt(gp.text, provider=provider, api_key=api_key)
            model_seen = model_seen or resp.model
            cat = CATEGORY_BY_KEY.get(gp.category)
            counts_for_factual = bool(cat and cat.counts_for_factual)
            is_answered = not resp.error and bool(resp.text.strip())
            answered += 1 if is_answered else 0

            signals = analyze_response(
                text=resp.text,
                citations=resp.citations,
                name=facts["name"],
                domain=facts["domain"],
                category=facts["category"],
            )
            flags = (
                hallucination.detect_flags(
                    text=resp.text,
                    category_key=gp.category,
                    brand_mentioned=signals.brand_mentioned,
                    name=facts["name"],
                    city=facts["city"],
                    counts_for_factual=counts_for_factual,
                )
                if is_answered
                else []
            )

            analyzed.append(
                AnalyzedResponse(
                    category=gp.category,
                    answered=is_answered,
                    brand_mentioned=signals.brand_mentioned,
                    competitor_domains=signals.competitor_domains,
                    competitor_names=signals.competitor_names,
                )
            )
            # Extract the ranked business list from the AI answer — the report
            # renders these compact ranking rows instead of the full prose,
            # which is what buyers actually want to see (position, not phone).
            from geoready_platform.services.probe.rank_extraction import (
                brand_position, extract_ranked_names,
            )
            ranked_names = extract_ranked_names(resp.text) if is_answered else []
            you_position = brand_position(ranked_names, facts["name"]) if ranked_names else None

            rows.append(
                {
                    "prompt_category": gp.category,
                    "prompt": gp.text,
                    "provider": resp.provider,
                    "model": resp.model,
                    "raw_response": resp.text,
                    "recommended": signals.brand_mentioned if (cat and cat.counts_for_share) else None,
                    "brand_mentioned": signals.brand_mentioned,
                    "domain_cited": signals.domain_cited,
                    "competitors_named": signals.competitor_domains + signals.competitor_names,
                    "flags": [f.__dict__ for f in flags],
                    "error": resp.error,
                    "ranked_names": ranked_names,
                    "you_position": you_position,
                }
            )

        som = share_of_model.compute_share_of_model(analyzed)

        # A run where EVERY prompt failed at the provider (e.g. 401) produced no
        # readable answers — it is a provider/auth failure, not a 0-visibility
        # result. Mark it failed (with a safe reason) so the UI never presents it
        # as a legitimate report. Per-prompt rows + details.error are still saved
        # below for diagnostics. Partial runs stay `complete` (frontend warns).
        provider_errors = [row["error"] for row in rows if row["error"]]
        all_failed = bool(rows) and answered == 0 and len(provider_errors) == len(rows)
        run_error = _provider_error_summary(provider, provider_errors) if all_failed else None

        # Phase B.4: misinformation detection — flag facts AI stated wrong.
        # Reads the homepage + all answers, returns a list of {issue, evidence,
        # fix}. Failures are non-fatal; they just leave the flag list empty.
        misinfo_flags: list[dict] = []
        if not all_failed and answered > 0:
            misinfo_flags = _detect_misinformation_or_empty(
                name=facts["name"], domain=facts.get("domain"),
                website_url=facts.get("website_url") or "",
                answers=[r["raw_response"] for r in rows if r.get("raw_response")],
                api_key=api_key,
            )

        run_flags = [
            {**f, "perception_index": i}
            for i, row in enumerate(rows)
            for f in row["flags"]
        ]
        # Append misinformation findings as top-level run flags — they aren't
        # tied to a single response so they carry no perception_index.
        run_flags.extend(misinfo_flags)

        # Phase B.5: semantic competitor extraction.
        # Ask the LLM to identify who a buyer would ACTUALLY consider instead —
        # replacing the URL-count + static denylist output. Falls back to the
        # legacy list on any failure so a run is never blocked by this.
        competitors_for_run = som.competitors  # fallback: today's URL-count list
        if not all_failed and answered > 0:
            competitors_for_run = _extract_competitors_or_fallback(
                name=facts["name"],
                category=facts["category"],
                city=facts["city"],
                domain=facts["domain"],
                rows=rows,
                fallback=som.competitors,
                api_key=api_key,
            )

        # Phase C: persist everything.
        final_status = "failed" if all_failed else "complete"
        logger.info("Probe %s: %d/%d answered, status=%s", run_id, answered, len(rows), final_status)
        with session_scope() as session:
            run = session.get(ProbeRun, run_id)
            if run is None:
                raise ProbeRunNotFoundError(run_id)
            run.status = AuditStatus.failed.value if all_failed else AuditStatus.complete.value
            run.error = run_error
            run.provider = provider
            run.model = model_seen
            run.prompt_count = len(rows)
            run.answered_count = answered
            run.share_of_model = som.share_of_model
            run.recommended_count = som.recommended_count
            run.competitors = competitors_for_run
            run.flags = run_flags
            run.completed_at = _utcnow()

            for row in rows:
                session.add(
                    Perception(
                        entity_id=entity_id,
                        org_id=org_id,
                        probe_run_id=run_id,
                        engine=provider,
                        provider=row["provider"],
                        model=row["model"],
                        taxonomy_version=taxonomy_version,
                        prompt_category=row["prompt_category"],
                        prompt=row["prompt"],
                        raw_response=row["raw_response"],
                        recommended=row["recommended"],
                        brand_mentioned=row["brand_mentioned"],
                        domain_cited=row["domain_cited"],
                        competitors_named=row["competitors_named"],
                        flags=row["flags"],
                        details=_build_perception_details(row),
                    )
                )
    except ProbeRunNotFoundError:
        raise
    except Exception as exc:  # noqa: BLE001 — record any failure, never leave run hanging
        with session_scope() as session:
            run = session.get(ProbeRun, run_id)
            if run is not None and run.status != AuditStatus.complete.value:
                run.status = AuditStatus.failed.value
                run.error = f"{type(exc).__name__}: {exc}"
                run.completed_at = _utcnow()
        return
