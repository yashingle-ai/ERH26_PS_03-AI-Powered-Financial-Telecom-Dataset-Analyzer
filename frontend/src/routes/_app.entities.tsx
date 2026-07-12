import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Input } from "@/components/ui/input";
import type { Entity } from "@/lib/mock-data";
import { RiskBadge, RiskGauge } from "@/components/risk-badge";
import { Search, User, Building2, Phone as PhoneIcon, CreditCard, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { useEntities } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { mapEntity } from "@/lib/mappers";

export const Route = createFileRoute("/_app/entities")({
  head: () => ({ meta: [{ title: "Entity explorer — ERakshak" }] }),
  component: EntitiesPage,
});

function KindIcon({ kind }: { kind: Entity["kind"] }) {
  const cls = "h-3.5 w-3.5";
  if (kind === "individual") return <User className={cls} />;
  if (kind === "merchant") return <Building2 className={cls} />;
  if (kind === "phone") return <PhoneIcon className={cls} />;
  return <CreditCard className={cls} />;
}

function EntitiesPage() {
  const { dataset } = useInvestigation();
  const { data, isLoading, error } = useEntities();
  const entities = useMemo(() => (data?.items || []).map(mapEntity), [data]);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Entity | null>(null);

  useEffect(() => {
    if (entities.length && (!selected || !entities.find((e) => e.id === selected.id))) {
      setSelected(entities[0]);
    }
  }, [entities, selected]);

  const list = entities.filter((e) =>
    (e.label + e.identifiers.map((i) => i.value).join(" ")).toLowerCase().includes(q.toLowerCase())
  );

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" /> Loading entities…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-[color:var(--risk-high)]/40 bg-[color:var(--risk-high)]/10 p-4 text-sm text-[color:var(--risk-high)]">
        {(error as Error).message}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`Case · ${(dataset || "").toUpperCase()}`}
        title="Entity explorer"
        description={`${data?.total ?? 0} scored entities from the fusion pipeline.`}
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
                <TableHead className="text-mono text-[10px] uppercase tracking-widest">Entity</TableHead>
                <TableHead className="text-mono text-[10px] uppercase tracking-widest">Primary identifier</TableHead>
                <TableHead className="text-mono text-right text-[10px] uppercase tracking-widest">Txns</TableHead>
                <TableHead className="text-mono text-[10px] uppercase tracking-widest">Risk</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((e) => (
                <TableRow
                  key={e.id}
                  onClick={() => setSelected(e)}
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
                  {selected.events} txns · ₹ {(selected.volume / 100000).toFixed(1)}L volume
                </div>
              </div>
              <RiskGauge score={selected.risk} />
            </div>

            <div className="mt-6">
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

            <div className="mt-6">
              <div className="text-mono mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">
                Risk factors
              </div>
              <div className="space-y-2">
                {selected.flags.length === 0 && (
                  <div className="text-sm text-muted-foreground">No rule flags on this entity.</div>
                )}
                {selected.flags.map((f) => (
                  <div key={f} className="flex items-center gap-3">
                    <div className="h-1.5 w-1.5 rounded-full bg-[color:var(--risk-high)]" />
                    <div className="flex-1 text-[12px] text-foreground">{f.replace(/_/g, " ")}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-6 flex gap-2">
              <Button size="sm" variant="outline">Open timeline</Button>
              <Button size="sm" variant="outline">Show on graph</Button>
              <Button size="sm" className="ml-auto bg-primary text-primary-foreground hover:opacity-90">
                Add to report
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
