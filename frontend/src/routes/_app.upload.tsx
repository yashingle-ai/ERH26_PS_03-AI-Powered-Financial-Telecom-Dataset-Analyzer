import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { UploadCloud, FileSpreadsheet, PhoneCall, Globe, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { useInvestigation } from "@/lib/investigation-context";
import { api } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";

export const Route = createFileRoute("/_app/upload")({
  head: () => ({ meta: [{ title: "Upload & ingest — ERakshak" }] }),
  component: UploadPage,
});

const stages = [
  "Ingest", "Normalize", "Resolve entities", "Timeline", "Correlate",
  "Money-flow", "Detect", "Graph", "Report",
];

function KindIcon({ kind }: { kind: string }) {
  if (kind === "bank") return <FileSpreadsheet className="h-4 w-4 text-primary" />;
  if (kind === "cdr") return <PhoneCall className="h-4 w-4 text-[color:var(--evt-call)]" />;
  return <Globe className="h-4 w-4 text-[color:var(--evt-ip)]" />;
}

function UploadPage() {
  const [drag, setDrag] = useState(false);
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(0);
  const [summary, setSummary] = useState<string | null>(null);
  const { dataset, windowMinutes } = useInvestigation();
  const qc = useQueryClient();

  const start = useCallback(async () => {
    if (!dataset) {
      toast.error("No active dataset selected");
      return;
    }
    setRunning(true);
    setStage(1);
    setSummary(null);
    toast.message(`Running pipeline on ${dataset}…`);
    try {
      const tick = window.setInterval(() => {
        setStage((s) => (s < 8 ? s + 1 : s));
      }, 400);
      const result = await api.analyze(dataset, windowMinutes);
      window.clearInterval(tick);
      setStage(9);
      setSummary(
        `${result.summary.events} events · ${result.summary.entities} entities · ${result.summary.correlation_hits} hits`,
      );
      await qc.invalidateQueries();
      toast.success("Pipeline complete", { description: `Dataset ${dataset}` });
    } catch (e) {
      toast.error((e as Error).message || "Pipeline failed");
      setStage(0);
    } finally {
      setRunning(false);
    }
  }, [dataset, windowMinutes, qc]);

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`Dataset · ${(dataset || "—").toUpperCase()}`}
        title="Upload & ingest datasets"
        description="HTTP upload is not available yet. Place Bank/CDR/IPDR files under datasets/raw/{dataset}, then run the API pipeline."
        actions={
          <Button size="sm" onClick={start} disabled={running || !dataset} className="gap-2 bg-primary text-primary-foreground hover:opacity-90">
            <Loader2 className={`h-3.5 w-3.5 ${running ? "animate-spin" : ""}`} />
            {running ? "Running…" : "Run pipeline"}
          </Button>
        }
      />

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          toast.message("Drop ignored", {
            description: "Copy files into datasets/raw on the server, then click Run pipeline.",
          });
        }}
        className={`grid-bg mb-6 grid place-items-center rounded-xl border-2 border-dashed p-10 transition-colors ${
          drag ? "border-primary bg-primary/5" : "border-border bg-surface/30"
        }`}
      >
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/15 ring-1 ring-primary/40">
            <UploadCloud className="h-6 w-6 text-primary" />
          </div>
          <div className="text-sm font-medium text-foreground">Files are read from disk by the API</div>
          <div className="mt-1 text-mono text-[11px] uppercase tracking-widest text-muted-foreground">
            datasets/raw/{dataset || "<name>"} · Bank · CDR · IPDR
          </div>
          <div className="mt-4 flex justify-center gap-2">
            <Button size="sm" onClick={start} disabled={running || !dataset}>
              Run pipeline on active dataset
            </Button>
          </div>
          {summary && (
            <div className="text-mono mt-4 text-[11px] text-primary">{summary}</div>
          )}
        </div>
      </div>

      <div className="mb-6 rounded-lg border border-border bg-surface/60 p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Pipeline</div>
          <div className="text-mono text-[11px] text-muted-foreground">
            {running ? `Stage ${stage}/9` : stage === 9 ? "Complete" : "Idle"}
          </div>
        </div>
        <Progress value={(stage / 9) * 100} className="mb-4 h-1.5" />
        <div className="grid grid-cols-3 gap-2 md:grid-cols-9">
          {stages.map((s, i) => {
            const done = i < stage;
            const active = i + 1 === stage && running;
            return (
              <div
                key={s}
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
                <div className="text-mono text-[9px] uppercase tracking-widest">{s}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="rounded-lg border border-border bg-surface/40 p-5">
        <h3 className="mb-4 text-sm font-semibold text-foreground">Data formatting & folder layout</h3>
        <div className="grid gap-6 md:grid-cols-3">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <KindIcon kind="bank" /> Bank Statements
            </div>
            <p className="text-xs text-muted-foreground">
              Place under <span className="text-mono text-primary">datasets/raw/{dataset || "<name>"}/bank/</span>
            </p>
            <ul className="ml-4 list-disc text-xs text-muted-foreground">
              <li>Format: <code>.xlsx</code> or <code>.csv</code></li>
              <li>Required columns: Date, Amount, Type (Cr/Dr), Narration, Account No</li>
            </ul>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <KindIcon kind="cdr" /> Call Records (CDR)
            </div>
            <p className="text-xs text-muted-foreground">
              Place under <span className="text-mono text-primary">datasets/raw/{dataset || "<name>"}/cdr/</span>
            </p>
            <ul className="ml-4 list-disc text-xs text-muted-foreground">
              <li>Format: <code>.csv</code> or <code>.txt</code></li>
              <li>Required columns: Timestamp, Caller IMSI/Phone, Receiver Phone, Duration</li>
            </ul>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <KindIcon kind="ip" /> IP Sessions (IPDR)
            </div>
            <p className="text-xs text-muted-foreground">
              Place under <span className="text-mono text-primary">datasets/raw/{dataset || "<name>"}/ipdr/</span>
            </p>
            <ul className="ml-4 list-disc text-xs text-muted-foreground">
              <li>Format: <code>.csv</code></li>
              <li>Required columns: Start Time, Source IP, Destination IP, Protocol, Bytes</li>
            </ul>
          </div>
        </div>
        <div className="mt-5 rounded border border-[color:var(--risk-med)]/30 bg-[color:var(--risk-med)]/5 p-3 text-xs text-muted-foreground">
          <span className="font-semibold text-[color:var(--risk-med)]">Note:</span> The pipeline parses raw files directly from the server disk. Ensure file names don't contain spaces. Once the files are in place, click <b>Run pipeline</b> to begin the ingestion and correlation process.
        </div>
      </div>
    </div>
  );
}
