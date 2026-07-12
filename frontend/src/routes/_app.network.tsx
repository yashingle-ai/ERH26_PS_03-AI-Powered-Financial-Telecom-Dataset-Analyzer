import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { riskBand } from "@/lib/mock-data";
import { useMemo, useState } from "react";
import { Share2, MessageSquare, Loader2 } from "lucide-react";
import { useGraph } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { layoutGraph } from "@/lib/mappers";

export const Route = createFileRoute("/_app/network")({
  head: () => ({ meta: [{ title: "Network graph — ERakshak" }] }),
  component: NetworkPage,
});

type Mode = "money" | "comm";

const kindGlyph = (k: string) => (k === "phone" ? "☎" : k === "account" ? "◈" : "◉");
const bandColor = (r: number) => {
  const b = riskBand(r);
  return b === "high" ? "var(--risk-high)" : b === "medium" ? "var(--risk-med)" : "var(--risk-low)";
};

function NetworkPage() {
  const { dataset } = useInvestigation();
  const { data, isLoading, error } = useGraph();
  const graph = useMemo(() => (data ? layoutGraph(data) : { nodes: [], edges: [] }), [data]);
  const [mode, setMode] = useState<Mode>("money");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = graph.nodes.find((n) => n.id === selectedId) || graph.nodes[0];
  const edges = graph.edges.filter((e) =>
    mode === "money" ? e.kind !== "comm" : e.kind !== "money"
  );

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" /> Building graph…
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
        title="Network graph"
        description="Money-flow and communication overlays from the API graph payload."
        actions={
          <div className="flex rounded-md border border-border bg-surface p-0.5">
            {[
              { k: "money" as Mode, label: "Money flow", Icon: Share2 },
              { k: "comm" as Mode, label: "Communication", Icon: MessageSquare },
            ].map((m) => (
              <button
                key={m.k}
                onClick={() => setMode(m.k)}
                className={`text-mono flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] uppercase tracking-widest transition-colors ${
                  mode === m.k ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <m.Icon className="h-3 w-3" /> {m.label}
              </button>
            ))}
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="relative h-[560px] overflow-hidden rounded-lg border border-border bg-surface/40 grid-bg">
          <svg viewBox="0 0 1120 520" className="h-full w-full">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--primary)" fillOpacity="0.6" />
              </marker>
            </defs>

            {edges.map((e, i) => {
              const from = graph.nodes.find((n) => n.id === e.from);
              const to = graph.nodes.find((n) => n.id === e.to);
              if (!from || !to) return null;
              const stroke =
                e.kind === "money" ? "var(--primary)" :
                e.kind === "comm" ? "var(--risk-med)" :
                "var(--muted-foreground)";
              const dash = e.kind === "shared_id" ? "4 4" : undefined;
              return (
                <g key={i}>
                  <line
                    x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                    stroke={stroke}
                    strokeOpacity={0.55}
                    strokeWidth={Math.max(1, Math.min(4, e.weight * 0.4))}
                    strokeDasharray={dash}
                    markerEnd={e.kind !== "shared_id" ? "url(#arrow)" : undefined}
                  />
                </g>
              );
            })}

            {graph.nodes.map((n) => {
              const r = 14 + (n.risk / 100) * 12;
              const isSel = (selectedId || selected?.id) === n.id;
              return (
                <g key={n.id} className="cursor-pointer" onClick={() => setSelectedId(n.id)}>
                  {isSel && (
                    <circle cx={n.x} cy={n.y} r={r + 8} fill="none" stroke={bandColor(n.risk)} strokeOpacity="0.35" />
                  )}
                  <circle
                    cx={n.x} cy={n.y} r={r}
                    fill={bandColor(n.risk)}
                    fillOpacity="0.18"
                    stroke={bandColor(n.risk)}
                    strokeWidth={isSel ? 2 : 1.2}
                  />
                  <text x={n.x} y={n.y + 4} textAnchor="middle" fontSize="12" fill={bandColor(n.risk)} fontFamily="IBM Plex Mono">
                    {kindGlyph(n.kind)}
                  </text>
                  <text x={n.x} y={n.y + r + 14} textAnchor="middle" fontSize="10" fill="var(--foreground)" fontFamily="IBM Plex Sans">
                    {(n.label || "").slice(0, 18)}
                  </text>
                </g>
              );
            })}
          </svg>

          <div className="text-mono absolute bottom-3 left-3 flex flex-col gap-1.5 rounded border border-border bg-background/80 p-2.5 text-[10px] uppercase tracking-widest backdrop-blur">
            <div className="text-muted-foreground">Legend</div>
            <div className="flex items-center gap-2"><svg width="26" height="6"><line x1="0" y1="3" x2="26" y2="3" stroke="var(--primary)" strokeWidth="2" /></svg> Money flow</div>
            <div className="flex items-center gap-2"><svg width="26" height="6"><line x1="0" y1="3" x2="26" y2="3" stroke="var(--risk-med)" strokeWidth="2" /></svg> Communication</div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface/40 p-4">
          {!selected ? (
            <div className="text-sm text-muted-foreground">No nodes in graph.</div>
          ) : (
            <>
              <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Selected node</div>
              <div className="mt-2 flex items-center gap-2">
                <span
                  className="flex h-8 w-8 items-center justify-center rounded"
                  style={{ backgroundColor: `${bandColor(selected.risk)}22`, color: bandColor(selected.risk) }}
                >
                  {kindGlyph(selected.kind)}
                </span>
                <div>
                  <div className="text-sm text-foreground">{selected.label}</div>
                  <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">{selected.kind}</div>
                </div>
              </div>

              <div className="text-mono mt-4 space-y-2 text-[11px]">
                {[
                  ["Risk score", selected.risk],
                  ["Node id", selected.id],
                ].map(([k, v]) => (
                  <div key={String(k)} className="flex justify-between border-b border-border/60 pb-1.5">
                    <span className="text-muted-foreground">{k}</span>
                    <span className="text-foreground">{v}</span>
                  </div>
                ))}
              </div>

              <div className="mt-4">
                <div className="text-mono mb-1.5 text-[10px] uppercase tracking-widest text-muted-foreground">Neighbors</div>
                <div className="space-y-1">
                  {graph.edges
                    .filter((e) => e.from === selected.id || e.to === selected.id)
                    .slice(0, 8)
                    .map((e, i) => {
                      const other = graph.nodes.find((n) => n.id === (e.from === selected.id ? e.to : e.from));
                      if (!other) return null;
                      return (
                        <button
                          key={i}
                          onClick={() => setSelectedId(other.id)}
                          className="flex w-full items-center justify-between rounded border border-border bg-background/50 px-2 py-1.5 text-left text-[12px] hover:border-primary"
                        >
                          <span className="truncate text-foreground">{other.label}</span>
                          <span className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                            {e.kind === "money" ? "₹" : e.kind === "comm" ? "↔" : "="} · {e.weight}
                          </span>
                        </button>
                      );
                    })}
                </div>
              </div>

              <Button size="sm" className="mt-5 w-full bg-primary text-primary-foreground hover:opacity-90">
                Expand subgraph
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
