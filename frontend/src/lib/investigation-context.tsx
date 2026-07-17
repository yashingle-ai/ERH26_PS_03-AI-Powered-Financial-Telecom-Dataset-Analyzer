import { createContext, useContext, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Entity } from "@/lib/types";

const DS_KEY = "erakshak.active_dataset";
const WIN_KEY = "erakshak.window_minutes";
const PINNED_KEY = "erakshak.pinned_entity";

export type BreadcrumbEntry = {
  id: string;
  label: string;
  page: string;
  timestamp: number;
};

type InvestigationContextValue = {
  dataset: string | null;
  windowMinutes: number;
  setDataset: (ds: string) => void;
  setWindowMinutes: (w: number) => void;
  /** Pinned entity — persists across page navigation */
  pinnedEntity: Entity | null;
  setPinnedEntity: (entity: Entity | null) => void;
  /** Entity IDs pinned as evidence */
  pinnedEvidence: string[];
  toggleEvidence: (entityId: string) => void;
  /** Breadcrumb trail of investigated entities */
  breadcrumbs: BreadcrumbEntry[];
  addBreadcrumb: (entry: Omit<BreadcrumbEntry, "timestamp">) => void;
  clearBreadcrumbs: () => void;
};

const InvestigationContext = createContext<InvestigationContextValue | null>(null);

export function InvestigationProvider({ children }: { children: ReactNode }) {
  const [dataset, setDatasetState] = useState<string | null>(() => {
    if (typeof window === "undefined") return "smoke";
    return localStorage.getItem(DS_KEY) || "smoke";
  });
  const [windowMinutes, setWindowState] = useState<number>(() => {
    if (typeof window === "undefined") return 10;
    const raw = localStorage.getItem(WIN_KEY);
    const n = raw ? Number(raw) : 10;
    return Number.isFinite(n) && n > 0 ? n : 10;
  });

  /* ── Pinned entity ──────────────────────────────────── */
  const [pinnedEntity, setPinnedEntityState] = useState<Entity | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const raw = sessionStorage.getItem(PINNED_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  const setPinnedEntity = useCallback((entity: Entity | null) => {
    setPinnedEntityState(entity);
    if (entity) {
      sessionStorage.setItem(PINNED_KEY, JSON.stringify(entity));
    } else {
      sessionStorage.removeItem(PINNED_KEY);
    }
  }, []);

  /* ── Pinned evidence ────────────────────────────────── */
  const [pinnedEvidence, setPinnedEvidence] = useState<string[]>([]);

  const toggleEvidence = useCallback((entityId: string) => {
    setPinnedEvidence((prev) =>
      prev.includes(entityId)
        ? prev.filter((id) => id !== entityId)
        : [...prev, entityId]
    );
  }, []);

  /* ── Breadcrumbs ────────────────────────────────────── */
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbEntry[]>([]);

  const addBreadcrumb = useCallback((entry: Omit<BreadcrumbEntry, "timestamp">) => {
    setBreadcrumbs((prev) => {
      // Don't add duplicate consecutive entries
      const last = prev[prev.length - 1];
      if (last && last.id === entry.id && last.page === entry.page) return prev;
      // Keep last 20 entries
      const next = [...prev, { ...entry, timestamp: Date.now() }];
      return next.slice(-20);
    });
  }, []);

  const clearBreadcrumbs = useCallback(() => setBreadcrumbs([]), []);

  /* ── Persist to localStorage ────────────────────────── */
  useEffect(() => {
    if (dataset) localStorage.setItem(DS_KEY, dataset);
  }, [dataset]);

  useEffect(() => {
    localStorage.setItem(WIN_KEY, String(windowMinutes));
  }, [windowMinutes]);

  const value = useMemo(
    () => ({
      dataset,
      windowMinutes,
      setDataset: (ds: string) => setDatasetState(ds),
      setWindowMinutes: (w: number) => setWindowState(w),
      pinnedEntity,
      setPinnedEntity,
      pinnedEvidence,
      toggleEvidence,
      breadcrumbs,
      addBreadcrumb,
      clearBreadcrumbs,
    }),
    [dataset, windowMinutes, pinnedEntity, setPinnedEntity, pinnedEvidence, toggleEvidence, breadcrumbs, addBreadcrumb, clearBreadcrumbs],
  );

  return (
    <InvestigationContext.Provider value={value}>
      {children}
    </InvestigationContext.Provider>
  );
}

export function useInvestigation() {
  const ctx = useContext(InvestigationContext);
  if (!ctx) throw new Error("useInvestigation must be used within InvestigationProvider");
  return ctx;
}
