import { useEffect, useRef, useMemo, useCallback } from "react";
import { scaleLinear } from "d3-scale";
import { select } from "d3-selection";
import { zoom as d3Zoom, zoomIdentity, type ZoomTransform, type ZoomBehavior } from "d3-zoom";
import type { Event } from "@/lib/types";

/* ── Types ────────────────────────────────────────────── */

export type CorrelationWindow = { start: number; end: number };

export type TimelineCanvasProps = {
  events: Event[];
  windows?: CorrelationWindow[];
  filters: { txn: boolean; call: boolean; ip: boolean };
  selectedId?: string | null;
  highlightEntity?: string | null;
  onSelectEvent?: (event: Event) => void;
  onHoverEvent?: (event: Event | null, x?: number, y?: number) => void;
  width?: number;
  height?: number;
};

export type TimelineCanvasRef = {
  fitDay: () => void;
  fitWindow: (start: number, end: number) => void;
  jumpToMinute: (minute: number) => void;
};

/* ── Constants ────────────────────────────────────────── */

const TRACK_META = [
  { key: "txn" as const, label: "Transactions", color: "var(--evt-txn)" },
  { key: "call" as const, label: "Calls", color: "var(--evt-call)" },
  { key: "ip" as const, label: "IP Sessions", color: "var(--evt-ip)" },
];

const MARGIN = { top: 28, right: 16, bottom: 24, left: 16 };
const TRACK_HEIGHT = 48;
const TRACK_GAP = 10;
const DOT_RADIUS = 5;

/* ── Component ────────────────────────────────────────── */

export function TimelineCanvas({
  events,
  windows = [],
  filters,
  selectedId,
  highlightEntity,
  onSelectEvent,
  onHoverEvent,
  width = 900,
  height = 280,
}: TimelineCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const transformRef = useRef<ZoomTransform>(zoomIdentity);
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  /* Memoize track contents */
  const tracks = useMemo(() => {
    return TRACK_META.map((meta) => ({
      ...meta,
      events: filters[meta.key] ? events.filter((e) => e.type === meta.key) : [],
    }));
  }, [events, filters]);

  /* Jitter: offset events at the same minute vertically */
  const jitteredEvents = useMemo(() => {
    const buckets = new Map<string, number>();
    return events.map((e) => {
      const bk = `${e.type}-${e.minute}`;
      const count = buckets.get(bk) || 0;
      buckets.set(bk, count + 1);
      return { ...e, jitterY: (count % 3) * 7 - 7 }; // -7, 0, +7
    });
  }, [events]);

  const getJitter = useCallback(
    (e: Event) => jitteredEvents.find((j) => j.id === e.id)?.jitterY || 0,
    [jitteredEvents]
  );

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const innerW = width - MARGIN.left - MARGIN.right;
    const innerH = TRACK_META.length * (TRACK_HEIGHT + TRACK_GAP);

    /* ── Scales ───────────────────────────────────── */
    const xScale = scaleLinear().domain([0, 24 * 60]).range([0, innerW]);

    /* ── Clear & draw ──────────────────────────────── */
    const root = select(svg);
    root.selectAll("*").remove();

    /* Container for zoom */
    const clipId = "timeline-clip";
    root
      .append("defs")
      .append("clipPath")
      .attr("id", clipId)
      .append("rect")
      .attr("width", innerW)
      .attr("height", innerH + MARGIN.top + MARGIN.bottom);

    const container = root
      .append("g")
      .attr("transform", `translate(${MARGIN.left},${MARGIN.top})`)
      .attr("clip-path", `url(#${clipId})`);

    const content = container.append("g").attr("class", "content");

    /* ── Time axis ──────────────────────────────────── */
    const axisG = root
      .append("g")
      .attr("class", "time-axis")
      .attr("transform", `translate(${MARGIN.left},${MARGIN.top - 4})`);

    const drawAxis = (currentXScale: ReturnType<typeof scaleLinear<number>>) => {
      axisG.selectAll("*").remove();
      const [d0, d1] = currentXScale.domain();
      const step = (d1 - d0) < 180 ? 15 : (d1 - d0) < 360 ? 30 : (d1 - d0) < 720 ? 60 : 180;
      for (let m = Math.ceil(d0 / step) * step; m <= d1; m += step) {
        const x = currentXScale(m);
        if (x < 0 || x > innerW) continue;
        const h = Math.floor(m / 60);
        const min = m % 60;
        const label = `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
        axisG
          .append("line")
          .attr("x1", x).attr("x2", x)
          .attr("y1", 0).attr("y2", 4)
          .attr("stroke", "var(--border)")
          .attr("stroke-width", 1);
        axisG
          .append("text")
          .attr("x", x).attr("y", -3)
          .attr("text-anchor", "middle")
          .attr("fill", "var(--muted-foreground)")
          .attr("font-size", 10)
          .attr("font-family", "IBM Plex Mono")
          .text(label);
      }
    };

    drawAxis(xScale);

    /* ── Correlation window bands ──────────────────── */
    const windowG = content.append("g").attr("class", "windows");
    windows.forEach((w) => {
      windowG
        .append("rect")
        .attr("x", xScale(w.start))
        .attr("y", 0)
        .attr("width", Math.max(xScale(w.end) - xScale(w.start), 2))
        .attr("height", innerH)
        .attr("fill", "var(--primary)")
        .attr("opacity", 0.08)
        .attr("rx", 3);
      windowG
        .append("rect")
        .attr("x", xScale(w.start))
        .attr("y", 0)
        .attr("width", Math.max(xScale(w.end) - xScale(w.start), 2))
        .attr("height", innerH)
        .attr("fill", "none")
        .attr("stroke", "var(--primary)")
        .attr("stroke-opacity", 0.25)
        .attr("rx", 3);
    });

    /* ── Tracks ────────────────────────────────────── */
    tracks.forEach((track, ti) => {
      const ty = ti * (TRACK_HEIGHT + TRACK_GAP);

      // Track label
      root
        .append("text")
        .attr("x", MARGIN.left)
        .attr("y", MARGIN.top + ty - 2)
        .attr("fill", track.color)
        .attr("font-size", 10)
        .attr("font-family", "IBM Plex Mono")
        .attr("text-transform", "uppercase")
        .text(track.label);

      // Track background
      content
        .append("rect")
        .attr("x", 0)
        .attr("y", ty)
        .attr("width", innerW)
        .attr("height", TRACK_HEIGHT)
        .attr("rx", 4)
        .attr("fill", "var(--muted)")
        .attr("opacity", 0.1);

      // Centerline
      content
        .append("line")
        .attr("x1", 0).attr("x2", innerW)
        .attr("y1", ty + TRACK_HEIGHT / 2)
        .attr("y2", ty + TRACK_HEIGHT / 2)
        .attr("stroke", "var(--border)")
        .attr("stroke-opacity", 0.4);

      // Event dots
      const dots = content
        .selectAll(`.dot-${track.key}`)
        .data(track.events)
        .join("circle")
        .attr("class", `dot-${track.key}`)
        .attr("cx", (d) => xScale(d.minute))
        .attr("cy", (d) => ty + TRACK_HEIGHT / 2 + getJitter(d))
        .attr("r", DOT_RADIUS)
        .attr("fill", track.color)
        .attr("fill-opacity", (d) => {
          // Entity highlighting
          if (highlightEntity && d.entity !== highlightEntity) return 0.12;
          return 0.7;
        })
        .attr("stroke", (d) => {
          if (highlightEntity && d.entity === highlightEntity) return "var(--primary)";
          return "var(--background)";
        })
        .attr("stroke-width", (d) => {
          if (highlightEntity && d.entity === highlightEntity) return 2;
          return 1.5;
        })
        .style("cursor", "pointer")
        .style("transition", "fill-opacity 0.2s ease, r 0.15s ease")
        .on("click", (_event, d) => {
          onSelectEvent?.(d);
        })
        .on("mouseenter", function (_event, d) {
          select(this).attr("r", DOT_RADIUS + 2);
          const rect = svg.getBoundingClientRect();
          onHoverEvent?.(d, (d.minute / (24 * 60)) * rect.width, rect.height / 2);
        })
        .on("mouseleave", function () {
          select(this).attr("r", DOT_RADIUS);
          onHoverEvent?.(null);
        });

      // Selected dot styling
      dots
        .filter((d) => d.id === selectedId)
        .attr("r", DOT_RADIUS + 3)
        .attr("fill-opacity", 1)
        .attr("stroke", "var(--primary)")
        .attr("stroke-width", 2.5);
    });

    /* ── Zoom + Pan behavior ─────────────────────── */
    const zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([1, 60])
      .translateExtent([[0, 0], [innerW, innerH]])
      .extent([[0, 0], [innerW, innerH]])
      .on("zoom", (event) => {
        transformRef.current = event.transform;
        const newX = event.transform.rescaleX(xScale);

        // Update dot positions
        tracks.forEach((track, ti) => {
          const ty = ti * (TRACK_HEIGHT + TRACK_GAP);
          content
            .selectAll<SVGCircleElement, Event>(`.dot-${track.key}`)
            .attr("cx", (d) => newX(d.minute));
        });

        // Update window bands
        windowG.selectAll<SVGRectElement, unknown>("rect").each(function (_, i) {
          const wIdx = Math.floor(i / 2);
          const w = windows[wIdx];
          if (!w) return;
          select(this)
            .attr("x", newX(w.start))
            .attr("width", Math.max(newX(w.end) - newX(w.start), 2));
        });

        // Redraw axis
        drawAxis(newX);
      });

    zoomBehaviorRef.current = zoomBehavior;
    root.call(zoomBehavior);

    // Apply saved transform
    if (transformRef.current !== zoomIdentity) {
      root.call(zoomBehavior.transform, transformRef.current);
    }

    return () => {
      root.on(".zoom", null);
    };
  }, [events, tracks, windows, selectedId, highlightEntity, onSelectEvent, onHoverEvent, width, height, getJitter]);

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${width} ${height}`}
      className="h-full w-full"
      style={{ background: "transparent", cursor: "grab" }}
    />
  );
}
