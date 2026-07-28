import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/case-topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useInvestigation } from "@/lib/investigation-context";
import { api, type NlQueryResponse } from "@/lib/api";
import { Loader2, MessageSquareText, Send } from "lucide-react";
import { useState } from "react";

export const Route = createFileRoute("/_app/ask")({
  head: () => ({
    meta: [
      { title: "Ask — ERakshak" },
      { name: "description", content: "Natural-language questions over the fused investigation." },
    ],
  }),
  component: AskPage,
});

const EXAMPLES = [
  "who did 9702000558 call most often?",
  "transfers over 100000",
  "high risk entities",
  "calls between 2am and 5am",
  "events on 2024-08-01",
];

function AskPage() {
  const { dataset, windowMinutes } = useInvestigation();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NlQueryResponse | null>(null);

  async function run(question: string) {
    const text = question.trim();
    if (!text || !dataset) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.query(dataset, text, windowMinutes);
      setResult(res);
    } catch (e) {
      setResult(null);
      setError((e as Error).message || "Query failed");
    } finally {
      setBusy(false);
    }
  }

  const columns = result?.rows?.length
    ? Object.keys(result.rows[0])
    : [];

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow="Natural-language query · FR-19"
        title="Ask"
        description={
          dataset
            ? `Questions run against ${dataset} (W=${windowMinutes}m). The plan is generated; the answer is composed locally from the result — case rows never leave the machine.`
            : "Select a dataset from Investigations first."
        }
      />

      <form
        className="mb-4 flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          void run(q);
        }}
      >
        <div className="relative flex-1">
          <MessageSquareText className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. who did 9702000558 call most often?"
            className="h-11 border-border bg-surface pl-10 text-[14px]"
            disabled={!dataset || busy}
          />
        </div>
        <Button
          type="submit"
          size="lg"
          className="gap-2 bg-primary text-primary-foreground"
          disabled={!dataset || busy || !q.trim()}
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Ask
        </Button>
      </form>

      <div className="mb-6 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            className="text-mono rounded border border-border bg-surface/50 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            onClick={() => {
              setQ(ex);
              void run(ex);
            }}
            disabled={!dataset || busy}
          >
            {ex}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-[color:var(--risk-high)]/40 bg-[color:var(--risk-high)]/10 px-4 py-3 text-sm text-[color:var(--risk-high)]">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-5">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Answer
              </span>
              <Badge variant="outline" className="text-mono text-[10px] uppercase tracking-widest">
                {result.engine}
              </Badge>
              {result.truncated && (
                <Badge variant="outline" className="text-mono text-[10px] uppercase tracking-widest text-[color:var(--risk-med)]">
                  truncated · {result.matched}/{result.total}
                </Badge>
              )}
            </div>
            <p className="text-lg leading-snug text-foreground">{result.answer}</p>
            {result.explanation && (
              <p className="mt-2 text-sm text-muted-foreground">
                Plan · {result.explanation}
              </p>
            )}
            {result.window && (
              <p className="text-mono mt-2 text-[11px] text-muted-foreground">
                Resolved window · {result.window[0]} → {result.window[1]}
              </p>
            )}
            {result.note && (
              <p className="mt-2 text-sm text-[color:var(--risk-med)]">{result.note}</p>
            )}
          </div>

          {result.spec && (
            <details className="rounded-lg border border-border bg-surface/40 p-4">
              <summary className="text-mono cursor-pointer text-[11px] uppercase tracking-widest text-muted-foreground">
                Audit trail — generated QuerySpec
              </summary>
              <pre className="text-mono mt-3 overflow-x-auto text-[11px] leading-relaxed text-foreground/90">
                {JSON.stringify(result.spec, null, 2)}
              </pre>
            </details>
          )}

          {result.rows && result.rows.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-border bg-surface/40">
              <div className="border-b border-border px-4 py-2 text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Supporting rows · {result.matched}
                {result.total !== result.matched ? ` of ${result.total}` : ""}
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="border-border hover:bg-transparent">
                    {columns.map((c) => (
                      <TableHead key={c} className="text-mono text-[10px] uppercase tracking-widest">
                        {c}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.rows.map((row, i) => (
                    <TableRow key={i} className="border-border">
                      {columns.map((c) => (
                        <TableCell key={c} className="text-mono text-[12px]">
                          {row[c] == null ? "—" : String(row[c])}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
