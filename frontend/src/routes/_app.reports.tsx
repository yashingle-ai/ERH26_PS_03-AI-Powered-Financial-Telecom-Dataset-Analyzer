import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { Download, FileText, Printer, Loader2 } from "lucide-react";
import { LoadingState } from "@/components/shared/loading-state";
import { ErrorState } from "@/components/shared/error-state";
import { toast } from "sonner";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { useAnalyze } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapCaseFromAnalyze, mapEntity, mapHit } from "@/lib/mappers";

export const Route = createFileRoute("/_app/reports")({
  head: () => ({ meta: [{ title: "Reports — ERakshak" }] }),
  component: ReportsPage,
});

/**
 * Save a fetched blob to disk.
 *
 * The object URL is revoked on the next tick rather than immediately: Firefox
 * cancels an in-flight download if the URL is revoked before the click is
 * processed.
 */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function ReportsPage() {
  const { dataset, windowMinutes } = useInvestigation();
  const { data, isLoading, error } = useAnalyze();
  const [exporting, setExporting] = useState<"pdf" | "docx" | null>(null);

  const exportReport = useCallback(async (fmt: "pdf" | "docx") => {
    const ds = dataset || data?.dataset;
    if (!ds) {
      toast.error("No active dataset");
      return;
    }
    setExporting(fmt);
    toast.message(`Generating ${fmt.toUpperCase()} report…`, {
      description: "The generator re-reads the full investigation; this takes a moment.",
    });
    try {
      const blob = await api.report(ds, fmt, windowMinutes);
      const stamp = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `erakshak-${ds}-w${windowMinutes}-${stamp}.${fmt}`);
      toast.success(`${fmt.toUpperCase()} report downloaded`, { description: ds });
    } catch (e) {
      toast.error((e as Error).message || `Could not generate the ${fmt} report`);
    } finally {
      setExporting(null);
    }
  }, [dataset, data?.dataset, windowMinutes]);

  if (isLoading) {
    return <LoadingState message="Preparing report preview…" />;
  }

  if (error || !data) {
    return <ErrorState message={(error as Error)?.message || "No analysis data"} />;
  }

  const c = mapCaseFromAnalyze(dataset || data.dataset, data);
  const top = data.top_risk.map(mapEntity).slice(0, 5);
  const hits = data.correlation_hits.slice(0, 5).map(mapHit);

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`${c.code} · Report drafts`}
        title="Reports"
        description="Preview from live analyze results. Export generates the full forensic report server-side, including the STR draft and the detection audit."
        actions={
          <>
            <Button variant="outline" size="sm" className="no-print gap-2"
                    onClick={() => window.print()} disabled={exporting !== null}
                    title="Print this preview from the browser">
              <Printer className="h-3.5 w-3.5" /> Print preview
            </Button>
            <Button variant="outline" size="sm" className="no-print gap-2"
                    onClick={() => exportReport("docx")} disabled={exporting !== null}
                    title="Full forensic report as a Word document">
              {exporting === "docx"
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <FileText className="h-3.5 w-3.5" />}
              Export DOCX
            </Button>
            <Button size="sm" className="no-print gap-2 bg-primary text-primary-foreground hover:opacity-90"
                    onClick={() => exportReport("pdf")} disabled={exporting !== null}
                    title="Full forensic report as a PDF, generated server-side">
              {exporting === "pdf"
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Download className="h-3.5 w-3.5" />}
              Export PDF
            </Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="print-container rounded-lg border border-border bg-[oklch(0.94_0.01_240)] p-8 text-[oklch(0.18_0.02_250)] shadow-2xl">
          <div className="mb-6 flex items-start justify-between border-b border-[oklch(0.85_0.01_240)] pb-4">
            <div>
              <div className="text-mono text-[9px] uppercase tracking-[0.3em] text-[oklch(0.45_0.02_250)]">
                Confidential · Evidentiary
              </div>
              <h2 className="mt-1 text-xl font-semibold">Forensic Investigation Report</h2>
              <div className="text-mono mt-1 text-[11px]">{c.code} · {c.title}</div>
            </div>
            <div className="text-right">
              <div className="text-mono text-[10px] uppercase tracking-widest text-[oklch(0.45_0.02_250)]">ERakshak</div>
              <div className="text-mono text-[10px]">API · W={windowMinutes}m</div>
            </div>
          </div>

          <section className="mb-5">
            <h3 className="text-mono mb-1.5 text-[10px] uppercase tracking-[0.25em] text-[oklch(0.45_0.02_250)]">
              1 · Case narrative
            </h3>
            <p className="text-[12.5px] leading-relaxed">
              ERakshak fused {c.files.bank} bank statements, {c.files.cdr} CDR extracts, and{" "}
              {c.files.ipdr} IPDR extracts covering {c.entities} resolved entities and{" "}
              {c.events.toLocaleString("en-IN")} events. Detected{" "}
              <b>{c.hits} call → transfer coincidences</b> within a {windowMinutes}-minute window.
            </p>
          </section>

          <section className="mb-5">
            <h3 className="text-mono mb-1.5 text-[10px] uppercase tracking-[0.25em] text-[oklch(0.45_0.02_250)]">
              2 · Top entities
            </h3>
            <table className="w-full text-[11.5px]">
              <thead>
                <tr className="border-b border-[oklch(0.82_0.01_240)] text-mono text-[10px] uppercase tracking-widest text-[oklch(0.45_0.02_250)]">
                  <th className="py-1.5 text-left font-normal">Entity</th>
                  <th className="py-1.5 text-left font-normal">Primary identifier</th>
                  <th className="py-1.5 text-right font-normal">Volume</th>
                  <th className="py-1.5 text-right font-normal">Risk</th>
                </tr>
              </thead>
              <tbody>
                {top.map((e) => (
                  <tr key={e.id} className="border-b border-[oklch(0.9_0.005_240)]">
                    <td className="py-1.5">{e.label}</td>
                    <td className="py-1.5 font-mono text-[10px]">{e.identifiers[0]?.value || "—"}</td>
                    <td className="py-1.5 text-right">₹ {(e.volume / 100000).toFixed(1)}L</td>
                    <td className="py-1.5 text-right font-mono">{e.risk}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h3 className="text-mono mb-1.5 text-[10px] uppercase tracking-[0.25em] text-[oklch(0.45_0.02_250)]">
              3 · Correlation hits
            </h3>
            <ul className="space-y-1.5 text-[12px]">
              {hits.map((h) => (
                <li key={h.id}>
                  <span className="font-mono text-[10px]">{h.window}</span> — {h.entities.join(", ")} (Δ {h.delta})
                </li>
              ))}
              {hits.length === 0 && <li>No correlation hits.</li>}
            </ul>
          </section>
        </div>

        <div className="space-y-3 no-print">
          <div className="rounded-lg border border-border bg-surface/40 p-4 text-sm text-muted-foreground">
            Summary: {data.summary.entities} entities · {data.summary.correlation_hits} hits ·{" "}
            {data.summary.high_risk_entities} high-risk.
          </div>
        </div>
      </div>
    </div>
  );
}
