import { clearSession, getToken, getUsername, secondsUntilExpiry, setSession } from "@/lib/auth";

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
  /**
   * Renew the token unless at least this many seconds remain. Set it above the
   * expected duration of a slow call so the token cannot expire mid-flight.
   */
  minTokenSeconds?: number;
  /** Abort a hung fetch (progress polls must not wait forever on a GIL-blocked API). */
  signal?: AbortSignal;
};

/**
 * Renew the token when it is close to expiring.
 *
 * Analysing a real case takes ~10 minutes and an analyst reads the results for
 * much longer, so a fixed-lifetime token runs out mid-session. Renewing before
 * each call — rather than reacting to a 401 — means a long-running request is
 * never started on a token that will expire while it is in flight.
 *
 * `minRemaining` is raised for known-slow calls so the token outlives the request.
 */
const REFRESH_MARGIN_S = 120;
const REFRESH_COOLDOWN_MS = 30_000;
let refreshInFlight: Promise<void> | null = null;
let lastRefreshAt = 0;

async function ensureFreshToken(minRemaining = REFRESH_MARGIN_S): Promise<void> {
  const left = secondsUntilExpiry();
  if (left === null || left > minRemaining) return;
  if (left <= 0) return;             // already dead — only a fresh login helps
  if (refreshInFlight) return refreshInFlight;
  // If the server's TTL is shorter than a slow call needs, a fresh token still
  // won't clear the bar — without this, every request would refresh forever.
  // Renew at most once per cooldown and let the request proceed regardless.
  if (Date.now() - lastRefreshAt < REFRESH_COOLDOWN_MS) return;
  lastRefreshAt = Date.now();

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) return;           // let the real request surface the failure
      const data = (await res.json()) as TokenResponse;
      if (data?.access_token) setSession(data.access_token, getUsername() || "");
    } catch {
      /* offline or server down — the request below reports it properly */
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  const auth = opts.auth !== false;
  if (auth) {
    await ensureFreshToken(opts.minTokenSeconds);
    const token = getToken();
    if (!token) throw new ApiError(401, "Not signed in");
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body ?? null,
    signal: opts.signal,
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

/**
 * Binary sibling of `request` for endpoints that stream a file.
 *
 * Kept separate rather than adding a flag to `request`: that one reads the body as
 * text to parse JSON, which would corrupt a PDF. The error path still decodes as
 * text, because a failure returns the normal JSON error schema even from a route
 * whose success path is binary.
 */
async function requestBlob(path: string, opts: RequestOptions = {}): Promise<Blob> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  await ensureFreshToken(opts.minTokenSeconds);
  const token = getToken();
  if (!token) throw new ApiError(401, "Not signed in");
  headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body ?? null,
  });

  if (res.status === 401) clearSession();

  if (!res.ok) {
    const text = await res.text();
    let message = res.statusText || "Request failed";
    let code: number | undefined;
    try {
      const err = JSON.parse(text) as { error?: { message?: string; code?: number } };
      message = err?.error?.message || message;
      code = err?.error?.code;
    } catch {
      if (text) message = text;
    }
    throw new ApiError(res.status, message, code);
  }

  return res.blob();
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
  /** STRONG only (call + IP + transfer) — FR-9 headline. */
  correlation_hits: number;
  /** MEDIUM (call + transfer, no IP) — mitigation, not FR-9. */
  correlation_hits_medium?: number;
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
  /** Whether `ml_score` is a measurement or an absence. The forest is fitted only on entities
   *  that have records of their own, and min-max normalisation also hands 0.0 to the least
   *  anomalous fitted entity — so a bare 0.0 cannot distinguish "we looked and found nothing
   *  unusual" from "there was never anything to look at". */
  ml_scored?: boolean;
  /** How many distinct typologies fired. `risk_score` saturates (enabled weights sum to 1.2
   *  against a component capped at 1.0), so this is what separates six from eight. */
  typologies_fired?: number;
  rule_weight_raw?: number;
  rule_component_saturated?: boolean;
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
  /** STRONG = call+IP+txn (FR-9); MEDIUM = call+txn only. */
  tier?: "STRONG" | "MEDIUM";
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
  ip_session?: {
    start: string;
    end?: string | null;
    ip?: string | null;
    provenance?: Record<string, unknown>;
  } | null;
  explanation?: string;
};

/** One pipeline stage as the server defines it. Weights sum to ~100. */
export type AnalyzeStage = { id: string; label: string; weight: number };

/**
 * Live progress for an in-flight analyze — `GET /v1/analyze/progress/{ds}`.
 *
 * Polled by a *second* request while the analyze request is still open: the
 * pipeline is synchronous and a real FIR case takes 11–49 minutes, so the call
 * itself carries no intermediate signal.
 *
 * `stages` is the server's own stage list. Render it rather than a local copy —
 * the page used to hardcode nine labels that did not match the server's, and
 * nothing tied the two lists together.
 */
export type AnalyzeProgress = {
  dataset: string;
  window_minutes: number;
  status: "idle" | "running" | "done" | "error";
  stage?: string;
  stage_label?: string;
  stage_index?: number;
  stage_count?: number;
  message?: string;
  percent?: number;
  done?: number;
  total?: number;
  elapsed_seconds?: number;
  /** null until at least 1% is complete — before that the estimate is noise. */
  eta_seconds?: number | null;
  error?: string | null;
  from_cache?: boolean;
  stages?: AnalyzeStage[];
  /**
   * Client-only: seconds since the last successful progress poll. Large values
   * mean the API is busy (GIL) and stage/percent may be stale — elapsed still ticks.
   */
  stale_seconds?: number | null;
};

export type AnalyzeResponse = {
  dataset: string;
  window_minutes: number;
  /** True when served from a durable snapshot instead of a fresh pipeline run. */
  from_cache?: boolean;
  summary: AnalyzeSummary;
  file_counts: { bank: number; cdr: number; ipdr: number; other: number };
  money_flow_series: { t: string; inflow: number; outflow: number }[];
  correlation_hits: CorrelationHitDto[];
  correlation_hits_medium?: CorrelationHitDto[];
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
  /** BANK | CDR | IPDR | CRYPTO, or absent when the source was never identified.
   *  Declared explicitly: the index signature below types it as `unknown`, which
   *  is not renderable and silently pushes the error into the consuming screen. */
  source_type?: string | null;
  profile?: string | null;
  [key: string]: unknown;
};

export type DataQualityResponse = {
  balance_breaks: BalanceBreakDto[];
  rejects: RejectDto[];
  parsed_files: Record<string, unknown>[];
};

/** FR-18. `matrix[i][j]` is the weight of `columns[j]` on `entities[i]`, as a percentage.
 *  `entities_scored` vs `entities_with_a_fired_rule` lets the UI distinguish "nothing fired"
 *  from "nothing was evaluated" — an empty grid must not read as "assessed and clean". */
export type RiskHeatmap = {
  dataset: string;
  window_minutes: number;
  columns: string[];
  entities: {
    entity_id: string | null;
    label: string | null;
    risk_score: number;
    band: string;
    rules_fired: string[];
  }[];
  matrix: number[][];
  unit: string;
  rules_evaluated: string[];
  entities_scored: number;
  entities_with_a_fired_rule: number;
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
  /** Window resolved from an anchor event, e.g. "the day before the last transaction". */
  relative_window?: { anchor: string; offset_days: number; span_days: number } | null;
  group_by?: string | null;
  aggregate: string;
  /** Post-grouping conditions — how "stopped calling after August" is expressed. */
  having?: { metric: string; op: string; value?: unknown; values?: unknown[] }[];
  /** Keep only groups covering every listed value ("called both A and B"). */
  group_must_include?: { field: string; values: string[] } | null;
  order_desc: boolean;
  limit: number;
  explanation: string;
};

/** NL query result (F1). `rows` is null when the query wasn't understood. */
export type NlQueryResponse = {
  query: string;
  /** "llm" | "offline" (local QuerySpec patterns) | "rules" (legacy regex intents). */
  engine: "llm" | "rules" | "offline";
  /**
   * Plain-text answer to the question, composed locally from the spec + rows.
   * Distinct from `explanation`, which describes the *plan*.
   */
  answer: string;
  explanation: string;
  rows: Record<string, unknown>[] | null;
  /** Rows actually returned (capped by `limit`). */
  matched: number;
  /** True match count — differs from `matched` when the result was capped. */
  total: number;
  truncated: boolean;
  /** Concrete [start, end) dates a relative window resolved to — show this to the analyst. */
  window?: [string, string] | null;
  /** Rows excluded from a grouping because the key was a blank/placeholder value. */
  skipped_blank?: number | null;
  /** Set when the query could not be answered as asked (e.g. no event to anchor to). */
  note?: string | null;
  spec: QuerySpec | null;
};

export type UploadKind = "bank" | "cdr" | "ipdr" | "other";

/**
 * Per-file outcome. Every submitted file comes back with a status — a rejected
 * file is never silently dropped, because "what I uploaded" and "what the system
 * holds" have to be the same set for the evidence to mean anything.
 */
export type UploadFileResult = {
  file: string;
  status: "stored" | "rejected";
  bytes?: number;
  path?: string;
  reason?: string;
};

export type UploadResponse = {
  dataset: string;
  kind: UploadKind;
  accepted: number;
  rejected: number;
  bytes: number;
  files: UploadFileResult[];
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

  /**
   * Run (or load) the pipeline for a dataset.
   *
   * `force` drops the durable snapshot for this (dataset, window) and re-runs from
   * scratch. Needed after a profile, threshold or pipeline change — otherwise the
   * snapshot is served indefinitely and the API returns figures that predate the
   * edit. It costs a full parse, so callers must confirm before passing it.
   *
   * The third parameter stays positional for `persist` so existing callers are
   * unaffected; `force` is opt-in via the options object.
   */
  analyze(
    dataset: string,
    windowMinutes = 10,
    persist = false,
    opts: { force?: boolean } = {},
  ) {
    return request<AnalyzeResponse>("/v1/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // A real case with PDFs takes ~10 minutes to parse. Losing that run to an
      // expiry that was already visible before the request started is the worst
      // possible failure, so demand a token that will outlast it.
      minTokenSeconds: 20 * 60,
      body: JSON.stringify({
        dataset,
        window_minutes: windowMinutes,
        persist,
        force: opts.force ?? false,
      }),
    });
  },

  /**
   * Generate the forensic report (FR-16) and return it as a file blob.
   *
   * The generator has existed since `7d20672` and only Streamlit could reach it;
   * the React app — the primary UI — offered `window.print()` and told the user
   * "PDF/STR export endpoints are not exposed on the API yet". They are.
   *
   * Server-side this reaches into matplotlib and reportlab and re-reads the whole
   * investigation, so it is slow enough to need the long token minimum.
   */
  report(dataset: string, fmt: "pdf" | "docx" = "pdf", windowMinutes = 10) {
    return requestBlob(`/v1/report/${encodeURIComponent(dataset)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      minTokenSeconds: 20 * 60,
      body: JSON.stringify({ fmt, window_minutes: windowMinutes }),
    });
  },

  /**
   * Progress of an in-flight analyze. Cheap — a locked dict read on the server.
   *
   * Do not raise `minTokenSeconds` here: this is polled repeatedly and a long
   * minimum would trigger a token refresh on every poll. The analyze call it
   * accompanies already holds a token good for 20 minutes.
   */
  analyzeProgress(dataset: string, window = 10, opts: { signal?: AbortSignal } = {}) {
    const q = new URLSearchParams({ window: String(window) });
    return request<AnalyzeProgress>(
      `/v1/analyze/progress/${encodeURIComponent(dataset)}?${q}`,
      { signal: opts.signal },
    );
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

  riskHeatmap(dataset: string, window = 10, top = 20) {
    const q = new URLSearchParams({ window: String(window), top: String(top) });
    return request<RiskHeatmap>(`/v1/risk-heatmap/${encodeURIComponent(dataset)}?${q}`);
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

  /**
   * Upload evidence files into datasets/raw/{dataset}/{kind}/.
   *
   * Deliberately does NOT set Content-Type — the browser must add the multipart
   * boundary itself, and setting it by hand produces a body the server cannot parse.
   */
  upload(dataset: string, files: File[], kind: UploadKind = "other") {
    const body = new FormData();
    for (const f of files) body.append("files", f);
    body.set("kind", kind);
    return request<UploadResponse>(`/v1/upload/${encodeURIComponent(dataset)}`, {
      method: "POST",
      minTokenSeconds: 10 * 60,   // hundreds of files / several hundred MB
      body,
    });
  },

  query(dataset: string, q: string, windowMinutes = 10, engine?: "llm" | "rules") {
    return request<NlQueryResponse>(`/v1/query/${encodeURIComponent(dataset)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q, window_minutes: windowMinutes, engine }),
    });
  },
};
