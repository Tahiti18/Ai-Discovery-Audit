import { useState } from 'react';

// Cattura email → platform endpoint (CORS già aperto per geoready.dev).
// Dedupe e validazione server-side; source distingue i punti di ingresso.
const CAPTURE_URL = '/pricing/';

type Status = 'idle' | 'loading' | 'done' | 'error';

interface Props {
  source: string;
  title?: string;
  detail?: string;
}

export default function NewsletterSignup({
  source,
  title = 'Get the State of GEO report',
  detail = 'One email when the benchmark report ships, plus occasional GEO findings. No spam, unsubscribe anytime.',
}: Props) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed.includes('@')) {
      setStatus('error');
      return;
    }
    setStatus('loading');
    // Record the opt-in page so the backend can store it on the consent record.
    const sourceUrl = typeof window !== 'undefined' ? window.location.href : undefined;
    try {
      const res = await fetch(CAPTURE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: trimmed, source, source_url: sourceUrl }),
      });
      setStatus(res.ok ? 'done' : 'error');
    } catch {
      setStatus('error');
    }
  }

  if (status === 'done') {
    return (
      <div className="rounded-xl border border-accent-teal/40 bg-accent-teal/5 px-5 py-4 text-sm text-text-primary">
        ✅ You're on the list. We'll email you when the report is out.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-bg-surface px-5 py-5">
      <p className="font-display text-lg font-semibold text-text-primary">{title}</p>
      <p className="mt-1 text-sm text-text-secondary">{detail}</p>
      <form onSubmit={handleSubmit} className="mt-4 flex flex-col sm:flex-row gap-2">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          className="flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-teal focus:outline-none"
        />
        <button
          type="submit"
          disabled={status === 'loading'}
          className="rounded-lg bg-accent-teal px-5 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
        >
          {status === 'loading' ? 'Subscribing…' : 'Notify me'}
        </button>
      </form>
      <p className="mt-2 text-xs text-text-muted">
        By submitting, you agree to receive the State of GEO report and occasional GeoReady benchmark
        updates. You can unsubscribe anytime. See our{' '}
        <a href="/privacy/" className="underline hover:text-text-secondary">
          Privacy Policy
        </a>
        .
      </p>
      {status === 'error' && (
        <p className="mt-2 text-xs text-red-500">Something went wrong — check the email and try again.</p>
      )}
    </div>
  );
}
