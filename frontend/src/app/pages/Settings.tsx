/** Settings — workspace, local API key (honestly labeled), provider status. */
import { useState } from "react";
import { clearWorkspace, getWorkspace } from "../../lib/platformStore";
import { navigate } from "../router";
import { Button, Card, Caveat, Chip, PreviewBadge } from "../ui";

export function Settings() {
  const ws = getWorkspace();
  const [reveal, setReveal] = useState(false);

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-5 text-2xl font-semibold tracking-tight">Settings</h1>

      <Card className="mb-4 p-5">
        <p className="text-sm font-medium text-text-primary">Workspace</p>
        {ws ? (
          <div className="mt-3 space-y-3 text-sm">
            <Row label="Name" value={ws.orgName} />
            <Row label="Plan" value={ws.plan} />
            <div>
              <p className="text-text-muted">API key</p>
              <div className="mt-1 flex items-center gap-2">
                <code className="rounded bg-bg-base px-2 py-1 font-mono text-xs text-text-secondary">
                  {reveal ? ws.apiKey : `${ws.apiKey.slice(0, 8)}••••••••••••`}
                </code>
                <button onClick={() => setReveal((r) => !r)} className="text-xs text-accent-teal hover:underline">{reveal ? "Hide" : "Reveal"}</button>
              </div>
              <Caveat>
                <span className="mt-1 block">
                  This is a local-operator key stored in your browser — <strong>not production authentication</strong>.
                  Real accounts, login and teams are on the roadmap. Provider keys (for the AI engine) live only on the
                  API server and are never stored in this browser.
                </span>
              </Caveat>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-text-muted">No workspace yet.</p>
        )}
      </Card>

      <Card className="mb-4 p-5">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-text-primary">AI engines</p>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Chip tone="teal">Perplexity · live</Chip>
          <span className="inline-flex items-center gap-1"><PreviewBadge label="ChatGPT" /></span>
          <span className="inline-flex items-center gap-1"><PreviewBadge label="Claude" /></span>
          <span className="inline-flex items-center gap-1"><PreviewBadge label="Gemini" /></span>
        </div>
        <Caveat><span className="mt-2 block">Today’s results come from one web-grounded engine. Multi-engine comparison is built into the data model and will light up as engines are connected — we won’t show an engine’s results until it’s actually queried.</span></Caveat>
      </Card>

      <Card className="p-5">
        <p className="text-sm font-medium text-text-primary">Reset</p>
        <Caveat><span className="mt-1 block">Removes the local workspace from this browser. Your businesses remain in the API database.</span></Caveat>
        <div className="mt-3">
          <Button variant="ghost" onClick={() => { clearWorkspace(); navigate("#/onboarding"); }}>Reset local workspace</Button>
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-text-muted">{label}</span>
      <span className="text-text-secondary">{value}</span>
    </div>
  );
}
