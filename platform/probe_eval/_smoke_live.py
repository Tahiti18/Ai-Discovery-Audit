"""Temporary live smoke runner (deleted after use). Prints NO secrets."""

from __future__ import annotations

import json

from probe_eval import metrics
from probe_eval.harness import FIXTURES_LIVE, business_by_id, record_live_openrouter, score_business

IDS = ["slack", "notion", "stripe", "joes-plumbing-austin", "smile-dental-denver"]
MODEL = "perplexity/sonar"
RUNS = ["r1", "r2"]


def _load(bid: str, label: str) -> dict:
    return json.loads((FIXTURES_LIVE / f"{bid}__{label}.json").read_text(encoding="utf-8"))


def main() -> None:
    for label in RUNS:
        record_live_openrouter(IDS, model=MODEL, max_prompts=4, run_label=label)

    out = {"model": MODEL, "businesses": {}}
    for bid in IDS:
        biz = business_by_id(bid)
        per_run = []
        runs_for_stability = []
        for label in RUNS:
            fx = _load(bid, label)
            errors = sum(1 for r in fx["responses"] if r.get("error"))
            res = score_business(biz, fx)
            per_run.append({
                "som": res["share_of_model"],
                "denominator": res["share_denominator"],
                "competitors": res["predicted_competitors"],
                "contamination": res["contamination_rate"],
                "flags": res["flags"],
                "errors": errors,
            })
            runs_for_stability.append({
                "share_of_model": res["share_of_model"],
                "competitors": res["predicted_competitors"],
                "flags": res["flags"],
            })
        stab = metrics.stability(runs_for_stability)
        out["businesses"][bid] = {
            "tier": biz["prominence_tier"],
            "runs": per_run,
            "stability": {
                "som_stddev": stab.som_stddev,
                "som_mean": stab.som_mean,
                "competitor_jaccard_median": stab.competitor_jaccard_median,
                "flag_persistence": stab.flag_persistence,
            },
        }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
