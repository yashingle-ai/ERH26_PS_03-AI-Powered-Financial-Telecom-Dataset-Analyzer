import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, ApiError } from "./api";
import { setSession, clearSession } from "./auth";

/**
 * Request-construction tests for the analyze surface.
 *
 * `force: true` deletes the durable snapshot and re-parses an entire case — 11 to
 * 49 minutes on a real FIR folder. Sending it by accident is expensive and silent,
 * and *not* sending it when asked means the analyst keeps seeing figures that
 * predate their change. Both directions are pinned here.
 */
/**
 * A syntactically real JWT with a far-future `exp`, so `ensureFreshToken()` sees
 * plenty of life left and never fires a refresh call that the assertions would
 * then have to skip over.
 */
function tokenValidFor(seconds: number): string {
  const payload = { exp: Math.floor(Date.now() / 1000) + seconds };
  const b64url = btoa(JSON.stringify(payload))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `header.${b64url}.sig`;
}

describe("api.analyze", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  const okAnalyze = {
    dataset: "demo", window_minutes: 10, from_cache: false,
    summary: {}, file_counts: {}, money_flow_series: [],
    correlation_hits: [], top_risk: [],
  };

  beforeEach(() => {
    setSession(tokenValidFor(86_400), "tester");
    fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200, statusText: "OK",
      text: async () => JSON.stringify(okAnalyze),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  const bodyOf = () => JSON.parse(fetchMock.mock.calls[0][1].body as string);

  it("does not force by default — the caller must ask for it explicitly", async () => {
    await api.analyze("demo", 10);
    expect(bodyOf().force).toBe(false);
  });

  it("sends force when asked", async () => {
    await api.analyze("demo", 10, false, { force: true });
    expect(bodyOf()).toMatchObject({ dataset: "demo", window_minutes: 10, force: true });
  });

  /**
   * The trap this guards. `onClick={start}` passes a MouseEvent as the first
   * argument; if `start(force)` took force positionally from that, every click on
   * "Run pipeline" would discard the saved analysis and re-parse the case. The
   * page uses `onClick={() => start()}` for exactly this reason — so a non-boolean
   * reaching the API must still serialise as a plain false, never as an object.
   */
  it("coerces a missing force to boolean false, never to a truthy object", async () => {
    await api.analyze("demo", 10, false, {});
    expect(bodyOf().force).toBe(false);
    expect(typeof bodyOf().force).toBe("boolean");
  });

  it("keeps persist independent of force", async () => {
    await api.analyze("demo", 10, true, { force: true });
    expect(bodyOf()).toMatchObject({ persist: true, force: true });
  });

  it("surfaces the server's error message rather than a bare status", async () => {
    fetchMock.mockResolvedValue({
      ok: false, status: 404, statusText: "Not Found",
      text: async () => JSON.stringify({ error: { code: 404, message: "dataset 'nope' not found" } }),
    });
    await expect(api.analyze("nope", 10)).rejects.toThrow(/dataset 'nope' not found/);
    await expect(api.analyze("nope", 10)).rejects.toBeInstanceOf(ApiError);
  });
});

describe("api.analyzeProgress", () => {
  beforeEach(() => {
    setSession(tokenValidFor(86_400), "tester");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("encodes the dataset and passes the window", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200, statusText: "OK",
      text: async () => JSON.stringify({ dataset: "a b", window_minutes: 30, status: "idle" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.analyzeProgress("a b", 30);

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/v1/analyze/progress/a%20b");
    expect(url).toContain("window=30");
    expect(fetchMock.mock.calls[0][1].method ?? "GET").toBe("GET");
  });
});
