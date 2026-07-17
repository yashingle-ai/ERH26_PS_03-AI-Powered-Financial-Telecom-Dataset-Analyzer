import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { RiskBadge } from "@/components/risk-badge";
import { Plus, Search, Filter, FileSpreadsheet, PhoneCall, Globe, Loader2 } from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useMemo, useState } from "react";
import { useDatasets } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapCaseFromAnalyze } from "@/lib/mappers";
import { useQueries } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const Route = createFileRoute("/_app/investigations")({
  head: () => ({
    meta: [
      { title: "Investigations — ERakshak" },
      { name: "description", content: "Active and archived financial-cybercrime investigations." },
    ],
  }),
  component: InvestigationsPage,
});

function statusChip(status: string) {
  const map: Record<string, string> = {
    ready: "bg-primary/15 text-primary border-primary/30",
    analyzing: "bg-[color:var(--risk-med)]/15 text-[color:var(--risk-med)] border-[color:var(--risk-med)]/30",
    ingested: "bg-muted-foreground/10 text-muted-foreground border-muted-foreground/20",
  };
  return map[status] ?? map.ingested;
}

function InvestigationsPage() {
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [riskFilter, setRiskFilter] = useState<string | null>(null);
  const { setDataset, windowMinutes } = useInvestigation();
  const { data: dsData, isLoading: loadingList, error: listError } = useDatasets();
  const datasets = dsData?.datasets || [];

  const analyses = useQueries({
    queries: datasets.map((ds) => ({
      queryKey: ["analyze", ds, windowMinutes],
      queryFn: () => api.analyze(ds, windowMinutes),
      staleTime: 60_000,
    })),
  });

  const cases = useMemo(() => {
    return datasets.map((ds, i) => {
      const result = analyses[i]?.data;
      if (!result) {
        return {
          id: ds,
          code: ds.toUpperCase(),
          title: `Dataset · ${ds}`,
          status: analyses[i]?.isLoading ? "analyzing" : "ingested",
          files: { bank: 0, cdr: 0, ipdr: 0 },
          entities: 0,
          events: 0,
          hits: 0,
          moneyMoved: 0,
          topRisk: 0,
          updated: analyses[i]?.isError ? "error" : "…",
          lead: "API pipeline",
        } as const;
      }
      return mapCaseFromAnalyze(ds, result);
    });
  }, [datasets, analyses]);

  const list = cases.filter((c) => {
    const matchesQ = (c.title + c.code).toLowerCase().includes(q.toLowerCase());
    const matchesStatus = statusFilter === "all" || c.status.toLowerCase() === statusFilter.toLowerCase();
    const matchesRisk = !riskFilter || (
      riskFilter === "high" ? c.topRisk >= 70 :
      riskFilter === "med" ? (c.topRisk >= 40 && c.topRisk < 70) :
      c.topRisk > 0 && c.topRisk < 40
    );
    return matchesQ && matchesStatus && matchesRisk;
  });

  const highRisk = analyses.reduce((n, a) => n + (a.data?.summary.high_risk_entities || 0), 0);
  const totalEvents = analyses.reduce((n, a) => n + (a.data?.summary.events || 0), 0);

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow="Case registry"
        title="Investigations"
        description="Datasets under datasets/raw/. Open one to run the fusion pipeline via the API."
        actions={
          <>
            <Button variant="outline" size="sm" className="gap-2">
              <Filter className="h-3.5 w-3.5" /> Filter
            </Button>
            <Button asChild size="sm" className="gap-2 bg-primary text-primary-foreground hover:opacity-90">
              <Link to="/upload"><Plus className="h-4 w-4" /> New investigation</Link>
            </Button>
          </>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { label: "Open cases", value: String(datasets.length), trail: "raw datasets" },
          { label: "Events fused", value: totalEvents.toLocaleString("en-IN"), trail: "across analyzed sets" },
          { label: "High-risk entities", value: String(highRisk), trail: "score ≥ 70" },
          { label: "API", value: "live", trail: "JWT · /v1" },
        ].map((k) => (
          <div key={k.label} className="rounded-lg border border-border bg-surface/60 p-4">
            <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {k.label}
            </div>
            <div className="text-mono mt-2 text-2xl font-semibold text-foreground">{k.value}</div>
            <div className="mt-1 text-[11px] text-muted-foreground">{k.trail}</div>
          </div>
        ))}
      </div>

      {(loadingList || listError) && (
        <div className="mb-4 rounded-lg border border-border bg-surface/40 px-4 py-3 text-sm text-muted-foreground">
          {loadingList && <span className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Loading datasets…</span>}
          {listError && <span className="text-[color:var(--risk-high)]">{(listError as Error).message}</span>}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-64">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search dataset name…"
            className="h-9 border-border bg-surface pl-8 text-mono text-[13px]"
          />
        </div>
        {["All", "Ready", "Analyzing", "Ingested"].map((s) => (
          <Button
            key={s}
            variant={statusFilter === s.toLowerCase() || (s === "All" && statusFilter === "all") ? "secondary" : "ghost"}
            size="sm"
            className="text-mono h-9 text-[11px] uppercase tracking-widest"
            onClick={() => setStatusFilter(s.toLowerCase() === "all" ? "all" : s.toLowerCase())}
          >
            {s}
          </Button>
        ))}
        <div className="ml-2 flex items-center gap-1">
          {[
            { label: "Low", c: "var(--risk-low)", k: "low" },
            { label: "Med", c: "var(--risk-med)", k: "med" },
            { label: "High", c: "var(--risk-high)", k: "high" },
          ].map((b) => (
            <Badge
              key={b.label}
              variant="outline"
              className={`text-mono h-7 cursor-pointer rounded border-border text-[10px] uppercase tracking-widest transition-colors ${riskFilter === b.k ? 'bg-primary/10 border-primary/40' : 'bg-transparent hover:bg-accent/30'}`}
              onClick={() => setRiskFilter(riskFilter === b.k ? null : b.k)}
            >
              <span className="mr-1.5 h-1.5 w-1.5 rounded-full" style={{ backgroundColor: b.c }} />
              {b.label}
            </Badge>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface/40">
        <Table>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Case</TableHead>
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Status</TableHead>
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Datasets</TableHead>
              <TableHead className="text-mono text-right text-[10px] uppercase tracking-widest">Entities</TableHead>
              <TableHead className="text-mono text-right text-[10px] uppercase tracking-widest">Events</TableHead>
              <TableHead className="text-mono text-right text-[10px] uppercase tracking-widest">Hits</TableHead>
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Top risk</TableHead>
              <TableHead className="text-mono text-[10px] uppercase tracking-widest">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.map((c) => (
              <TableRow key={c.id} className="border-border hover:bg-accent/40">
                <TableCell>
                  <Link
                    to="/overview"
                    onClick={() => setDataset(c.id)}
                    className="block"
                  >
                    <div className="text-mono text-[11px] text-primary">{c.code}</div>
                    <div className="mt-0.5 line-clamp-1 text-sm text-foreground">{c.title}</div>
                    <div className="text-mono mt-0.5 text-[10px] text-muted-foreground">Lead · {c.lead}</div>
                  </Link>
                </TableCell>
                <TableCell>
                  <span className={`text-mono inline-flex rounded border px-2 py-0.5 text-[10px] uppercase tracking-widest ${statusChip(c.status)}`}>
                    {c.status}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="text-mono flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1"><FileSpreadsheet className="h-3 w-3" />{c.files.bank}</span>
                    <span className="inline-flex items-center gap-1"><PhoneCall className="h-3 w-3" />{c.files.cdr}</span>
                    <span className="inline-flex items-center gap-1"><Globe className="h-3 w-3" />{c.files.ipdr}</span>
                  </div>
                </TableCell>
                <TableCell className="text-mono text-right">{c.entities.toLocaleString("en-IN")}</TableCell>
                <TableCell className="text-mono text-right">{c.events.toLocaleString("en-IN")}</TableCell>
                <TableCell className="text-mono text-right">{c.hits.toLocaleString("en-IN")}</TableCell>
                <TableCell>{c.topRisk > 0 ? <RiskBadge score={c.topRisk} /> : <span className="text-mono text-[11px] text-muted-foreground">—</span>}</TableCell>
                <TableCell className="text-mono text-[11px] text-muted-foreground">{c.updated}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
