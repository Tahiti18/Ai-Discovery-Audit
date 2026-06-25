/** Plain-English navigation IA. Items route to real pages, real explainers, or
 *  honest "coming soon" pages — never dead ends. `preview` marks unbuilt features. */

export interface NavItem {
  label: string;
  to?: string; // real route (hash)
  soon?: string; // key into the Learn/ComingSoon content map
  preview?: boolean; // show a Preview badge (unbuilt feature). Explainers are not Preview.
}
export interface NavGroup {
  title: string;
  defaultOpen?: boolean;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    title: "Overview",
    defaultOpen: true,
    items: [
      { label: "Dashboard", to: "#/dashboard" },
      { label: "Businesses", to: "#/dashboard" },
      { label: "What changed", soon: "what-changed", preview: true },
    ],
  },
  {
    title: "Analyze",
    defaultOpen: true,
    items: [
      { label: "Run AI Visibility Check", to: "#/onboarding" },
      { label: "Add Business", to: "#/onboarding" },
      { label: "Discovery Visibility", soon: "discovery" },
      { label: "Brand Knowledge", soon: "brand" },
      { label: "AI Answers", soon: "ai-answers" },
    ],
  },
  {
    title: "Improve",
    items: [
      { label: "Your Next Moves", soon: "next-moves" },
      { label: "Action Plan (90-day)", soon: "action-plan", preview: true },
      { label: "Website Readiness", soon: "readiness" },
      { label: "Trust Signals", soon: "trust-signals", preview: true },
      { label: "Content & Entity Signals", soon: "content-signals", preview: true },
    ],
  },
  {
    title: "Prove",
    items: [
      { label: "Progress History", soon: "history" },
      { label: "Before / After", soon: "before-after", preview: true },
      { label: "Proof Report", soon: "proof-report", preview: true },
      { label: "Export Evidence", soon: "export", preview: true },
      { label: "Raw Data Download", soon: "raw-download" },
    ],
  },
  {
    title: "Monitor",
    items: [
      { label: "Scheduled Checks", soon: "scheduled", preview: true },
      { label: "Alerts", soon: "alerts", preview: true },
      { label: "Trend Tracking", soon: "trends", preview: true },
      { label: "Engines Compared", soon: "engines", preview: true },
    ],
  },
  {
    title: "Learn & Trust",
    items: [
      { label: "How It Works", soon: "how-it-works" },
      { label: "Methodology", soon: "methodology" },
      { label: "Research Notes", soon: "research" },
      { label: "FAQ", soon: "faq" },
      { label: "Limitations", soon: "limitations" },
    ],
  },
  {
    title: "Agency",
    items: [
      { label: "Client Portfolio", soon: "portfolio", preview: true },
      { label: "White-Label Reports", soon: "white-label", preview: true },
      { label: "Shareable Links", soon: "shareable", preview: true },
      { label: "Team Access", soon: "team", preview: true },
    ],
  },
  {
    title: "System",
    items: [
      { label: "Settings", to: "#/settings" },
      { label: "API Status", to: "#/settings" },
      { label: "Integrations", soon: "integrations", preview: true },
      { label: "Technical Diagnostics", soon: "diagnostics", preview: true },
      { label: "Roadmap", soon: "roadmap" },
    ],
  },
];
