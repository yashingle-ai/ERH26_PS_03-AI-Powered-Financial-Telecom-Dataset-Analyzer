import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/risk-badge";
import {
  Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Area, AreaChart, CartesianGrid,
} from "recharts";
import { ArrowUpRight, Clock, Share2, FileText, TrendingUp, PhoneCall, Globe, ArrowRightLeft } from "lucide-react";
import { LoadingState } from "@/components/shared/loading-state";
import { ErrorState } from "@/components/shared/error-state";
import { OverviewSkeleton } from "@/components/shared/skeletons";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useAnalyze } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapCaseFromAnalyze, mapEntity, mapHit, riskDistributionFrom } from "@/lib/mappers";

export const Route = createFileRoute("/_app/overview")({
  head: () => ({ meta: [{ title: "Case overview — ERakshak" }] }),
  component: OverviewPage,
});

function KPI({ label, value, sub, tone = "default" }: { label: string; value: string; sub?: string; tone?: "default" | "risk" | "primary" }) {
  const color = tone === "risk" ? "text-[color:var(--risk-high)]" : tone === "primary" ? "text-primary" : "text-foreground";
  return (
    <div className="hover-lift rounded-lg border border-border bg-surface/60 p-4">
      <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className={`text-mono mt-2 text-2xl font-semibold ${color}`}>{value}</div>
      {sub && <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function OverviewPage() {
  const { dataset, windowMinutes } = useInvestigation();
  const { data, isLoading, error } = useAnalyze();

  if (isLoading) {
    return <OverviewSkeleton />;
  }

  if (error || !data) {
    return <ErrorState message={(error as Error)?.message || "No analysis data"} />;
  }

  const c = mapCaseFromAnalyze(dataset || data.dataset, data);
  const top = data.top_risk.map(mapEntity).slice(0, 6);
  const correlationHits = data.correlation_hits.slice(0, 8).map(mapHit);
  const riskDistribution = riskDistributionFrom(data.top_risk);
  const moneyFlowSeries = data.money_flow_series.length
    ? data.money_flow_series
    : [{ t: "—", inflow: 0, outflow: 0 }];

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`${c.code} · Ready for review`}
        title={c.title}
        description={`Window W=${windowMinutes}m  ·  Datasets fused: ${c.files.bank} bank · ${c.files.cdr} CDR · ${c.files.ipdr} IPDR`}
        actions={
          <>
            <Button asChild variant="outline" size="sm" className="gap-2">
              <Link to="/timeline" search={{ entity: undefined }}><Clock className="h-3.5 w-3.5" /> Timeline</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="gap-2">
              <Link to="/network"><Share2 className="h-3.5 w-3.5" /> Network</Link>
            </Button>
            <Button asChild size="sm" className="gap-2 bg-primary text-primary-foreground hover:opacity-90">
              <Link to="/reports"><FileText className="h-3.5 w-3.5" /> Export report</Link>
            </Button>
          </>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        <KPI label="Entities" value={c.entities.toLocaleString("en-IN")} sub="resolved" />
        <KPI label="Events" value={c.events.toLocaleString("en-IN")} sub="txn · call · ip" />
        <KPI label="Correlation hits" value={c.hits.toLocaleString("en-IN")} sub={`W = ${windowMinutes}m`} tone="primary" />
        <KPI label="High-risk entities" value={String(data.summary.high_risk_entities)} sub="score ≥ 70" tone="risk" />
        <KPI label="Transfers" value={String(data.summary.transfers)} sub="money-flow edges" />
      </div>

      <div className="mb-6 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="rounded-lg border border-border bg-surface/40 p-4">
          <div className="mb-2 flex items-center justify-between">
            <div>
              <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Money flow · daily</div>
              <div className="mt-1 text-sm text-foreground">Inflow vs outflow across transactions (₹ Cr)</div>
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={moneyFlowSeries}>
                <defs>
                  <linearGradient id="fill-in" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="fill-out" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--risk-med)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="var(--risk-med)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="t" tick={{ fill: "var(--muted-foreground)", fontSize: 11, fontFamily: "IBM Plex Mono" }} axisLine={{ stroke: "var(--border)" }} tickLine={false} />
                <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11, fontFamily: "IBM Plex Mono" }} axisLine={{ stroke: "var(--border)" }} tickLine={false} />
                <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, fontFamily: "IBM Plex Mono" }} />
                <Area type="monotone" dataKey="inflow" stroke="var(--primary)" strokeWidth={2} fill="url(#fill-in)" />
                <Area type="monotone" dataKey="outflow" stroke="var(--risk-med)" strokeWidth={2} fill="url(#fill-out)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface/40 p-4">
          <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Risk distribution</div>
          <div className="mt-1 text-sm text-foreground">Top-scored entities in this response</div>
          <div className="mt-4 h-40">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={riskDistribution} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" horizontal={false} />
                <XAxis type="number" hide />
                <YAxis dataKey="band" type="category" width={130}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 11, fontFamily: "IBM Plex Mono" }}
                  axisLine={{ stroke: "var(--border)" }} tickLine={false} />
                <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, fontFamily: "IBM Plex Mono" }} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} fill="var(--primary)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <div className="overflow-hidden rounded-lg border border-border bg-surface/40">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Top suspicious entities</div>
              <div className="mt-0.5 text-sm text-foreground">Ranked by composite risk score</div>
            </div>
            <Button asChild size="sm" variant="ghost" className="text-mono text-[11px] uppercase tracking-widest text-primary">
              <Link to="/entities" search={{ id: undefined, rule: undefined }}>All entities <ArrowUpRight className="ml-1 h-3 w-3" /></Link>
            </Button>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-mono text-[10px] uppercase tracking-widest">Entity</TableHead>
                <TableHead className="text-mono text-[10px] uppercase tracking-widest">Flags</TableHead>
                <TableHead className="text-mono text-right text-[10px] uppercase tracking-widest">Txns</TableHead>
                <TableHead className="text-mono text-right text-[10px] uppercase tracking-widest">₹ Volume</TableHead>
                <TableHead className="text-mono text-[10px] uppercase tracking-widest">Risk</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {top.map((e) => (
                <TableRow key={e.id} className="border-border hover:bg-accent/40">
                  <TableCell>
                    <Link to="/entities" search={{ id: e.id, rule: undefined }} className="block">
                      <div className="text-sm text-foreground">{e.label}</div>
                      <div className="text-mono mt-0.5 text-[10px] text-muted-foreground">
                        {e.identifiers[0]?.value || e.id}
                      </div>
                    </Link>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {e.flags.slice(0, 3).map((f) => (
                        <span key={f} className="text-mono rounded border border-border bg-background/60 px-1.5 py-0.5 text-[10px] uppercase tracking-widest text-muted-foreground">
                          {f}
                        </span>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-mono text-right text-[12px]">{e.events}</TableCell>
                  <TableCell className="text-mono text-right text-[12px]">
                    {e.volume ? `₹ ${(e.volume / 100000).toFixed(1)}L` : "—"}
                  </TableCell>
                  <TableCell><RiskBadge score={e.risk} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="rounded-lg border border-border bg-surface/40">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">Recent correlation hits</div>
              <div className="mt-0.5 text-sm text-foreground">Call + IP + transfer within W</div>
            </div>
            <TrendingUp className="h-4 w-4 text-primary" />
          </div>
          <ul className="divide-y divide-border">
            {correlationHits.length === 0 && (
              <li className="px-4 py-6 text-sm text-muted-foreground">No correlation hits in this window.</li>
            )}
            {correlationHits.map((h) => (
              <li key={h.id} className="px-4 py-3 hover:bg-accent/40">
                <div className="flex items-center justify-between">
                  <div className="text-mono text-[11px] text-primary">{h.window}</div>
                  <RiskBadge score={h.score} />
                </div>
                <div className="mt-1.5 text-sm text-foreground">{h.entities.join("  ↔  ")}</div>
                <div className="text-mono mt-1.5 flex items-center gap-3 text-[10px] uppercase tracking-widest text-muted-foreground">
                  <span className="inline-flex items-center gap-1"><PhoneCall className="h-3 w-3" />call</span>
                  <span className="inline-flex items-center gap-1"><Globe className="h-3 w-3" />ip</span>
                  <span className="inline-flex items-center gap-1"><ArrowRightLeft className="h-3 w-3" />txn</span>
                  <span className="ml-auto text-primary">Δ {h.delta}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
