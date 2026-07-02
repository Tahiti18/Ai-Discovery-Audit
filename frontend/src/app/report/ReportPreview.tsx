/**
 * Public sample report for the landing page. Uses FICTIONAL data for an example
 * bakery — never a real customer's business — so it can be shown publicly. Same
 * shape as a real report so it accurately shows what a customer gets.
 */
import "../visibletoai.css";
import { ReportScreen, type ReportData, type Move } from "./ReportScreen";
import type { Entity, ProbeRun, Perception } from "../../lib/platformApi";

const entity: Entity = {
  id: "sample",
  org_id: "sample",
  canonical_name: "My Bakery",
  website_url: "https://my-bakery.com",
  category: "bakery",
  geo: "Austin",
  verified_at: null,
  created_at: "2026-06-27T00:00:00Z",
};

const run: ProbeRun = {
  id: "sample-run",
  entity_id: "sample",
  status: "complete",
  provider: "openrouter",
  model: "perplexity/sonar",
  taxonomy_version: "v3",
  prompt_count: 8,
  answered_count: 8,
  share_of_model: 0.0,
  recommended_count: 0,
  competitors: [
    { name: "flourandstone.com", mentions: 5 },
    { name: "thedailyloaf.com", mentions: 4 },
    { name: "risebakehouse.com", mentions: 4 },
    { name: "sunrisebreads.com", mentions: 3 },
    { name: "crumbandco.com", mentions: 2 },
  ],
  flags: [],
  error: null,
  created_at: "2026-06-27T09:00:00Z",
  started_at: "2026-06-27T09:00:01Z",
  completed_at: "2026-06-27T09:00:38Z",
};

function mkP(p: Partial<Perception> & { id: string }): Perception {
  return {
    probe_run_id: "sample-run",
    prompt_category: null,
    provider: "openrouter",
    model: "perplexity/sonar",
    taxonomy_version: "v3",
    prompt: null,
    raw_response: null,
    recommended: null,
    brand_mentioned: null,
    domain_cited: null,
    competitors_named: null,
    flags: null,
    details: null,
    probed_at: "2026-06-27T09:00:20Z",
    ...p,
  };
}

const responses: Perception[] = [
  mkP({ id: "s1", prompt_category: "category_recommendation", brand_mentioned: false,
    prompt: "What are the best bakeries in Austin?",
    raw_response: "Austin has a thriving bakery scene. Based on reviews and reputation, top picks include: 1. Flour & Stone — artisan sourdough and pastries. 2. The Daily Loaf — known for fresh baguettes. 3. Rise Bakehouse — popular for cinnamon rolls and morning buns." }),
  mkP({ id: "s2", prompt_category: "problem_solution", brand_mentioned: false,
    prompt: "Where should I buy fresh bread in Austin?",
    raw_response: "For fresh, daily-baked bread in Austin, Flour & Stone and Sunrise Breads are top choices — both bake sourdough and country loaves every morning." }),
  mkP({ id: "s3", prompt_category: "category_recommendation", brand_mentioned: false,
    prompt: "Which bakery in Austin would you recommend and why?",
    raw_response: "I'd recommend Flour & Stone for its artisan breads and consistent quality, with The Daily Loaf and Crumb & Co as excellent alternatives for pastries and cakes." }),
  mkP({ id: "s4", prompt_category: "legitimacy", brand_mentioned: true,
    prompt: "Is My Bakery a reputable, trustworthy bakery?",
    raw_response: "Yes — My Bakery appears reputable and well-regarded. Reviews praise its sourdough and friendly service, and it has been a family-run neighbourhood bakery since 2015." }),
  mkP({ id: "s5", prompt_category: "factual_attributes", brand_mentioned: true,
    flags: [{ type: "wrong_hours" }],
    prompt: "What are My Bakery's opening hours?",
    raw_response: "My Bakery is open Monday to Friday, 8am–4pm, and closed on weekends." }),
];

const moves: Move[] = [
  {
    title: "Tell AI clearly that you're an Austin bakery",
    body: "AI isn't confident about what you do and where, so it leaves you out of “best bakery in Austin” answers. Make your category and location unmistakable on your site — a clear homepage headline, location page, and consistent name + address.",
    why: "Why it matters: this is exactly why you score 0% on local discovery. · Effort: medium · Ask your web person.",
    impact: "high", impactLabel: "High impact",
  },
  {
    title: "Add the structured data AI reads to recommend you",
    body: "Your site has no Organization or LocalBusiness schema and no llms.txt — the machine-readable signals AI engines lean on when choosing who to name. Adding them is a known, concrete fix.",
    why: "Why it matters: AI can't confidently recommend what it can't cleanly read. · Effort: low–medium · Ask your web person.",
    impact: "high", impactLabel: "High impact",
  },
  {
    title: "Fix the opening hours AI is getting wrong",
    body: "AI is quoting outdated hours for your bakery — customers may show up to a closed door. Update your Google Business Profile and add opening-hours structured data so AI has the right source.",
    why: "Why it matters: wrong hours sent to customers cost you real visits. · Effort: low.",
    impact: "medium", impactLabel: "Worth doing",
  },
];

const data: ReportData = {
  entity, run, responses, moves,
  technicalReportHref: "/sample-technical-report.html",
  technicalScore: 36,
  homeHref: "/", // public sample: logo/back lead to the landing page
  // no onRunAgain: run-again affordances become "check my business" CTAs
};

export default function ReportPreview() {
  return <ReportScreen data={data} />;
}
