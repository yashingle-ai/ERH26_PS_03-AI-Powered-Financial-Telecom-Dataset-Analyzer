import React, { useMemo } from "react";
import type { GraphNode, GraphEdge } from "@/lib/types";
import { riskColor } from "@/lib/constants";

type GraphMinimapProps = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId?: string | null;
  onSelectNode?: (id: string) => void;
};

export function GraphMinimap({ nodes, edges, selectedId, onSelectNode }: GraphMinimapProps) {
  // Compute bounds and static positions for thumbnail preview using hash/seeded positions or normalized degree layout
  const previewNodes = useMemo(() => {
    if (!nodes.length) return [];
    // Generate deterministic positions based on node ID hash so thumbnail is stable and representative
    return nodes.map((n, idx) => {
      let hash = 0;
      for (let i = 0; i < n.id.length; i++) {
        hash = (hash << 5) - hash + n.id.charCodeAt(i);
        hash |= 0;
      }
      const angle = (idx / nodes.length) * Math.PI * 2 + (hash % 100) * 0.01;
      const radius = 35 + ((Math.abs(hash) % 40) - 20);
      const cx = 60 + Math.cos(angle) * radius;
      const cy = 60 + Math.sin(angle) * radius;
      return { ...n, cx, cy };
    }, [nodes]);
  }, [nodes]);

  const nodeMap = useMemo(() => new Map(previewNodes.map((n) => [n.id, n])), [previewNodes]);

  if (nodes.length === 0) return null;

  return (
    <div
      className="absolute bottom-3 right-3 z-10 hidden overflow-hidden rounded-lg shadow-xl md:block animate-scale-in"
      style={{
        width: 120,
        height: 120,
        backgroundColor: "oklch(0.18 0.03 250 / 0.92)",
        border: "1px solid oklch(0.32 0.02 250)",
        backdropFilter: "blur(12px)",
      }}
      title="Graph Overview Minimap"
    >
      <div className="text-mono absolute left-1.5 top-1 z-10 text-[8px] uppercase tracking-widest text-muted-foreground/70">
        Minimap
      </div>
      <svg viewBox="0 0 120 120" className="h-full w-full">
        {/* Edges preview */}
        <g opacity={0.3}>
          {edges.slice(0, 40).map((e, i) => {
            const src = nodeMap.get(e.from);
            const tgt = nodeMap.get(e.to);
            if (!src || !tgt) return null;
            return (
              <line
                key={i}
                x1={src.cx}
                y1={src.cy}
                x2={tgt.cx}
                y2={tgt.cy}
                stroke="var(--border)"
                strokeWidth={0.75}
              />
            );
          })}
        </g>
        {/* Nodes preview */}
        <g>
          {previewNodes.map((n) => {
            const isSelected = n.id === selectedId;
            return (
              <circle
                key={n.id}
                cx={n.cx}
                cy={n.cy}
                r={isSelected ? 3.5 : 2}
                fill={riskColor(n.risk)}
                fillOpacity={isSelected ? 1 : 0.6}
                stroke={isSelected ? "var(--foreground)" : "none"}
                strokeWidth={isSelected ? 1 : 0}
                className="cursor-pointer transition-all"
                onClick={() => onSelectNode?.(n.id)}
              />
            );
          })}
        </g>
        {/* Viewport frame indicator */}
        <rect
          x={20}
          y={20}
          width={80}
          height={80}
          rx={4}
          fill="none"
          stroke="var(--primary)"
          strokeOpacity={0.35}
          strokeWidth={1}
          strokeDasharray="3 2"
        />
      </svg>
    </div>
  );
}
