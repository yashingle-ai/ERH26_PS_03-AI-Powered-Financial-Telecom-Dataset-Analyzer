import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { ShieldAlert, Users, FileSearch, ArrowUpRight } from "lucide-react";
import { LoadingState } from "@/components/shared/loading-state";
import { ErrorState } from "@/components/shared/error-state";
import { DetectionsSkeleton } from "@/components/shared/skeletons";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { useMemo, useState } from "react";
import { useEntities } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapDetections } from "@/lib/mappers";
import { riskBand } from "@/lib/constants";
import { RiskHeatmap } from "@/components/risk-heatmap";

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
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const list = detections.filter((d) => filter === "all" || d.band === filter);

  /* Summary stats */
  const counts = useMemo(() => ({
    total: detections.length,
    high: detections.filter((d) => d.band === "high").length,
    medium: detections.filter((d) => d.band === "medium").length,
    low: detections.filter((d) => d.band === "low").length,
  }), [detections]);

  if (isLoading) {
    return <DetectionsSkeleton />;
  }

  if (error) {
    return <ErrorState message={(error as Error).message} />;
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
                {b !== "all" && (
                  <span className="ml-1 opacity-60">{counts[b]}</span>
                )}
              </button>
            ))}
          </div>
        }
      />

      {/* Summary chips */}
      <div className="mb-4 flex gap-3">
        {[
          { label: "Total rules", value: counts.total, color: "var(--foreground)" },
          { label: "High risk", value: counts.high, color: "var(--risk-high)" },
          { label: "Medium", value: counts.medium, color: "var(--risk-med)" },
          { label: "Low", value: counts.low, color: "var(--risk-low)" },
        ].map((s) => (
          <div key={s.label} className="rounded-lg border border-border bg-surface/40 px-3 py-2">
            <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">{s.label}</div>
            <div className="text-xl font-semibold" style={{ color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* FR-18 — which typologies drive each risky entity. Previously Streamlit-only. */}
      <section className="mb-6 rounded-lg border border-border bg-surface/40 p-4">
        <h2 className="mb-1 text-sm font-semibold">Risk heat map — entities × typologies</h2>
        <p className="mb-3 text-xs text-muted-foreground">
          Rule weight per entity. A dot means the typology did not fire on that entity.
        </p>
        <RiskHeatmap top={20} />
      </section>

      <div className="space-y-3">
        {list.length === 0 && (
          <EmptyState
            icon={ShieldAlert}
            title="No detections"
            description="No rule detections match the current filter."
          />
        )}
        {list.map((d) => {
          const isExpanded = expandedId === d.id;
          return (
            <div
              key={d.id}
              className={`hover-lift rounded-lg border bg-surface/40 p-4 transition-colors ${
                isExpanded ? "border-primary/40" : "border-border"
              }`}
            >
              <div className="flex items-start gap-4">
                <div
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded"
                  style={{ backgroundColor: `${bandColor(d.band)}22`, color: bandColor(d.band) }}
                >
                  <ShieldAlert className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className="text-sm font-medium text-foreground hover:text-primary transition-colors text-left"
                      onClick={() => setExpandedId(isExpanded ? null : d.id)}
                    >
                      {d.name}
                    </button>
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

                  {/* Stats & drill-down */}
                  <div className="mt-3 flex items-center gap-4">
                    <div className="text-mono flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted-foreground">
                      <Users className="h-3 w-3" /> {d.entities} entities
                    </div>
                    <div className="text-mono flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted-foreground">
                      <FileSearch className="h-3 w-3" /> {d.evidence} evidence
                    </div>
                    <Button asChild size="sm" variant="ghost" className="text-mono ml-auto gap-1 text-[10px] uppercase tracking-widest text-primary">
                      <Link to="/entities" search={{ id: undefined, rule: d.name }}>
                        View entities <ArrowUpRight className="h-3 w-3" />
                      </Link>
                    </Button>
                  </div>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="mt-4 rounded border border-border/60 bg-background/40 p-3">
                      <div className="text-mono mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">
                        Detection details
                      </div>
                      <div className="text-mono space-y-1.5 text-[11px]">
                        <div className="flex justify-between border-b border-border/40 pb-1">
                          <span className="text-muted-foreground">Rule ID</span>
                          <span className="text-foreground">{d.name}</span>
                        </div>
                        <div className="flex justify-between border-b border-border/40 pb-1">
                          <span className="text-muted-foreground">Risk band</span>
                          <span style={{ color: bandColor(d.band) }}>{d.band}</span>
                        </div>
                        <div className="flex justify-between border-b border-border/40 pb-1">
                          <span className="text-muted-foreground">Weight contribution</span>
                          <span className="text-foreground">+{d.weight} points</span>
                        </div>
                        <div className="flex justify-between border-b border-border/40 pb-1">
                          <span className="text-muted-foreground">Affected entities</span>
                          <span className="text-foreground">{d.entities}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Evidence notes</span>
                          <span className="text-foreground">{d.evidence}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
