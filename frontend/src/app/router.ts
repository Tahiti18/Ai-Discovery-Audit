/** Minimal dependency-free hash router for the AI Visibility OS SPA island. */
import { useEffect, useState } from "react";

export interface Route {
  name: "onboarding" | "dashboard" | "entity" | "probe" | "settings" | "learn";
  params: Record<string, string>;
}

export function parseHash(hash: string): Route {
  const h = hash.replace(/^#/, "");
  const seg = h.split("/").filter(Boolean); // ["e","123"]
  if (seg[0] === "e" && seg[1]) return { name: "entity", params: { id: seg[1] } };
  if (seg[0] === "probe" && seg[1]) return { name: "probe", params: { runId: seg[1] } };
  if ((seg[0] === "soon" || seg[0] === "learn") && seg[1]) return { name: "learn", params: { key: seg[1] } };
  if (seg[0] === "settings") return { name: "settings", params: {} };
  if (seg[0] === "dashboard") return { name: "dashboard", params: {} };
  if (seg[0] === "onboarding" || seg[0] === "new") return { name: "onboarding", params: {} };
  return { name: "dashboard", params: {} }; // default; root decides onboarding vs dashboard
}

export function navigate(to: string): void {
  window.location.hash = to;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
