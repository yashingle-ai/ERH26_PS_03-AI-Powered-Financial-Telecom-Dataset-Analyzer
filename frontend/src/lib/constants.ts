/* ──────────────────────────────────────────────────────────
 * ERakshak — Frontend Constants
 * ──────────────────────────────────────────────────────── */

import type { RiskBand } from "@/lib/types";

/* ── Risk scoring ─────────────────────────────────────── */

export const RISK_HIGH_THRESHOLD = 70;
export const RISK_MED_THRESHOLD = 40;

export const riskBand = (score: number): RiskBand =>
  score >= RISK_HIGH_THRESHOLD
    ? "high"
    : score >= RISK_MED_THRESHOLD
      ? "medium"
      : "low";

export const riskColor = (score: number): string => {
  const b = riskBand(score);
  return b === "high"
    ? "var(--risk-high)"
    : b === "medium"
      ? "var(--risk-med)"
      : "var(--risk-low)";
};

/* ── Event types ──────────────────────────────────────── */

export const EVENT_TYPE_MAP: Record<string, "txn" | "call" | "ip"> = {
  TRANSACTION: "txn",
  CALL: "call",
  IP_SESSION: "ip",
};

/* ── Identifier kind mapping (backend → frontend) ──── */

export const ID_KIND_MAP: Record<string, "ACCOUNT_NO" | "PHONE" | "UPI" | "IMEI" | "IMSI"> = {
  ACCOUNT_NO: "ACCOUNT_NO",
  PHONE: "PHONE",
  UPI_ID: "UPI",
  UPI: "UPI",
  IMEI: "IMEI",
  IMSI: "IMSI",
};

/* ── Risk distribution buckets ────────────────────────── */

export const RISK_DISTRIBUTION_LABELS = [
  { band: "Low (0–39)", key: "low" as const, color: "var(--risk-low)" },
  { band: "Medium (40–69)", key: "medium" as const, color: "var(--risk-med)" },
  { band: "High (70–100)", key: "high" as const, color: "var(--risk-high)" },
] as const;

/* ── Graph edge kind mapping (backend → frontend) ──── */

export const EDGE_KIND_MAP: Record<string, "money" | "comm" | "shared_id"> = {
  MONEY_FLOW: "money",
  COMMUNICATION: "comm",
  SHARED_IDENTIFIER: "shared_id",
};

/* ── Currency formatting ──────────────────────────────── */

export const formatLakhs = (value: number): string =>
  value ? `₹ ${(value / 100000).toFixed(1)}L` : "—";

export const formatCrores = (value: number): string =>
  `₹ ${value.toFixed(2)} Cr`;
