import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { riskColor } from "@/lib/constants";
import { useMemo, useState, useRef, useCallback } from "react";
import {
  Share2, MessageSquare, Search, ChevronLeft, ChevronRight,
  Maximize2, Minimize2, Target, RotateCcw, Eye,
} from "lucide-react";
import { useGraph, useEntities } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { layoutGraph, mapEntity } from "@/lib/mappers";
import { NetworkGraph, type NetworkGraphRef } from "@/components/visualizations/network-graph";
import { GraphToolbar } from "@/components/visualizations/graph-toolbar";
import { GraphTooltip } from "@/components/visualizations/graph-tooltip";
import { GraphMinimap } from "@/components/visualizations/graph-minimap";
import { ErrorState } from "@/components/shared/error-state";
import { NetworkSkeleton } from "@/components/shared/skeletons";
import { Slider } from "@/components/ui/slider";

export const Route = createFileRoute("/_app/network")({
  head: () => ({ meta: [{ title: "Network graph — ERakshak" }] }),
  component: NetworkPage,
});

type Mode = "all" | "money" | "comm";
type FocusLevel = 1 | 2 | "all";
type BreadcrumbItem = { id: string; label: string };

const kindGlyph = (k: string) => (k === "phone" ? "☎" : k === "account" ? "◈" : "◉");

function NetworkPage() {
  const { dataset, addBreadcrumb, setPinnedEntity } = useInvestigation();
  const { data, isLoading, error, refetch } = useGraph();
  const { data: entitiesData } = useEntities();
  const graph = useMemo(() => (data ? layoutGraph(data) : { nodes: [], edges: [] }), [data]);
  const entities = useMemo(() => (entitiesData?.items || []).map(mapEntity), [entitiesData]);

  const [mode, setMode] = useState<Mode>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [forceStrength, setForceStrength] = useState([1]);
  const [edgeThreshold, setEdgeThreshold] = useState([0]);
  const [focusLevel, setFocusLevel] = useState<FocusLevel>("all");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isFrozen, setIsFrozen] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [graphSearch, setGraphSearch] = useState("");
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);
  const [breadcrumbIndex, setBreadcrumbIndex] = useState(-1);
  const [legendExpanded, setLegendExpanded] = useState(true);

  // Tooltip state
  const [tooltip, setTooltip] = useState<{
    id: string; label: string; kind: string; risk: number; degree: number;
    x: number; y: number;
  } | null>(null);

  const graphRef = useRef<NetworkGraphRef>(null);

  const selected = graph.nodes.find((n) => n.id === selectedId) || null;
  const selectedEntity = entities.find((e) => e.id === selectedId || e.label === selected?.label);

  const handleSelectNode = useCallback((id: string) => {
    setSelectedId(id);
    const node = graph.nodes.find(n => n.id === id);
    if (node) {
      // Add to breadcrumbs
      setBreadcrumbs(prev => {
        const trimmed = prev.slice(0, breadcrumbIndex + 1);
        const next = [...trimmed, { id: node.id, label: node.label }];
        return next.slice(-15);
      });
      setBreadcrumbIndex(prev => {
        const newIdx = Math.min(prev + 1, 14);
        return newIdx;
      });
      addBreadcrumb({ id: node.id, label: node.label, page: "network" });

      // Pin entity if found
      const entity = entities.find(e => e.id === id || e.label === node.label);
      if (entity) {
        setPinnedEntity(entity);
      }
    }
  }, [graph.nodes, breadcrumbIndex, addBreadcrumb, entities, setPinnedEntity]);

  const handleGraphSearch = useCallback(() => {
    if (!graphSearch.trim()) return;
    const lower = graphSearch.toLowerCase();
    const node = graph.nodes.find(n =>
      n.label.toLowerCase().includes(lower) || n.id.toLowerCase().includes(lower)
    );
    if (node) {
      graphRef.current?.flyToNode(node.id);
      handleSelectNode(node.id);
    }
  }, [graphSearch, graph.nodes, handleSelectNode]);

  const navigateBreadcrumb = useCallback((direction: "prev" | "next") => {
    const newIndex = direction === "prev"
      ? Math.max(0, breadcrumbIndex - 1)
      : Math.min(breadcrumbs.length - 1, breadcrumbIndex + 1);
    setBreadcrumbIndex(newIndex);
    const bc = breadcrumbs[newIndex];
    if (bc) {
      graphRef.current?.flyToNode(bc.id);
      setSelectedId(bc.id);
    }
  }, [breadcrumbs, breadcrumbIndex]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => {
      const next = !prev;
      if (next) {
        document.documentElement.classList.add("fullscreen-mode");
      } else {
        document.documentElement.classList.remove("fullscreen-mode");
      }
      return next;
    });
  }, []);

  if (isLoading) {
    return <NetworkSkeleton />;
  }

  if (error) {
    return <ErrorState message={(error as Error).message} onRetry={() => refetch()} />;
  }

  return (
    <div className={isFullscreen ? "fixed inset-0 z-50 bg-background" : "mx-auto max-w-7xl"}>
      {!isFullscreen && (
        <PageHeader
          eyebrow={`Case · ${(dataset || "").toUpperCase()}`}
          title="Network graph"
          description={`${graph.nodes.length} nodes · ${graph.edges.length} edges. Force-directed layout. Drag nodes, scroll to zoom.`}
          actions={
            <div className="flex items-center gap-2">
              <div className="flex rounded-md border border-border bg-surface p-0.5">
                {[
                  { k: "all" as Mode, label: "All edges" },
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
                    {m.Icon && <m.Icon className="h-3 w-3" />} {m.label}
                  </button>
                ))}
              </div>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={toggleFullscreen}
              >
                <Maximize2 className="h-3 w-3" /> Fullscreen
              </Button>
            </div>
          }
        />
      )}

      <div className={`grid gap-4 ${isFullscreen ? "h-full grid-cols-1" : "lg:grid-cols-[1fr_340px]"}`}>
        {/* ── Graph Canvas ──────────────────────────── */}
        <div className={`relative overflow-hidden rounded-lg border border-border bg-surface/40 grid-bg ${isFullscreen ? "h-full" : "h-[600px]"}`}>
          <NetworkGraph
            ref={graphRef}
            nodes={graph.nodes}
            edges={graph.edges}
            selectedId={selectedId}
            onSelectNode={handleSelectNode}
            onHoverNode={setTooltip}
            edgeFilter={mode}
            edgeThreshold={edgeThreshold[0]}
            forceStrength={forceStrength[0]}
            focusLevel={focusLevel}
            frozenLayout={isFrozen}
            isPaused={isPaused}
            width={isFullscreen ? window.innerWidth : 900}
            height={isFullscreen ? window.innerHeight : 600}
          />

          {/* Graph Toolbar */}
          <GraphToolbar
            isFullscreen={isFullscreen}
            isFrozen={isFrozen}
            isPaused={isPaused}
            onZoomIn={() => graphRef.current?.zoomIn()}
            onZoomOut={() => graphRef.current?.zoomOut()}
            onFitGraph={() => graphRef.current?.fitGraph()}
            onResetLayout={() => graphRef.current?.resetLayout()}
            onCenterSelection={() => selectedId && graphRef.current?.flyToNode(selectedId)}
            onToggleFullscreen={toggleFullscreen}
            onToggleFreeze={() => {
              if (isFrozen) {
                graphRef.current?.unfreezeLayout();
              } else {
                graphRef.current?.freezeLayout();
              }
              setIsFrozen(!isFrozen);
            }}
            onTogglePause={() => {
              if (isPaused) {
                graphRef.current?.resumeSimulation();
              } else {
                graphRef.current?.pauseSimulation();
              }
              setIsPaused(!isPaused);
            }}
          />

          {/* Tooltip */}
          <GraphTooltip
            x={tooltip?.x || 0}
            y={tooltip?.y || 0}
            label={tooltip?.label || ""}
            kind={tooltip?.kind || ""}
            risk={tooltip?.risk || 0}
            degree={tooltip?.degree || 0}
            visible={tooltip !== null}
          />

          {/* Minimap */}
          <GraphMinimap
            nodes={graph.nodes}
            edges={graph.edges}
            selectedId={selectedId}
            onSelectNode={handleSelectNode}
          />

          {/* Comprehensive Legend */}
          <div className="absolute bottom-3 left-3 z-10">
            <div
              className="rounded-lg text-[10px] backdrop-blur-xl"
              style={{
                backgroundColor: "oklch(0.18 0.03 250 / 0.92)",
                border: "1px solid oklch(0.32 0.02 250)",
              }}
            >
              <button
                onClick={() => setLegendExpanded(p => !p)}
                className="text-mono flex w-full items-center gap-1.5 px-2.5 py-2 uppercase tracking-widest text-muted-foreground hover:text-foreground"
              >
                <Eye className="h-3 w-3" />
                Legend
                <span className="ml-auto text-[9px]">{legendExpanded ? "▾" : "▸"}</span>
              </button>
              {legendExpanded && (
                <div className="space-y-1 border-t border-border/40 px-2.5 pb-2.5 pt-2">
                  <div className="text-mono text-[9px] uppercase tracking-widest text-muted-foreground/60">Edges</div>
                  <div className="flex items-center gap-2"><svg width="20" height="6"><line x1="0" y1="3" x2="20" y2="3" stroke="var(--primary)" strokeWidth="2.5" /></svg> <span className="text-foreground/80">Money flow</span></div>
                  <div className="flex items-center gap-2"><svg width="20" height="6"><line x1="0" y1="3" x2="20" y2="3" stroke="var(--risk-med)" strokeWidth="2" /></svg> <span className="text-foreground/80">Communication</span></div>
                  <div className="flex items-center gap-2"><svg width="20" height="6"><line x1="0" y1="3" x2="20" y2="3" stroke="var(--muted-foreground)" strokeWidth="2.5" strokeDasharray="6 3" /></svg> <span className="text-foreground/80">Shared ID</span></div>
                  <div className="mt-1 text-mono text-[9px] uppercase tracking-widest text-muted-foreground/60">Nodes</div>
                  <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--risk-high)" }} /> <span className="text-foreground/80">High risk (≥70)</span></div>
                  <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--risk-med)" }} /> <span className="text-foreground/80">Medium (40-69)</span></div>
                  <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--risk-low)" }} /> <span className="text-foreground/80">Low (&lt;40)</span></div>
                  <div className="mt-1 text-mono text-[9px] uppercase tracking-widest text-muted-foreground/60">Size</div>
                  <div className="text-foreground/60">Node size = connection count</div>
                </div>
              )}
            </div>
          </div>

          {/* Info chip */}
          {!isFullscreen && (
            <div className="text-mono absolute top-3 left-3 rounded border border-border bg-background/80 px-2 py-1 text-[10px] uppercase tracking-widest text-muted-foreground backdrop-blur">
              {graph.nodes.length} nodes · {graph.edges.length} edges
              {isFrozen && " · Frozen"}
              {isPaused && " · Paused"}
            </div>
          )}
        </div>

        {/* ── Right Panel ──────────────────────────── */}
        {!isFullscreen && (
          <div className="space-y-4 overflow-y-auto" style={{ maxHeight: "calc(100vh - 200px)" }}>
            {/* ── Graph Search ───────────────────────── */}
            <div className="rounded-lg border border-border bg-surface/40 p-3">
              <div className="text-mono mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">Search graph</div>
              <div className="flex gap-1.5">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={graphSearch}
                    onChange={(e) => setGraphSearch(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleGraphSearch()}
                    placeholder="Find entity…"
                    className="text-mono h-8 border-transparent bg-background/50 pl-7 text-[11px] focus-visible:ring-1 focus-visible:ring-primary"
                  />
                </div>
                <Button size="sm" variant="outline" onClick={handleGraphSearch} className="h-8 px-2.5">
                  <Target className="h-3 w-3" />
                </Button>
              </div>
            </div>

            {/* ── Focus Investigation Panel ───────── */}
            <div className="rounded-lg border border-border bg-surface/40 p-3">
              <div className="text-mono mb-3 text-[10px] uppercase tracking-widest text-muted-foreground">Focus Investigation</div>
              <div className="space-y-2">
                {([
                  { value: 1 as FocusLevel, label: "Direct Connections (1 Hop)" },
                  { value: 2 as FocusLevel, label: "Extended Network (2 Hops)" },
                  { value: "all" as FocusLevel, label: "Entire Network" },
                ] as const).map(opt => (
                  <label key={String(opt.value)} className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors hover:bg-accent/30">
                    <input
                      type="radio"
                      name="focusLevel"
                      checked={focusLevel === opt.value}
                      onChange={() => setFocusLevel(opt.value)}
                      className="h-3.5 w-3.5 accent-primary"
                    />
                    <span className="text-[12px] text-foreground">{opt.label}</span>
                  </label>
                ))}
              </div>
              <div className="mt-3 flex gap-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1 text-[10px]"
                  disabled={!selectedId}
                  onClick={() => selectedId && graphRef.current?.flyToNode(selectedId)}
                >
                  Focus on Selection
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-[10px]"
                  onClick={() => {
                    setFocusLevel("all");
                    setSelectedId(null);
                    graphRef.current?.fitGraph();
                  }}
                >
                  <RotateCcw className="h-3 w-3" />
                </Button>
              </div>
            </div>

            {/* ── Breadcrumb Trail ───────────────────── */}
            {breadcrumbs.length > 0 && (
              <div className="rounded-lg border border-border bg-surface/40 p-3">
                <div className="text-mono mb-2 flex items-center justify-between text-[10px] uppercase tracking-widest text-muted-foreground">
                  <span>Investigation Trail</span>
                  <span>{breadcrumbIndex + 1}/{breadcrumbs.length}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {breadcrumbs.map((bc, i) => (
                    <button
                      key={`${bc.id}-${i}`}
                      onClick={() => {
                        setBreadcrumbIndex(i);
                        graphRef.current?.flyToNode(bc.id);
                        setSelectedId(bc.id);
                      }}
                      className={`text-mono rounded px-1.5 py-0.5 text-[10px] transition-colors ${
                        i === breadcrumbIndex
                          ? "bg-primary/20 text-primary"
                          : "text-muted-foreground hover:bg-accent/30 hover:text-foreground"
                      }`}
                    >
                      {bc.label}
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 flex-1 gap-1 text-[10px]"
                    disabled={breadcrumbIndex <= 0}
                    onClick={() => navigateBreadcrumb("prev")}
                  >
                    <ChevronLeft className="h-3 w-3" /> Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 flex-1 gap-1 text-[10px]"
                    disabled={breadcrumbIndex >= breadcrumbs.length - 1}
                    onClick={() => navigateBreadcrumb("next")}
                  >
                    Next <ChevronRight className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            )}

            {/* ── Selected Node Panel ───────────────── */}
            <div className="rounded-lg border border-border bg-surface/40 p-4">
              {!selected ? (
                <div className="py-4 text-center text-sm text-muted-foreground">
                  Click a node to inspect
                </div>
              ) : (
                <>
                  <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Selected node</div>
                  <div className="mt-2 flex items-center gap-2">
                    <span
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-lg"
                      style={{ backgroundColor: `${riskColor(selected.risk)}22`, color: riskColor(selected.risk) }}
                    >
                      {kindGlyph(selected.kind)}
                    </span>
                    <div>
                      <div className="text-sm font-medium text-foreground">{selected.label}</div>
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
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {graph.edges
                        .filter((e) => e.from === selected.id || e.to === selected.id)
                        .slice(0, 12)
                        .map((e, i) => {
                          const other = graph.nodes.find((n) => n.id === (e.from === selected.id ? e.to : e.from));
                          if (!other) return null;
                          return (
                            <button
                              key={i}
                              onClick={() => handleSelectNode(other.id)}
                              className="flex w-full items-center justify-between rounded border border-border bg-background/50 px-2 py-1.5 text-left text-[12px] transition-colors hover:border-primary hover:bg-primary/5"
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
                </>
              )}
            </div>

            {/* ── Controls ───────────────────────────── */}
            <div className="space-y-4 rounded-lg border border-border bg-surface/40 p-4">
              <div>
                <div className="text-mono mb-3 flex items-center justify-between text-[10px] uppercase tracking-widest text-muted-foreground">
                  <span>Relationship strength</span>
                  <span>{Math.round(edgeThreshold[0] * 100)}%</span>
                </div>
                <Slider
                  value={edgeThreshold}
                  onValueChange={setEdgeThreshold}
                  min={0}
                  max={0.9}
                  step={0.05}
                />
                <div className="text-mono mt-1 text-[9px] text-muted-foreground/60">
                  Hide edges below this weight percentile
                </div>
              </div>

              <div className="border-t border-border/60 pt-4">
                <div className="text-mono mb-3 flex items-center justify-between text-[10px] uppercase tracking-widest text-muted-foreground">
                  <span>Force strength</span>
                  <span>{forceStrength[0]}x</span>
                </div>
                <Slider
                  value={forceStrength}
                  onValueChange={setForceStrength}
                  min={0.1}
                  max={3}
                  step={0.1}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
