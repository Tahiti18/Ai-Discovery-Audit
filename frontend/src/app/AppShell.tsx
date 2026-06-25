/** App chrome: full-width sticky top bar + grouped collapsible sidebar.
 *  Hierarchy comes from typography, spacing, indentation and active states —
 *  no icon webfont, no gimmicks. Violet brand. Responsive (sidebar → overlay on
 *  small screens). Preview items route to useful Learn pages (never dead ends). */
import { useEffect, useState, type ReactNode } from "react";
import { subscribeHealth } from "../lib/platformApi";
import { navigate } from "./router";
import { NAV, type NavGroup } from "./nav";
import { Button, PreviewBadge } from "./ui";

/** Reads the app-wide shared health poller (single interval, 60s). */
function useHealth(): boolean | null {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => subscribeHealth(setOk), []);
  return ok;
}

export function AppShell({ active, children }: { active: string; children: ReactNode }) {
  const health = useHealth();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <TopBar health={health} onMenu={() => setMobileOpen((o) => !o)} />
      {health === false && <OfflineBanner />}
      <div className="mx-auto flex w-full max-w-[1480px]">
        <Sidebar active={active} mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
        <main className="min-w-0 flex-1 px-5 py-8 sm:px-8">{children}</main>
      </div>
    </div>
  );
}

// ─── Top bar ─────────────────────────────────────────────────────────────────

function TopBar({ health, onMenu }: { health: boolean | null; onMenu: () => void }) {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-bg-surface">
      <div className="mx-auto flex h-14 max-w-[1480px] items-center justify-between gap-4 px-4 sm:px-8">
        <div className="flex items-center gap-2.5">
          <button onClick={onMenu} aria-label="Toggle menu" className="-ml-1 rounded-lg p-1.5 text-text-secondary hover:bg-bg-subtle lg:hidden">
            <Bars />
          </button>
          <button onClick={() => navigate("#/dashboard")} className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-accent-teal text-[11px] font-bold text-white">AV</span>
            <span className="text-[15px] font-semibold tracking-tight">AI Visibility <span className="text-accent-teal">OS</span></span>
          </button>
        </div>
        <div className="flex items-center gap-2.5">
          <StatusCluster health={health} />
          <Button onClick={() => navigate("#/onboarding")} className="px-3.5 py-2 text-xs">
            <span className="hidden sm:inline">Run AI Visibility Check</span><span className="sm:hidden">Run check</span>
          </Button>
          <button onClick={() => navigate("#/settings")} aria-label="Settings"
            className="rounded-lg border border-border px-2 py-1.5 text-text-secondary hover:text-text-primary">
            <Gear />
          </button>
        </div>
      </div>
    </header>
  );
}

/** Compact, single-pill status: engine + API in one element to de-clutter. */
function StatusCluster({ health }: { health: boolean | null }) {
  const hColor = health == null ? "#475569" : health ? "#34D399" : "#f87171";
  const hLabel = health == null ? "Checking" : health ? "Connected" : "Offline";
  return (
    <div className="hidden items-center gap-2.5 rounded-full border border-border bg-bg-base px-3 py-1 text-[11px] text-text-muted md:flex">
      <span className="flex items-center gap-1.5"><Dot color="#34D399" /><span className="text-text-secondary">Perplexity</span></span>
      <span className="text-text-muted/50">·</span>
      <span className="text-text-muted">+3 soon</span>
      <span className="h-3 w-px bg-border" />
      <span className="flex items-center gap-1.5"><Dot color={hColor} />{hLabel}</span>
    </div>
  );
}
const Dot = ({ color }: { color: string }) => <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />;

// ─── Sidebar ─────────────────────────────────────────────────────────────────

function Sidebar({ active, mobileOpen, onClose }: { active: string; mobileOpen: boolean; onClose: () => void }) {
  const nav = (
    <nav className="px-3 py-5">
      {NAV.map((g) => <NavGroupView key={g.title} group={g} active={active} onNavigate={onClose} />)}
    </nav>
  );
  return (
    <>
      <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-60 shrink-0 overflow-y-auto border-r border-border bg-bg-surface/30 lg:block">
        {nav}
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={onClose} />
          <aside className="absolute left-0 top-0 h-full w-72 overflow-y-auto border-r border-border bg-bg-surface">{nav}</aside>
        </div>
      )}
    </>
  );
}

function isItemActive(active: string, href: string, soon?: string): boolean {
  return active === href || (!!soon && active === `#/soon/${soon}`);
}

function NavGroupView({ group, active, onNavigate }: { group: NavGroup; active: string; onNavigate: () => void }) {
  const hasActive = group.items.some((it) => isItemActive(active, it.to ?? `#/soon/${it.soon}`, it.soon));
  const [open, setOpen] = useState(!!group.defaultOpen || hasActive);
  useEffect(() => { if (hasActive) setOpen(true); }, [hasActive]);

  return (
    <div className="mb-5 first:mt-0">
      <button onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.13em] text-text-muted transition-colors hover:text-text-secondary">
        <span>{group.title}</span>
        <Chevron open={open} />
      </button>
      {open && (
        <div className="mt-1 space-y-0.5 border-l border-border pl-2">
          {group.items.map((item) => {
            const href = item.to ?? (item.soon ? `#/soon/${item.soon}` : "#/dashboard");
            const activeItem = isItemActive(active, href, item.soon);
            return (
              <button key={item.label} onClick={() => { navigate(href); onNavigate(); }}
                className={`relative flex w-full items-center justify-between gap-2 rounded-lg py-1.5 pl-3 pr-2 text-left text-[13px] transition-colors ${
                  activeItem ? "bg-accent-teal/10 font-medium text-accent-teal" : "text-text-secondary hover:bg-bg-subtle hover:text-text-primary"
                }`}>
                {activeItem && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-accent-teal" />}
                <span className="truncate">{item.label}</span>
                {item.preview && <PreviewBadge />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Offline banner (useful, not dominant) ───────────────────────────────────

function OfflineBanner() {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-border bg-bg-subtle/60 px-4 py-2 text-[13px] text-text-secondary sm:px-8">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-x-3 gap-y-1">
        <Dot color="#f87171" />
        <span className="font-medium text-text-primary">Analysis API not connected.</span>
        <span className="text-text-muted">Start it to run analyses — saved results stay viewable.</span>
        <button onClick={() => setOpen((o) => !o)} className="text-accent-teal hover:underline">{open ? "Hide command" : "Show command"}</button>
      </div>
      {open && (
        <pre className="mx-auto mt-2 max-w-[1480px] overflow-x-auto rounded-lg border border-border bg-bg-base p-3 font-mono text-[11px] leading-relaxed text-text-secondary">{`cd "$env:USERPROFILE\\geo-ai-visibility-app\\platform"
$env:GR_DATABASE_URL="sqlite:///./geoready_platform.db"; $env:GR_CELERY_EAGER="true"; $env:GR_PROBE_MODEL="perplexity/sonar"; $env:GR_FREE_PROBES_PER_DAY="100000"; $env:PYTHONPATH="$PWD;$PWD\\..\\src"
python -m uvicorn geoready_platform.api.main:app --host "::" --port 8001`}</pre>
      )}
    </div>
  );
}

// ─── Tiny inline SVG glyphs (no webfont dependency) ──────────────────────────

const Bars = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
);
const Gear = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H10a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V10a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </svg>
);
const Chevron = ({ open }: { open: boolean }) => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
    className={`transition-transform ${open ? "" : "-rotate-90"}`}><path d="M6 9l6 6 6-6" /></svg>
);
