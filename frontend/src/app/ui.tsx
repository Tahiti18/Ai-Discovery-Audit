/**
 * AI Visibility OS — design-system primitives.
 * Dark-first, restrained, executive. Reuses the global Tailwind v4 theme tokens.
 *
 * Honesty primitives are first-class here: ProvenanceLine, Caveat, PreviewBadge,
 * MethodologyNote — so every metric ships with confident headline + evidence +
 * methodology one tap away, never inline disclaimer clutter.
 */
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

// ─── Layout primitives ───────────────────────────────────────────────────────

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-border bg-bg-surface ${className}`}>{children}</div>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "subtle";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-teal";
  const variants = {
    primary: "bg-accent-teal text-white hover:bg-accent-teal-dark",
    ghost: "border border-border text-text-secondary hover:text-text-primary hover:border-accent-teal/50",
    subtle: "text-text-muted hover:text-text-primary",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

// ─── Chips & badges ──────────────────────────────────────────────────────────

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: ChipTone }) {
  const tones: Record<ChipTone, string> = {
    neutral: "bg-bg-subtle text-text-secondary border-border",
    teal: "bg-accent-teal/10 text-accent-teal border-accent-teal/30",
    amber: "bg-[#fbbf24]/10 text-[#fbbf24] border-[#fbbf24]/30",
    red: "bg-[#f87171]/10 text-[#f87171] border-[#f87171]/30",
    violet: "bg-[#a78bfa]/10 text-[#a78bfa] border-[#a78bfa]/30",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}
export type ChipTone = "neutral" | "teal" | "amber" | "red" | "violet";

/** Marks anything not yet backed by the API. Never attach to fabricated data. */
export function PreviewBadge({ label = "Preview" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[#a78bfa]/30 bg-[#a78bfa]/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#a78bfa]">
      {label}
    </span>
  );
}

export function StatusChip({ status }: { status: string }) {
  const map: Record<string, ChipTone> = {
    queued: "neutral", running: "violet", complete: "teal", failed: "red",
  };
  return <Chip tone={map[status] ?? "neutral"}>{status}</Chip>;
}

export function SeverityChip({ severity }: { severity?: string }) {
  const tone: ChipTone = severity === "high" ? "red" : severity === "medium" ? "amber" : "neutral";
  return <Chip tone={tone}>{severity ?? "info"}</Chip>;
}

// ─── Honesty primitives ──────────────────────────────────────────────────────

/** Quiet single line under a metric: engine · model · date · sample. */
export function ProvenanceLine({
  provider, model, date, sample, taxonomy,
}: { provider?: string | null; model?: string | null; date?: string | null; sample?: string; taxonomy?: string | null }) {
  const parts = [
    provider ? cap(provider) : null,
    model || null,
    date ? fmtDate(date) : null,
    sample || null,
    taxonomy ? `taxonomy ${taxonomy}` : null,
  ].filter(Boolean);
  return <p className="font-mono text-[11px] text-text-muted">{parts.join("  ·  ")}</p>;
}

export function Caveat({ children }: { children: ReactNode }) {
  return <p className="text-[12px] leading-relaxed text-text-muted">{children}</p>;
}

/** "How we measure this" — methodology one tap away (not inline clutter). */
export function MethodologyNote({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-[12px] text-accent-teal underline decoration-accent-teal/40 underline-offset-2 hover:decoration-accent-teal"
      >
        How we measure this
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setOpen(false)}>
          <Card className="max-w-lg p-6" >
            <div onClick={(e) => e.stopPropagation()}>
              <h3 className="mb-3 text-lg font-semibold text-text-primary">{title}</h3>
              <div className="space-y-3 text-sm leading-relaxed text-text-secondary">{children}</div>
              <div className="mt-5 flex justify-end">
                <Button variant="ghost" onClick={() => setOpen(false)}>Close</Button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

// ─── Explain drawer (executive insight first, raw receipts one tap away) ─────

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60]">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-border bg-bg-surface shadow-2xl">
        <div className="sticky top-0 flex items-center justify-between border-b border-border bg-bg-surface px-5 py-4">
          <h3 className="text-base font-semibold text-text-primary">{title}</h3>
          <button onClick={onClose} aria-label="Close" className="rounded-lg px-2 py-1 text-text-muted hover:bg-bg-subtle hover:text-text-primary">✕</button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

/** "Explain this result" — opens a plain-English drawer with a raw-data toggle. */
export function ExplainButton({ title, plain, raw }: { title: string; plain: ReactNode; raw?: unknown }) {
  const [open, setOpen] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 text-[12px] text-text-secondary hover:border-accent-teal/50 hover:text-text-primary"
      >
        Explain this
      </button>
      <Drawer open={open} onClose={() => setOpen(false)} title={title}>
        <div className="space-y-3 text-sm leading-relaxed text-text-secondary">{plain}</div>
        {raw !== undefined && (
          <div className="mt-5 border-t border-border pt-4">
            <button onClick={() => setShowRaw((r) => !r)} className="text-[12px] text-accent-teal hover:underline">
              {showRaw ? "Hide raw data" : "View raw data"}
            </button>
            {showRaw && (
              <pre className="mt-2 max-h-80 overflow-auto rounded-lg border border-border bg-bg-base p-3 font-mono text-[11px] leading-relaxed text-text-muted">
                {JSON.stringify(raw, null, 2)}
              </pre>
            )}
          </div>
        )}
      </Drawer>
    </>
  );
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── States (mandatory on every data view) ───────────────────────────────────

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-bg-surface/50 px-6 py-14 text-center">
      <p className="text-base font-medium text-text-primary">{title}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-text-muted">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-border bg-bg-surface px-5 py-8 text-text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent-teal border-t-transparent" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", detail, action }: { title?: string; detail?: string; action?: ReactNode }) {
  return (
    <Card className="border-[#f87171]/30 p-5">
      <p className="text-sm font-semibold text-[#f87171]">{title}</p>
      {detail && <p className="mt-1 font-mono text-xs text-text-muted break-words">{detail}</p>}
      {action && <div className="mt-4">{action}</div>}
    </Card>
  );
}

// ─── Score / gauge ───────────────────────────────────────────────────────────

/** Circular gauge for 0..100 (score) or a % value. Pure SVG, no deps. */
export function Gauge({
  value, max = 100, label, suffix = "", size = 132, tone = "teal",
}: { value: number | null; max?: number; label?: string; suffix?: string; size?: number; tone?: "teal" | "amber" | "muted" }) {
  const stroke = Math.max(8, Math.round(size * 0.085));
  const r = size / 2 - stroke;
  const c = 2 * Math.PI * r;
  const frac = value == null ? 0 : Math.max(0, Math.min(1, value / max));
  const color = tone === "amber" ? "#F5B544" : tone === "muted" ? "#475569" : "#8B5CF6";
  const valueFont = Math.round(size * 0.24); // scales with the circle; never overflows
  return (
    <div className="flex shrink-0 flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="block -rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1E293B" strokeWidth={stroke} />
          {value != null && (
            <circle
              cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
              strokeDasharray={c} strokeDashoffset={c * (1 - frac)}
              style={{ strokeLinecap: "round", transition: "stroke-dashoffset .6s ease" }}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono font-semibold leading-none text-text-primary" style={{ fontSize: valueFont }}>
            {value == null ? "—" : value}{value == null ? "" : suffix}
          </span>
        </div>
      </div>
      {label && (
        <span className="mt-2 max-w-[9rem] text-center text-[11px] uppercase leading-tight tracking-wide text-text-muted">
          {label}
        </span>
      )}
    </div>
  );
}

// ─── helpers ─────────────────────────────────────────────────────────────────

export function fmtDate(s?: string | null): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch { return s; }
}
export function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
