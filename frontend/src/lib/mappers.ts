import type {
  AnalyzeResponse,
  CorrelationHitDto,
  EventDto,
  GraphPayload,
  RiskEntity,
} from "@/lib/api";
import type { Case, CorrelationHit, Detection, Entity, Event, GraphEdge, GraphNode, Identifier, RiskBand } from "@/lib/mock-data";
import { riskBand } from "@/lib/mock-data";

const ID_KIND_MAP: Record<string, Identifier["kind"]> = {
  ACCOUNT_NO: "ACCOUNT_NO",
  PHONE: "PHONE",
  UPI_ID: "UPI",
  UPI: "UPI",
  IMEI: "IMEI",
  IMSI: "IMSI",
};

export function mapIdentifiers(raw?: { kind: string; value: string }[]): Identifier[] {
  if (!raw?.length) return [];
  return raw
    .map((r) => {
      const kind = ID_KIND_MAP[r.kind];
      if (!kind) return null;
      return { kind, value: r.value } as Identifier;
    })
    .filter(Boolean) as Identifier[];
}

function entityKind(types: string[] | undefined, label: string | null): Entity["kind"] {
  const t = new Set((types || []).map((x) => x.toUpperCase()));
  if (t.has("ACCOUNT_NO") && t.has("PHONE")) return "individual";
  if (t.has("ACCOUNT_NO") && !t.has("PHONE")) return "account";
  if (t.has("PHONE") && !t.has("ACCOUNT_NO")) return "phone";
  if ((label || "").toLowerCase().includes("traders") || (label || "").toLowerCase().includes("llp")) {
    return "merchant";
  }
  return "individual";
}

export function mapEntity(row: RiskEntity): Entity {
  const identifiers = mapIdentifiers(row.identifiers);
  return {
    id: row.entity_id,
    label: row.label || row.entity_id,
    kind: entityKind(row.types, row.label),
    identifiers: identifiers.length
      ? identifiers
      : [{ kind: "ACCOUNT_NO", value: row.entity_id }],
    risk: Number(row.risk_score || 0),
    flags: (row.rule_flags || []).map((f) => f.rule),
    events: Number(row.txn_count ?? row.event_count ?? row.features?.txn_count ?? 0),
    volume: Number(row.volume ?? 0),
  };
}

export function mapCaseFromAnalyze(dataset: string, data: AnalyzeResponse): Case {
  const top = data.top_risk[0]?.risk_score ?? 0;
  const title = dataset === "smoke"
    ? "Smoke dataset — Bank + CDR + IPDR fusion"
    : dataset === "demo"
      ? "Demo dataset — labeled synthetic investigation"
      : `Dataset · ${dataset}`;
  return {
    id: dataset,
    code: dataset.toUpperCase(),
    title,
    status: "ready",
    files: {
      bank: data.file_counts.bank,
      cdr: data.file_counts.cdr,
      ipdr: data.file_counts.ipdr,
    },
    entities: data.summary.entities,
    events: data.summary.events,
    hits: data.summary.correlation_hits,
    moneyMoved: data.top_risk.reduce((sum, r) => sum + Number(r.volume || 0), 0),
    topRisk: Number(top),
    updated: "live",
    lead: "API pipeline",
  };
}

export function mapHit(hit: CorrelationHitDto, index: number): CorrelationHit {
  const txnTime = hit.transaction?.time ? new Date(hit.transaction.time) : null;
  const callTime = hit.call?.time ? new Date(hit.call.time) : null;
  const deltaMs = txnTime && callTime ? Math.abs(txnTime.getTime() - callTime.getTime()) : 0;
  const deltaMin = Math.floor(deltaMs / 60000);
  const deltaSec = Math.floor((deltaMs % 60000) / 1000);
  const windowLabel = txnTime
    ? txnTime.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })
    : `W=${hit.window_minutes}m`;

  return {
    id: `hit-${index}-${hit.entity_id}`,
    window: windowLabel,
    entities: [hit.entity_label || hit.entity_id].filter(Boolean),
    events: ["call", "ip", "txn"],
    delta: `+${deltaMin}m ${deltaSec}s`,
    score: Math.min(99, 70 + Math.round((hit.window_minutes || 10) / 2)),
  };
}

export function mapEvent(ev: EventDto): Event {
  const typeMap: Record<string, Event["type"]> = {
    TRANSACTION: "txn",
    CALL: "call",
    IP_SESSION: "ip",
  };
  const attrs: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(ev.attributes || {})) {
    if (v == null) continue;
    if (typeof v === "string" || typeof v === "number") attrs[k] = v;
    else attrs[k] = String(v);
  }
  if (ev.amount != null) attrs.amount = ev.amount;
  const prov = ev.provenance || {};
  const provenance = [prov.source_file, prov.row != null ? `R${prov.row}` : null]
    .filter(Boolean)
    .join(":");

  let minute = ev.minute ?? 0;
  if (ev.timestamp && (minute == null || Number.isNaN(minute))) {
    const d = new Date(ev.timestamp);
    minute = d.getHours() * 60 + d.getMinutes();
  }

  return {
    id: ev.id,
    type: typeMap[ev.event_type] || "txn",
    ts: ev.timestamp
      ? new Date(ev.timestamp).toLocaleTimeString("en-IN", { hour12: false })
      : "—",
    minute: Number(minute || 0),
    entity: ev.entity_label || ev.entity_id || "unknown",
    attrs,
    provenance: provenance || "—",
  };
}

export function layoutGraph(payload: GraphPayload): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const core = payload.nodes.filter((n) => !n.external).slice(0, 40);
  const ids = new Set(core.map((n) => n.id));
  const n = Math.max(core.length, 1);
  const cx = 560;
  const cy = 260;
  const radius = Math.min(220, 50 + n * 6);

  const nodes: GraphNode[] = core.map((node, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    const types = (node.types || []).map((t) => t.toUpperCase());
    let kind: GraphNode["kind"] = "entity";
    if (types.includes("PHONE") && !types.includes("ACCOUNT_NO")) kind = "phone";
    else if (types.includes("ACCOUNT_NO") && !types.includes("PHONE")) kind = "account";
    return {
      id: node.id,
      label: node.label || node.id,
      kind,
      risk: Number(node.risk || 0),
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  });

  const edges: GraphEdge[] = payload.edges
    .filter((e) => ids.has(e.source) && ids.has(e.target))
    .map((e) => {
      const kind =
        e.kind === "MONEY_FLOW" ? "money" :
        e.kind === "COMMUNICATION" ? "comm" :
        "shared_id";
      return {
        from: e.source,
        to: e.target,
        kind: kind as GraphEdge["kind"],
        weight: Number(e.count || e.amount || 1),
      };
    });

  return { nodes, edges };
}

export function mapDetections(entities: RiskEntity[]): Detection[] {
  const byRule = new Map<string, { weight: number; entities: Set<string>; reasons: string[]; bands: RiskBand[] }>();
  for (const ent of entities) {
    for (const flag of ent.rule_flags || []) {
      const cur = byRule.get(flag.rule) || {
        weight: 0,
        entities: new Set<string>(),
        reasons: [],
        bands: [],
      };
      cur.weight = Math.max(cur.weight, Math.round((flag.weight || 0) * 100));
      cur.entities.add(ent.entity_id);
      if (flag.detail) cur.reasons.push(flag.detail);
      cur.bands.push(ent.band);
      byRule.set(flag.rule, cur);
    }
  }

  return [...byRule.entries()].map(([name, v], i) => {
    const high = v.bands.filter((b) => b === "high").length;
    const med = v.bands.filter((b) => b === "medium").length;
    const band: RiskBand = high ? "high" : med ? "medium" : "low";
    return {
      id: `det-${i}-${name}`,
      name: name.replace(/_/g, " "),
      band,
      weight: v.weight,
      entities: v.entities.size,
      evidence: v.reasons.length,
      reason: v.reasons[0] || `Rule '${name}' triggered on ${v.entities.size} entities.`,
    };
  }).sort((a, b) => b.weight - a.weight);
}

export function riskDistributionFrom(entities: RiskEntity[]) {
  const counts = { low: 0, medium: 0, high: 0 };
  for (const e of entities) {
    const b = e.band || riskBand(e.risk_score);
    counts[b] += 1;
  }
  return [
    { band: "Low (0–39)", count: counts.low, color: "var(--risk-low)" },
    { band: "Medium (40–69)", count: counts.medium, color: "var(--risk-med)" },
    { band: "High (70–100)", count: counts.high, color: "var(--risk-high)" },
  ];
}
