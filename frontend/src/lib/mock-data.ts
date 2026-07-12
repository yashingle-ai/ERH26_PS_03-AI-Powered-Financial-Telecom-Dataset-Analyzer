export type RiskBand = "low" | "medium" | "high";

export const riskBand = (score: number): RiskBand =>
  score >= 70 ? "high" : score >= 40 ? "medium" : "low";

export type Case = {
  id: string;
  code: string;
  title: string;
  status: "ingested" | "analyzing" | "ready";
  files: { bank: number; cdr: number; ipdr: number };
  entities: number;
  events: number;
  hits: number;
  moneyMoved: number;
  topRisk: number;
  updated: string;
  lead: string;
};

export const cases: Case[] = [
  {
    id: "case-2041",
    code: "ERK-2041",
    title: "Operation Silverline — Mule ring, Delhi NCR",
    status: "ready",
    files: { bank: 12, cdr: 8, ipdr: 6 },
    entities: 342,
    events: 18420,
    hits: 87,
    moneyMoved: 41280000,
    topRisk: 92,
    updated: "2m ago",
    lead: "Insp. R. Menon",
  },
  {
    id: "case-2039",
    code: "ERK-2039",
    title: "UPI structuring — Chennai cluster",
    status: "analyzing",
    files: { bank: 4, cdr: 3, ipdr: 2 },
    entities: 108,
    events: 6210,
    hits: 24,
    moneyMoved: 8620000,
    topRisk: 74,
    updated: "18m ago",
    lead: "SI A. Krishnan",
  },
  {
    id: "case-2036",
    code: "ERK-2036",
    title: "Layered transfers — trade-based laundering",
    status: "ready",
    files: { bank: 22, cdr: 14, ipdr: 11 },
    entities: 512,
    events: 32104,
    hits: 156,
    moneyMoved: 129400000,
    topRisk: 88,
    updated: "1h ago",
    lead: "DySP V. Sharma",
  },
  {
    id: "case-2031",
    code: "ERK-2031",
    title: "OTP-hijack scam — Mumbai suburbs",
    status: "ingested",
    files: { bank: 3, cdr: 2, ipdr: 1 },
    entities: 42,
    events: 980,
    hits: 0,
    moneyMoved: 1240000,
    topRisk: 0,
    updated: "3h ago",
    lead: "SI P. Deshpande",
  },
  {
    id: "case-2028",
    code: "ERK-2028",
    title: "Circular flow — 14 shell accounts",
    status: "ready",
    files: { bank: 18, cdr: 6, ipdr: 4 },
    entities: 220,
    events: 12680,
    hits: 61,
    moneyMoved: 56900000,
    topRisk: 81,
    updated: "1d ago",
    lead: "Insp. R. Menon",
  },
];

export const activeCase = cases[0];

export type Identifier = {
  kind: "ACCOUNT_NO" | "PHONE" | "UPI" | "IMEI" | "IMSI";
  value: string;
};

export type Entity = {
  id: string;
  label: string;
  kind: "individual" | "account" | "phone" | "merchant";
  identifiers: Identifier[];
  risk: number;
  flags: string[];
  events: number;
  volume: number;
};

export const entities: Entity[] = [
  {
    id: "e-001",
    label: "Rakesh V.",
    kind: "individual",
    risk: 92,
    events: 412,
    volume: 12400000,
    flags: ["structuring", "rapid-in-out", "call-transfer-coincidence", "mule"],
    identifiers: [
      { kind: "ACCOUNT_NO", value: "HDFC 5001 2244 8890" },
      { kind: "PHONE", value: "+91 98104 22118" },
      { kind: "UPI", value: "rakesh.v@okhdfc" },
      { kind: "IMEI", value: "358240051111110" },
    ],
  },
  {
    id: "e-002",
    label: "Sanya Traders LLP",
    kind: "merchant",
    risk: 88,
    events: 302,
    volume: 41200000,
    flags: ["layering", "circular-flow", "ml-anomaly"],
    identifiers: [
      { kind: "ACCOUNT_NO", value: "ICICI 6110 8877 4200" },
      { kind: "UPI", value: "sanyatrd@icici" },
    ],
  },
  {
    id: "e-003",
    label: "Nodal-A / +91 90000 11223",
    kind: "phone",
    risk: 81,
    events: 189,
    volume: 0,
    flags: ["call-transfer-coincidence", "burner-pattern"],
    identifiers: [
      { kind: "PHONE", value: "+91 90000 11223" },
      { kind: "IMSI", value: "404450112233445" },
      { kind: "IMEI", value: "358240099887711" },
    ],
  },
  {
    id: "e-004",
    label: "M. Iqbal",
    kind: "individual",
    risk: 74,
    events: 156,
    volume: 3800000,
    flags: ["mule", "rapid-in-out"],
    identifiers: [
      { kind: "ACCOUNT_NO", value: "SBI 3341 0022 1198" },
      { kind: "PHONE", value: "+91 78290 55401" },
    ],
  },
  {
    id: "e-005",
    label: "Priya K.",
    kind: "individual",
    risk: 66,
    events: 98,
    volume: 1450000,
    flags: ["rapid-in-out"],
    identifiers: [
      { kind: "ACCOUNT_NO", value: "AXIS 9022 6611 4478" },
      { kind: "PHONE", value: "+91 99871 20034" },
    ],
  },
  {
    id: "e-006",
    label: "Neon Impex",
    kind: "merchant",
    risk: 58,
    events: 74,
    volume: 6200000,
    flags: ["layering"],
    identifiers: [{ kind: "ACCOUNT_NO", value: "KOTAK 4478 3300 2210" }],
  },
  {
    id: "e-007",
    label: "A. Fernandes",
    kind: "individual",
    risk: 44,
    events: 61,
    volume: 620000,
    flags: ["ml-anomaly"],
    identifiers: [
      { kind: "PHONE", value: "+91 98333 71120" },
      { kind: "UPI", value: "afernandes@ybl" },
    ],
  },
  {
    id: "e-008",
    label: "S. Rao",
    kind: "individual",
    risk: 31,
    events: 28,
    volume: 180000,
    flags: [],
    identifiers: [{ kind: "PHONE", value: "+91 90887 12234" }],
  },
];

export type Event = {
  id: string;
  type: "txn" | "call" | "ip";
  ts: string;
  minute: number; // minutes since day start (for timeline placement)
  entity: string;
  attrs: Record<string, string | number>;
  provenance: string;
};

export const events: Event[] = [
  { id: "ev-1", type: "call", ts: "09:12:04", minute: 552, entity: "Rakesh V.", attrs: { from: "+91 98104 22118", to: "+91 90000 11223", dur: "42s" }, provenance: "cdr_airtel_sep.csv:R2214" },
  { id: "ev-2", type: "ip", ts: "09:12:41", minute: 552, entity: "Rakesh V.", attrs: { src: "10.14.22.9", dst: "104.16.85.20:443", bytes: 18420 }, provenance: "ipdr_jio_sep.csv:R9021" },
  { id: "ev-3", type: "txn", ts: "09:14:22", minute: 554, entity: "Rakesh V.", attrs: { amount: 199000, to: "Sanya Traders LLP", mode: "IMPS" }, provenance: "hdfc_stmt_sep.xlsx:R442" },
  { id: "ev-4", type: "txn", ts: "09:14:58", minute: 554, entity: "Sanya Traders LLP", attrs: { amount: 198500, to: "M. Iqbal", mode: "NEFT" }, provenance: "icici_stmt_sep.xlsx:R118" },
  { id: "ev-5", type: "call", ts: "10:41:11", minute: 641, entity: "M. Iqbal", attrs: { from: "+91 78290 55401", to: "+91 90000 11223", dur: "1m 14s" }, provenance: "cdr_vi_sep.csv:R844" },
  { id: "ev-6", type: "txn", ts: "10:42:03", minute: 642, entity: "M. Iqbal", attrs: { amount: 96000, to: "Priya K.", mode: "UPI" }, provenance: "sbi_stmt_sep.pdf:P4" },
  { id: "ev-7", type: "ip", ts: "10:42:20", minute: 642, entity: "M. Iqbal", attrs: { src: "10.19.4.11", dst: "104.16.85.20:443", bytes: 9210 }, provenance: "ipdr_jio_sep.csv:R9998" },
  { id: "ev-8", type: "txn", ts: "13:08:44", minute: 788, entity: "Priya K.", attrs: { amount: 89500, to: "Neon Impex", mode: "IMPS" }, provenance: "axis_stmt_sep.xlsx:R209" },
  { id: "ev-9", type: "call", ts: "16:22:01", minute: 982, entity: "Rakesh V.", attrs: { from: "+91 98104 22118", to: "+91 78290 55401", dur: "3m 02s" }, provenance: "cdr_airtel_sep.csv:R2810" },
  { id: "ev-10", type: "txn", ts: "16:24:55", minute: 984, entity: "Rakesh V.", attrs: { amount: 245000, to: "Sanya Traders LLP", mode: "RTGS" }, provenance: "hdfc_stmt_sep.xlsx:R488" },
];

export type CorrelationHit = {
  id: string;
  window: string;
  entities: string[];
  events: string[];
  delta: string;
  score: number;
};

export const correlationHits: CorrelationHit[] = [
  { id: "h1", window: "09:12–09:14 IST", entities: ["Rakesh V.", "Sanya Traders LLP"], events: ["call", "ip", "txn"], delta: "+2m 18s", score: 92 },
  { id: "h2", window: "10:41–10:42 IST", entities: ["M. Iqbal", "Priya K."], events: ["call", "txn", "ip"], delta: "+0m 52s", score: 88 },
  { id: "h3", window: "13:07–13:09 IST", entities: ["Priya K.", "Neon Impex"], events: ["ip", "txn"], delta: "+1m 41s", score: 71 },
  { id: "h4", window: "16:22–16:25 IST", entities: ["Rakesh V.", "Sanya Traders LLP"], events: ["call", "txn"], delta: "+2m 54s", score: 84 },
  { id: "h5", window: "18:04–18:06 IST", entities: ["M. Iqbal", "Sanya Traders LLP"], events: ["call", "ip", "txn"], delta: "+1m 12s", score: 79 },
];

export const riskDistribution = [
  { band: "Low (0–39)", count: 188, color: "var(--risk-low)" },
  { band: "Medium (40–69)", count: 106, color: "var(--risk-med)" },
  { band: "High (70–100)", count: 48, color: "var(--risk-high)" },
];

export const riskHistogram = Array.from({ length: 10 }, (_, i) => ({
  bucket: `${i * 10}`,
  count: [22, 34, 41, 38, 29, 26, 22, 18, 14, 9][i],
}));

export const moneyFlowSeries = [
  { t: "Sep 01", inflow: 2.1, outflow: 1.9 },
  { t: "Sep 04", inflow: 3.4, outflow: 3.2 },
  { t: "Sep 07", inflow: 4.8, outflow: 4.6 },
  { t: "Sep 10", inflow: 6.2, outflow: 6.0 },
  { t: "Sep 13", inflow: 5.1, outflow: 5.0 },
  { t: "Sep 16", inflow: 7.4, outflow: 7.3 },
  { t: "Sep 19", inflow: 9.8, outflow: 9.6 },
  { t: "Sep 22", inflow: 8.2, outflow: 8.1 },
];

export type GraphNode = {
  id: string;
  label: string;
  kind: "account" | "phone" | "entity";
  risk: number;
  x: number;
  y: number;
};
export type GraphEdge = {
  from: string;
  to: string;
  kind: "money" | "comm" | "shared_id";
  weight: number;
};

export const graph: { nodes: GraphNode[]; edges: GraphEdge[] } = {
  nodes: [
    { id: "n1", label: "Rakesh V.", kind: "entity", risk: 92, x: 220, y: 180 },
    { id: "n2", label: "HDFC 5001…8890", kind: "account", risk: 90, x: 380, y: 120 },
    { id: "n3", label: "Sanya Traders", kind: "entity", risk: 88, x: 560, y: 200 },
    { id: "n4", label: "ICICI 6110…4200", kind: "account", risk: 84, x: 720, y: 140 },
    { id: "n5", label: "+91 90000 11223", kind: "phone", risk: 81, x: 420, y: 340 },
    { id: "n6", label: "M. Iqbal", kind: "entity", risk: 74, x: 620, y: 380 },
    { id: "n7", label: "SBI 3341…1198", kind: "account", risk: 70, x: 800, y: 340 },
    { id: "n8", label: "Priya K.", kind: "entity", risk: 66, x: 900, y: 250 },
    { id: "n9", label: "Neon Impex", kind: "entity", risk: 58, x: 980, y: 400 },
    { id: "n10", label: "+91 98104 22118", kind: "phone", risk: 70, x: 140, y: 300 },
  ],
  edges: [
    { from: "n1", to: "n2", kind: "shared_id", weight: 1 },
    { from: "n1", to: "n10", kind: "shared_id", weight: 1 },
    { from: "n2", to: "n4", kind: "money", weight: 8 },
    { from: "n4", to: "n7", kind: "money", weight: 6 },
    { from: "n7", to: "n8", kind: "money", weight: 4 },
    { from: "n8", to: "n9", kind: "money", weight: 3 },
    { from: "n9", to: "n2", kind: "money", weight: 2 },
    { from: "n10", to: "n5", kind: "comm", weight: 5 },
    { from: "n5", to: "n6", kind: "comm", weight: 4 },
    { from: "n3", to: "n4", kind: "shared_id", weight: 1 },
    { from: "n6", to: "n7", kind: "shared_id", weight: 1 },
  ],
};

export type Detection = {
  id: string;
  name: string;
  band: RiskBand;
  weight: number;
  entities: number;
  evidence: number;
  reason: string;
};

export const detections: Detection[] = [
  { id: "d1", name: "Call → Transfer coincidence (W=10m)", band: "high", weight: 28, entities: 14, evidence: 63, reason: "Outgoing IMPS/UPI within 10 min of an incoming call across 14 entity pairs." },
  { id: "d2", name: "Rapid in-out (< 5 min, ≥ 80% pass-through)", band: "high", weight: 24, entities: 9, evidence: 41, reason: "Funds received then re-routed within minutes at ≥80% pass-through — mule pattern." },
  { id: "d3", name: "Structuring under ₹50k threshold", band: "high", weight: 22, entities: 11, evidence: 88, reason: "Repeated deposits/transfers just under reporting threshold across accounts." },
  { id: "d4", name: "Circular flow (A→B→C→A)", band: "medium", weight: 18, entities: 6, evidence: 14, reason: "Cycles of length ≤4 closing within 48h across the money-flow graph." },
  { id: "d5", name: "Shared IMEI across accounts", band: "medium", weight: 15, entities: 7, evidence: 22, reason: "Same IMEI observed authenticating sessions for multiple beneficiary accounts." },
  { id: "d6", name: "ML anomaly — velocity outlier", band: "medium", weight: 12, entities: 12, evidence: 34, reason: "Transaction velocity Z-score > 3.2 vs entity baseline (isolation forest)." },
  { id: "d7", name: "Burner-phone pattern", band: "low", weight: 8, entities: 4, evidence: 11, reason: "Short-lived SIM active < 72h with concentrated outbound calls to flagged entities." },
];
