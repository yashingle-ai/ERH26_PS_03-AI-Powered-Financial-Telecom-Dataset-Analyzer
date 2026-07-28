import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { LoadingState } from "@/components/shared/loading-state";
import { ErrorState } from "@/components/shared/error-state";
import { useInvestigation } from "@/lib/investigation-context";
import { api, type DataQualityResponse } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

export const Route = createFileRoute("/_app/quality")({
  head: () => ({
    meta: [
      { title: "Data quality — ERakshak" },
      { name: "description", content: "Per-file ingestion rejects and ledger consistency breaks." },
    ],
  }),
  component: QualityPage,
});

function QualityPage() {
  const { dataset, windowMinutes } = useInvestigation();
  const { data, isLoading, error } = useQuery({
    queryKey: ["data-quality", dataset, windowMinutes],
    queryFn: () => api.dataQuality(dataset!, windowMinutes),
    enabled: !!dataset,
    staleTime: 60_000,
  });

  if (!dataset) {
    return <ErrorState message="Select a dataset from Investigations first." />;
  }
  if (isLoading) return <LoadingState message="Loading data quality…" />;
  if (error || !data) {
    return <ErrorState message={(error as Error)?.message || "No quality data"} />;
  }

  return <QualityBody data={data} dataset={dataset} />;
}

function QualityBody({ data, dataset }: { data: DataQualityResponse; dataset: string }) {
  const rejects = data.rejects || [];
  const bySource = useMemo(() => {
    const map = new Map<string, { rejected: number; rows: number; files: number }>();
    for (const r of rejects) {
      const key = r.source_type || (r.reason?.includes("duplicate") ? "DUP" : "NONE");
      const cur = map.get(key) || { rejected: 0, rows: 0, files: 0 };
      cur.rejected += Number(r.rejected ?? r.rows ?? 0);
      cur.rows += Number(r.rows ?? 0);
      cur.files += 1;
      map.set(key, cur);
    }
    return [...map.entries()].sort((a, b) => b[1].rejected - a[1].rejected);
  }, [rejects]);

  const top = [...rejects].sort(
    (a, b) => Number(b.rejected ?? b.rows ?? 0) - Number(a.rejected ?? a.rows ?? 0),
  );

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow="Ingestion diagnostics · FR-5"
        title="Data quality"
        description={`Rejected rows for ${dataset} — what the investigator thinks was ingested must match what the system holds.`}
      />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {bySource.slice(0, 4).map(([src, v]) => (
          <div key={src} className="rounded-lg border border-border bg-surface/60 p-4">
            <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {src || "unknown"}
            </div>
            <div className="text-mono mt-2 text-2xl font-semibold text-foreground">
              {v.rejected.toLocaleString("en-IN")}
            </div>
            <div className="mt-1 text-[11px] text-muted-foreground">
              rejected · {v.files} file(s)
            </div>
          </div>
        ))}
      </div>

      {(data.balance_breaks?.length ?? 0) > 0 && (
        <div className="mb-6 overflow-hidden rounded-lg border border-border bg-surface/40">
          <div className="border-b border-border px-4 py-2 text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Ledger consistency breaks
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                {Object.keys(data.balance_breaks![0]).map((c) => (
                  <TableHead key={c} className="text-mono text-[10px] uppercase tracking-widest">
                    {c}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.balance_breaks!.map((row, i) => (
                <TableRow key={i} className="border-border">
                  {Object.keys(data.balance_breaks![0]).map((c) => (
                    <TableCell key={c} className="text-mono text-[12px]">
                      {String((row as Record<string, unknown>)[c] ?? "—")}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-border bg-surface/40">
        <div className="border-b border-border px-4 py-2 text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Per-file rejects · {rejects.length} entries
        </div>
        <Table>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Rejected</TableHead>
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Rows</TableHead>
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Source</TableHead>
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Reason</TableHead>
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">File</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {top.map((r, i) => {
              const file = r.file || "";
              const short = file.length > 72 ? `…${file.slice(-72)}` : file;
              return (
                <TableRow key={i} className="border-border">
                  <TableCell className="text-mono text-right">
                    {Number(r.rejected ?? r.rows ?? 0).toLocaleString("en-IN")}
                  </TableCell>
                  <TableCell className="text-mono text-right text-muted-foreground">
                    {Number(r.rows ?? 0).toLocaleString("en-IN")}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-mono text-[10px] uppercase">
                      {r.source_type || "—"}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-sm text-muted-foreground">
                    {r.reason || "—"}
                  </TableCell>
                  <TableCell className="text-mono text-[11px] text-muted-foreground" title={file}>
                    {short}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
