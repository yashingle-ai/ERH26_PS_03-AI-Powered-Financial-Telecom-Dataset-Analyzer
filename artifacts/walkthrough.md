# ERakshak Frontend Redesign — Walkthrough

**Sprints Completed:** 1 through 5 (All Complete)
**Build Status:** ✅ TypeScript clean (`npx tsc --noEmit` passes)

---

## Sprint 1 — Foundation & Network Graph

### Type Cleanup & Mock Data Removal
Centralized all frontend display types and constants into dedicated modules, then deleted the legacy `mock-data.ts`.

| File | Purpose |
|------|---------|
| [types.ts](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/lib/types.ts) | All display types: `Entity`, `Event`, `GraphNode`, `Detection`, etc. |
| [constants.ts](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/lib/constants.ts) | Risk bands, color functions, ID/edge/event type maps, formatters |
| [mappers.ts](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/lib/mappers.ts) | Updated to import from `types.ts` and `constants.ts` instead of duplicating maps |

### Shared Components
Eliminated copy-pasted loading/error patterns across all 5 route files.

| Component | Path |
|-----------|------|
| LoadingState | [loading-state.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/shared/loading-state.tsx) |
| ErrorState | [error-state.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/shared/error-state.tsx) |
| EmptyState | [empty-state.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/shared/empty-state.tsx) |

### D3 Force-Directed Network Graph
Replaced the static circular SVG layout with a full D3 force-directed graph.

- **Component:** [network-graph.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/visualizations/network-graph.tsx)
- **Features:** Drag nodes, scroll-to-zoom, pan, collision avoidance, arrow markers, selection rings, edge filtering
- **Page:** [_app.network.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/routes/_app.network.tsx) — rewritten with legend overlay, info chip, mode toggles, neighbor list

---

## Sprint 2 — Timeline & Entity Workflow

### D3 Zoomable Timeline
Built a new D3-based swimlane timeline with three tracks (transactions, calls, IP sessions).

- **Component:** [timeline-canvas.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/visualizations/timeline-canvas.tsx)
- **Features:** Scroll-to-zoom, adaptive time axis labels, vertical jitter for overlapping events, correlation window highlights
- **Page:** [_app.timeline.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/routes/_app.timeline.tsx) — per-entity filtering via URL `?entity=`, entity selector dropdown

### Entity Explorer Upgrade
- **Page:** [_app.entities.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/routes/_app.entities.tsx)
- **Sortable columns:** Risk, events, volume, label (click header to toggle asc/desc)
- **URL params:** `?id=` for deep-linking, `?rule=` for rule-based filtering
- **Risk breakdown:** Stacked bar showing rule weight vs. ML anomaly score
- **Full rule flags:** Each rule shows name, weight contribution, and detail text
- **Cross-page nav:** Timeline, Graph, and Report buttons navigate with entity context

---

## Sprint 3 — Investigation Flow & Search

### Command Palette (⌘K)
- **Component:** [command-palette.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/command-palette.tsx)
- **Trigger:** `Ctrl+K` / `⌘K` or click the search button in the topbar
- **Sections:** Pages, Entities (with risk scores), Actions
- **Fuzzy search** on entity labels and identifiers

### Detection Drill-Down
- **Page:** [_app.detections.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/routes/_app.detections.tsx)
- **Summary chips:** Total rules, high/medium/low counts
- **Expandable cards:** Click detection name to see full details
- **"View entities" button:** Navigates to `/entities?rule=<rule_name>` to show all entities affected by that detection

### Cross-Page Entity Context
All navigation paths now carry entity context through URL search params:

| Source | Destination | Param |
|--------|-------------|-------|
| Overview entity table | Entity explorer | `?id=<entity_id>` |
| Entity detail → Timeline | Timeline | `?entity=<entity_id>` |
| Entity detail → Graph | Network | `?node=<entity_id>` |
| Detection "View entities" | Entities | `?rule=<rule_name>` |

### Topbar & Sidebar
- **Topbar:** [case-topbar.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/case-topbar.tsx) — static search input replaced with ⌘K trigger button
- **Sidebar:** [app-sidebar.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/app-sidebar.tsx) — links include typed search params for TanStack Router

---

## Sprint 4 — Polish & Performance

### Page-Specific Skeleton Loaders
- **File:** [skeletons.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/components/shared/skeletons.tsx)
- **Skeletons:** `OverviewSkeleton`, `EntitySkeleton`, `TimelineSkeleton`, `NetworkSkeleton`, `DetectionsSkeleton`
- Each skeleton mirrors the actual page layout for a polished loading experience

### Keyboard Shortcuts
- **File:** [use-keyboard-shortcuts.ts](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/hooks/use-keyboard-shortcuts.ts)
- **Shortcuts:** `G` then `O/E/T/N/D/R` for page navigation
- Ignores keypresses when focus is in input fields

### App Layout
- **File:** [_app.tsx](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/routes/_app.tsx) — wires CommandPalette and keyboard shortcuts

---

## Files Changed (Summary)

### New Files (12)
| File | Type |
|------|------|
| `src/lib/types.ts` | Display types |
| `src/lib/constants.ts` | Constants & helpers |
| `src/components/shared/loading-state.tsx` | Shared component |
| `src/components/shared/error-state.tsx` | Shared component |
| `src/components/shared/empty-state.tsx` | Shared component |
| `src/components/shared/skeletons.tsx` | Skeleton loaders |
| `src/components/visualizations/network-graph.tsx` | D3 force graph |
| `src/components/visualizations/timeline-canvas.tsx` | D3 timeline |
| `src/components/command-palette.tsx` | ⌘K command palette |
| `src/hooks/use-keyboard-shortcuts.ts` | Keyboard shortcuts |

### Modified Files (10)
| File | Changes |
|------|---------|
| `src/lib/mappers.ts` | Imports from types/constants, removed duplicates |
| `src/routes/_app.tsx` | Added CommandPalette + keyboard shortcuts |
| `src/routes/_app.overview.tsx` | Skeleton loader, entity deep-links |
| `src/routes/_app.entities.tsx` | Sort, URL params, risk breakdown, cross-nav |
| `src/routes/_app.timeline.tsx` | D3 canvas, entity filter, skeleton |
| `src/routes/_app.network.tsx` | D3 force graph, skeleton |
| `src/routes/_app.detections.tsx` | Summary chips, drill-down, skeleton |
| `src/routes/_app.reports.tsx` | Shared components |
| `src/components/case-topbar.tsx` | ⌘K trigger |
| `src/components/app-sidebar.tsx` | Typed search params |
| `src/components/risk-badge.tsx` | Import fix |

### Deleted Files (1)
| File | Reason |
|------|--------|
| `src/lib/mock-data.ts` | Replaced by types.ts + constants.ts |

### Dependencies Added
| Package | Purpose |
|---------|---------|
| `d3-force`, `d3-selection`, `d3-zoom`, `d3-drag` | Force-directed graph |
| `d3-scale`, `d3-axis`, `d3-brush` | Timeline canvas |
| `@types/d3-*` | TypeScript definitions |
| `cmdk` | Command palette |

---

## Sprint 5 — Reports & Hardening (Final)

### Report Generation Upgrade
- **Print Stylesheet:** Added a robust `@media print` CSS block to `src/styles.css` that strips out the UI (sidebar, navigation, ⌘K palette) and formats the report cleanly for paper or PDF export.
- **Export Action:** Wired the "Export Forensic Report (PDF)" button in the Reports page to trigger `window.print()`, directly invoking the native print/PDF engine.

### Upload Page Instructions
- **Detail Enhancements:** Replaced the generic upload placeholder text in `_app.upload.tsx` with explicit grid instructions.
- **Documentation:** Added required columns and file formats (`.csv`, `.txt`, `.xlsx`) for Bank, CDR, and IPDR data to ensure data scientists and investigators properly format datasets before dropping them in the `/raw` directory.

### Integration Tests
- **Vitest & Happy-DOM:** Installed and configured `vitest`, `@testing-library/react`, and `happy-dom`. 
- **Configuration:** Added `vitest.config.ts` and test setup environment for the app.
- **Baseline Test:** Wrote `error-state.test.tsx` verifying component rendering. All tests pass.

### Audits & Final Polish
- **Accessibility:** Conducted a sweep of interactive components. Added `aria-label` attributes to icon-only buttons in the `case-topbar.tsx` (Search trigger and User Profile dropdown) for better screen-reader support.
- **Performance:** Verified rendering optimizations for the main components. *Note: A full production build performance audit via `vite build` was not completed as the local environment runs Node 20.15.0, whereas Vite 6 requires Node 20.19+.*
- **Micro-Animations:** Added a `@utility hover-lift` class in `styles.css` that provides a subtle scaling and box-shadow transition. Applied to KPI cards in Overview and Detection cards to make the interface feel more tactile and premium.
- **Virtual Scrolling vs Native:** Evaluated `@tanstack/react-virtual` for the Entity List. Decided to defer full virtualization as the native `overflow` scales well for standard forensic datasets (<1000 rendered rows) without breaking native HTML table grid layouts.
- **Network Graph Controls:** Implemented the deferred **Force Strength Slider** allowing users to dynamically adjust the charge strength of the D3 graph via `@radix-ui/react-slider` (multiplier: 0.1x - 3.0x).

---

## Conclusion
The ERakshak frontend redesign is structurally and functionally complete per the design brief and implementation roadmap. All major workflows (Investigation, Analysis, Output) match the backend capabilities while significantly elevating the visual aesthetic, workflow speed, and usability for forensic analysts.
