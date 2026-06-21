"""Self-tests for the evaluation metrics + a harness smoke run on fixtures."""

from __future__ import annotations

from probe_eval import harness, metrics


# ─── competitor PRF & contamination ──────────────────────────────────────────


def test_competitor_prf_exact_and_recall():
    prf = metrics.competitor_prf(["microsoft.com", "discord.com"],
                                 ["microsoft.com", "discord.com", "mattermost.com", "zoom.us"])
    assert prf.precision == 1.0
    assert prf.recall == 0.5
    assert prf.tp == 2


def test_competitor_prf_subdomain_match():
    prf = metrics.competitor_prf(["shop.globex.com"], ["globex.com"])
    assert prf.tp == 1


def test_contamination_detects_reference_sites():
    assert metrics.contamination_rate(["yelp.com", "globex.com"]) == 0.5
    assert metrics.contamination_rate(["globex.com", "joesplumbing.com"]) == 0.0


# ─── recommendation relevance ────────────────────────────────────────────────


def test_recommendation_relevance_token_based():
    answers = [
        {"category_key": "category_recommendation", "answered": True, "text": "Top messaging tools include X."},
        {"category_key": "category_recommendation", "answered": True, "text": "Here is a recipe for soup."},
    ]
    rel = metrics.recommendation_relevance(answers, category="team messaging software", city="San Francisco")
    assert rel == 0.5


# ─── hallucination PRF ───────────────────────────────────────────────────────


def test_hallucination_prf_counts():
    cases = [
        {"predicted": ["claims_closed"], "expected": ["claims_closed"]},
        {"predicted": [], "expected": ["claims_closed"]},          # fn
        {"predicted": ["claims_closed"], "expected": []},          # fp
    ]
    prf = metrics.hallucination_prf(cases)
    assert prf.tp == 1 and prf.fn == 1 and prf.fp == 1
    assert prf.per_type_precision["claims_closed"] == 0.5


# ─── spearman / SoM correlation ──────────────────────────────────────────────


def test_spearman_perfect_and_rank_correlation():
    assert metrics.spearman([1, 2, 3], [10, 20, 30]) == 1.0
    rho = metrics.som_rank_correlation([1.0, 1.0, 0.0, 0.0], ["high", "high", "low", "low"])
    assert rho >= 0.9


# ─── stability ───────────────────────────────────────────────────────────────


def test_stability_variance_and_jaccard():
    runs = [
        {"share_of_model": 0.6, "competitors": ["a.com", "b.com"], "flags": ["claims_closed"]},
        {"share_of_model": 0.5, "competitors": ["a.com"], "flags": ["claims_closed"]},
    ]
    rep = metrics.stability(runs)
    assert rep.som_stddev <= 0.15
    assert rep.flag_persistence["claims_closed"] == 1.0
    assert 0.0 <= rep.competitor_jaccard_median <= 1.0


# ─── hallucination labeled set must hit precision gates ───────────────────────


def test_labeled_hallucination_cases_meet_precision_gates():
    prf = harness.score_hallucination(harness.load_halluc_cases())
    # Hard gate: claims_closed precision must be perfect.
    assert prf.per_type_precision.get("claims_closed", 1.0) == 1.0
    # Overall precision gate.
    assert prf.precision >= metrics.THRESHOLDS["halluc_precision_min"]


# ─── harness replay smoke: contamination gate holds end-to-end ───────────────


def test_replay_contamination_is_zero_and_runs():
    report = harness.run_replay()
    assert report["fixtures_present"] >= 4
    assert report["metrics"]["contamination_rate_max"] == 0.0
    # SoM should rank high-prominence (Slack/Notion) above low (SMBs).
    assert report["metrics"]["som_rank_correlation"] >= 0.5
