"""Perception Probe evaluation harness.

Modes:
- replay  : score recorded fixtures through the real probe pure-layers (offline,
            reproducible, CI-safe). Default.
- record  : run live probes against the benchmark and write fixtures. Requires
            PERPLEXITY_API_KEY (or another provider key). Not run in CI.

Outputs a per-dimension report with pass/fail against metrics.THRESHOLDS.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from geoready_platform.services.probe import hallucination
from geoready_platform.services.probe.analysis import analyze_response
from geoready_platform.services.probe.share_of_model import AnalyzedResponse, compute_share_of_model
from geoready_platform.services.probe.taxonomy import CATEGORY_BY_KEY

from probe_eval import metrics

BASE = Path(__file__).parent
BENCH = BASE / "benchmark"
FIXTURES = BASE / "fixtures"


# ─── Loading ─────────────────────────────────────────────────────────────────


def load_businesses() -> list[dict]:
    return json.loads((BENCH / "businesses.json").read_text(encoding="utf-8"))["businesses"]


def load_halluc_cases() -> list[dict]:
    return json.loads((BENCH / "hallucination_cases.json").read_text(encoding="utf-8"))["cases"]


def load_fixture(business_id: str) -> dict | None:
    path = FIXTURES / f"{business_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _domain_of(website: str) -> str:
    return metrics.norm_domain(website)


# ─── Per-business scoring (replay) ───────────────────────────────────────────


def score_business(biz: dict, fixture: dict) -> dict:
    name = biz["name"]
    domain = _domain_of(biz["website"])
    analyzed: list[AnalyzedResponse] = []
    rel_answers: list[dict] = []
    flags_by_type: set[str] = set()

    for r in fixture["responses"]:
        text = r.get("text", "")
        citations = r.get("citations", [])
        cat = CATEGORY_BY_KEY.get(r["category_key"])
        answered = bool(text.strip())
        sig = analyze_response(text=text, citations=citations, name=name, domain=domain)
        analyzed.append(
            AnalyzedResponse(
                category=r["category_key"],
                answered=answered,
                brand_mentioned=sig.brand_mentioned,
                competitor_domains=sig.competitor_domains,
                competitor_names=sig.competitor_names,
            )
        )
        rel_answers.append({"category_key": r["category_key"], "text": text, "answered": answered})
        if answered and cat:
            for f in hallucination.detect_flags(
                text=text,
                category_key=r["category_key"],
                brand_mentioned=sig.brand_mentioned,
                name=name,
                counts_for_factual=cat.counts_for_factual,
            ):
                flags_by_type.add(f.type)

    som = compute_share_of_model(analyzed)
    predicted_competitors = [c["name"] for c in som.competitors]

    result = {
        "id": biz["id"],
        "prominence_tier": biz["prominence_tier"],
        "share_of_model": som.share_of_model,
        "share_denominator": som.share_denominator,
        "predicted_competitors": predicted_competitors,
        "contamination_rate": metrics.contamination_rate(predicted_competitors),
        "recommendation_relevance": metrics.recommendation_relevance(
            rel_answers, category=biz.get("category", ""), city=biz.get("city")
        ),
        "flags": sorted(flags_by_type),
    }
    if not biz.get("needs_review", True):
        result["competitor_prf"] = metrics.competitor_prf(
            predicted_competitors, biz.get("known_competitors", [])
        ).__dict__
    return result


# ─── Aggregation + thresholds ────────────────────────────────────────────────


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def aggregate(results: list[dict], halluc: metrics.HallucPRF) -> dict:
    contamination_max = max((r["contamination_rate"] for r in results), default=0.0)
    rel = _mean([r["recommendation_relevance"] for r in results])

    prfs = [r["competitor_prf"] for r in results if "competitor_prf" in r]
    comp_p = _mean([p["precision"] for p in prfs])
    comp_r = _mean([p["recall"] for p in prfs])
    comp_f1 = _mean([p["f1"] for p in prfs])

    soms = [r["share_of_model"] for r in results]
    tiers = [r["prominence_tier"] for r in results]
    rho = metrics.som_rank_correlation(soms, tiers)
    denom_cov = _mean([1.0 if r["share_denominator"] >= metrics.THRESHOLDS["som_denominator_min"] else 0.0 for r in results])

    t = metrics.THRESHOLDS
    cc_precision = halluc.per_type_precision.get("claims_closed", 1.0)

    gates = {
        "contamination_zero (HARD)": contamination_max <= t["contamination_rate_max"],
        "claims_closed_precision==1.0 (HARD)": cc_precision >= t["halluc_claims_closed_precision_min"],
        "competitor_precision": comp_p >= t["competitor_precision_min"],
        "competitor_recall": comp_r >= t["competitor_recall_min"],
        "competitor_f1": comp_f1 >= t["competitor_f1_min"],
        "recommendation_relevance": rel >= t["recommendation_relevance_min"],
        "hallucination_precision": halluc.precision >= t["halluc_precision_min"],
        "hallucination_recall": halluc.recall >= t["halluc_recall_min"],
        "som_rank_correlation": rho >= t["som_rank_correlation_min"],
        "som_denominator_coverage": denom_cov >= t["som_denominator_coverage_min"],
    }
    hard_gates = [k for k in gates if "HARD" in k]
    hard_ok = all(gates[k] for k in hard_gates)
    soft = [k for k in gates if "HARD" not in k]
    soft_pass_rate = _mean([1.0 if gates[k] else 0.0 for k in soft])
    overall = hard_ok and soft_pass_rate >= 0.80

    return {
        "businesses_scored": len(results),
        "metrics": {
            "contamination_rate_max": contamination_max,
            "competitor_precision": comp_p,
            "competitor_recall": comp_r,
            "competitor_f1": comp_f1,
            "recommendation_relevance": rel,
            "hallucination_precision": halluc.precision,
            "hallucination_recall": halluc.recall,
            "claims_closed_precision": cc_precision,
            "som_rank_correlation": rho,
            "som_denominator_coverage": denom_cov,
        },
        "gates": gates,
        "soft_pass_rate": soft_pass_rate,
        "overall_pass": overall,
    }


def score_hallucination(cases: list[dict]) -> metrics.HallucPRF:
    scored = []
    for c in cases:
        cat = CATEGORY_BY_KEY.get(c["category_key"])
        predicted = [
            f.type
            for f in hallucination.detect_flags(
                text=c["text"],
                category_key=c["category_key"],
                brand_mentioned=c["brand_mentioned"],
                name=c["name"],
                counts_for_factual=c.get("counts_for_factual", bool(cat and cat.counts_for_factual)),
            )
        ]
        scored.append({"predicted": predicted, "expected": c["expected"]})
    return metrics.hallucination_prf(scored)


# ─── Replay / Record entrypoints ─────────────────────────────────────────────


def run_replay() -> dict:
    businesses = load_businesses()
    results = []
    missing = []
    for biz in businesses:
        fx = load_fixture(biz["id"])
        if fx is None:
            missing.append(biz["id"])
            continue
        results.append(score_business(biz, fx))
    halluc = score_hallucination(load_halluc_cases())
    report = aggregate(results, halluc)
    report["fixtures_present"] = len(results)
    report["fixtures_missing"] = len(missing)
    report["missing_ids"] = missing
    report["per_business"] = results
    return report


def run_record() -> dict:
    """Run live probes and write fixtures. Requires a provider key."""
    from geoready_platform.core_bridge.probe_adapter import resolve_probe_provider, run_prompt
    from geoready_platform.services.probe import prompt_generator

    provider, api_key = resolve_probe_provider(os.environ.get("GR_PROBE_PROVIDER"))
    if not provider or not api_key:
        raise SystemExit("record mode requires a provider key (e.g. PERPLEXITY_API_KEY).")

    FIXTURES.mkdir(exist_ok=True)
    written = 0
    for biz in load_businesses():
        prompts = prompt_generator.generate_prompts(
            name=biz["name"], category=biz.get("category"), city=biz.get("city"), max_prompts=8
        )
        responses = []
        for gp in prompts:
            resp = run_prompt(gp.text, provider=provider, api_key=api_key)
            responses.append(
                {"category_key": gp.category, "prompt": gp.text, "text": resp.text, "citations": resp.citations}
            )
        fixture = {
            "business_id": biz["id"],
            "taxonomy_version": prompt_generator.current_taxonomy_version(),
            "provider": provider,
            "responses": responses,
        }
        (FIXTURES / f"{biz['id']}.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        written += 1
    return {"recorded": written}


def _print_report(report: dict) -> None:
    print(json.dumps(report, indent=2))
    print("\n=== SUMMARY ===")
    print(f"fixtures present: {report.get('fixtures_present')} / missing: {report.get('fixtures_missing')}")
    for gate, ok in report.get("gates", {}).items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {gate}")
    print(f"soft pass rate: {report.get('soft_pass_rate')}")
    print(f"OVERALL: {'PASS' if report.get('overall_pass') else 'FAIL'}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Perception Probe evaluation harness")
    ap.add_argument("--mode", choices=["replay", "record"], default="replay")
    args = ap.parse_args()
    if args.mode == "record":
        print(json.dumps(run_record(), indent=2))
    else:
        _print_report(run_replay())


if __name__ == "__main__":
    main()
