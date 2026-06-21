"""Scoring functions + thresholds for the Perception Probe evaluation.

Pure and dependency-free. Each function returns plain dicts/dataclasses so the
harness can aggregate and the self-tests can assert on them.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from geoready_platform.services.probe.non_competitor_domains import is_non_competitor

# ─── Thresholds (single source of truth; mirrored in README) ─────────────────

THRESHOLDS = {
    "contamination_rate_max": 0.0,          # hard gate
    "competitor_precision_min": 0.60,
    "competitor_recall_min": 0.40,
    "competitor_f1_min": 0.50,
    "recommendation_relevance_min": 0.90,
    "halluc_precision_min": 0.85,           # overall
    "halluc_claims_closed_precision_min": 1.00,  # hard gate
    "halluc_recall_min": 0.30,
    "som_rank_correlation_min": 0.50,
    "som_denominator_min": 2,
    "som_denominator_coverage_min": 0.90,
    "stability_som_stddev_max": 0.15,
    "stability_jaccard_min": 0.50,
}


# ─── Matching helpers ────────────────────────────────────────────────────────


def norm_domain(value: str) -> str:
    v = (value or "").strip().lower()
    if "://" in v:
        v = v.split("://", 1)[1]
    v = v.split("/")[0]
    return v[4:] if v.startswith("www.") else v


def domains_match(a: str, b: str) -> bool:
    a, b = norm_domain(a), norm_domain(b)
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _set_match_count(predicted: list[str], truth: list[str]) -> int:
    matched = 0
    used: set[int] = set()
    for p in predicted:
        for i, t in enumerate(truth):
            if i not in used and domains_match(p, t):
                used.add(i)
                matched += 1
                break
    return matched


# ─── Competitor identification ───────────────────────────────────────────────


@dataclass
class PRF:
    precision: float
    recall: float
    f1: float
    tp: int
    predicted: int
    truth: int


def competitor_prf(predicted: list[str], truth: list[str]) -> PRF:
    pred = [norm_domain(d) for d in predicted if d]
    tru = [norm_domain(d) for d in truth if d]
    tp = _set_match_count(pred, tru)
    precision = tp / len(pred) if pred else (1.0 if not tru else 0.0)
    recall = tp / len(tru) if tru else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return PRF(round(precision, 4), round(recall, 4), round(f1, 4), tp, len(pred), len(tru))


def contamination_rate(predicted_competitors: list[str]) -> float:
    """Fraction of predicted competitors that are reference/social/etc. domains."""
    if not predicted_competitors:
        return 0.0
    bad = sum(1 for d in predicted_competitors if is_non_competitor(norm_domain(d)))
    return round(bad / len(predicted_competitors), 4)


# ─── Recommendation relevance ────────────────────────────────────────────────


def recommendation_relevance(answers: list[dict], *, category: str, city: str | None) -> float:
    """Fraction of recommendation-class answers that are on-topic.

    On-topic = the answer references the category (or city). Proxy for prompt
    quality: a good buyer-intent prompt should not yield off-topic answers.
    ``answers`` items: {"category_key": str, "text": str, "answered": bool}.
    """
    rec = [a for a in answers if a.get("category_key") in {"category_recommendation", "problem_solution", "comparison"}]
    answered = [a for a in rec if a.get("answered")]
    if not answered:
        return 0.0
    cat_tokens = [w for w in re.findall(r"\w+", (category or "").lower()) if len(w) > 3]
    cty = (city or "").lower()
    on_topic = 0
    for a in answered:
        t = (a.get("text") or "").lower()
        if any(tok in t for tok in cat_tokens) or (cty and cty in t):
            on_topic += 1
    return round(on_topic / len(answered), 4)


# ─── Hallucination precision / recall ────────────────────────────────────────


@dataclass
class HallucPRF:
    precision: float
    recall: float
    tp: int
    fp: int
    fn: int
    per_type_precision: dict[str, float] = field(default_factory=dict)


def hallucination_prf(cases: list[dict]) -> HallucPRF:
    """Score flags against labeled cases.

    Each case: {"predicted": [flag_type,...], "expected": [flag_type,...]}.
    Precision/recall are computed over (case, flag_type) pairs.
    """
    tp = fp = fn = 0
    type_tp: dict[str, int] = {}
    type_fp: dict[str, int] = {}
    for c in cases:
        pred = set(c.get("predicted", []))
        exp = set(c.get("expected", []))
        for ft in pred:
            if ft in exp:
                tp += 1
                type_tp[ft] = type_tp.get(ft, 0) + 1
            else:
                fp += 1
                type_fp[ft] = type_fp.get(ft, 0) + 1
        for ft in exp:
            if ft not in pred:
                fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    per_type = {
        ft: round(type_tp.get(ft, 0) / (type_tp.get(ft, 0) + type_fp.get(ft, 0)), 4)
        for ft in set(type_tp) | set(type_fp)
    }
    return HallucPRF(round(precision, 4), round(recall, 4), tp, fp, fn, per_type)


# ─── Share-of-Model usefulness (rank correlation) ────────────────────────────

_TIER_RANK = {"low": 0, "medium": 1, "high": 2}


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation. Returns 0.0 for degenerate inputs."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1  # average rank for ties (1-based)
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 4) if den else 0.0


def som_rank_correlation(soms: list[float], tiers: list[str]) -> float:
    tier_vals = [_TIER_RANK.get((t or "").lower(), 1) for t in tiers]
    return spearman(soms, tier_vals)


# ─── Stability across repeated runs ──────────────────────────────────────────


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = {norm_domain(x) for x in a}, {norm_domain(x) for x in b}
    if not sa and not sb:
        return 1.0
    return round(len(sa & sb) / len(sa | sb), 4) if (sa | sb) else 1.0


@dataclass
class StabilityReport:
    som_stddev: float
    som_mean: float
    competitor_jaccard_median: float
    flag_persistence: dict[str, float]  # flag_type -> fraction of runs present


def stability(runs: list[dict]) -> StabilityReport:
    """``runs``: [{"share_of_model": float, "competitors": [domains], "flags": [types]}]."""
    soms = [r.get("share_of_model", 0.0) for r in runs]
    som_sd = round(statistics.pstdev(soms), 4) if len(soms) > 1 else 0.0
    som_mean = round(statistics.mean(soms), 4) if soms else 0.0

    jacc: list[float] = []
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            jacc.append(jaccard(runs[i].get("competitors", []), runs[j].get("competitors", [])))
    jacc_med = round(statistics.median(jacc), 4) if jacc else 1.0

    all_types: set[str] = set()
    for r in runs:
        all_types |= set(r.get("flags", []))
    persistence = {
        ft: round(sum(1 for r in runs if ft in set(r.get("flags", []))) / len(runs), 4)
        for ft in all_types
    } if runs else {}

    return StabilityReport(som_sd, som_mean, jacc_med, persistence)
