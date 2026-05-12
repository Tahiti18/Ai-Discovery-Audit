# GEO Analysis — GEO Optimizer Frontend v2

**URL audited:** https://geoready.dev (live production) + `frontend/dist/` (new Astro v2 build)  
**Date:** 2026-05-12  
**Auditor:** Claude Code / geo-optimizer-skill MCP

---

## 1. GEO Readiness Score

| Component | Live Site | New Astro v2 | Delta |
|-----------|-----------|--------------|-------|
| **Overall** | **75/100** (Good) | **~58/100** (Foundation) | **-17** |
| robots.txt | 18/18 | 0/18 (missing) | -18 |
| llms.txt | 12/18 | 0/18 (missing) | -12 |
| Schema JSON-LD | 7/16 | 0/16 (missing) | -7 |
| Meta Tags | 14/14 | 14/14 | 0 |
| Content | 10/12 | ~8/12 (thin) | -2 |
| Signals | 5/6 | 3/6 (no RSS) | -2 |
| AI Discovery | 6/6 | 2/6 (no endpoints) | -4 |
| Brand & Entity | 3/10 | 2/10 | -1 |

**Note:** The new Astro frontend is a significant regression in GEO readiness because critical infrastructure files (`robots.txt`, `llms.txt`, JSON-LD schema) are present on the live site but absent from the `public/` directory of the new build.

---

## 2. Platform Breakdown

### Google AI Overviews — 70/100 (Live) → ~50/100 (New)
- **Strengths:** Complete meta tags, canonical, OG tags, SSR content.
- **Weaknesses:** No schema on new build = zero structured data for rich snippets.

### ChatGPT — 60/100 (Live) → ~45/100 (New)
- **Strengths:** Content is fully server-side rendered (Astro SSG).
- **Weaknesses:** No `robots.txt` = crawlers may be cautious; no JSON-LD Organization schema = weak entity resolution.

### Perplexity — 62/100 (Live) → ~48/100 (New)
- **Strengths:** Clean HTML, external links present.
- **Weaknesses:** No RSS feed linked on new build; no llms.txt for structured discovery.

---

## 3. AI Crawler Access Status

### Live Site
- **Status:** Excellent. All 27 tracked AI crawlers explicitly allowed.
- **GPTBot, ClaudeBot, PerplexityBot:** Allowed with explicit directives.
- **CCBot:** Allowed (training data inclusion).

### New Astro Build
- **Status:** **Missing.** No `robots.txt` in `frontend/public/`.
- **Risk:** AI crawlers encountering a missing robots.txt may default to conservative behavior or skip the site.

**Required fix:** Add `public/robots.txt` with explicit allow directives for citation bots.

---

## 4. llms.txt Status

### Live Site
- **Status:** Present at `/llms.txt`.
- **Score:** 12/18 (missing `has_full` completeness flag).
- **Word count:** 456 words, 8 sections, 18 links.

### New Astro Build
- **Status:** **Missing.** No `llms.txt` in `frontend/public/`.
- **Risk:** AI crawlers have no structured content guidance.

**Required fix:** Add `public/llms.txt` with site overview, page descriptions, and key facts.

---

## 5. Brand Mention Analysis

### Live Site
- **Brand consistency:** Good ("GEO Optimizer" consistent across title/H1/schema).
- **Entity presence:** Weak. No Wikipedia, no Wikidata, no LinkedIn company page detected.
- **sameAs links:** Missing in schema.

### New Astro Build
- **Brand consistency:** Good.
- **Entity presence:** Worse — no Organization schema at all means zero entity disambiguation for AI crawlers.

**Recommendation:** Add Organization JSON-LD with `sameAs` links to GitHub, PyPI, LinkedIn, Crunchbase.

---

## 6. Passage-Level Citability

### Optimal Range: 134–167 words per self-contained block

**Homepage (new build):**
- Hero paragraph: ~24 words — too short.
- "Why this tool exists": ~40 words — too short.
- Feature cards: ~12 words each — too short.
- **Zero passages in optimal range.**

**Manifesto page:** Likely longer passages. Needs manual verification.
**Research page:** Contains data-rich content. Best candidate for citation blocks.

**Top improvements:**
1. Expand homepage hero to 150+ words with a self-contained definition.
2. Add a "What is GEO?" section with 134–167 word answer block.
3. Use blockquotes for research attribution on `/research`.

---

## 7. Server-Side Rendering Check

- **Framework:** Astro 5 SSG (Static Site Generation)
- **JavaScript dependency:** Minimal. Content is in raw HTML.
- **AI crawler accessibility:** Excellent. All text content is in the initial HTML response.
- **Hydration islands:** React components (AuditForm, CookieConsentManager, CompareContainer) hydrate client-side but their SSR fallback is present.

**Verdict:** No JS dependency issues for AI crawlers.

---

## 8. Top 5 Highest-Impact Changes

| Priority | Fix | Impact | Effort |
|----------|-----|--------|--------|
| **P0** | Add `public/robots.txt` with AI crawler directives | +12–15 points | 5 min |
| **P0** | Add JSON-LD schema (Organization + WebSite) to Layout.astro | +10–12 points | 15 min |
| **P0** | Add `public/llms.txt` with site structure | +8–10 points | 10 min |
| **P1** | Add `public/sitemap.xml` | +3–5 points | 5 min |
| **P1** | Add RSS `<link>` in Layout.astro (GitHub releases feed) | +2–3 points | 2 min |

**Lower priority:**
- Create OG image at `/assets/og-image.png` (currently 404)
- Expand homepage content to 300+ words
- Add blockquotes with research attribution on `/research`
- Add `dateModified` to schema for freshness signals

---

## 9. Schema Recommendations

### Missing schemas on new build:
1. **Organization** — Entity disambiguation for "Auriti Labs" / "GEO Optimizer".
2. **WebSite** — Enables SearchAction potential for AI agents.
3. **SoftwareApplication** (or WebApplication) — Describes the tool itself.
4. **FAQPage** — Already present on live site; should be preserved.

### Recommended JSON-LD for Layout.astro:
```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "name": "Auriti Labs",
      "url": "https://github.com/Auriti-Labs",
      "sameAs": [
        "https://github.com/Auriti-Labs",
        "https://pypi.org/project/geo-optimizer-skill/"
      ]
    },
    {
      "@type": "WebSite",
      "name": "GEO Optimizer",
      "url": "https://geoready.dev",
      "publisher": { "@id": "https://github.com/Auriti-Labs" }
    },
    {
      "@type": "WebApplication",
      "name": "GEO Optimizer",
      "applicationCategory": "DeveloperApplication",
      "operatingSystem": "Web",
      "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" }
    }
  ]
}
```

---

## 10. Content Reformatting Suggestions

### Homepage (`/index.astro`)
**Current:** ~180 words total. Thin for AI citation.
**Fix:** Add a 150-word "What is GEO?" definition block after the hero:
> "Generative Engine Optimization (GEO) is the practice of making websites discoverable and citable by AI search engines like ChatGPT, Perplexity, Claude, and Gemini. Unlike traditional SEO, GEO focuses on signals that AI crawlers prioritize: structured data, clear definitions, authoritative citations, and self-contained answer blocks."

### Research Page (`/research.astro`)
**Current:** Has research data.
**Fix:** Wrap each research finding in `<blockquote>` with attribution:
> "Cite Sources increased AI citation probability by 27–115% across 10,000 queries." — Princeton KDD 2024

### Manifesto Page (`/manifesto.astro`)
**Current:** Likely the longest content page.
**Fix:** Ensure H2 headings are question-based where possible (e.g., "What makes AI visibility different from SEO?").

---

## Appendix: Negative Signals Detected (Live Site)

1. **Thin content** — Homepage ~233 words (below 300 threshold).
2. **Keyword stuffing** — "optimizer" at 3.2% density.
3. **Hidden text** — `display:none` content detected (likely cookie banner elements).
4. **Popup indicators** — Cookie consent modal flagged as overlay.
5. **Hallucination bait** — 6 AI-generated signals detected; 1 medical claim without disclaimer.

**Mitigation for new build:**
- Ensure cookie banner markup does not contain hidden text with semantic meaning.
- Add `aria-hidden="true"` to decorative cookie banner internals.
- Add a disclaimer to any health-adjacent content (if present).

---

*Report generated by geo-optimizer-skill MCP audit suite.*
