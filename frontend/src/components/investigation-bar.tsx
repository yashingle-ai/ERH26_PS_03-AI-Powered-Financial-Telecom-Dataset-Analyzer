import { useInvestigation, type BreadcrumbEntry } from "@/lib/investigation-context";
import { riskColor, riskBand } from "@/lib/constants";
import { useNavigate } from "@tanstack/react-router";
import {
  X, Clock, Share2, ShieldAlert, Pin, ChevronRight, Trash2,
} from "lucide-react";

/* ── Investigation Bar — floating bottom context bar ── */

export function InvestigationBar() {
  const {
    pinnedEntity,
    setPinnedEntity,
    pinnedEvidence,
    breadcrumbs,
    clearBreadcrumbs,
  } = useInvestigation();
  const navigate = useNavigate();

  /* Only show when there's a pinned entity or evidence */
  if (!pinnedEntity && pinnedEvidence.length === 0 && breadcrumbs.length === 0) {
    return null;
  }

  return (
    <div
      className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in duration-300"
      style={{ maxWidth: "min(90vw, 900px)", width: "100%" }}
    >
      <div
        className="flex items-center gap-3 rounded-xl px-4 py-2.5 shadow-2xl backdrop-blur-xl"
        style={{
          backgroundColor: "oklch(0.20 0.03 250 / 0.92)",
          border: "1px solid oklch(0.36 0.03 250)",
          boxShadow: "0 20px 50px -15px rgba(0,0,0,0.5), 0 0 0 1px oklch(0.36 0.03 250 / 0.3)",
        }}
      >
        {/* Pinned entity indicator */}
        {pinnedEntity && (
          <>
            <div className="flex items-center gap-2">
              <Pin className="h-3 w-3 text-primary" />
              <div
                className="flex h-6 w-6 items-center justify-center rounded text-[11px] font-medium"
                style={{
                  backgroundColor: `${riskColor(pinnedEntity.risk)}22`,
                  color: riskColor(pinnedEntity.risk),
                }}
              >
                {pinnedEntity.risk}
              </div>
              <div className="leading-tight">
                <div className="text-[12px] font-medium text-foreground">
                  {pinnedEntity.label}
                </div>
                <div className="text-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                  {pinnedEntity.kind} · {riskBand(pinnedEntity.risk)} risk
                </div>
              </div>
            </div>

            {/* Quick nav actions */}
            <div className="ml-2 flex items-center gap-1">
              <button
                onClick={() => navigate({ to: "/timeline", search: { entity: pinnedEntity.id } as any })}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-primary/15 hover:text-primary"
                title="View on Timeline"
              >
                <Clock className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => navigate({ to: "/network", search: { node: pinnedEntity.id } as any })}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-primary/15 hover:text-primary"
                title="View on Graph"
              >
                <Share2 className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => navigate({ to: "/entities", search: { id: pinnedEntity.id, rule: undefined } as any })}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-primary/15 hover:text-primary"
                title="View Detections"
              >
                <ShieldAlert className="h-3.5 w-3.5" />
              </button>
            </div>

            <div
              className="mx-2 h-5 w-px shrink-0"
              style={{ backgroundColor: "oklch(0.36 0.03 250)" }}
            />
          </>
        )}

        {/* Breadcrumb trail */}
        {breadcrumbs.length > 0 && (
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
            <span className="text-mono shrink-0 text-[9px] uppercase tracking-widest text-muted-foreground/60">
              Trail
            </span>
            {breadcrumbs.slice(-5).map((b, i, arr) => (
              <span key={`${b.id}-${b.timestamp}`} className="flex shrink-0 items-center gap-1">
                <button
                  onClick={() => {
                    if (b.page === "entities") {
                      navigate({ to: "/entities", search: { id: b.id, rule: undefined } as any });
                    } else if (b.page === "network") {
                      navigate({ to: "/network", search: { node: b.id } as any });
                    } else if (b.page === "timeline") {
                      navigate({ to: "/timeline", search: { entity: b.id } as any });
                    }
                  }}
                  className="text-mono rounded px-1.5 py-0.5 text-[10px] text-primary/80 transition-colors hover:bg-primary/15 hover:text-primary"
                >
                  {b.label}
                </button>
                {i < arr.length - 1 && (
                  <ChevronRight className="h-2.5 w-2.5 text-muted-foreground/40" />
                )}
              </span>
            ))}
            <button
              onClick={clearBreadcrumbs}
              className="ml-1 shrink-0 rounded p-1 text-muted-foreground/40 transition-colors hover:text-muted-foreground"
              title="Clear trail"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        )}

        {/* Evidence count */}
        {pinnedEvidence.length > 0 && (
          <>
            <div
              className="mx-2 h-5 w-px shrink-0"
              style={{ backgroundColor: "oklch(0.36 0.03 250)" }}
            />
            <div className="text-mono text-[10px] text-muted-foreground">
              <span className="text-primary">{pinnedEvidence.length}</span> pinned
            </div>
          </>
        )}

        {/* Clear pinned entity */}
        {pinnedEntity && (
          <button
            onClick={() => setPinnedEntity(null)}
            className="ml-auto shrink-0 rounded-md p-1.5 text-muted-foreground/60 transition-colors hover:bg-destructive/15 hover:text-destructive"
            title="Unpin entity"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
