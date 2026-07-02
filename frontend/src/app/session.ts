/**
 * Visible to AI — client session (passwordless / magic-link).
 *
 * Stores the session JWT + the signed-in user and their workspace (org) in
 * localStorage. The API client reads the access token from here and sends it as
 * `Authorization: Bearer <jwt>`. No passwords, no provider keys client-side.
 */

export interface SessionUser {
  id: string;
  email: string;
  name: string | null;
}

export interface SessionOrg {
  id: string;
  name: string;
  plan: string;
  role: string;
}

export interface Session {
  accessToken: string;
  user: SessionUser;
  org: SessionOrg;
}

const SESSION_KEY = "vta.session";

export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function setSession(s: Session): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(s));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

export function getAccessToken(): string | null {
  return getSession()?.accessToken ?? null;
}

export function isSignedIn(): boolean {
  return getAccessToken() != null;
}
