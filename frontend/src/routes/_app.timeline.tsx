import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import type { Event as Ev } from "@/lib/mock-data";
import { useMemo, useState } from "react";
import { ArrowRightLeft, Globe, PhoneCall, Loader2 } from "lucide-react";
import { useAnalyze, useEvents } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapEvent } from "@/lib/mappers";

export const Route = createFileRoute("/_app/timeline")({
  head: () => ({ meta: [{ title: "Unified timeline — ERakshak" }] }),
  component: TimelinePage,
});

const HOURS = Array.from({ length: 25 }, (_, i) => i);
const TRACK_TYPES = [
  { key: "txn", label: "Transactions", color: "var(--evt-txn)", Icon: ArrowRightLeft },
  { key: "call", label: "Calls", color: "var(--evt-call)", Icon: PhoneCall },
  { key: "ip", label: "IP sessions", color: "var(--evt-ip)", Icon: Globe },
] as const;

function TimelinePage() {
  const { dataset, windowMinutes } = useInvestigation();
  const { data, isLoading, error } = useEvents();
  const { data: analyze } = useAnalyze();
  const events = useMemo(() => (data?.items || []).map(mapEvent), [data]);
  const [selected, setSelected] = useState<Ev | null>(null);
  const [filters, setFilters] = useState({ txn: true, call: true, ip: true });

  const windows = useMemo(() => {
    return (analyze?.correlation_hits || []).slice(0, 8).map((h) => {
      const t = h.transaction?.time ? new Date(h.transaction.time) : null;
      const minute = t ? t.getHours() * 60 + t.getMinutes() : 0;
      return { start: Math.max(0, minute - windowMinutes), end: Math.min(24 * 60, minute + windowMinutes) };
    });
  }, [analyze, windowMinutes]);

  const pct = (minute: number) => (minute / (24 * 60)) * 100;
  const active = selected || events[0] || null;

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" /> Loading timeline events…
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
        eyebrow={`Case · ${(dataset || "").toUpperCase()} · Asia/Kolkata`}
        title="Unified timeline"
        description={`Showing ${events.length} of ${data?.total ?? 0} events. Highlighted bands mark correlation windows (W = ${windowMinutes}m).`}
        actions={
          <>
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
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="rounded-lg border border-border bg-surface/40 p-4">
          <div className="relative mb-3 h-6">
            <div className="absolute inset-x-0 top-3 h-px bg-border" />
            {HOURS.map((h) => (
              <div key={h} className="absolute -translate-x-1/2" style={{ left: `${(h / 24) * 100}%`, top: 0 }}>
                <div className="mx-auto h-2 w-px bg-border" />
                {h % 3 === 0 && (
                  <div className="text-mono mt-0.5 text-[10px] text-muted-foreground">
                    {String(h).padStart(2, "0")}:00
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="relative">
            {windows.map((w, i) => (
              <div
                key={i}
                className="absolute top-0 bottom-0 rounded bg-primary/10 ring-1 ring-primary/40"
                style={{ left: `${pct(w.start)}%`, width: `${Math.max(pct(w.end - w.start), 0.4)}%`, zIndex: 0 }}
              />
            ))}

            <div className="relative space-y-6 py-4">
              {TRACK_TYPES.map((track) => (
                <div key={track.key} className="relative">
                  <div className="mb-1 flex items-center gap-2">
                    <track.Icon className="h-3.5 w-3.5" style={{ color: track.color }} />
                    <span className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                      {track.label}
                    </span>
                  </div>
                  <div className="relative h-10 rounded bg-muted/20">
                    <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
                    {filters[track.key] &&
                      events
                        .filter((e) => e.type === track.key)
                        .map((e) => (
                          <button
                            key={e.id}
                            onClick={() => setSelected(e)}
                            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-sm ring-2 ring-background"
                            style={{
                              left: `${pct(e.minute)}%`,
                              backgroundColor: track.color,
                              outline: active?.id === e.id ? "2px solid var(--primary)" : undefined,
                            }}
                            title={`${e.ts} · ${e.entity}`}
                          />
                        ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface/40 p-4">
          <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Event detail</div>
          {!active ? (
            <div className="mt-3 text-sm text-muted-foreground">No events loaded.</div>
          ) : (
            <>
              <div className="mt-2 text-lg font-medium text-foreground">{active.ts}</div>
              <div className="text-mono mt-1 text-[11px] uppercase tracking-widest text-muted-foreground">
                {active.type} · {active.entity}
              </div>
              <div className="text-mono mt-4 space-y-2 text-[11px]">
                {Object.entries(active.attrs).slice(0, 10).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 border-b border-border/60 pb-1.5">
                    <span className="text-muted-foreground">{k}</span>
                    <span className="truncate text-foreground">{String(v)}</span>
                  </div>
                ))}
              </div>
              <div className="text-mono mt-4 text-[10px] text-muted-foreground">
                Provenance · {active.provenance}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
