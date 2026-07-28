/* ──────────────────────────────────────────────────────────
 * ERakshak — Frontend Display Types
 * ──────────────────────────────────────────────────────── */

export type RiskBand = "low" | "medium" | "high";

/* ── Investigation / Case ─────────────────────────────── */

export type Case = {
  id: string;
  code: string;
  title: string;
  status: "idle" | "analyzing" | "ready" | "error";
  files: { bank: number; cdr: number; ipdr: number };
  entities: number;
  events: number;
  hits: number;
  moneyMoved: number;
  topRisk: number;
  updated: string;
  lead: string;
};

/* ── Entity ───────────────────────────────────────────── */

export type Identifier = {
  kind: "ACCOUNT_NO" | "PHONE" | "UPI" | "IMEI" | "IMSI";
  value: string;
};

export type RuleFlagDisplay = {
  rule: string;
  detail: string;
  weight: number;
};

export type Entity = {
  id: string;
  label: string;
  kind: "individual" | "account" | "phone" | "merchant";
  identifiers: Identifier[];
  risk: number;
  mlScore: number;
  flags: string[];
  ruleFlags: RuleFlagDisplay[];
  events: number;
  volume: number;
};

/* ── Event ────────────────────────────────────────────── */

export type Event = {
  id: string;
  type: "txn" | "call" | "ip";
  ts: string;
  minute: number; // minutes since day start (for timeline placement)
  entity: string;
  attrs: Record<string, string | number>;
  provenance: string;
};

/* ── Correlation ──────────────────────────────────────── */

export type CorrelationHit = {
  id: string;
  window: string;
  entities: string[];
  events: string[];
  delta: string;
  score: number;
  /** STRONG = FR-9 three-leg; MEDIUM = call+txn only. */
  tier: "STRONG" | "MEDIUM";
};

/* ── Detection ────────────────────────────────────────── */

export type Detection = {
  id: string;
  name: string;
  band: RiskBand;
  weight: number;
  entities: number;
  evidence: number;
  reason: string;
};

/* ── Graph ────────────────────────────────────────────── */

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
