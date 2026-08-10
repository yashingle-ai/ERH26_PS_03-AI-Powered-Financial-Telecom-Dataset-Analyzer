import { useEffect, useMemo, useRef, useState } from "react";
import { api, type AnalyzeProgress } from "@/lib/api";

/** How often to ask the server where the pipeline has got to. */
const POLL_MS = 1_500;

/**
 * Cap how long a progress poll may wait. During heavy parse/detect stages the
 * API holds the GIL and a fetch can hang for minutes; without a timeout the
 * next poll never schedules and the UI freezes on the last known percent/ETA
 * (e.g. "16m 30s elapsed" for half an hour while the pipeline keeps moving).
 */
const POLL_TIMEOUT_MS = 4_000;

/**
 * Poll `GET /v1/analyze/progress/{ds}` while an analyze is running.
 *
 * Why polling at all: `POST /v1/analyze` is synchronous and a real FIR case takes
 * 11–49 minutes, so the analyze request itself carries no intermediate signal. A
 * second, cheap request reports where the first one has reached.
 *
 * Properties this hook must have, each learned from how the backend behaves:
 *
 * 1. **A failed / timed-out poll is never fatal.** The pipeline is CPU-bound Python
 *    holding the GIL, so the whole API goes unresponsive during heavy stages —
 *    polls will hang or fail *while everything is working correctly*. Keep the
 *    last known state and keep polling. Progress is decoration; it must never be
 *    able to fail, abort or misreport the analyze it describes.
 * 2. **Never overlap polls, and never wait forever.** A hung poll under a fixed
 *    interval would queue more requests (or stall the loop entirely). Each poll
 *    is aborted after POLL_TIMEOUT_MS and the next one is scheduled only after
 *    the previous settles.
 * 3. **Stop cleanly.** No timer may outlive `active` going false or the component
 *    unmounting, or a finished run keeps polling forever.
 * 4. **Elapsed time ticks on the client.** Server `elapsed_seconds` only updates
 *    when a poll succeeds; while the API is blocked the wall clock must still
 *    move or the UI looks hung.
 */
export function useAnalyzeProgress(
  dataset: string | null | undefined,
  windowMinutes: number,
  active: boolean,
): AnalyzeProgress | null {
  const [progress, setProgress] = useState<AnalyzeProgress | null>(null);
  const [elapsedTick, setElapsedTick] = useState(0);
  // Read inside the async loop so a stale closure cannot keep it alive.
  const activeRef = useRef(active);
  activeRef.current = active;
  /** Wall-clock start of this active run (client). Synced from server when a poll lands. */
  const startedAtRef = useRef<number | null>(null);
  const lastPollAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active || !dataset) return;

    let cancelled = false;
    let timer: number | undefined;
    startedAtRef.current = Date.now();
    lastPollAtRef.current = null;
    setElapsedTick(0);

    const poll = async () => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), POLL_TIMEOUT_MS);
      try {
        const p = await api.analyzeProgress(dataset, windowMinutes, {
          signal: controller.signal,
        });
        if (cancelled) return;
        lastPollAtRef.current = Date.now();
        // Align the client wall clock with the server's elapsed so a late poll
        // does not jump the timer backwards or forwards by more than a second.
        if (typeof p.elapsed_seconds === "number" && Number.isFinite(p.elapsed_seconds)) {
          startedAtRef.current = Date.now() - p.elapsed_seconds * 1000;
        }
        setProgress(p);
      } catch {
        // Swallowed on purpose — see (1) above. Timeout/abort and 500s mean "no news".
      } finally {
        window.clearTimeout(timeout);
      }
      if (cancelled || !activeRef.current) return;
      timer = window.setTimeout(poll, POLL_MS);
    };

    // Ask immediately so the first stage appears without a 1.5 s blank.
    poll();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [dataset, windowMinutes, active]);

  // Clear between runs so a new analyze never briefly shows the previous one's
  // 100%-complete state.
  useEffect(() => {
    if (active) setProgress(null);
  }, [active, dataset, windowMinutes]);

  // Client elapsed ticker — independent of whether polls are succeeding.
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setElapsedTick((n) => n + 1), 1_000);
    return () => window.clearInterval(id);
  }, [active, dataset, windowMinutes]);

  return useMemo(() => {
    if (!active && !progress) return null;
    if (!progress && !active) return null;
    const started = startedAtRef.current;
    const clientElapsed =
      active && started != null
        ? Math.max(0, (Date.now() - started) / 1000)
        : progress?.elapsed_seconds;
    // elapsedTick is only here to re-render every second while running.
    void elapsedTick;
    const staleSeconds =
      active && lastPollAtRef.current != null
        ? Math.max(0, (Date.now() - lastPollAtRef.current) / 1000)
        : null;
    if (!progress) {
      return {
        dataset: dataset || "",
        window_minutes: windowMinutes,
        status: "running" as const,
        message: "Starting pipeline…",
        percent: 0,
        elapsed_seconds: clientElapsed ?? 0,
        stale_seconds: staleSeconds,
      };
    }
    return {
      ...progress,
      elapsed_seconds: clientElapsed ?? progress.elapsed_seconds,
      stale_seconds: staleSeconds,
    };
  }, [progress, active, dataset, windowMinutes, elapsedTick]);
}

/** `93` → `1m 33s`. Returns null for absent/negative input so callers can hide the field. */
export function formatDuration(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return null;
  }
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rest = s % 60;
  if (m < 60) return rest ? `${m}m ${rest}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}
