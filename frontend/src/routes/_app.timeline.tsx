import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import type { Event as Ev } from "@/lib/types";
import { useMemo, useState } from "react";
import { ArrowRightLeft, Globe, PhoneCall, Filter, X, Clock, Crosshair, Maximize2 } from "lucide-react";
import { LoadingState } from "@/components/shared/loading-state";
import { ErrorState } from "@/components/shared/error-state";
import { TimelineSkeleton } from "@/components/shared/skeletons";
import { EmptyState } from "@/components/shared/empty-state";
import { useAnalyze, useEvents, useEntities } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapEvent, mapEntity } from "@/lib/mappers";
import { TimelineCanvas, type CorrelationWindow } from "@/components/visualizations/timeline-canvas";

export const Route = createFileRoute("/_app/timeline")({
  head: () => ({ meta: [{ title: "Unified timeline — ERakshak" }] }),
  component: TimelinePage,
  validateSearch: (search: Record<string, unknown>) => ({
    entity: (search.entity as string) || undefined,
  }),
});

const TRACK_TYPES = [
  { key: "txn" as const, label: "Transactions", color: "var(--evt-txn)", Icon: ArrowRightLeft },
  { key: "call" as const, label: "Calls", color: "var(--evt-call)", Icon: PhoneCall },
  { key: "ip" as const, label: "IP sessions", color: "var(--evt-ip)", Icon: Globe },
] as const;

function TimelinePage() {
  const { dataset, windowMinutes, pinnedEntity, addBreadcrumb, setPinnedEntity } = useInvestigation();
  const { entity: entityFilter } = Route.useSearch();
  const navigate = Route.useNavigate();

  const { data, isLoading, error } = useEvents();
  const { data: analyze } = useAnalyze();
  const { data: entitiesData } = useEntities();

  const allEvents = useMemo(() => (data?.items || []).map(mapEvent), [data]);
  const entities = useMemo(() => (entitiesData?.items || []).map(mapEntity), [entitiesData]);

  /* Per-entity filtering */
  const filteredEntityLabel = useMemo(() => {
    if (!entityFilter) return null;
    return entities.find((e) => e.id === entityFilter)?.label || entityFilter;
  }, [entityFilter, entities]);

  const events = useMemo(() => {
    if (!entityFilter) return allEvents;
    return allEvents.filter((e) => e.entity === filteredEntityLabel || e.id.includes(entityFilter));
  }, [allEvents, entityFilter, filteredEntityLabel]);

  const [selected, setSelected] = useState<Ev | null>(null);
  const [filters, setFilters] = useState({ txn: true, call: true, ip: true });
  const [hoveredEvent, setHoveredEvent] = useState<Ev | null>(null);

  // Determine highlight entity: from URL filter or from pinned entity
  const highlightEntityLabel = useMemo(() => {
    if (entityFilter && filteredEntityLabel) return filteredEntityLabel;
    return null;
  }, [entityFilter, filteredEntityLabel]);

  const windows: CorrelationWindow[] = useMemo(() => {
    return (analyze?.correlation_hits || []).slice(0, 12).map((h) => {
      const t = h.transaction?.time ? new Date(h.transaction.time) : null;
      const minute = t ? t.getHours() * 60 + t.getMinutes() : 0;
      return { start: Math.max(0, minute - windowMinutes), end: Math.min(24 * 60, minute + windowMinutes) };
    });
  }, [analyze, windowMinutes]);

  const active = selected || events[0] || null;

  const handleSelectEvent = (ev: Ev) => {
    setSelected(ev);
    // Add to breadcrumb trail
    addBreadcrumb({ id: ev.entity, label: ev.entity, page: "timeline" });
  };

  if (isLoading) {
    return <TimelineSkeleton />;
  }

  if (error) {
    return <ErrorState message={(error as Error).message} />;
  }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`Case · ${(dataset || "").toUpperCase()} · Asia/Kolkata`}
        title="Unified timeline"
        description={`Showing ${events.length} of ${data?.total ?? 0} events. Scroll to zoom, drag to pan. Highlighted bands mark correlation windows (W = ${windowMinutes}m).`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* Entity filter indicator */}
            {entityFilter && (
              <div className="text-mono flex items-center gap-1.5 rounded border border-primary/40 bg-primary/10 px-2.5 py-1.5 text-[11px] text-primary">
                <Filter className="h-3 w-3" />
                {filteredEntityLabel}
                <button
                  onClick={() => navigate({ search: { entity: undefined } })}
                  className="ml-1 rounded-full p-0.5 hover:bg-primary/20"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}

            {/* Entity selector */}
            {!entityFilter && entities.length > 0 && (
              <select
                className="text-mono h-8 rounded border border-border bg-surface px-2 text-[11px] text-foreground"
                value=""
                onChange={(e) => {
                  if (e.target.value) {
                    navigate({ search: { entity: e.target.value } });
                    const ent = entities.find(en => en.id === e.target.value);
                    if (ent) {
                      setPinnedEntity(ent);
                      addBreadcrumb({ id: ent.id, label: ent.label, page: "timeline" });
                    }
                  }
                }}
              >
                <option value="">All entities</option>
                {entities.slice(0, 30).map((ent) => (
                  <option key={ent.id} value={ent.id}>{ent.label} ({ent.risk})</option>
                ))}
              </select>
            )}

            {/* Track toggles */}
            {TRACK_TYPES.map((t) => {
              const on = filters[t.key];
              return (
                <Button
                  key={t.key}
                  size="sm"
                  variant={on ? "secondary" : "ghost"}
                  onClick={() => setFilters((f) => ({ ...f, [t.key]: !on }))}
                  className="text-mono gap-1.5 text-[11px] uppercase tracking-widest"
                >
                  <t.Icon className="h-3 w-3" style={{ color: t.color }} /> {t.label}
                </Button>
              );
            })}

            {/* Jump to first correlation hit */}
            {windows.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                className="text-mono gap-1 text-[10px] uppercase tracking-widest"
                onClick={() => {
                  // Find the first correlation hit event
                  const firstWindow = windows[0];
                  if (firstWindow) {
                    const hitEvent = events.find(e => e.minute >= firstWindow.start && e.minute <= firstWindow.end);
                    if (hitEvent) handleSelectEvent(hitEvent);
                  }
                }}
              >
                <Crosshair className="h-3 w-3" /> Jump to Hit
              </Button>
            )}
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="relative h-[300px] overflow-hidden rounded-lg border border-border bg-surface/40 p-2">
          {events.length === 0 ? (
            <EmptyState
              title="No events"
              description={entityFilter ? "No events found for the selected entity." : "No events in this dataset."}
            />
          ) : (
            <>
              <TimelineCanvas
                events={events}
                windows={windows}
                filters={filters}
                selectedId={active?.id}
                highlightEntity={highlightEntityLabel}
                onSelectEvent={handleSelectEvent}
                onHoverEvent={(ev) => setHoveredEvent(ev)}
                height={300}
              />

              {/* Hover preview tooltip */}
              {hoveredEvent && (
                <div
                  className="pointer-events-none absolute z-20 rounded-lg px-3 py-2 shadow-xl tooltip-appear"
                  style={{
                    left: Math.min((hoveredEvent.minute / (24 * 60)) * 100, 80) + "%",
                    bottom: 12,
                    backgroundColor: "var(--overlay-bg)",
                    border: "1px solid var(--overlay-border)",
                    backdropFilter: "blur(12px)",
                    maxWidth: 220,
                  }}
                >
                  <div className="text-mono text-[10px] text-primary">{hoveredEvent.ts}</div>
                  <div className="mt-0.5 text-[11px] text-foreground">{hoveredEvent.entity}</div>
                  <div className="text-mono mt-0.5 text-[9px] text-muted-foreground">
                    {hoveredEvent.type === "txn" ? "Transaction" : hoveredEvent.type === "call" ? "Call" : "IP Session"}
                    {hoveredEvent.attrs.amount ? ` · ₹${hoveredEvent.attrs.amount}` : ""}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="rounded-lg border border-border bg-surface/40 p-4">
          <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Event detail</div>
          {!active ? (
            <div className="mt-3 text-sm text-muted-foreground">No events loaded.</div>
          ) : (
            <>
              <div className="mt-2 text-lg font-medium text-foreground">{active.ts}</div>
              <div className="text-mono mt-1 flex items-center gap-2 text-[11px] uppercase tracking-widest">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: active.type === "txn" ? "var(--evt-txn)" : active.type === "call" ? "var(--evt-call)" : "var(--evt-ip)" }}
                />
                <span className="text-muted-foreground">
                  {active.type === "txn" ? "Transaction" : active.type === "call" ? "Call" : "IP Session"} · {active.entity}
                </span>
              </div>
              <div className="text-mono mt-4 space-y-2 text-[11px]">
                {Object.entries(active.attrs).slice(0, 12).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 border-b border-border/60 pb-1.5">
                    <span className="text-muted-foreground">{k}</span>
                    <span className="truncate text-foreground">{String(v)}</span>
                  </div>
                ))}
              </div>
              <div className="text-mono mt-4 rounded border border-border/60 bg-background/40 px-2.5 py-1.5 text-[10px] text-muted-foreground">
                <span className="text-primary/80">Provenance</span> · {active.provenance}
              </div>

              {/* Quick actions */}
              <div className="mt-4 flex gap-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1 gap-1 text-[10px]"
                  onClick={() => {
                    const entity = entities.find(e => e.label === active.entity);
                    if (entity) {
                      navigate({ search: { entity: entity.id } } as any);
                      setPinnedEntity(entity);
                    }
                  }}
                >
                  <Filter className="h-3 w-3" /> Filter Entity
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
