/** Root of the AI Visibility OS SPA island: routing + shell. */
import { AppShell } from "./AppShell";
import { useRoute } from "./router";
import { getWorkspace } from "../lib/platformStore";
import { Dashboard } from "./pages/Dashboard";
import { Onboarding } from "./pages/Onboarding";
import { EntityDetail } from "./pages/EntityDetail";
import { ProbeResult } from "./pages/ProbeResult";
import { Settings } from "./pages/Settings";
import { Learn } from "./pages/Learn";

export default function AIVisibilityApp() {
  const route = useRoute();
  const hasWorkspace = !!getWorkspace();

  // First-time visitors land on the value-first onboarding, not admin.
  if (route.name === "dashboard" && !hasWorkspace) {
    return <Shell active="#/onboarding"><Onboarding /></Shell>;
  }

  switch (route.name) {
    case "onboarding":
      return <Shell active="#/onboarding"><Onboarding /></Shell>;
    case "entity":
      return <Shell active="#/dashboard"><EntityDetail id={route.params.id} /></Shell>;
    case "probe":
      return <Shell active="#/dashboard"><ProbeResult key={route.params.runId} runId={route.params.runId} /></Shell>;
    case "settings":
      return <Shell active="#/settings"><Settings /></Shell>;
    case "learn":
      return <Shell active={`#/soon/${route.params.key}`}><Learn contentKey={route.params.key} /></Shell>;
    case "dashboard":
    default:
      return <Shell active="#/dashboard"><Dashboard /></Shell>;
  }
}

function Shell({ active, children }: { active: string; children: React.ReactNode }) {
  return <AppShell active={active}>{children}</AppShell>;
}
