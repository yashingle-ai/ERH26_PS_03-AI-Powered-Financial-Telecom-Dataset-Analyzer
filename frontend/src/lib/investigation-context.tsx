import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

const DS_KEY = "erakshak.active_dataset";
const WIN_KEY = "erakshak.window_minutes";

type InvestigationContextValue = {
  dataset: string | null;
  windowMinutes: number;
  setDataset: (ds: string) => void;
  setWindowMinutes: (w: number) => void;
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
    }),
    [dataset, windowMinutes],
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
