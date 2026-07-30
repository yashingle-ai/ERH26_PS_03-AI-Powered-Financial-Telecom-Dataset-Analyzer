import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useInvestigation } from "@/lib/investigation-context";

export function useDatasets() {
  return useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.datasets(),
  });
}

export function useAnalyze(dataset?: string | null) {
  const { dataset: active, windowMinutes } = useInvestigation();
  const ds = dataset ?? active;
  return useQuery({
    queryKey: ["analyze", ds, windowMinutes],
    queryFn: () => api.analyze(ds!, windowMinutes),
    enabled: Boolean(ds),
    staleTime: 60_000,
  });
}

export function useEntities(dataset?: string | null) {
  const { dataset: active, windowMinutes } = useInvestigation();
  const ds = dataset ?? active;
  return useQuery({
    queryKey: ["entities", ds, windowMinutes],
    queryFn: () => api.entities(ds!, windowMinutes, 200, 0),
    enabled: Boolean(ds),
    staleTime: 60_000,
  });
}

export function useEvents(dataset?: string | null) {
  const { dataset: active, windowMinutes } = useInvestigation();
  const ds = dataset ?? active;
  return useQuery({
    queryKey: ["events", ds, windowMinutes],
    queryFn: () => api.events(ds!, windowMinutes, 500, 0),
    enabled: Boolean(ds),
    staleTime: 60_000,
  });
}

export function useGraph(dataset?: string | null) {
  const { dataset: active, windowMinutes } = useInvestigation();
  const ds = dataset ?? active;
  return useQuery({
    queryKey: ["graph", ds, windowMinutes],
    queryFn: () => api.graph(ds!, windowMinutes),
    enabled: Boolean(ds),
    staleTime: 60_000,
  });
}

/** FR-18 risk heat map: entities x typologies. */
export function useRiskHeatmap(dataset?: string | null, top = 20) {
  const { dataset: active, windowMinutes } = useInvestigation();
  const ds = dataset ?? active;
  return useQuery({
    queryKey: ["risk-heatmap", ds, windowMinutes, top],
    queryFn: () => api.riskHeatmap(ds!, windowMinutes, top),
    enabled: Boolean(ds),
    staleTime: 60_000,
  });
}
