import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Input } from "@/components/ui/input";
import type { Entity } from "@/lib/types";
import { RiskBadge, RiskGauge } from "@/components/risk-badge";
import { Search, User, Building2, Phone as PhoneIcon, CreditCard, ArrowUpDown, Clock, Share2, FileText, Pin, Check } from "lucide-react";
import { LoadingState } from "@/components/shared/loading-state";
import { ErrorState } from "@/components/shared/error-state";
import { EntitySkeleton } from "@/components/shared/skeletons";
import { useEffect, useMemo, useState } from "react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { useEntities } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapEntity } from "@/lib/mappers";
import { riskColor, formatLakhs } from "@/lib/constants";

export const Route = createFileRoute("/_app/entities")({
  head: () => ({ meta: [{ title: "Entity explorer — ERakshak" }] }),
  component: EntitiesPage,
  validateSearch: (search: Record<string, unknown>) => ({
    id: (search.id as string) || undefined,
    rule: (search.rule as string) || undefined,
  }),
});

function KindIcon({ kind }: { kind: Entity["kind"] }) {
  const cls = "h-3.5 w-3.5";
  if (kind === "individual") return <User className={cls} />;
  if (kind === "merchant") return <Building2 className={cls} />;
  if (kind === "phone") return <PhoneIcon className={cls} />;
  return <CreditCard className={cls} />;
}

type SortKey = "risk" | "events" | "volume" | "label";
type SortDir = "asc" | "desc";

function EntitiesPage() {
  const { dataset, setPinnedEntity, toggleEvidence, pinnedEvidence, addBreadcrumb } = useInvestigation();
  const { id: selectedIdFromUrl, rule: ruleFilter } = Route.useSearch();
  const navigate = Route.useNavigate();

  const { data, isLoading, error } = useEntities();
  const entities = useMemo(() => (data?.items || []).map(mapEntity), [data]);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Entity | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("risk");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  /* Select entity from URL param on first load */
  useEffect(() => {
    if (selectedIdFromUrl && entities.length) {
      const found = entities.find((e) => e.id === selectedIdFromUrl);
      if (found) {
        setSelected(found);
        setPinnedEntity(found);
        addBreadcrumb({ id: found.id, label: found.label, page: "entities" });
      }
    }
  }, [selectedIdFromUrl, entities, setPinnedEntity, addBreadcrumb]);

  /* Auto-select first entity */
  useEffect(() => {
    if (entities.length && !selected && !selectedIdFromUrl) {
      setSelected(entities[0]);
    }
  }, [entities, selected, selectedIdFromUrl]);

  /* Sorting */
  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("desc"); }
  };

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === "desc" ? " ↓" : " ↑") : "";

  /* Filter & sort list */
  const list = useMemo(() => {
    let filtered = entities;

    // Text search
    if (q) {
      const lower = q.toLowerCase();
      filtered = filtered.filter((e) =>
        (e.label + e.identifiers.map((i) => i.value).join(" ")).toLowerCase().includes(lower)
      );
    }

    // Rule filter
    if (ruleFilter) {
      filtered = filtered.filter((e) => e.flags.includes(ruleFilter));
    }

    // Sort
    return [...filtered].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "risk") cmp = a.risk - b.risk;
      else if (sortKey === "events") cmp = a.events - b.events;
      else if (sortKey === "volume") cmp = a.volume - b.volume;
      else cmp = a.label.localeCompare(b.label);
      return sortDir === "desc" ? -cmp : cmp;
    });
  }, [entities, q, ruleFilter, sortKey, sortDir]);

  if (isLoading) {
    return <EntitySkeleton />;
  }

  if (error) {
    return <ErrorState message={(error as Error).message} />;
  }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`Case · ${(dataset || "").toUpperCase()}`}
        title="Entity explorer"
        description={`${data?.total ?? 0} scored entities from the fusion pipeline.${ruleFilter ? ` Filtered by rule: ${ruleFilter.replace(/_/g, " ")}` : ""}`}
        actions={
          ruleFilter ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate({ search: (prev: any) => ({ ...prev, id: undefined, rule: undefined }) })}
              className="text-mono gap-1.5 text-[11px] uppercase tracking-widest"
            >
              Clear filter
            </Button>
          ) : undefined
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="overflow-hidden rounded-lg border border-border bg-surface/40">
          <div className="border-b border-border px-3 py-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search name, account, phone, UPI, IMEI…"
                className="text-mono h-9 border-transparent bg-transparent pl-8 text-[12px] focus-visible:ring-0"
              />
            </div>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead
                  onClick={() => toggleSort("label")}
                  className="text-mono cursor-pointer select-none text-[10px] uppercase tracking-widest hover:text-foreground"
                >
                  Entity{sortIndicator("label")}
                </TableHead>
                <TableHead className="text-mono text-[10px] uppercase tracking-widest">Primary identifier</TableHead>
                <TableHead
                  onClick={() => toggleSort("events")}
                  className="text-mono cursor-pointer select-none text-right text-[10px] uppercase tracking-widest hover:text-foreground"
                >
                  Txns{sortIndicator("events")}
                </TableHead>
                <TableHead
                  onClick={() => toggleSort("risk")}
                  className="text-mono cursor-pointer select-none text-[10px] uppercase tracking-widest hover:text-foreground"
                >
                  Risk{sortIndicator("risk")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((e) => (
                <TableRow
                  key={e.id}
                  onClick={() => {
                    setSelected(e);
                    setPinnedEntity(e);
                    addBreadcrumb({ id: e.id, label: e.label, page: "entities" });
                  }}
                  data-selected={selected?.id === e.id}
                  className="cursor-pointer border-border data-[selected=true]:bg-primary/10 hover:bg-accent/40"
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded bg-muted text-muted-foreground">
                        <KindIcon kind={e.kind} />
                      </span>
                      <div>
                        <div className="text-sm text-foreground">{e.label}</div>
                        <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">{e.kind}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-mono text-[11px] text-muted-foreground">
                    {e.identifiers[0]?.value || "—"}
                  </TableCell>
                  <TableCell className="text-mono text-right text-[12px]">{e.events}</TableCell>
                  <TableCell><RiskBadge score={e.risk} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {selected && (
          <div className="rounded-lg border border-border bg-surface/40 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Entity · {selected.kind}
                </div>
                <h2 className="mt-1 text-xl font-semibold text-foreground">{selected.label}</h2>
                <div className="text-mono mt-1 text-[11px] text-muted-foreground">
                  {selected.events} txns · {formatLakhs(selected.volume)} volume
                </div>
              </div>
              <RiskGauge score={selected.risk} />
            </div>

            {/* ── Risk Score Breakdown ──────────────────── */}
            <div className="mt-5">
              <div className="text-mono mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">
                Risk score breakdown
              </div>
              <div className="space-y-1.5">
                {/* Stacked bar */}
                <div className="flex h-3 overflow-hidden rounded-full bg-muted/30">
                  <div
                    className="transition-all"
                    style={{
                      width: `${70}%`,
                      backgroundColor: riskColor(selected.risk),
                      opacity: 0.7,
                    }}
                  />
                  <div
                    className="transition-all"
                    style={{
                      width: `${30}%`,
                      backgroundColor: "var(--primary)",
                      opacity: 0.4,
                    }}
                  />
                </div>
                <div className="text-mono flex justify-between text-[10px] text-muted-foreground">
                  <span>Rule score · 70% weight</span>
                  <span>ML anomaly · 30% ({(selected.mlScore * 100).toFixed(0)}%)</span>
                </div>
              </div>
            </div>

            {/* ── Resolved identifiers ─────────────────── */}
            <div className="mt-5">
              <div className="text-mono mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">
                Resolved identifiers
              </div>
              <div className="space-y-1.5">
                {selected.identifiers.map((id) => (
                  <div key={`${id.kind}-${id.value}`} className="flex items-center justify-between rounded border border-border bg-background/50 px-3 py-2">
                    <span className="text-mono text-[10px] uppercase tracking-widest text-primary">{id.kind}</span>
                    <span className="text-mono text-[12px] text-foreground">{id.value}</span>
                  </div>
                ))}
                <div className="text-mono mt-2 text-[10px] italic text-muted-foreground">
                  * IP sessions are retained as evidence, never used as a merge key.
                </div>
              </div>
            </div>

            {/* ── Risk Factors with details ────────────── */}
            <div className="mt-5">
              <div className="text-mono mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">
                Risk factors
              </div>
              <div className="space-y-2">
                {selected.ruleFlags.length === 0 && (
                  <div className="text-sm text-muted-foreground">No rule flags on this entity.</div>
                )}
                {selected.ruleFlags.map((f) => (
                  <div key={f.rule} className="rounded border border-border/60 bg-background/30 px-3 py-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-1.5 rounded-full bg-[color:var(--risk-high)]" />
                        <span className="text-[12px] font-medium text-foreground">{f.rule.replace(/_/g, " ")}</span>
                      </div>
                      <span className="text-mono text-[10px] text-muted-foreground">
                        +{Math.round(f.weight * 100)}
                      </span>
                    </div>
                    {f.detail && (
                      <div className="mt-1 pl-4 text-[11px] text-muted-foreground">{f.detail}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* ── Action buttons with navigation ──────── */}
            <div className="mt-6 flex gap-2">
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => navigate({ to: "/timeline", search: { entity: selected.id } as any })}
              >
                <Clock className="h-3 w-3" /> Timeline
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => navigate({ to: "/network", search: { node: selected.id } as any })}
              >
                <Share2 className="h-3 w-3" /> Graph
              </Button>
              <Button
                size="sm"
                className={`ml-auto gap-1.5 ${pinnedEvidence.includes(selected.id) ? 'bg-primary/20 text-primary border border-primary/40' : 'bg-primary text-primary-foreground hover:opacity-90'}`}
                onClick={() => toggleEvidence(selected.id)}
              >
                {pinnedEvidence.includes(selected.id) ? (
                  <><Check className="h-3 w-3" /> In report</>
                ) : (
                  <><Pin className="h-3 w-3" /> Add to report</>
                )}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
