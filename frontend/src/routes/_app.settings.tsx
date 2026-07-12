import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { useInvestigation } from "@/lib/investigation-context";
import { api } from "@/lib/api";

export const Route = createFileRoute("/_app/settings")({
  head: () => ({ meta: [{ title: "Settings — ERakshak" }] }),
  component: SettingsPage,
});

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface/40 p-5">
      <div className="mb-4">
        <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">{title}</div>
        <p className="mt-1 text-[13px] text-muted-foreground">{description}</p>
      </div>
      {children}
    </div>
  );
}

function SettingsPage() {
  const { windowMinutes, setWindowMinutes, dataset } = useInvestigation();
  const [w, setW] = useState([windowMinutes]);
  const [tz] = useState("Asia/Kolkata");
  const [checking, setChecking] = useState(false);

  const save = () => {
    setWindowMinutes(w[0]);
    toast.success(`Correlation window set to ${w[0]}m`);
  };

  const ping = async () => {
    setChecking(true);
    try {
      const h = await api.health();
      toast.success(`API healthy · ${h.status} · ${api.baseUrl}`);
    } catch (e) {
      toast.error((e as Error).message || "API unreachable");
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        description={`Active dataset: ${dataset || "—"}. Correlation window is sent to /v1/analyze and related endpoints.`}
        actions={
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={ping} disabled={checking}>
              {checking ? "Checking…" : "Ping API"}
            </Button>
            <Button size="sm" className="bg-primary text-primary-foreground hover:opacity-90" onClick={save}>
              Save changes
            </Button>
          </div>
        }
      />

      <div className="space-y-4">
        <Panel title="Correlation window · W" description="Time window used to link a call, IP session, and transfer as one incident.">
          <div className="flex items-end gap-6">
            <div className="flex-1">
              <Slider value={w} onValueChange={setW} min={1} max={30} step={1} />
              <div className="text-mono mt-2 flex justify-between text-[10px] uppercase tracking-widest text-muted-foreground">
                <span>1 min</span><span>15 min</span><span>30 min</span>
              </div>
            </div>
            <div className="text-mono w-24 text-right text-3xl font-semibold text-primary">{w[0]}m</div>
          </div>
        </Panel>

        <Panel title="Timezone" description="All timestamps in the workspace are normalized to this timezone.">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-mono text-[10px] uppercase tracking-widest">Timezone</Label>
              <Input value={tz} readOnly className="text-mono bg-surface" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-mono text-[10px] uppercase tracking-widest">Locale</Label>
              <Input value="en-IN" readOnly className="text-mono bg-surface" />
            </div>
          </div>
        </Panel>

        <Panel title="Upload limits" description="Per-case ingestion caps. File upload is not exposed on the HTTP API yet — place files under datasets/raw/.">
          <div className="grid grid-cols-3 gap-4 text-mono text-[12px]">
            {[
              ["Max file size", "512 MB"],
              ["Files per batch", "64"],
              ["Rows per file", "5,000,000"],
            ].map(([k, v]) => (
              <div key={k} className="rounded border border-border bg-background/40 p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{k}</div>
                <div className="mt-1 text-lg text-foreground">{v}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Privacy guards" description="CGNAT-aware merge policy — public IP is never a merge key.">
          <div className="flex items-center justify-between rounded border border-border bg-background/40 px-3 py-3">
            <div>
              <div className="text-sm text-foreground">Exclude public IP from entity merges</div>
              <div className="text-[12px] text-muted-foreground">Recommended · prevents false entity collapse</div>
            </div>
            <Switch checked disabled />
          </div>
        </Panel>
      </div>
    </div>
  );
}
