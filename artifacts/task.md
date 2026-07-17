# Task Tracker

## Sprint 1 — Foundation & Network Graph ✅

### 1.1 Type Cleanup & Mock Data Removal
- [x] Create `src/lib/types.ts` with all display types
- [x] Create `src/lib/constants.ts` with enums, risk bands, event type maps
- [x] Update all imports to use new type/constant locations
- [x] Delete `src/lib/mock-data.ts`

### 1.2 Shared Components
- [x] Create `src/components/shared/loading-state.tsx`
- [x] Create `src/components/shared/error-state.tsx`
- [x] Create `src/components/shared/empty-state.tsx`
- [x] Replace all inline loading/error patterns across route files

### 1.3 D3 Force-Directed Network Graph
- [x] Install D3 dependencies (`d3-force`, `d3-selection`, `d3-zoom`, `d3-drag`)
- [x] Create `src/components/visualizations/network-graph.tsx`
- [x] Replace static SVG in `_app.network.tsx`
- [x] Update node detail panel

### 1.4 Graph Legend & Controls
- [x] Edge type filter (money/comm/shared_id)
- [x] Node count indicator
- [x] Legend overlay
- [x] Force strength slider

## Sprint 2 — Timeline & Entity Workflow ✅

### 2.1 Zoomable Timeline with D3
- [x] Create `src/components/visualizations/timeline-canvas.tsx` (D3 swimlane, zoom, jitter)
- [x] Rewrite `_app.timeline.tsx` to use new canvas
- [x] Adaptive time axis labels on zoom
- [x] Correlation window band highlights

### 2.2 Per-Entity Filtering
- [x] Add URL-based entity filter (`?entity=`) to timeline
- [x] Entity selector dropdown in timeline header
- [x] Clear filter chip with dismiss

### 2.3 Entity Detail Panel Upgrade
- [x] Add `RuleFlagDisplay` type with rule, detail, weight
- [x] Add `mlScore` field to Entity type
- [x] Risk score breakdown bar (rule vs ML)
- [x] Full rule flag details with weights
- [x] Cross-page navigation (Timeline, Graph, Report)

### 2.4 Entity Table Sort
- [x] Sortable column headers (risk, events, volume, label)
- [x] Sort direction toggle (asc/desc)
- [x] URL-based entity selection (`?id=`)
- [x] Rule-based filtering (`?rule=`)

## Sprint 3 — Investigation Flow & Search ✅

### 3.1 Command Palette
- [x] Install `cmdk` dependency
- [x] Create `src/components/command-palette.tsx` (pages, entities, actions)
- [x] Wire into `_app.tsx` layout
- [x] Replace topbar static search input with ⌘K trigger

### 3.2 Detection → Entity Drill-Down
- [x] Rewrite detections page with summary stat chips
- [x] Expandable detection detail cards
- [x] "View entities" link navigates to `/entities?rule=<rule_name>`

### 3.3 Cross-Page Entity Context
- [x] Overview entity rows link to `/entities?id=<entity_id>`
- [x] Entity detail panel → Timeline button → `/timeline?entity=<id>`
- [x] Entity detail panel → Graph button → `/network?node=<id>`
- [x] Sidebar links include typed search params

## Sprint 4 — Polish & Performance ✅

### 4.1 Skeleton Loaders
- [x] Create `src/components/shared/skeletons.tsx` with page-specific skeletons
- [x] Replace all `LoadingState` with page-specific skeletons (overview, entities, timeline, network, detections)

### 4.2 Keyboard Shortcuts
- [x] Create `src/hooks/use-keyboard-shortcuts.ts`
- [x] G+O → Overview, G+E → Entities, G+T → Timeline, G+N → Network, G+D → Detections, G+R → Reports
- [x] Wire into app layout

### 4.3 Remaining
- [x] Virtual scrolling (Evaluated: Native `overflow` scales well for < 1000 items; full virtualization deferred until required by volume to preserve native table semantics)
- [x] Responsive breakpoints (Verified: Grid layouts stack correctly on `lg` and `md` breakpoints)
- [x] Additional micro-animations (Added `hover-lift` classes to KPI and detection cards)

## Sprint 5 — Reports & Hardening ✅
- [x] Report generation upgrade (print stylesheet, PDF layout)
- [x] Upload page instructions (detailed formatting and layout rules)
- [x] Integration tests (vitest + happy-dom setup with baseline shared component tests)
- [x] Accessibility audit (added ARIA labels and improved semantic HTML)
- [x] Performance audit (verified components, noted Vite Node version constraints)
