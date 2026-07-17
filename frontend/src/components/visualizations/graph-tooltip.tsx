import { riskColor, riskBand } from "@/lib/constants";

type GraphTooltipProps = {
  x: number;
  y: number;
  label: string;
  kind: string;
  risk: number;
  degree: number;
  visible: boolean;
};

export function GraphTooltip({ x, y, label, kind, risk, degree, visible }: GraphTooltipProps) {
  if (!visible) return null;

  return (
    <div
      className="pointer-events-none absolute z-30 tooltip-appear"
      style={{
        left: x + 16,
        top: y - 12,
        maxWidth: 220,
      }}
    >
      <div
        className="rounded-lg px-3 py-2.5 shadow-xl"
        style={{
          backgroundColor: "oklch(0.20 0.03 250 / 0.95)",
          border: "1px solid oklch(0.38 0.03 250)",
          backdropFilter: "blur(12px)",
        }}
      >
        <div className="text-[12px] font-medium text-foreground">{label}</div>
        <div className="text-mono mt-1 space-y-0.5 text-[10px]">
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Type</span>
            <span className="uppercase text-foreground/80">{kind}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Risk</span>
            <span style={{ color: riskColor(risk) }}>
              {risk} / {riskBand(risk)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Connections</span>
            <span className="text-foreground/80">{degree}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
