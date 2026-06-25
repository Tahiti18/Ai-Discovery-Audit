/**
 * Local workspace state for AI Visibility OS.
 *
 * HONEST LIMITATION: the API key is created once via POST /v1/orgs and stored in
 * localStorage. This is a *local operator* convenience, NOT production auth.
 * Surfaced as such in Settings. No provider keys are ever stored client-side.
 */

export interface Workspace {
  orgId: string;
  orgName: string;
  apiKey: string; // gr_... shown once at creation
  plan: string;
}

const ORG_KEY = "aivos.workspace";
const LAST_ENTITY_KEY = "aivos.lastEntityId";

export function getWorkspace(): Workspace | null {
  try {
    const raw = localStorage.getItem(ORG_KEY);
    return raw ? (JSON.parse(raw) as Workspace) : null;
  } catch {
    return null;
  }
}

export function setWorkspace(ws: Workspace): void {
  localStorage.setItem(ORG_KEY, JSON.stringify(ws));
}

export function clearWorkspace(): void {
  localStorage.removeItem(ORG_KEY);
  localStorage.removeItem(LAST_ENTITY_KEY);
}

export function getApiKey(): string | null {
  return getWorkspace()?.apiKey ?? null;
}

export function getLastEntityId(): string | null {
  return localStorage.getItem(LAST_ENTITY_KEY);
}

export function setLastEntityId(id: string): void {
  localStorage.setItem(LAST_ENTITY_KEY, id);
}
