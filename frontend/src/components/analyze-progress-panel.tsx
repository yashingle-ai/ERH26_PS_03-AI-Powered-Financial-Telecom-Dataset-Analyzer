import { Progress } from "@/components/ui/progress";
import {
  AlertTriangle, CheckCircle2, Database, Loader2,
} from "lucide-react";
import type { AnalyzeProgress, AnalyzeStage } from "@/lib/api";
import { formatDuration } from "@/hooks/use-analyze-progress";

/**
 * Shown only until the first progress poll returns; after that the server's own
 * stage list is authoritative (`analyze_progress.STAGES`).
 */
export const FALLBACK_ANALYZE_STAGES: AnalyzeStage[] = [
  { id: "parse", label: "Parsing evidence files", weight: 55 },
  { id: "normalize", label: "Normalising fields & timestamps", weight: 8 },
  { id: "resolve", label: "Resolving entities", weight: 7 },
  { id: "documents", label: "Indexing narrative documents", weight: 5 },
  { id: "timeline", label: "Building timeline & transfers", weight: 5 },
  { id: "correlate", label: "Correlating call / IP / transfers", weight: 8 },
  { id: "detect", label: "Scoring risk & typologies", weight: 7 },
  { id: "graph", label: "Building investigation graph", weight: 4 },
  { id: "persist", label: "Saving durable snapshot", weight: 1 },
];

/** Two or three words for the stepper chip; the full label goes in `title`. */
function shortLabel(label: string): string {
  return label.split(/\s+/).slice(0, 2).join(" ");
}

type Props = {
  running: boolean;
  finished?: boolean;
  progress: AnalyzeProgress | null;
  /** null = nothing finished yet; used for the post-run badge on Upload. */
  servedFromCache?: boolean | null;
  summary?: string | null;
  /** Optional heading override (defaults to "Pipeline"). */
  title?: string;
  className?: string;
};

/**
 * Live pipeline progress: percent, ETA, stage chips, and the server's own
 * message. Shared by Upload (explicit Run) and Overview (auto-analyze on open).
 */
export function AnalyzeProgressPanel({
  running,
  finished = false,
  progress,
  servedFromCache = null,
  summary = null,
  title = "Pipeline",
  className = "mb-6 rounded-lg border border-border bg-surface/60 p-4",
}: Props) {
  const stageList = progress?.stages?.length ? progress.stages : FALLBACK_ANALYZE_STAGES;
  const stageIndex = progress?.stage_index ?? -1;
  const percent = finished ? 100 : (progress?.percent ?? 0);
  const eta = formatDuration(progress?.eta_seconds);
  const elapsed = formatDuration(progress?.elapsed_seconds);
  const fromCache = progress?.from_cache === true;
  const staleSeconds = progress?.stale_seconds ?? null;
  const progressStale = running && staleSeconds != null && staleSeconds >= 15;

  return (
    <div className={className}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {title}
        </div>
        <div className="text-mono flex items-center gap-3 text-[11px] text-muted-foreground">
          {running && stageIndex >= 0 && (
            <span>Stage {stageIndex + 1}/{stageList.length}</span>
          )}
          {running && <span className="text-foreground">{percent.toFixed(1)}%</span>}
          {elapsed && <span title="Elapsed">{elapsed} elapsed</span>}
          {/* ETA only while running: after completion it is 0 and looks pending. */}
          {running && eta && !progressStale && (
            <span title="Estimated time remaining">~{eta} left</span>
          )}
          {progressStale && (
            <span
              title="The API is busy parsing/scoring — progress details pause while work continues. Elapsed still ticks."
              className="text-[color:var(--risk-med)]"
            >
              details paused · pipeline still running
            </span>
          )}
          {!running && !finished && "Idle"}
          {!running && finished && (
            servedFromCache
              ? (
                <span title="Served from a saved analysis — no files were re-parsed"
                      className="flex items-center gap-1 rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 text-[10px] uppercase tracking-widest text-primary">
                  <Database className="h-3 w-3" /> From saved analysis
                </span>
              )
              : (
                <span title="A full pipeline run — every file was parsed"
                      className="rounded border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-widest">
                  Freshly parsed
                </span>
              )
          )}
        </div>
      </div>

      <Progress value={percent} className="mb-2 h-1.5"
                aria-label="Pipeline progress" />

      {/* Server message is what proves a long run is alive, not hung. */}
      <div className="text-mono mb-4 flex min-h-[16px] items-center gap-2 text-[11px]"
           role="status" aria-live="polite">
        {running && <Loader2 className="h-3 w-3 shrink-0 animate-spin text-[color:var(--risk-med)]" />}
        <span className="truncate text-muted-foreground">
          {progress?.message || (running ? "Starting pipeline…" : "")}
        </span>
        {progress?.total ? (
          <span className="shrink-0 text-muted-foreground/70">
            {progress.done ?? 0}/{progress.total}
          </span>
        ) : null}
        {fromCache && (
          <span className="shrink-0 rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 text-[9px] uppercase tracking-widest text-primary">
            cached
          </span>
        )}
      </div>

      <div className="grid grid-cols-3 gap-2 md:grid-cols-9">
        {stageList.map((s, i) => {
          const done = finished || (stageIndex >= 0 && i < stageIndex);
          const active = running && i === stageIndex;
          return (
            <div
              key={s.id}
              title={s.label}
              className={`rounded border px-2 py-2 text-center ${
                done ? "border-primary/40 bg-primary/10 text-primary" :
                active ? "border-[color:var(--risk-med)]/40 bg-[color:var(--risk-med)]/10 text-[color:var(--risk-med)]" :
                "border-border text-muted-foreground"
              }`}
            >
              <div className="mx-auto mb-1 flex h-5 w-5 items-center justify-center">
                {done ? <CheckCircle2 className="h-3.5 w-3.5" /> :
                 active ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> :
                 <AlertTriangle className="h-3.5 w-3.5 opacity-30" />}
              </div>
              <div className="text-mono text-[9px] uppercase tracking-widest">
                {shortLabel(s.label)}
              </div>
            </div>
          );
        })}
      </div>
      {summary && <div className="text-mono mt-4 text-[11px] text-primary">{summary}</div>}
    </div>
  );
}
