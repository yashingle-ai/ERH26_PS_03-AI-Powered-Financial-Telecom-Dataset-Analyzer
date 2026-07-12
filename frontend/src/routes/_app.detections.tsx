import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { ShieldAlert, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useEntities } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapDetections } from "@/lib/mappers";

export const Route = createFileRoute("/_app/detections")({
  head: () => ({ meta: [{ title: "Detections & risk — ERakshak" }] }),
  component: DetectionsPage,
});

const bandColor = (b: string) =>
  b === "high" ? "var(--risk-high)" : b === "medium" ? "var(--risk-med)" : "var(--risk-low)";

function DetectionsPage() {
  const { dataset } = useInvestigation();
  const { data, isLoading, error } = useEntities();
  const detections = useMemo(() => mapDetections(data?.items || []), [data]);
  const [filter, setFilter] = useState<"all" | "high" | "medium" | "low">("all");
  const list = detections.filter((d) => filter === "all" || d.band === filter);

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" /> Loading detections…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-[color:var(--risk-high)]/40 bg-[color:var(--risk-high)]/10 p-4 text-sm text-[color:var(--risk-high)]">
        {(error as Error).message}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`Case · ${(dataset || "").toUpperCase()}`}
        title="Detections & risk"
        description="Aggregated from rule_flags returned by the detection service."
        actions={
          <div className="flex gap-1 rounded-md border border-border bg-surface p-0.5">
            {(["all", "high", "medium", "low"] as const).map((b) => (
              <button
                key={b}
                onClick={() => setFilter(b)}
                className={`text-mono rounded px-3 py-1.5 text-[11px] uppercase tracking-widest transition-colors ${
                  filter === b ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {b}
              </button>
            ))}
          </div>
        }
      />

      <div className="space-y-3">
        {list.length === 0 && (
          <div className="rounded-lg border border-border bg-surface/40 p-6 text-sm text-muted-foreground">
            No rule detections for this dataset/window.
          </div>
        )}
        {list.map((d) => (
          <div key={d.id} className="rounded-lg border border-border bg-surface/40 p-4">
            <div className="flex items-start gap-4">
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded"
                style={{ backgroundColor: `${bandColor(d.band)}22`, color: bandColor(d.band) }}
              >
                <ShieldAlert className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-medium text-foreground">{d.name}</h3>
                  <span
                    className="text-mono rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-widest"
                    style={{ color: bandColor(d.band), borderColor: `${bandColor(d.band)}55`, backgroundColor: `${bandColor(d.band)}15` }}
                  >
                    {d.band}
                  </span>
                  <span className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    weight +{d.weight}
                  </span>
                </div>
                <p className="mt-1.5 max-w-3xl text-[13px] text-muted-foreground">{d.reason}</p>
                <div className="text-mono mt-3 flex gap-4 text-[10px] uppercase tracking-widest text-muted-foreground">
                  <span>{d.entities} entities</span>
                  <span>{d.evidence} evidence notes</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
