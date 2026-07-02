/**
 * Visible to AI — authenticated app root.
 *
 * Guards on the session (redirects to /login/ when signed out), then hash-routes
 * between the dashboard and a live report. Everything here runs against the real
 * backend using the session JWT.
 */
import "./visibletoai.css";
import { useEffect, useState } from "react";
import { isSignedIn } from "./session";
import { Dashboard } from "./home/Dashboard";
import { AddBusiness } from "./home/AddBusiness";
import { ReportContainer } from "./report/ReportContainer";

function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash.replace(/^#\/?/, ""));
  useEffect(() => {
    const on = () => setHash(window.location.hash.replace(/^#\/?/, ""));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export function navigate(to: string): void {
  window.location.hash = to;
}

export default function AppRoot() {
  const route = useHashRoute();

  useEffect(() => {
    if (!isSignedIn()) window.location.href = "/login/";
  }, []);

  if (!isSignedIn()) return null; // redirecting

  const [seg, param] = route.split("/");
  if (seg === "report" && param) {
    return <ReportContainer runId={param} />;
  }
  if (seg === "new") {
    return <AddBusiness />;
  }
  return <Dashboard />;
}
