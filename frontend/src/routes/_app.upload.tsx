import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  UploadCloud, FileSpreadsheet, PhoneCall, Globe, CheckCircle2,
  AlertTriangle, Loader2, X, FileWarning, RotateCw,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { useInvestigation } from "@/lib/investigation-context";
import { api, type UploadFileResult, type UploadKind } from "@/lib/api";
import { useAnalyzeProgress } from "@/hooks/use-analyze-progress";
import { AnalyzeProgressPanel } from "@/components/analyze-progress-panel";
import { useQueryClient } from "@tanstack/react-query";

export const Route = createFileRoute("/_app/upload")({
  head: () => ({ meta: [{ title: "Upload & ingest — ERakshak" }] }),
  component: UploadPage,
});

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
  /**
   * Whether the last completed analyze was served from a saved snapshot.
   * `null` = nothing has run yet. A 130 ms cache hit and a 49-minute run are
   * otherwise indistinguishable, which matters after a code change.
   */
  const [servedFromCache, setServedFromCache] = useState<boolean | null>(null);
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

  const start = useCallback(async (force = false) => {
    const ds = target.trim() || dataset;
    if (!ds) {
      toast.error("No active dataset selected");
      return;
    }
    // A forced run deletes the saved analysis and re-parses the whole case —
    // 11 to 49 minutes on a real FIR folder. A misclick must not be able to do
    // that silently.
    if (force && !window.confirm(
      `Re-run the full pipeline on "${ds}"?\n\n` +
      "This discards the saved analysis and parses every file again. On a real " +
      "case that takes 11–49 minutes. Do this after changing a profile, a " +
      "threshold, or the pipeline itself — otherwise the saved result is fine.",
    )) return;

    setRunning(true);
    setRunningDs(ds);
    setFinished(false);
    setSummary(null);
    setServedFromCache(null);
    toast.message(force ? `Re-running pipeline on ${ds}…` : `Running pipeline on ${ds}…`);
    try {
      const result = await api.analyze(ds, windowMinutes, false, { force });
      setFinished(true);
      setServedFromCache(result.from_cache === true);
      setSummary(
        `${result.summary.events} events · ${result.summary.entities} entities · ${result.summary.correlation_hits} hits`,
      );
      await qc.invalidateQueries();
      toast.success(
        result.from_cache ? "Loaded saved analysis" : "Pipeline complete",
        {
          description: result.from_cache
            ? `${ds} — no files were re-parsed. Use Re-run to force a fresh pass.`
            : `Dataset ${ds}`,
        },
      );
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
          <div className="flex gap-2">
            {/* `() => start()` deliberately, not `start`: an onClick handler is
                called with the MouseEvent, which is truthy and would arrive as
                `force` — silently discarding the saved analysis on every click. */}
            <Button size="sm" onClick={() => start()}
                    disabled={running || uploading || !(target.trim() || dataset)}
                    className="gap-2 bg-primary text-primary-foreground hover:opacity-90">
              <Loader2 className={`h-3.5 w-3.5 ${running ? "animate-spin" : ""}`} />
              {running ? "Running…" : "Run pipeline"}
            </Button>
            <Button size="sm" variant="outline" onClick={() => start(true)}
                    disabled={running || uploading || !(target.trim() || dataset)}
                    title="Discard the saved analysis and parse every file again. Needed after changing a profile, a threshold or the pipeline."
                    className="gap-2">
              <RotateCw className="h-3.5 w-3.5" />
              Re-run
            </Button>
          </div>
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
            <Button size="sm" className="mt-3" onClick={() => start()} disabled={running}>
              Run pipeline on {target.trim() || dataset}
            </Button>
          )}
        </div>
      )}

      <AnalyzeProgressPanel
        running={running}
        finished={finished}
        progress={progress}
        servedFromCache={servedFromCache}
        summary={summary}
      />

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
