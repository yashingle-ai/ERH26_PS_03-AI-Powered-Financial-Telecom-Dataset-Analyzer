import { useEffect, useRef, useCallback, useImperativeHandle, forwardRef, useState } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import { select } from "d3-selection";
import "d3-transition";
import { zoom as d3Zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import { drag } from "d3-drag";
import type { GraphNode, GraphEdge } from "@/lib/types";
import { riskColor } from "@/lib/constants";

/* ── D3 node/link types ──────────────────────────────── */

interface SimNode extends SimulationNodeDatum {
  id: string;
  label: string;
  kind: GraphNode["kind"];
  risk: number;
  degree: number;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  kind: GraphEdge["kind"];
  weight: number;
}

/* ── Props ────────────────────────────────────────────── */

export type NetworkGraphProps = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId?: string | null;
  onSelectNode?: (id: string) => void;
  onDoubleClickNode?: (id: string) => void;
  onHoverNode?: (node: { id: string; label: string; kind: string; risk: number; degree: number; x: number; y: number } | null) => void;
  edgeFilter?: "all" | "money" | "comm" | "shared_id";
  edgeThreshold?: number;
  forceStrength?: number;
  focusLevel?: 1 | 2 | "all";
  frozenLayout?: boolean;
  isPaused?: boolean;
  width?: number;
  height?: number;
};

export type NetworkGraphRef = {
  flyToNode: (id: string) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitGraph: () => void;
  resetLayout: () => void;
  freezeLayout: () => void;
  unfreezeLayout: () => void;
  pauseSimulation: () => void;
  resumeSimulation: () => void;
};

/* ── Glyph by entity kind ──────────────────────────── */

const kindGlyph = (k: string) =>
  k === "phone" ? "☎" : k === "account" ? "◈" : "◉";

/* ── Stroke style by edge kind ──────────────────────── */

const edgeStroke = (k: string) =>
  k === "money"
    ? "var(--primary)"
    : k === "comm"
      ? "var(--risk-med)"
      : "var(--muted-foreground)";

/* ── Component ────────────────────────────────────────── */

export const NetworkGraph = forwardRef<NetworkGraphRef, NetworkGraphProps>(function NetworkGraph({
  nodes,
  edges,
  selectedId,
  onSelectNode,
  onDoubleClickNode,
  onHoverNode,
  edgeFilter = "all",
  edgeThreshold = 0,
  forceStrength = 1,
  focusLevel = "all",
  frozenLayout = false,
  isPaused = false,
  width = 800,
  height = 560,
}, ref) {
  const svgRef = useRef<SVGSVGElement>(null);
  const simulationRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const [currentZoomScale, setCurrentZoomScale] = useState(1);

  /* Build degree map */
  const degreeMap = useCallback(() => {
    const m = new Map<string, number>();
    for (const e of edges) {
      m.set(e.from, (m.get(e.from) || 0) + 1);
      m.set(e.to, (m.get(e.to) || 0) + 1);
    }
    return m;
  }, [edges]);

  /* ── Focus mode: compute visible nodes/edges ─────── */
  const getVisibleData = useCallback(() => {
    if (focusLevel === "all" || !selectedId) {
      return { visibleNodeIds: new Set(nodes.map(n => n.id)), focusActive: false };
    }

    const visibleNodeIds = new Set<string>();
    visibleNodeIds.add(selectedId);

    // 1 hop: direct neighbors
    for (const e of edges) {
      if (e.from === selectedId) visibleNodeIds.add(e.to);
      if (e.to === selectedId) visibleNodeIds.add(e.from);
    }

    if (focusLevel === 2) {
      // 2 hops: neighbors of neighbors
      const hop1 = new Set(visibleNodeIds);
      for (const e of edges) {
        if (hop1.has(e.from)) visibleNodeIds.add(e.to);
        if (hop1.has(e.to)) visibleNodeIds.add(e.from);
      }
    }

    return { visibleNodeIds, focusActive: true };
  }, [nodes, edges, selectedId, focusLevel]);

  /* ── Imperative API ─────────────────────────────────── */
  useImperativeHandle(ref, () => ({
    flyToNode(id: string) {
      const svg = svgRef.current;
      if (!svg || !zoomBehaviorRef.current) return;
      const node = nodesRef.current.find(n => n.id === id);
      if (!node || node.x == null || node.y == null) return;

      const root = select(svg);
      const transform = zoomIdentity
        .translate(width / 2, height / 2)
        .scale(1.8)
        .translate(-node.x, -node.y);

      root.transition().duration(800).ease((t: number) => t * (2 - t))
        .call(zoomBehaviorRef.current!.transform, transform);

      onSelectNode?.(id);
    },
    zoomIn() {
      const svg = svgRef.current;
      if (!svg || !zoomBehaviorRef.current) return;
      select(svg).transition().duration(300)
        .call(zoomBehaviorRef.current!.scaleBy, 1.5);
    },
    zoomOut() {
      const svg = svgRef.current;
      if (!svg || !zoomBehaviorRef.current) return;
      select(svg).transition().duration(300)
        .call(zoomBehaviorRef.current!.scaleBy, 0.67);
    },
    fitGraph() {
      const svg = svgRef.current;
      if (!svg || !zoomBehaviorRef.current || !nodesRef.current.length) return;
      const xs = nodesRef.current.map(n => n.x!).filter(x => x != null);
      const ys = nodesRef.current.map(n => n.y!).filter(y => y != null);
      if (!xs.length) return;

      const minX = Math.min(...xs) - 50;
      const maxX = Math.max(...xs) + 50;
      const minY = Math.min(...ys) - 50;
      const maxY = Math.max(...ys) + 50;
      const dx = maxX - minX;
      const dy = maxY - minY;
      const scale = Math.min(width / dx, height / dy, 2) * 0.9;
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;

      const transform = zoomIdentity
        .translate(width / 2, height / 2)
        .scale(scale)
        .translate(-cx, -cy);

      select(svg).transition().duration(600)
        .call(zoomBehaviorRef.current!.transform, transform);
    },
    resetLayout() {
      if (!simulationRef.current) return;
      nodesRef.current.forEach(n => {
        n.fx = null;
        n.fy = null;
        n.x = width / 2 + (Math.random() - 0.5) * 200;
        n.y = height / 2 + (Math.random() - 0.5) * 200;
      });
      simulationRef.current.alpha(1).restart();
    },
    freezeLayout() {
      nodesRef.current.forEach(n => {
        n.fx = n.x;
        n.fy = n.y;
      });
      simulationRef.current?.stop();
    },
    unfreezeLayout() {
      nodesRef.current.forEach(n => {
        n.fx = null;
        n.fy = null;
      });
      simulationRef.current?.alpha(0.3).restart();
    },
    pauseSimulation() {
      simulationRef.current?.stop();
    },
    resumeSimulation() {
      simulationRef.current?.alpha(0.3).restart();
    },
  }), [width, height, onSelectNode]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !nodes.length) return;

    const degrees = degreeMap();
    const maxWeight = Math.max(1, ...edges.map(e => e.weight));
    const { visibleNodeIds, focusActive } = getVisibleData();

    /* ── Prepare data for simulation ──────────────── */
    const simNodes: SimNode[] = nodes.map((n) => ({
      id: n.id,
      label: n.label,
      kind: n.kind,
      risk: n.risk,
      degree: degrees.get(n.id) || 1,
      x: width / 2 + (Math.random() - 0.5) * 200,
      y: height / 2 + (Math.random() - 0.5) * 200,
    }));

    nodesRef.current = simNodes;
    const nodeById = new Map(simNodes.map((n) => [n.id, n]));

    const simLinks: SimLink[] = edges
      .filter((e) => nodeById.has(e.from) && nodeById.has(e.to))
      .map((e) => ({
        source: e.from,
        target: e.to,
        kind: e.kind,
        weight: e.weight,
      }));

    /* ── D3 selections ────────────────────────────── */
    const root = select(svg);
    root.selectAll("*").remove();

    /* Container group for zoom/pan */
    const g = root.append("g").attr("class", "graph-container");

    /* Zoom behavior */
    const zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 6])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
        setCurrentZoomScale(event.transform.k);
      });

    zoomBehaviorRef.current = zoomBehavior;
    root.call(zoomBehavior);
    root.call(zoomBehavior.transform, zoomIdentity.translate(0, 0).scale(1));

    /* Arrow markers */
    const defs = g.append("defs");
    ["money", "comm"].forEach((kind) => {
      defs
        .append("marker")
        .attr("id", `arrow-${kind}`)
        .attr("viewBox", "0 0 10 10")
        .attr("refX", 28)
        .attr("refY", 5)
        .attr("markerWidth", 5)
        .attr("markerHeight", 5)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M 0 0 L 10 5 L 0 10 z")
        .attr("fill", edgeStroke(kind))
        .attr("fill-opacity", 0.6);
    });

    /* ── Draw edges ────────────────────────────────── */
    const linkGroup = g
      .append("g")
      .attr("class", "links")
      .selectAll("line")
      .data(simLinks)
      .join("line")
      .attr("stroke", (d) => edgeStroke(d.kind))
      .attr("stroke-opacity", (d) => {
        // Progressive rendering: hide weak edges below threshold
        const normalizedWeight = d.weight / maxWeight;
        if (normalizedWeight < edgeThreshold) return 0;
        // Opacity based on weight: weak=0.12, strong=0.7
        const isVisible = visibleNodeIds.has((d.source as SimNode).id || (d.source as string))
          && visibleNodeIds.has((d.target as SimNode).id || (d.target as string));
        if (focusActive && !isVisible) return 0.04;
        return 0.12 + 0.58 * normalizedWeight;
      })
      .attr("stroke-width", (d) => {
        if (d.kind === "shared_id") return 2.5;
        if (d.kind === "money") return Math.max(1.5, Math.min(5, d.weight * 0.4));
        return Math.max(1, Math.min(3, d.weight * 0.3));
      })
      .attr("stroke-dasharray", (d) =>
        d.kind === "shared_id" ? "6 3" : null
      )
      .attr("marker-end", (d) =>
        d.kind !== "shared_id" ? `url(#arrow-${d.kind})` : null
      )
      .style("transition", "stroke-opacity 0.3s ease");

    /* ── Draw nodes ────────────────────────────────── */
    const nodeGroup = g
      .append("g")
      .attr("class", "nodes")
      .selectAll("g")
      .data(simNodes)
      .join("g")
      .attr("class", "node-group")
      .style("cursor", "pointer")
      .style("transition", "opacity 0.3s ease")
      .attr("opacity", (d) => {
        if (!focusActive) return 1;
        return visibleNodeIds.has(d.id) ? 1 : 0.12;
      })
      .on("click", (_event, d) => {
        onSelectNode?.(d.id);
      })
      .on("dblclick", (_event, d) => {
        // Double click: pin node
        if (d.fx != null) {
          d.fx = null;
          d.fy = null;
        } else {
          d.fx = d.x;
          d.fy = d.y;
        }
        onDoubleClickNode?.(d.id);
      })
      .on("mouseenter", function (_event, d) {
        // Get screen position
        const svgRect = svg.getBoundingClientRect();
        const nodeX = d.x || 0;
        const nodeY = d.y || 0;
        onHoverNode?.({
          id: d.id,
          label: d.label,
          kind: d.kind,
          risk: d.risk,
          degree: d.degree,
          x: nodeX,
          y: nodeY,
        });
      })
      .on("mouseleave", () => {
        onHoverNode?.(null);
      });

    /* Selection ring (pulsing glow for selected) */
    nodeGroup
      .append("circle")
      .attr("class", "selection-ring")
      .attr("r", (d) => 14 + (d.degree * 1.2) + 10)
      .attr("fill", "none")
      .attr("stroke", (d) => riskColor(d.risk))
      .attr("stroke-opacity", 0)
      .attr("stroke-width", 2)
      .attr("stroke-dasharray", "4 3");

    /* Node circle */
    nodeGroup
      .append("circle")
      .attr("class", "node-circle")
      .attr("r", (d) => 10 + d.degree * 1.2)
      .attr("fill", (d) => riskColor(d.risk))
      .attr("fill-opacity", 0.18)
      .attr("stroke", (d) => riskColor(d.risk))
      .attr("stroke-width", 1.5)
      .style("transition", "r 0.3s ease, fill-opacity 0.3s ease, stroke-width 0.3s ease");

    /* Glyph */
    nodeGroup
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("font-size", 12)
      .attr("fill", (d) => riskColor(d.risk))
      .attr("font-family", "IBM Plex Mono")
      .text((d) => kindGlyph(d.kind));

    /* Label below node — visibility controlled by zoom level */
    nodeGroup
      .append("text")
      .attr("class", "node-label")
      .attr("text-anchor", "middle")
      .attr("dy", (d) => 10 + d.degree * 1.2 + 14)
      .attr("font-size", 10)
      .attr("fill", "var(--foreground)")
      .attr("fill-opacity", 0)
      .attr("font-family", "IBM Plex Sans")
      .text((d) => (d.label || "").slice(0, 18))
      .style("transition", "fill-opacity 0.2s ease");

    /* ── Drag behavior — gentle physics ───────────── */
    const dragBehavior = drag<SVGGElement, SimNode>()
      .on("start", (event, d) => {
        if (!event.active) simulation.alphaTarget(0.01).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on("end", (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        // Keep pinned if layout is frozen
        if (!frozenLayout) {
          d.fx = null;
          d.fy = null;
        }
      });

    nodeGroup.call(dragBehavior as any);

    /* ── Force simulation — tuned for minimal disruption ── */
    const simulation = forceSimulation(simNodes)
      .velocityDecay(0.65)
      .force(
        "link",
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(90)
          .strength(0.35)
      )
      .force("charge", forceManyBody().strength(-180 * forceStrength))
      .force("center", forceCenter(width / 2, height / 2).strength(0.05))
      .force("collide", forceCollide<SimNode>().radius((d) => 14 + d.degree * 1.2 + 10).strength(0.6))
      .on("tick", () => {
        linkGroup
          .attr("x1", (d) => (d.source as SimNode).x!)
          .attr("y1", (d) => (d.source as SimNode).y!)
          .attr("x2", (d) => (d.target as SimNode).x!)
          .attr("y2", (d) => (d.target as SimNode).y!);

        nodeGroup.attr("transform", (d) => `translate(${d.x},${d.y})`);
      });

    simulationRef.current = simulation;

    return () => {
      simulation.stop();
    };
  }, [nodes, edges, width, height, onSelectNode, onDoubleClickNode, onHoverNode, degreeMap, edgeThreshold, focusLevel, selectedId, getVisibleData, frozenLayout]);

  /* ── Update force strength ───────────────────────── */
  useEffect(() => {
    if (!simulationRef.current) return;
    simulationRef.current
      .force("charge", forceManyBody().strength(-180 * forceStrength))
      .alpha(0.2)
      .restart();
  }, [forceStrength]);

  /* ── Update selection ring + focus highlighting ──── */
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const root = select(svg);

    // Selection ring animation
    root
      .selectAll<SVGCircleElement, SimNode>(".selection-ring")
      .attr("stroke-opacity", (d) => d?.id === selectedId ? 0.6 : 0)
      .attr("stroke-width", (d) => d?.id === selectedId ? 2.5 : 1.5);

    // Enlarge selected node
    root
      .selectAll<SVGCircleElement, SimNode>(".node-circle")
      .attr("fill-opacity", (d) => d?.id === selectedId ? 0.35 : 0.18)
      .attr("stroke-width", (d) => d?.id === selectedId ? 2.5 : 1.5);

    // Show/hide labels: always show selected, show on hover handled by CSS
    root
      .selectAll<SVGTextElement, SimNode>(".node-label")
      .attr("fill-opacity", (d) => {
        if (d?.id === selectedId) return 1;
        if (currentZoomScale > 1.5) return 0.8;
        return 0;
      });

    // Fade unrelated nodes when something is selected
    if (selectedId) {
      const neighborIds = new Set<string>();
      neighborIds.add(selectedId);
      edges.forEach(e => {
        if (e.from === selectedId) neighborIds.add(e.to);
        if (e.to === selectedId) neighborIds.add(e.from);
      });

      root
        .selectAll<SVGGElement, SimNode>(".node-group")
        .transition()
        .duration(300)
        .attr("opacity", (d: SimNode) => neighborIds.has(d.id) ? 1 : 0.15);

      // Highlight connected edges
      root
        .selectAll<SVGLineElement, SimLink>(".links line")
        .transition()
        .duration(300)
        .attr("stroke-opacity", (d: SimLink) => {
          const src = typeof d.source === "string" ? d.source : (d.source as SimNode).id;
          const tgt = typeof d.target === "string" ? d.target : (d.target as SimNode).id;
          if (src === selectedId || tgt === selectedId) return 0.8;
          return 0.04;
        });
    } else {
      // Reset all opacities
      const maxWeight = Math.max(1, ...edges.map(e => e.weight));
      root
        .selectAll<SVGGElement, SimNode>(".node-group")
        .transition()
        .duration(300)
        .attr("opacity", 1);

      root
        .selectAll<SVGLineElement, SimLink>(".links line")
        .transition()
        .duration(300)
        .attr("stroke-opacity", (d: SimLink) => 0.12 + 0.58 * (d.weight / maxWeight));
    }

    // Fly to selected node
    if (selectedId && zoomBehaviorRef.current) {
      const node = nodesRef.current.find(n => n.id === selectedId);
      if (node && node.x != null && node.y != null) {
        const transform = zoomIdentity
          .translate(width / 2, height / 2)
          .scale(Math.max(currentZoomScale, 1.2))
          .translate(-node.x, -node.y);

        root.transition().duration(600).ease((t: number) => t * (2 - t))
          .call(zoomBehaviorRef.current!.transform, transform);
      }
    }
  }, [selectedId, edges, width, height, currentZoomScale]);

  /* ── Update edge visibility (filter) ────────────── */
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const root = select(svg);
    root
      .selectAll<SVGLineElement, SimLink>(".links line")
      .attr("display", (d) => {
        if (!d) return "none";
        if (edgeFilter === "all") return null;
        return d.kind === edgeFilter || d.kind === "shared_id" ? null : "none";
      });
  }, [edgeFilter]);

  /* ── Pause/resume simulation ────────────────────── */
  useEffect(() => {
    if (!simulationRef.current) return;
    if (isPaused) {
      simulationRef.current.stop();
    } else {
      simulationRef.current.alpha(0.1).restart();
    }
  }, [isPaused]);

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${width} ${height}`}
      className="h-full w-full"
      style={{ background: "transparent" }}
    />
  );
});
