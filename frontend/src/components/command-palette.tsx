import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { Command } from "cmdk";
import { useNavigate } from "@tanstack/react-router";
import {
  Search, BarChart3, Users, Clock, Share2, ShieldAlert, FileText, Upload,
  User, Building2, Phone, CreditCard, X, FolderSearch, Settings,
} from "lucide-react";
import { useEntities, useDatasets } from "@/hooks/use-investigation-data";
import { mapEntity, mapDetections } from "@/lib/mappers";
import { riskColor } from "@/lib/constants";

/* ── Pages for quick navigation ──────────────────────── */

const PAGES = [
  { label: "Overview dashboard", to: "/overview", icon: BarChart3, search: {} },
  { label: "Investigations", to: "/investigations", icon: FolderSearch, search: {} },
  { label: "Entity explorer", to: "/entities", icon: Users, search: { id: undefined, rule: undefined } },
  { label: "Unified timeline", to: "/timeline", icon: Clock, search: { entity: undefined } },
  { label: "Network graph", to: "/network", icon: Share2, search: {} },
  { label: "Detections & risk", to: "/detections", icon: ShieldAlert, search: {} },
  { label: "Export report", to: "/reports", icon: FileText, search: {} },
  { label: "Upload files", to: "/upload", icon: Upload, search: {} },
  { label: "Settings", to: "/settings", icon: Settings, search: {} },
] as const;

/* ── Entity kind icon helper ─────────────────────────── */

function KindIcon({ kind }: { kind: string }) {
  const cls = "h-3.5 w-3.5";
  if (kind === "individual") return <User className={cls} />;
  if (kind === "merchant") return <Building2 className={cls} />;
  if (kind === "phone") return <Phone className={cls} />;
  return <CreditCard className={cls} />;
}

/* ── Component ────────────────────────────────────────── */

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const { data: entitiesData } = useEntities();
  const { data: datasetsData } = useDatasets();

  const entities = useMemo(
    () => (entitiesData?.items || []).map(mapEntity).slice(0, 30),
    [entitiesData]
  );

  const detections = useMemo(
    () => mapDetections(entitiesData?.items || []).slice(0, 10),
    [entitiesData]
  );

  const datasets = useMemo(
    () => datasetsData?.datasets || [],
    [datasetsData]
  );

  /* ⌘K / Ctrl+K hotkey */
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        e.stopPropagation();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  /* Autofocus input when dialog opens */
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [open]);

  const go = useCallback(
    (to: string, search?: Record<string, unknown>) => {
      setOpen(false);
      navigate({ to, search: (search ?? {}) as any });
    },
    [navigate]
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-md animate-in fade-in duration-150"
        onClick={() => setOpen(false)}
      />

      {/* Dialog — explicitly styled for visibility against dark backdrop */}
      <div
        className="relative mt-[12vh] w-full max-w-xl animate-in fade-in zoom-in-95 slide-in-from-top-2 duration-200"
        style={{ zIndex: 101 }}
      >
        <Command
          className="overflow-hidden rounded-xl shadow-2xl"
          style={{
            backgroundColor: "var(--overlay-bg)",
            border: "1px solid var(--overlay-border)",
            boxShadow: "var(--overlay-shadow-lg)",
          }}
          label="Command palette"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              setOpen(false);
            }
          }}
        >
          {/* Search input */}
          <div
            className="flex items-center gap-2.5 px-4"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <Search className="h-4 w-4 shrink-0 text-primary" />
            <Command.Input
              ref={inputRef}
              placeholder="Search pages, entities, rules, datasets…"
              className="text-mono h-12 w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground/60"
              style={{ color: "var(--foreground)" }}
            />
            <button
              onClick={() => setOpen(false)}
              className="flex h-6 items-center rounded border px-1.5 text-[10px] text-muted-foreground transition-colors hover:text-foreground"
              style={{
                borderColor: "var(--overlay-border)",
                backgroundColor: "var(--overlay-muted)",
              }}
            >
              ESC
            </button>
          </div>

          <Command.List
            className="max-h-[50vh] overflow-y-auto p-2"
            style={{ scrollbarWidth: "thin" }}
          >
            <Command.Empty className="py-8 text-center text-sm text-muted-foreground">
              No results found
            </Command.Empty>

            {/* ── Pages ──────────────────────────────────── */}
            <Command.Group
              heading="Pages"
              className="text-mono px-2 pb-1 pt-2 text-[10px] uppercase tracking-widest text-muted-foreground/70"
            >
              {PAGES.map((page) => (
                <Command.Item
                  key={page.to}
                  value={`page ${page.label}`}
                  onSelect={() => go(page.to, page.search)}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors aria-selected:bg-primary/15 aria-selected:text-primary"
                  style={{ color: "var(--foreground)" }}
                >
                  <page.icon className="h-4 w-4 text-muted-foreground" />
                  {page.label}
                </Command.Item>
              ))}
            </Command.Group>

            {/* ── Entities ───────────────────────────────── */}
            {entities.length > 0 && (
              <Command.Group
                heading="Entities"
                className="text-mono px-2 pb-1 pt-2 text-[10px] uppercase tracking-widest text-muted-foreground/70"
              >
                {entities.map((entity) => (
                  <Command.Item
                    key={entity.id}
                    value={`entity ${entity.label} ${entity.identifiers.map((i) => i.value).join(" ")}`}
                    onSelect={() =>
                      go("/entities", { id: entity.id, rule: undefined })
                    }
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors aria-selected:bg-primary/15 aria-selected:text-primary"
                    style={{ color: "var(--foreground)" }}
                  >
                    <KindIcon kind={entity.kind} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate">{entity.label}</div>
                      <div className="text-mono text-[10px] text-muted-foreground">
                        {entity.identifiers[0]?.value || entity.id}
                      </div>
                    </div>
                    <div
                      className="text-mono text-[11px] font-medium"
                      style={{ color: riskColor(entity.risk) }}
                    >
                      {entity.risk}
                    </div>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {/* ── Detection Rules ────────────────────────── */}
            {detections.length > 0 && (
              <Command.Group
                heading="Detection Rules"
                className="text-mono px-2 pb-1 pt-2 text-[10px] uppercase tracking-widest text-muted-foreground/70"
              >
                {detections.map((d) => (
                  <Command.Item
                    key={d.id}
                    value={`rule ${d.name} detection`}
                    onSelect={() =>
                      go("/entities", { id: undefined, rule: d.name })
                    }
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors aria-selected:bg-primary/15 aria-selected:text-primary"
                    style={{ color: "var(--foreground)" }}
                  >
                    <ShieldAlert className="h-4 w-4 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate">{d.name}</div>
                      <div className="text-mono text-[10px] text-muted-foreground">
                        {d.entities} entities · {d.band} risk
                      </div>
                    </div>
                    <span
                      className="text-mono text-[10px] font-medium"
                      style={{ color: d.band === "high" ? "var(--risk-high)" : d.band === "medium" ? "var(--risk-med)" : "var(--risk-low)" }}
                    >
                      +{d.weight}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {/* ── Datasets ───────────────────────────────── */}
            {datasets.length > 0 && (
              <Command.Group
                heading="Datasets"
                className="text-mono px-2 pb-1 pt-2 text-[10px] uppercase tracking-widest text-muted-foreground/70"
              >
                {datasets.map((ds) => (
                  <Command.Item
                    key={ds}
                    value={`dataset ${ds}`}
                    onSelect={() => go("/overview")}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors aria-selected:bg-primary/15 aria-selected:text-primary"
                    style={{ color: "var(--foreground)" }}
                  >
                    <FolderSearch className="h-4 w-4 text-muted-foreground" />
                    <div className="truncate">{ds.toUpperCase()}</div>
                    <span className="text-mono ml-auto text-[10px] text-muted-foreground">
                      datasets/raw/{ds}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {/* ── Quick Actions ──────────────────────────── */}
            <Command.Group
              heading="Quick Actions"
              className="text-mono px-2 pb-1 pt-2 text-[10px] uppercase tracking-widest text-muted-foreground/70"
            >
              <Command.Item
                value="View timeline for all entities"
                onSelect={() => go("/timeline", { entity: undefined })}
                className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors aria-selected:bg-primary/15 aria-selected:text-primary"
                style={{ color: "var(--foreground)" }}
              >
                <Clock className="h-4 w-4 text-muted-foreground" />
                View full timeline
              </Command.Item>
              <Command.Item
                value="Open network graph visualization"
                onSelect={() => go("/network")}
                className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors aria-selected:bg-primary/15 aria-selected:text-primary"
                style={{ color: "var(--foreground)" }}
              >
                <Share2 className="h-4 w-4 text-muted-foreground" />
                Open network graph
              </Command.Item>
              <Command.Item
                value="Export investigation report PDF"
                onSelect={() => go("/reports")}
                className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors aria-selected:bg-primary/15 aria-selected:text-primary"
                style={{ color: "var(--foreground)" }}
              >
                <FileText className="h-4 w-4 text-muted-foreground" />
                Export investigation report
              </Command.Item>
            </Command.Group>
          </Command.List>

          {/* Footer hints */}
          <div
            className="px-4 py-2.5"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <div className="text-mono flex items-center gap-4 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <kbd
                  className="rounded px-1"
                  style={{ border: "1px solid var(--overlay-border)", backgroundColor: "var(--overlay-muted)" }}
                >↑</kbd>
                <kbd
                  className="rounded px-1"
                  style={{ border: "1px solid var(--overlay-border)", backgroundColor: "var(--overlay-muted)" }}
                >↓</kbd>
                navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd
                  className="rounded px-1"
                  style={{ border: "1px solid var(--overlay-border)", backgroundColor: "var(--overlay-muted)" }}
                >↵</kbd>
                select
              </span>
              <span className="flex items-center gap-1">
                <kbd
                  className="rounded px-1"
                  style={{ border: "1px solid var(--overlay-border)", backgroundColor: "var(--overlay-muted)" }}
                >Esc</kbd>
                close
              </span>
            </div>
          </div>
        </Command>
      </div>
    </div>
  );
}
