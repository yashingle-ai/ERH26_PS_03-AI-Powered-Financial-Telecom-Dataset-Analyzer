import { useEffect, useRef, useState } from "react";
import { api, type AnalyzeProgress } from "@/lib/api";

/** How often to ask the server where the pipeline has got to. */
const POLL_MS = 1_500;

/**
 * Poll `GET /v1/analyze/progress/{ds}` while an analyze is running.
 *
 * Why polling at all: `POST /v1/analyze` is synchronous and a real FIR case takes
 * 11–49 minutes, so the analyze request itself carries no intermediate signal. A
 * second, cheap request reports where the first one has reached.
 *
 * Three properties this hook must have, each learned from how the backend behaves:
 *
 * 1. **A failed poll is never fatal.** The pipeline is CPU-bound Python holding the
 *    GIL, so the whole API goes unresponsive during heavy stages — polls will hang
 *    or fail *while everything is working correctly*. Keep the last known state and
 *    keep polling. Progress is decoration; it must never be able to fail, abort or
 *    misreport the analyze it describes.
 * 2. **Never overlap polls.** A hung poll under a fixed interval would queue more
 *    requests behind it and pile up against an API that is already blocked. Each
 *    poll schedules the next one only after it settles.
 * 3. **Stop cleanly.** No timer may outlive `active` going false or the component
 *    unmounting, or a finished run keeps polling forever.
 */
export function useAnalyzeProgress(
  dataset: string | null | undefined,
  windowMinutes: number,
  active: boolean,
): AnalyzeProgress | null {
  const [progress, setProgress] = useState<AnalyzeProgress | null>(null);
  // Read inside the async loop so a stale closure cannot keep it alive.
  const activeRef = useRef(active);
  activeRef.current = active;

  useEffect(() => {
    if (!active || !dataset) return;

    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const p = await api.analyzeProgress(dataset, windowMinutes);
        if (cancelled) return;
        setProgress(p);
      } catch {
        // Swallowed on purpose — see (1) above. The analyze call reports its own
        // failure; a progress poll that 500s or times out means "no news".
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

  return progress;
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
