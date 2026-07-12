import { cn } from "@/lib/utils";
import { riskBand } from "@/lib/mock-data";

export function RiskBadge({ score, className }: { score: number; className?: string }) {
  const band = riskBand(score);
  const styles = {
    low: "bg-[color:var(--risk-low)]/15 text-[color:var(--risk-low)] border-[color:var(--risk-low)]/30",
    medium: "bg-[color:var(--risk-med)]/15 text-[color:var(--risk-med)] border-[color:var(--risk-med)]/30",
    high: "bg-[color:var(--risk-high)]/15 text-[color:var(--risk-high)] border-[color:var(--risk-high)]/40",
  }[band];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider text-mono",
        styles,
        className,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {score}
      <span className="opacity-60">/{band}</span>
    </span>
  );
}

export function RiskGauge({ score }: { score: number }) {
  const band = riskBand(score);
  const color =
    band === "high" ? "var(--risk-high)" : band === "medium" ? "var(--risk-med)" : "var(--risk-low)";
  const r = 46;
  const c = 2 * Math.PI * r;
  const off = c - (score / 100) * c;
  return (
    <div className="relative h-32 w-32">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r={r} stroke="var(--border)" strokeWidth="8" fill="none" />
        <circle
          cx="60"
          cy="60"
          r={r}
          stroke={color}
          strokeWidth="8"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={off}
          style={{ transition: "stroke-dashoffset 800ms ease-out" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-mono text-3xl font-semibold" style={{ color }}>
          {score}
        </div>
        <div className="text-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {band} risk
        </div>
      </div>
    </div>
  );
}
