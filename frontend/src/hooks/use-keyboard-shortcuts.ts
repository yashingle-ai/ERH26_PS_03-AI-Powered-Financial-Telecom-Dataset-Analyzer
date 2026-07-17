import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";

/**
 * Global keyboard shortcuts for the investigation platform.
 *
 * ⌘K / Ctrl+K  → Command palette (handled by CommandPalette itself)
 * G then O      → Overview
 * G then E      → Entities
 * G then T      → Timeline
 * G then N      → Network
 * G then D      → Detections
 * G then R      → Reports
 * ?              → Show shortcuts help (future)
 */
export function useKeyboardShortcuts() {
  const navigate = useNavigate();

  useEffect(() => {
    let gPending = false;
    let gTimer: ReturnType<typeof setTimeout> | null = null;

    const handler = (e: KeyboardEvent) => {
      // Skip if user is typing in an input/textarea
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
      ) {
        return;
      }

      // G + <key> sequences for page navigation
      if (e.key === "g" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        gPending = true;
        if (gTimer) clearTimeout(gTimer);
        gTimer = setTimeout(() => {
          gPending = false;
        }, 800);
        return;
      }

      if (gPending) {
        gPending = false;
        if (gTimer) clearTimeout(gTimer);
        e.preventDefault();

        const routes: Record<string, { to: string; search?: any }> = {
          o: { to: "/overview" },
          e: { to: "/entities", search: { id: undefined, rule: undefined } },
          t: { to: "/timeline", search: { entity: undefined } },
          n: { to: "/network" },
          d: { to: "/detections" },
          r: { to: "/reports" },
        };

        const route = routes[e.key];
        if (route) {
          navigate({ to: route.to, search: route.search } as any);
        }
      }
    };

    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      if (gTimer) clearTimeout(gTimer);
    };
  }, [navigate]);
}
