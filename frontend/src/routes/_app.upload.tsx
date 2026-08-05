import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  UploadCloud, FileSpreadsheet, PhoneCall, Globe, CheckCircle2,
  AlertTriangle, Loader2, X, FileWarning,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { useInvestigation } from "@/lib/investigation-context";
import { api, type AnalyzeStage, type UploadFileResult, type UploadKind } from "@/lib/api";
import { useAnalyzeProgress, formatDuration } from "@/hooks/use-analyze-progress";
import { useQueryClient } from "@tanstack/react-query";

export const Route = createFileRoute("/_app/upload")({
  head: () => ({ meta: [{ title: "Upload & ingest — ERakshak" }] }),
  component: UploadPage,
});

/**
 * Shown only until the first progress poll returns; after that the server's own
 * stage list is authoritative (`analyze_progress.STAGES`).
 *
 * These are deliberately the *server's* nine stages, not the nine this page used
 * to invent. The old list ("Ingest", "Money-flow", "Report") described a pipeline
 * that does not exist in that order, and nothing tied the two lists together.
 */
const FALLBACK_STAGES: AnalyzeStage[] = [
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

/** Mirrors UPLOAD_EXTENSIONS on the API. Kept in step so the picker does not
 *  offer a type the server will reject. */
const ACCEPT = ".csv,.txt,.xlsx,.xls,.pdf,.docx,.zip";

/** Mirrors FIXTURE_DATASETS on the API — sample data that ships in the repo and
 *  is tracked by git, so uploads into it are refused server-side. */
const FIXTURE_DATASETS = new Set(["demo", "smoke"]);

const KINDS: { id: UploadKind; label: string; hint: string }[] = [
  { id: "bank", label: "Bank", hint: "statements" },
  { id: "cdr", label: "CDR", hint: "call records" },
  { id: "ipdr", label: "IPDR", hint: "IP sessions" },
  { id: "other", label: "Other", hint: "mixed / unsure" },
];

function KindIcon({ kind }: { kind: string }) {
  if (kind === "bank") return <FileSpreadsheet className="h-4 w-4 text-primary" />;
  if (kind === "cdr") return <PhoneCall className="h-4 w-4 text-[color:var(--evt-call)]" />;
  return <Globe className="h-4 w-4 text-[color:var(--evt-ip)]" />;
}

function humanBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function UploadPage() {
  const [drag, setDrag] = useState(false);
  const [queued, setQueued] = useState<File[]>([]);
  const [kind, setKind] = useState<UploadKind>("other");
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadFileResult[] | null>(null);
  const [running, setRunning] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  /** The dataset an analyze is running against — also the progress poll key. */
  const [runningDs, setRunningDs] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const { dataset, setDataset, windowMinutes } = useInvestigation();
  // Do NOT prefill with a sample dataset. Prefilling the active dataset means a
  // drag-and-upload without editing the name writes a real case into `demo` or
  // `smoke` — the two paths under datasets/ that are tracked by git. The API
  // refuses those names outright; leaving the field empty stops the user being
  // led into the error in the first place.
  const [target, setTarget] = useState(
    dataset && !FIXTURE_DATASETS.has(dataset.toLowerCase()) ? dataset : "",
  );
  const inputRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const addFiles = useCallback((list: FileList | null) => {
    if (!list?.length) return;
    const incoming = Array.from(list);
    setQueued((prev) => {
      // De-duplicate by name+size: dropping the same folder twice is easy to do
      // and silently uploading it twice would double-count the evidence.
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const fresh = incoming.filter((f) => !seen.has(`${f.name}:${f.size}`));
      if (fresh.length < incoming.length) {
        toast.message(`Skipped ${incoming.length - fresh.length} duplicate file(s)`);
      }
      return [...prev, ...fresh];
    });
    setResults(null);
  }, []);

  const doUpload = useCallback(async () => {
    const ds = target.trim();
    if (!ds) {
      toast.error("Name the dataset to upload into");
      return;
    }
    if (!queued.length) {
      toast.error("No files selected");
      return;
    }
    setUploading(true);
    setResults(null);
    try {
      const res = await api.upload(ds, queued, kind);
      setResults(res.files);
      setQueued([]);
      if (inputRef.current) inputRef.current.value = "";
      setDataset(ds);                       // make the uploaded case the active one
      await qc.invalidateQueries();
      if (res.rejected > 0) {
        toast.warning(`${res.accepted} stored, ${res.rejected} rejected`, {
          description: "Check the per-file reasons below.",
        });
      } else {
        toast.success(`${res.accepted} file(s) stored`, {
          description: `${humanBytes(res.bytes)} into ${ds}/${kind}`,
        });
      }
    } catch (e) {
      toast.error((e as Error).message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [target, queued, kind, setDataset, qc]);

  const start = useCallback(async () => {
    const ds = target.trim() || dataset;
    if (!ds) {
      toast.error("No active dataset selected");
      return;
    }
    setRunning(true);
    setRunningDs(ds);
    setFinished(false);
    setSummary(null);
    toast.message(`Running pipeline on ${ds}…`);
    try {
      const result = await api.analyze(ds, windowMinutes);
      setFinished(true);
      setSummary(
        `${result.summary.events} events · ${result.summary.entities} entities · ${result.summary.correlation_hits} hits`,
      );
      await qc.invalidateQueries();
      toast.success("Pipeline complete", { description: `Dataset ${ds}` });
    } catch (e) {
      toast.error((e as Error).message || "Pipeline failed");
    } finally {
      // `running` gates the progress poll, so it must clear on the error path too
      // — the previous fake ticker leaked for exactly this reason before it was
      // moved into a `finally`.
      setRunning(false);
    }
  }, [target, dataset, windowMinutes, qc]);

  // Poll only while a run is in flight. Nothing is requested when idle.
  const progress = useAnalyzeProgress(runningDs, windowMinutes, running);

  const stageList = progress?.stages?.length ? progress.stages : FALLBACK_STAGES;
  const stageIndex = progress?.stage_index ?? -1;
  // Before the first poll lands there is no server percent yet; showing 0 while
  // "Running…" is honest, and beats inventing motion.
  const percent = finished ? 100 : (progress?.percent ?? 0);
  const eta = formatDuration(progress?.eta_seconds);
  const elapsed = formatDuration(progress?.elapsed_seconds);
  const fromCache = progress?.from_cache === true;

  const isFixtureTarget = FIXTURE_DATASETS.has(target.trim().toLowerCase());
  const queuedBytes = queued.reduce((a, f) => a + f.size, 0);
  const stored = results?.filter((r) => r.status === "stored").length ?? 0;
  const rejected = results?.filter((r) => r.status === "rejected").length ?? 0;

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`Dataset · ${(target || dataset || "—").toUpperCase()}`}
        title="Upload & ingest datasets"
        description="Drop Bank/CDR/IPDR files here, or point the pipeline at a dataset already on disk."
        actions={
          <Button size="sm" onClick={start} disabled={running || uploading || !(target.trim() || dataset)}
                  className="gap-2 bg-primary text-primary-foreground hover:opacity-90">
            <Loader2 className={`h-3.5 w-3.5 ${running ? "animate-spin" : ""}`} />
            {running ? "Running…" : "Run pipeline"}
          </Button>
        }
      />

      {/* dataset + kind */}
      <div className="mb-4 grid gap-3 md:grid-cols-[1fr_auto]">
        <div>
          <label htmlFor="ds" className="text-mono mb-1 block text-[10px] uppercase tracking-widest text-muted-foreground">
            Dataset (new or existing)
          </label>
          <Input id="ds" value={target} placeholder="e.g. fir-65-2024"
                 onChange={(e) => setTarget(e.target.value)} className="h-9 max-w-sm"
                 aria-invalid={isFixtureTarget || undefined} />
          {isFixtureTarget && (
            <p className="mt-1 max-w-sm text-xs text-[color:var(--risk-high)]">
              <b>{target}</b> is read-only sample data that ships with the repo and is
              tracked by git. Name your case something else so real evidence is never
              written into a tracked folder.
            </p>
          )}
        </div>
        <div>
          <span className="text-mono mb-1 block text-[10px] uppercase tracking-widest text-muted-foreground">
            File kind
          </span>
          <div className="flex gap-1">
            {KINDS.map((k) => (
              <Button key={k.id} size="sm" variant={kind === k.id ? "default" : "outline"}
                      onClick={() => setKind(k.id)} title={k.hint} className="h-9">
                {k.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
        className={`grid-bg mb-4 grid place-items-center rounded-xl border-2 border-dashed p-10 transition-colors ${
          drag ? "border-primary bg-primary/5" : "border-border bg-surface/30"
        }`}
      >
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/15 ring-1 ring-primary/40">
            <UploadCloud className="h-6 w-6 text-primary" />
          </div>
          <div className="text-sm font-medium text-foreground">
            Drop files here, or browse
          </div>
          <div className="text-mono mt-1 text-[11px] uppercase tracking-widest text-muted-foreground">
            csv · txt · xlsx · xls · pdf · docx · zip
          </div>
          <input ref={inputRef} type="file" multiple accept={ACCEPT} className="hidden"
                 onChange={(e) => addFiles(e.target.files)} />
          <div className="mt-4 flex justify-center gap-2">
            <Button size="sm" variant="outline" onClick={() => inputRef.current?.click()} disabled={uploading}>
              Browse files
            </Button>
            <Button size="sm" onClick={doUpload}
                    disabled={uploading || !queued.length || isFixtureTarget} className="gap-2">
              {uploading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {uploading ? "Uploading…" : `Upload ${queued.length || ""}`.trim()}
            </Button>
          </div>
        </div>
      </div>

      {/* queue */}
      {queued.length > 0 && (
        <div className="mb-4 rounded-lg border border-border bg-surface/60 p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Ready to upload · {queued.length} file(s) · {humanBytes(queuedBytes)}
            </div>
            <Button size="sm" variant="ghost" onClick={() => setQueued([])} disabled={uploading}>Clear</Button>
          </div>
          <ul className="max-h-48 space-y-1 overflow-y-auto">
            {queued.map((f, i) => (
              <li key={`${f.name}:${f.size}`} className="flex items-center justify-between rounded border border-border/60 px-2 py-1">
                <span className="truncate text-xs text-foreground">{f.name}</span>
                <span className="flex items-center gap-2">
                  <span className="text-mono text-[10px] text-muted-foreground">{humanBytes(f.size)}</span>
                  <button aria-label={`Remove ${f.name}`} disabled={uploading}
                          onClick={() => setQueued((p) => p.filter((_, j) => j !== i))}
                          className="text-muted-foreground hover:text-foreground">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* per-file outcome — a rejected file is reported, never dropped quietly */}
      {results && (
        <div className="mb-6 rounded-lg border border-border bg-surface/60 p-4">
          <div className="mb-2 text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Result · {stored} stored{rejected ? ` · ${rejected} rejected` : ""}
          </div>
          <ul className="max-h-56 space-y-1 overflow-y-auto">
            {results.map((r) => (
              <li key={r.file} className="flex items-center justify-between rounded border border-border/60 px-2 py-1">
                <span className="flex min-w-0 items-center gap-2">
                  {r.status === "stored"
                    ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" />
                    : <FileWarning className="h-3.5 w-3.5 shrink-0 text-[color:var(--risk-high)]" />}
                  <span className="truncate text-xs text-foreground">{r.file}</span>
                </span>
                <span className="text-mono shrink-0 pl-3 text-[10px] text-muted-foreground">
                  {r.status === "stored" ? humanBytes(r.bytes ?? 0) : r.reason}
                </span>
              </li>
            ))}
          </ul>
          {stored > 0 && (
            <Button size="sm" className="mt-3" onClick={start} disabled={running}>
              Run pipeline on {target.trim() || dataset}
            </Button>
          )}
        </div>
      )}

      <div className="mb-6 rounded-lg border border-border bg-surface/60 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Pipeline
          </div>
          <div className="text-mono flex items-center gap-3 text-[11px] text-muted-foreground">
            {running && stageIndex >= 0 && (
              <span>Stage {stageIndex + 1}/{stageList.length}</span>
            )}
            {running && <span className="text-foreground">{percent.toFixed(1)}%</span>}
            {elapsed && <span title="Elapsed">{elapsed} elapsed</span>}
            {/* An ETA is only shown while running: after completion it is 0 and
                reads as though something is still pending. */}
            {running && eta && <span title="Estimated time remaining">~{eta} left</span>}
            {!running && (finished ? "Complete" : "Idle")}
          </div>
        </div>

        <Progress value={percent} className="mb-2 h-1.5" />

        {/* The server's own message — "Parsing evidence files 812/986" — is the
            only thing that distinguishes a working long run from a hung one. */}
        <div className="text-mono mb-4 flex min-h-[16px] items-center gap-2 text-[11px]">
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

      <div className="rounded-lg border border-border bg-surface/40 p-5">
        <h3 className="mb-4 text-sm font-semibold text-foreground">Data formatting & folder layout</h3>
        <div className="grid gap-6 md:grid-cols-3">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <KindIcon kind="bank" /> Bank Statements
            </div>
            <p className="text-xs text-muted-foreground">
              Stored under <span className="text-mono text-primary">datasets/raw/{target || dataset || "<name>"}/bank/</span>
            </p>
            <ul className="ml-4 list-disc text-xs text-muted-foreground">
              <li>Format: <code>.xlsx</code>, <code>.csv</code> or <code>.pdf</code></li>
              <li>Columns: Date, Amount, Type (Cr/Dr), Narration, Account No</li>
            </ul>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <KindIcon kind="cdr" /> Call Records (CDR)
            </div>
            <p className="text-xs text-muted-foreground">
              Stored under <span className="text-mono text-primary">datasets/raw/{target || dataset || "<name>"}/cdr/</span>
            </p>
            <ul className="ml-4 list-disc text-xs text-muted-foreground">
              <li>Format: <code>.csv</code> or <code>.txt</code></li>
              <li>Columns: Timestamp, Caller IMSI/Phone, Receiver Phone, Duration</li>
            </ul>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <KindIcon kind="ip" /> IP Sessions (IPDR)
            </div>
            <p className="text-xs text-muted-foreground">
              Stored under <span className="text-mono text-primary">datasets/raw/{target || dataset || "<name>"}/ipdr/</span>
            </p>
            <ul className="ml-4 list-disc text-xs text-muted-foreground">
              <li>Format: <code>.csv</code></li>
              <li>Columns: Start Time, Source IP, Destination IP, Protocol, Bytes</li>
            </ul>
          </div>
        </div>
        <div className="mt-5 rounded border border-[color:var(--risk-med)]/30 bg-[color:var(--risk-med)]/5 p-3 text-xs text-muted-foreground">
          <span className="font-semibold text-[color:var(--risk-med)]">Note:</span> The
          kind above only chooses the subfolder — files are identified by their contents,
          so a statement filed under the wrong kind is still read as a statement. ZIPs are
          expanded during ingestion. Existing files are never overwritten; a same-named
          upload is stored alongside with a <code>-1</code> suffix.
        </div>
      </div>
    </div>
  );
}
