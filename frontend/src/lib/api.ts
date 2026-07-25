import { clearSession, getToken } from "@/lib/auth";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "")
  || "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  code?: number;

  constructor(status: number, message: string, code?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type RequestOptions = {
  method?: string;
  body?: BodyInit | null;
  auth?: boolean;
  headers?: Record<string, string>;
};

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  const auth = opts.auth !== false;
  if (auth) {
    const token = getToken();
    if (!token) throw new ApiError(401, "Not signed in");
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body ?? null,
  });

  if (res.status === 401 && auth) {
    clearSession();
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: { message: text } };
    }
  }

  if (!res.ok) {
    const err = data as { error?: { message?: string; code?: number } } | null;
    throw new ApiError(
      res.status,
      err?.error?.message || res.statusText || "Request failed",
      err?.error?.code,
    );
  }

  return data as T;
}

export type TokenResponse = { access_token: string; token_type: string };

export type AnalyzeSummary = {
  files: number;
  events: number;
  transactions: number;
  calls: number;
  ip_sessions: number;
  /** Rows dropped during normalization, summed across every reject entry. */
  rejected_rows: number;
  /** Number of distinct (file, reason) reject groups behind `rejected_rows`. */
  reject_entries: number;
  entities: number;
  correlation_hits: number;
  transfers: number;
  high_risk_entities: number;
};

export type RuleFlag = { rule: string; detail: string; weight: number };

export type IdentifierDto = { kind: string; value: string };

export type RiskEntity = {
  entity_id: string;
  label: string | null;
  risk_score: number;
  band: "low" | "medium" | "high";
  ml_score: number;
  rule_flags: RuleFlag[];
  features: Record<string, number | null | undefined>;
  identifiers?: IdentifierDto[];
  types?: string[];
  external?: boolean;
  event_count?: number;
  volume?: number;
  txn_count?: number;
};

export type CorrelationHitDto = {
  entity_id: string;
  entity_label?: string | null;
  window_minutes: number;
  transaction: {
    time: string;
    amount?: number | null;
    direction?: string | null;
    ref_no?: string | null;
    provenance?: Record<string, unknown>;
  };
  call: {
    time: string;
    counterparty_entity_id?: string | null;
    provenance?: Record<string, unknown>;
  };
  ip_session: {
    start: string;
    end?: string | null;
    ip?: string | null;
    provenance?: Record<string, unknown>;
  };
  explanation?: string;
};

export type AnalyzeResponse = {
  dataset: string;
  window_minutes: number;
  summary: AnalyzeSummary;
  file_counts: { bank: number; cdr: number; ipdr: number; other: number };
  money_flow_series: { t: string; inflow: number; outflow: number }[];
  correlation_hits: CorrelationHitDto[];
  top_risk: RiskEntity[];
};

export type GraphPayload = {
  nodes: {
    id: string;
    label: string | null;
    risk: number | null;
    types?: string[];
    external?: boolean;
    community?: number;
    centrality?: number;
    degree?: number;
  }[];
  edges: {
    source: string;
    target: string;
    kind: string;
    amount?: number | null;
    count?: number | null;
  }[];
};

export type EventDto = {
  id: string;
  event_type: string;
  timestamp: string | null;
  timestamp_end?: string | null;
  minute: number | null;
  entity_id?: string | null;
  entity_label?: string | null;
  counterparty_entity_id?: string | null;
  amount?: number | null;
  direction?: string | null;
  attributes: Record<string, unknown>;
  provenance: {
    source_file?: string | null;
    sheet?: string | null;
    row?: number | null;
    offset?: number | null;
    profile?: string | null;
  };
};

/** A bank account whose running balance does not reconcile (A5). */
export type BalanceBreakDto = {
  account: string;
  checked: number;
  breaks: number;
  first_break_ref?: string | null;
  consistency: number | null;
};

/** Per-file / per-reason breakdown of rows dropped at ingestion (B3). */
export type RejectDto = {
  file?: string | null;
  reason?: string | null;
  rows?: number | null;
  rejected?: number | null;
  [key: string]: unknown;
};

export type DataQualityResponse = {
  balance_breaks: BalanceBreakDto[];
  rejects: RejectDto[];
  parsed_files: Record<string, unknown>[];
};

/**
 * A candidate same-actor pair surfaced for analyst review (C3).
 * Never auto-merged — deterministic resolution stays authoritative.
 */
export type LinkSuggestionDto = {
  entity_a: string;
  label_a: string;
  entity_b: string;
  label_b: string;
  similarity: number;
};

export type SuggestionsResponse = {
  total: number;
  items: LinkSuggestionDto[];
  threshold: number;
};

/**
 * A validated, locally-executed query plan (F1). Present only on the "llm" engine —
 * it is the audit trail for how a natural-language answer was derived, and should be
 * surfaced to the analyst rather than hidden.
 */
export type QuerySpec = {
  target: "events" | "entities" | "correlations";
  filters: { field: string; op: string; value?: unknown; values?: unknown[] }[];
  group_by?: string | null;
  aggregate: string;
  order_desc: boolean;
  limit: number;
  explanation: string;
};

/** NL query result (F1). `rows` is null when the query wasn't understood. */
export type NlQueryResponse = {
  query: string;
  /** "llm" = question translated to a validated spec, run locally. "rules" = offline. */
  engine: "llm" | "rules";
  explanation: string;
  rows: Record<string, unknown>[] | null;
  /** Rows actually returned (capped by `limit`). */
  matched: number;
  /** True match count — differs from `matched` when the result was capped. */
  total: number;
  truncated: boolean;
  spec: QuerySpec | null;
};

export const api = {
  baseUrl: API_BASE,

  login(username: string, password: string) {
    const body = new URLSearchParams();
    body.set("username", username);
    body.set("password", password);
    return request<TokenResponse>("/v1/auth/token", {
      method: "POST",
      auth: false,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  },

  health() {
    return request<{ status: string }>("/health", { auth: false });
  },

  datasets() {
    return request<{ datasets: string[] }>("/v1/datasets");
  },

  analyze(dataset: string, windowMinutes = 10, persist = false) {
    return request<AnalyzeResponse>("/v1/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset,
        window_minutes: windowMinutes,
        persist,
      }),
    });
  },

  entities(dataset: string, window = 10, limit = 200, offset = 0) {
    const q = new URLSearchParams({
      window: String(window),
      limit: String(limit),
      offset: String(offset),
    });
    return request<{ total: number; items: RiskEntity[] }>(`/v1/entities/${encodeURIComponent(dataset)}?${q}`);
  },

  events(dataset: string, window = 10, limit = 400, offset = 0, eventType?: string) {
    const q = new URLSearchParams({
      window: String(window),
      limit: String(limit),
      offset: String(offset),
    });
    if (eventType) q.set("event_type", eventType);
    return request<{ total: number; items: EventDto[] }>(`/v1/events/${encodeURIComponent(dataset)}?${q}`);
  },

  graph(dataset: string, window = 10) {
    const q = new URLSearchParams({ window: String(window) });
    return request<GraphPayload>(`/v1/graph/${encodeURIComponent(dataset)}?${q}`);
  },

  dataQuality(dataset: string, window = 10) {
    const q = new URLSearchParams({ window: String(window) });
    return request<DataQualityResponse>(`/v1/data-quality/${encodeURIComponent(dataset)}?${q}`);
  },

  suggestions(dataset: string, window = 10, threshold = 0.88, limit = 50) {
    const q = new URLSearchParams({
      window: String(window),
      threshold: String(threshold),
      limit: String(limit),
    });
    return request<SuggestionsResponse>(`/v1/suggestions/${encodeURIComponent(dataset)}?${q}`);
  },

  query(dataset: string, q: string, windowMinutes = 10, engine?: "llm" | "rules") {
    return request<NlQueryResponse>(`/v1/query/${encodeURIComponent(dataset)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q, window_minutes: windowMinutes, engine }),
    });
  },
};
