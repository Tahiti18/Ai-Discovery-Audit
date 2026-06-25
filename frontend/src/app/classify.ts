/**
 * Presentation-layer classification (NOT backend truth).
 *
 * - Prompt type: derived from the backend-stored `prompt_category` (real data),
 *   grouped into Discovery / Alternative / Brand-knowledge so brand-check prompts
 *   never inflate the discovery headline.
 * - Domain bucket: a conservative heuristic so we DON'T call directories,
 *   manufacturers or citation sources "competitors". Clearly labeled as heuristic.
 */

export type PromptGroup = "discovery" | "alternative" | "brand";

export interface PromptType {
  label: string; // badge text
  group: PromptGroup;
}

const PROMPT_TYPE: Record<string, PromptType> = {
  category_recommendation: { label: "Discovery", group: "discovery" },
  problem_solution: { label: "Discovery", group: "discovery" },
  comparison: { label: "Alternative", group: "alternative" },
  legitimacy: { label: "Reputation", group: "brand" },
  factual_attributes: { label: "Contact / location", group: "brand" },
  awareness: { label: "Brand check", group: "brand" },
};

export function promptType(category: string | null | undefined): PromptType {
  if (category && PROMPT_TYPE[category]) return PROMPT_TYPE[category];
  // Unknown categories are treated conservatively as brand-knowledge, so they
  // never inflate Discovery Visibility.
  return { label: (category || "other").replace(/_/g, " "), group: "brand" };
}

// ─── Domain buckets ──────────────────────────────────────────────────────────

export type DomainBucket = "business" | "directory" | "manufacturer" | "citation" | "unclassified";

export const DOMAIN_BUCKET_LABEL: Record<DomainBucket, string> = {
  business: "Possible businesses",
  directory: "Directories & marketplaces",
  manufacturer: "Manufacturers & associations",
  citation: "Citation sources & platforms",
  unclassified: "Other mentions",
};

// Keyword-based (works across industries & countries, not just US trades).
const DIRECTORY_KW = [
  "tripadvisor", "yellowpages", "yelp", "2gis", "angloinfo", "foursquare", "whatson",
  "oncyprus", "cyprus-faq", "cyprusinfo", "bestcompanies", "top-rated", "directory",
  "listings", "homeadvisor", "angieslist", "thumbtack", "houzz", "checkatrade",
  "diamondcertified", "thebluebook", "comparelocalpros", "directorii", "rooflists",
  "checkbook", "manta", "energysage", "mapquest", "birdeye", "trustpilot",
  "expertise", "threebestrated", "nextdoor", "clutch", "capterra", "yell.com",
];
const MANUFACTURER_KW = ["gaf", "owenscorning", "certainteed", "malarkey", "calssa", "nrca", "association"];
const CITATION_KW = [
  "wikipedia", "reddit", "quora", "facebook", "instagram", "linkedin", "youtube",
  "twitter", "x.com", "medium", "procore", "cosmopolitan", "abebooks", "thegoodtrade",
  "graalians", "google", "bing",
];

function norm(d: string): string {
  let v = (d || "").toLowerCase().trim();
  if (v.startsWith("http")) { try { v = new URL(v).hostname; } catch { /* keep */ } }
  return v.replace(/^www\./, "");
}
const hasKw = (d: string, kws: string[]) => kws.some((k) => d.includes(k));
const exactDir = new Set(["angi.com", "g2.com", "bbb.org", "cytayellowpages.com.cy"]);

export function domainBucket(domain: string): DomainBucket {
  const d = norm(domain);
  if (!d) return "unclassified";
  if (/\.gov(\.|$)|\.edu(\.|$)|\.mil(\.|$)/.test(d)) return "citation";
  if (hasKw(d, CITATION_KW)) return "citation";
  if (exactDir.has(d) || hasKw(d, DIRECTORY_KW)) return "directory";
  if (hasKw(d, MANUFACTURER_KW)) return "manufacturer";
  // Unknown domains are most likely actual businesses in this context — label
  // conservatively as "Possible businesses", never asserted as competitors.
  return "business";
}
