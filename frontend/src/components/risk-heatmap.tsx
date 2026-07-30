/**
 * FR-18 risk heat map — entities x typologies.
 *
 * The heat map existed only in the Streamlit dashboard, so the React app, which is the
 * primary UI, could not show which typologies drive each risky entity.
 *
 * Rendered as a CSS grid rather than through a charting library: the matrix is small
 * (<=20 rows x ~8 rules), every cell needs a readable number and a tooltip anyway, and a
 * grid stays keyboard- and screen-reader-navigable. It also avoids adding a dependency for
 * one view.
 *
 * The empty state distinguishes "no rule fired on any entity" from "no entities scored".
 * A blank grid that reads as "assessed and clean" is the same failure the reject report
 * exists to prevent: a rule that never ran must not look like a rule that found nothing.
 */
import { useRiskHeatmap } from "@/hooks/use-investigation-data";

const RULE_LABELS: Record<string, string> = {
  structuring: "Structuring",
  rapid_in_out: "Rapid in/out",
  mule_account: "Mule account",
  layering: "Layering",
  circular_flow: "Circular flow",
  call_transfer_coincidence: "Call+transfer",
  comm_burst: "Comm burst",
  dormant_activation: "Dormant activation",
};

const prettyRule = (r: string) =>
  RULE_LABELS[r] ?? r.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** 0 stays transparent so "did not fire" is visually absent, not a pale shade of "fired". */
function cellStyle(value: number, max: number): React.CSSProperties {
  if (value <= 0) return { background: "transparent", color: "var(--muted-foreground)" };
  const intensity = max > 0 ? value / max : 0;
  return {
    background: `color-mix(in srgb, var(--risk-high) ${Math.round(20 + intensity * 70)}%, transparent)`,
    color: intensity > 0.55 ? "white" : "inherit",
    fontWeight: 600,
  };
}

const bandColor = (b: string) =>
  b === "high" ? "var(--risk-high)" : b === "medium" ? "var(--risk-med)" : "var(--risk-low)";

export function RiskHeatmap({ top = 20 }: { top?: number }) {
  const { data, isLoading, error } = useRiskHeatmap(undefined, top);

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading risk heat map…</div>;
  }
  if (error) {
    return (
      <div className="text-sm text-destructive">
        Could not load the risk heat map: {(error as Error).message}
      </div>
    );
  }
  if (!data) return null;

  const { columns, entities, matrix, rules_evaluated, entities_scored } = data;

  if (!entities.length) {
    return (
      <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">No typology fired on any entity.</p>
        <p className="mt-1">
          {entities_scored.toLocaleString()} entities were scored against{" "}
          {rules_evaluated.length} rule{rules_evaluated.length === 1 ? "" : "s"}
          {rules_evaluated.length ? ` (${rules_evaluated.map(prettyRule).join(", ")})` : ""}.
          An empty grid here means nothing matched — not that nothing was checked.
        </p>
      </div>
    );
  }

  const max = Math.max(...matrix.flat(), 0);

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <caption className="sr-only">
            Risk heat map: {entities.length} entities by {columns.length} typologies, cell
            values are {data.unit}
          </caption>
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 z-10 bg-background p-2 text-left font-medium">
                Entity
              </th>
              <th scope="col" className="p-2 text-right font-medium">Score</th>
              {columns.map((c) => (
                <th key={c} scope="col" className="p-2 text-center font-medium whitespace-nowrap">
                  {prettyRule(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entities.map((e, i) => (
              <tr key={e.entity_id ?? i} className="border-t">
                <th scope="row" className="sticky left-0 z-10 bg-background p-2 text-left font-normal">
                  <span
                    className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle"
                    style={{ background: bandColor(e.band) }}
                    aria-hidden="true"
                  />
                  <span title={e.entity_id ?? undefined}>{e.label ?? e.entity_id ?? "—"}</span>
                  <span className="sr-only"> — {e.band} risk</span>
                </th>
                <td className="p-2 text-right tabular-nums">{e.risk_score}</td>
                {matrix[i].map((v, j) => (
                  <td
                    key={columns[j]}
                    className="p-2 text-center tabular-nums"
                    style={cellStyle(v, max)}
                    title={
                      v > 0
                        ? `${e.label ?? e.entity_id}: ${prettyRule(columns[j])} weight ${v}`
                        : `${prettyRule(columns[j])} did not fire`
                    }
                  >
                    {v > 0 ? v : "·"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Cell value is {data.unit}. {data.entities_with_a_fired_rule.toLocaleString()} of{" "}
        {entities_scored.toLocaleString()} scored entities had at least one typology fire;
        showing the top {entities.length} by risk score.
      </p>
    </div>
  );
}
