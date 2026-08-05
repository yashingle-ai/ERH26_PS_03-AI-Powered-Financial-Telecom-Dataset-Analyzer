import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useAnalyzeProgress, formatDuration } from "./use-analyze-progress";
import { api } from "@/lib/api";

/**
 * These tests pin the three properties that make the progress bar honest. The bar
 * they replace was a `setInterval` that ticked nine stages in 3.6 seconds in front
 * of an 11-to-49-minute pipeline run — it agreed with the server only by accident
 * and reported "nearly done" within four seconds of every run, including hung ones.
 */
describe("useAnalyzeProgress", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it("does not poll while idle", async () => {
    const spy = vi.spyOn(api, "analyzeProgress").mockResolvedValue({
      dataset: "demo", window_minutes: 10, status: "idle",
    });

    renderHook(() => useAnalyzeProgress("demo", 10, false));

    await new Promise((r) => setTimeout(r, 30));
    expect(spy).not.toHaveBeenCalled();
  });

  it("reports the server's percent rather than inventing one", async () => {
    vi.spyOn(api, "analyzeProgress").mockResolvedValue({
      dataset: "demo", window_minutes: 10, status: "running",
      stage: "correlate", stage_label: "Correlating call / IP / transfers",
      stage_index: 5, percent: 71.4, eta_seconds: 161,
    });

    const { result } = renderHook(() => useAnalyzeProgress("demo", 10, true));

    await waitFor(() => expect(result.current?.percent).toBe(71.4));
    expect(result.current?.stage_index).toBe(5);
    expect(result.current?.stage_label).toBe("Correlating call / IP / transfers");
  });

  /**
   * The one that matters most. The pipeline is CPU-bound Python holding the GIL, so
   * the whole API goes unresponsive during heavy stages and polls fail *while
   * everything is working correctly*. A failed poll must never surface an error or
   * abort the analyze it is describing — progress is decoration.
   */
  it("keeps the last known state when a poll fails, and keeps polling", async () => {
    const spy = vi.spyOn(api, "analyzeProgress")
      .mockResolvedValueOnce({
        dataset: "demo", window_minutes: 10, status: "running",
        stage: "parse", percent: 12.5,
      })
      .mockRejectedValueOnce(new Error("API unresponsive"))
      .mockResolvedValue({
        dataset: "demo", window_minutes: 10, status: "running",
        stage: "parse", percent: 20.0,
      });

    const { result } = renderHook(() => useAnalyzeProgress("demo", 10, true));

    await waitFor(() => expect(result.current?.percent).toBe(12.5));
    // The rejected poll must not blank the state or stop the loop.
    await waitFor(() => expect(spy.mock.calls.length).toBeGreaterThan(2), { timeout: 6000 });
    expect(result.current).not.toBeNull();
    expect(result.current?.percent).toBeGreaterThanOrEqual(12.5);
  }, 10_000);

  it("stops polling once the run is no longer active", async () => {
    const spy = vi.spyOn(api, "analyzeProgress").mockResolvedValue({
      dataset: "demo", window_minutes: 10, status: "running", percent: 40,
    });

    const { rerender } = renderHook(
      ({ active }) => useAnalyzeProgress("demo", 10, active),
      { initialProps: { active: true } },
    );

    await waitFor(() => expect(spy).toHaveBeenCalled());
    await act(async () => { rerender({ active: false }); });

    const after = spy.mock.calls.length;
    await new Promise((r) => setTimeout(r, POLL_SETTLE_MS));
    expect(spy.mock.calls.length).toBe(after);
  });
});

/** Longer than the 1.5 s poll interval, so a leaked timer would have fired. */
const POLL_SETTLE_MS = 2_000;

describe("formatDuration", () => {
  it("formats seconds, minutes and hours", () => {
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(93)).toBe("1m 33s");
    expect(formatDuration(120)).toBe("2m");
    expect(formatDuration(3_720)).toBe("1h 2m");
  });

  it("returns null for absent or nonsensical input so the caller can hide the field", () => {
    // The server sends eta_seconds: null until 1% is done — the estimate before
    // that is noise, and rendering "~0s left" at the start of a 49-minute run
    // would be worse than showing nothing.
    expect(formatDuration(null)).toBeNull();
    expect(formatDuration(undefined)).toBeNull();
    expect(formatDuration(-1)).toBeNull();
    expect(formatDuration(Number.NaN)).toBeNull();
  });
});
