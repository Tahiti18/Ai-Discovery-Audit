# AI Perception Probe — Evaluation Framework

Internal tooling. **Not shipped** with the platform package and **not a product
feature** — it exists to make the probe trustworthy enough for external demos
and paying customers, by measuring output quality against curated ground truth.

It imports the *real* probe pure-layers (`analysis`, `share_of_model`,
`hallucination`, `prompt_generator`) so it scores the actual production logic,
not a reimplementation. The engine (`src/geo_optimizer`) is never touched.

```
probe_eval/
  benchmark/
    businesses.json          # >=50 diverse businesses + curated ground truth
    hallucination_cases.json # labeled AI responses for precision/recall
  fixtures/
    <business_id>.json       # recorded probe transcripts (replay mode)
  metrics.py                 # scoring functions + thresholds
  harness.py                 # load -> (live|replay) -> score -> report
```

## Why an eval framework at all

LLM outputs are non-deterministic and provider-dependent. "It worked in the demo"
is not evidence of quality. We need (a) a fixed benchmark, (b) objective metrics
with pass/fail thresholds, and (c) **reproducibility**: record real responses
once into `fixtures/`, then re-score offline forever. This separates *prompt/logic
quality* (deterministic, what we control) from *model behavior* (stochastic, what
we observe).

## Execution modes

- **Replay (default, offline, reproducible):** read recorded transcripts from
  `fixtures/`, run them through the probe pure-layers, score against ground truth.
  Runs in CI, no API key.
- **Record (manual, key-gated):** run live probes against the benchmark once with
  `PERPLEXITY_API_KEY` set, writing transcripts to `fixtures/`. Used to refresh
  the golden set. Not run in CI.

> Status: the framework, benchmark, metrics, and self-tests are complete and
> executed offline. Live recording of the full 50-business set requires a
> provider key and is the documented next step.

---

## 1. Benchmark set

`benchmark/businesses.json` — ≥50 businesses spanning industries (local services,
SaaS/tech, DTC/e-commerce, hospitality, healthcare, professional services,
education, nonprofit) and geographies (North America, UK/EU, APAC, LATAM, Middle
East, Africa). Each entry:

| field | meaning |
|---|---|
| `id` | stable slug (fixture filename) |
| `name`, `website`, `category`, `city`, `country` | probe inputs |
| `prominence_tier` | curated `high`/`medium`/`low` — expected AI visibility; used for Share-of-Model rank correlation |
| `known_competitors` | curated competitor domains (ground truth). Empty + `needs_review:true` for SMBs where we can't curate confidently |
| `needs_review` | competitor ground truth not yet human-verified |

Hallucination ground truth is **not** asserted on real businesses (we won't
fabricate facts). It lives in `hallucination_cases.json` as labeled synthetic
responses, so precision/recall are measured against known-correct labels.

## 2. What "quality" means + 3. metrics & thresholds

| Dimension | Metric | Pass threshold | Why |
|---|---|---|---|
| **Reference contamination** | % of predicted competitors that are reference/social/directory/etc. domains | **0% (hard fail if >0)** | The #1 demo-credibility killer (Wikipedia-as-competitor). Zero tolerance. |
| **Competitor identification** | precision / recall / F1 vs `known_competitors` (on curated entries) | precision ≥ 0.60, recall ≥ 0.40, F1 ≥ 0.50 | Names must be plausible businesses; recall can lag in v1. |
| **Recommendation relevance** | % of recommendation-class answers that are on-topic (category/city present, is a recommendation) | ≥ 0.90 | Bad prompts produce off-topic answers; this guards prompt quality, not the business's merit. |
| **Hallucination precision** | correct flags / all flags raised (labeled set) | **≥ 0.85 overall; `claims_closed` = 1.00** | We optimize for precision; a false "you're closed" is unacceptable. |
| **Hallucination recall** | true issues flagged / all true issues (labeled set) | ≥ 0.30 (advisory) | Recall is explicitly secondary in v1. |
| **Share-of-Model usefulness** | Spearman ρ between SoM and curated `prominence_tier`; share denominator coverage | ρ ≥ 0.50; denominator ≥ 2 in ≥ 90% of runs | SoM must *discriminate* strong vs weak; a metric that doesn't rank is noise. |
| **Stability (repeat runs)** | SoM std-dev; competitor-set Jaccard; flag persistence over N=5 | SoM σ ≤ 0.15; median Jaccard ≥ 0.50; true `claims_closed` persists in ≥ 3/5 | LLM variance must be bounded or aggregated; unstable outputs can't be trusted run-to-run. |

A benchmark **passes** when every hard gate (contamination, claims_closed
precision) is met and ≥ 80% of the soft thresholds are met across the set.

## 4. Most likely embarrassing demo failures

1. **Reference site shown as a competitor** (Wikipedia/Yelp/Reddit). *Mitigated* by the denylist; the contamination gate guards against regressions.
2. **Competitor's closure attributed to the business** ("You are permanently closed" when the answer was about a competitor). *Mitigated* by brand-gating `claims_closed`.
3. **`brand_not_recognized` spam** for legitimate-but-niche businesses, read as "the tool is broken." *Mitigated* by low severity + substantive-response gate; still expect it for low-prominence entries.
4. **Share-of-Model = 0 for a clearly strong brand** because the model phrased recommendations without the exact name, or used a nickname. High-impact: undermines the headline number.
5. **Wild run-to-run swings** (SoM 0.2 → 0.6) shown live without aggregation.
6. **Empty/odd prompts** when category or city is missing (e.g. only a name) — generator skips templates, but the run can look thin.
7. **Non-English / non-US businesses** getting US-centric phrasing and irrelevant answers.
8. **Provider outage / rate limit** mid-demo surfacing as a failed run (now handled, but visible as "failed").

## 5. Recommended regression tests before public release

- **Contamination gate as a CI test**: assert 0 reference domains in competitor output across the replay benchmark (not just unit denylist tests).
- **`claims_closed` precision on the labeled set** must equal 1.00 (CI gate).
- **SoM name-matching robustness**: brand mentioned via partial/nickname/possessive ("Acme's", "Acme Plumbing Co.") still counts — *currently exact-substring; likely the biggest recall gap.* Add cases.
- **Multilingual answer handling**: at least smoke cases for non-English responses (brand detection, denylist).
- **Empty/degenerate inputs**: name-only, missing city, very long names, punctuation in names.
- **Stability harness** wired to run N times in record mode and assert variance bounds.
- **Provider-error path** already covered; keep.

## 6. Taxonomy calibration plan (preserving historical comparability)

The taxonomy is the lever with the most leverage on output quality, but changing
it breaks longitudinal comparisons unless versioned. Discipline:

1. **Every template change bumps `TAXONOMY_VERSION`** (already done: v1 → v2).
   Provenance (`taxonomy_version` on every `perception` row and `probe_run`) makes
   each response self-describing.
2. **Compare like-with-like:** trend/Share-of-Model comparisons must filter to a
   single `taxonomy_version`. Cross-version deltas are invalid and should be
   surfaced as "taxonomy changed" rather than a score movement.
3. **Calibration cycle:** when proposing v(N+1), run BOTH versions against the
   replay benchmark, measure metric deltas (recommendation relevance, SoM rank
   correlation, contamination), and only promote if non-regressing.
4. **Bridge runs:** when a version ships, run one probe per active entity on both
   old and new taxonomy so each entity has an overlap point, enabling a
   re-baselined trend without discarding history.
5. **Never silently edit a template.** Even wording tweaks shift model behavior;
   they are version events, not patches.

## Running it

```bash
cd platform
# offline, reproducible (CI):
python -m probe_eval.harness --mode replay
# refresh golden transcripts (manual, needs PERPLEXITY_API_KEY):
python -m probe_eval.harness --mode record
# self-tests of the scoring functions:
pytest tests/test_eval_metrics.py -q
```
