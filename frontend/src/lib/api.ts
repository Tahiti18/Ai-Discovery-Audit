import { mapBackendToFrontend } from './reportMapper';
import type { AuditReport } from './mockData';

const API_BASE = import.meta.env.PUBLIC_API_BASE || '/api';

/**
 * Costruisce un URL API assoluto combinando il prefisso configurato
 * con il path e i parametri di query.
 *
 * In dev: API_BASE = '/api' → '/api/audit?url=...'
 * In prod: API_BASE = 'https://api.geoready.dev' → 'https://api.geoready.dev/audit?url=...'
 */
export function buildApiUrl(
  path: string,
  params?: Record<string, string | undefined>,
): string {
  const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
  const cleanPath = path.startsWith('/') ? path : `/${path}`;

  const searchParams = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        searchParams.set(key, value);
      }
    });
  }
  const query = searchParams.toString();
  return query ? `${base}${cleanPath}?${query}` : `${base}${cleanPath}`;
}

export interface FetchAuditResult {
  report: AuditReport | null;
  error: string | null;
}

/**
 * Esegue un audit GEO chiamando il backend FastAPI.
 * Il backend restituisce un oggetto JSON completo che viene
 * mappato nel formato AuditReport atteso dai componenti UI.
 */
export async function fetchAuditReport(url: string): Promise<FetchAuditResult> {
  try {
    const encodedUrl = encodeURIComponent(url);
    const res = await fetch(buildApiUrl('/audit', { url: encodedUrl }));

    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        detail = err.detail || detail;
      } catch {
        // ignore JSON parse error on error response
      }
      return { report: null, error: detail };
    }

    const data = await res.json();
    const report = mapBackendToFrontend(data);
    return { report, error: null };
  } catch (e: any) {
    return {
      report: null,
      error: e.message || 'Network error. Is the backend running?',
    };
  }
}
