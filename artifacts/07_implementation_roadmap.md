# Implementation Roadmap

**Project:** ERakshak — Frontend Redesign
**Version:** 1.0 · 2026-07-17

---

## Strategy

The existing frontend is a working v1 that correctly connects to the backend API. We are **not rewriting from scratch** — we're upgrading systematically. The stack (React 19 + Vite + TanStack Router/Query + Tailwind v4 + shadcn/ui) is kept. The redesign focuses on:

1. **Visualization quality** — D3 force graph, zoomable timeline, proper event rendering
2. **Investigation workflow** — per-entity drill-down, cross-page navigation, command palette
3. **Professional polish** — skeleton loaders, virtual scrolling, keyboard shortcuts, accessibility
4. **Code quality** — type cleanup, shared components, test coverage

---

## Sprint Overview

| Sprint | Theme | Duration | Critical Deliverables |
|--------|-------|----------|-----------------------|
| **1** | Foundation & Network Graph | 1 week | Type cleanup; shared loading/error/empty components; D3 force-directed graph |
| **2** | Timeline & Entity Workflow | 1 week | Zoomable timeline with jitter; per-entity filtering; entity detail upgrades |
| **3** | Investigation Flow & Search | 1 week | Cross-page entity navigation; command palette; correlation detail; detection drill-down |
| **4** | Polish & Performance | 1 week | Skeleton loaders; virtual scrolling; keyboard shortcuts; responsive breakpoints |
| **5** | Reports & Hardening | 1 week | Report generation; print stylesheet; integration tests; accessibility audit |

---

## Sprint 1 — Foundation & Network Graph

### Goal
Clean up the codebase foundation and deliver a production-quality network graph — the most visually impactful upgrade.

### Tasks

#### 1.1 Type Cleanup & Mock Data Removal
- **Create** `src/lib/types.ts` — move all display types (`Entity`, `Event`, `GraphNode`, etc.) from `mock-data.ts`
- **Update** all imports across routes and components
- **Delete** `src/lib/mock-data.ts`
- **Create** `src/lib/constants.ts` — risk band thresholds, event type maps, ID kind maps

#### 1.2 Shared Components
- **Create** `src/components/shared/loading-state.tsx` — reusable centered spinner with text
- **Create** `src/components/shared/error-state.tsx` — reusable error banner with retry button
- **Create** `src/components/shared/empty-state.tsx` — purposeful empty state with icon + guidance text
- **Replace** all inline loading/error patterns across 8 route files

#### 1.3 D3 Force-Directed Network Graph
- **Install** `d3-force`, `d3-selection`, `d3-zoom`, `d3-drag`
- **Create** `src/components/visualizations/network-graph.tsx` — D3 force simulation:
  - Nodes: sized by `degree`, colored by `risk_score`, glyph by entity kind
  - Edges: colored by kind (money=teal, comm=amber, shared_id=dashed muted)
  - Force layout: charge repulsion, link distance ∝ weight, center gravity
  - Interactions: drag nodes, zoom/pan canvas, click to select
  - Community clustering: optional hull/background coloring by `community`
  - Progressive rendering: show top-40 nodes, expand on request
- **Replace** static SVG in `_app.network.tsx` with the new component
- **Keep** the node detail panel (right side) — update to show centrality, degree, community

#### 1.4 Graph Legend & Controls
- Zoom controls (zoom in/out/reset buttons)
- Filter by edge type (money / comm / shared_id checkboxes)
- Node count indicator
- Strength slider (adjusts force simulation parameters)

### Verification
- Graph renders with force layout for demo dataset (~40 nodes, ~100 edges)
- Drag, zoom, pan all work
- Node selection updates the detail panel
- Mode toggle (money/comm) filters edges
- No regressions on other pages

---

## Sprint 2 — Timeline & Entity Workflow

### Goal
Rebuild the timeline visualization for real investigative use and establish per-entity filtering.

### Tasks

#### 2.1 Zoomable Timeline
- **Install** `d3-scale`, `d3-axis`, `d3-brush`
- **Create** `src/components/visualizations/timeline-canvas.tsx`:
  - Horizontal time axis with zoom (brush or scroll)
  - 3 swimlane tracks (transaction, call, IP session)
  - Event markers: colored by type, sized by significance (amount for txn, duration for call)
  - **Vertical jitter**: events at the same minute are vertically offset to prevent overlap
  - **Tooltip on hover**: show timestamp, entity, amount/duration, provenance
  - **Correlation bands**: semi-transparent overlays marking W windows
  - Time labels on each event marker (optional, shown at zoom level)
- **Replace** static timeline in `_app.timeline.tsx`

#### 2.2 Per-Entity Filtering
- **Add** entity selector to timeline header:
  - Dropdown/combobox: "All entities" or select specific entity
  - Populated from `useEntities()` data (top N by risk)
  - Filters events client-side by `entity_id`
- **Add** `?entity=<id>` search param to timeline route
- **Update** `useEvents()` to optionally accept entity filter (client-side)
- **Update** Entity Explorer's "Open timeline" button to navigate with `?entity=<id>`

#### 2.3 Entity Detail Panel Upgrade
- **Add** mini-timeline to entity detail panel: last 10 events rendered as a horizontal strip
- **Add** risk score breakdown:
  - Rule score (70% weight): list each rule with its weight and detail
  - ML score (30% weight): anomaly score value
  - Visual: stacked bar showing contribution
- **Add** identifier provenance: show which source file each identifier was extracted from
- **Add** connected entities: list of entities sharing identifiers or having money/comm edges

#### 2.4 Entity Table Sort
- Add column sort (click header to sort by risk, events, volume, label)
- Sort state persisted in URL search params

### Verification
- Timeline renders events for demo dataset with proper jitter
- Zoom in/out works smoothly
- Entity filter shows only that entity's events
- Navigating from Entity Explorer → Timeline preserves entity filter
- Entity detail shows risk breakdown

---

## Sprint 3 — Investigation Flow & Search

### Goal
Wire the full cross-page investigation workflow and add global search.

### Tasks

#### 3.1 Cross-Page Entity Context
- **Update** all "Show on graph" buttons → navigate to `/network?node=<entity_id>` → auto-select and center that node
- **Update** all "Open timeline" buttons → navigate to `/timeline?entity=<entity_id>` → filter events
- **Add** entity quick-link in correlation hits → click entity name → `/entities?id=<entity_id>` → auto-select in table
- **Add** breadcrumb trail: show navigation path (e.g., "Entities → Rakesh V. → Timeline")

#### 3.2 Command Palette
- **Wire** `cmdk` (already installed) as a global command palette
- **Trigger:** `Ctrl+K` / `⌘+K`
- **Search scope:** Entities (by label, identifier), Pages (by name), Detection rules
- **Actions:** Navigate to entity, open timeline, switch dataset, change window
- **Keyboard:** Arrow keys navigate, Enter selects, Esc closes

#### 3.3 Correlation Detail View
- **Upgrade** correlation hits on Overview page:
  - Show both entities in the pair (currently shows one)
  - Show all three evidence legs: call time, IP time, transaction time
  - Show delta between earliest and latest event
  - Clickable → navigates to timeline filtered to that time window
- **Add** dedicated correlation list page (or tab within Overview):
  - Full list of all correlation hits (up to 100 from API)
  - Sortable by entity, delta time, score
  - Expandable rows with full provenance for each leg

#### 3.4 Detection → Entity Drill-Down
- **Add** clickable entity count on detection cards → navigate to `/entities?rule=<rule_name>` → filter entity list to only those with that rule flag
- **Add** `?rule=<name>` search param to entities route
- **Update** entity table filtering to support rule-based filtering

### Verification
- Click "Show on graph" from entity detail → graph opens with that node centered and selected
- Click entity in correlation hit → entity explorer opens with that entity selected
- Ctrl+K opens command palette; can search and navigate to any entity
- Detection card → entity list → entity detail → timeline forms a complete drill-down chain

---

## Sprint 4 — Polish & Performance

### Goal
Professional-grade UX polish and performance optimizations.

### Tasks

#### 4.1 Skeleton Loaders
- **Create** skeleton components for each page layout:
  - `OverviewSkeleton` — shimmer blocks matching KPI strip + chart + table layout
  - `EntityTableSkeleton` — shimmer rows in table format
  - `TimelineSkeleton` — shimmer tracks
  - `GraphSkeleton` — centered shimmer circle
- Replace all `<Loader2>` spinner states with matching skeletons

#### 4.2 Virtual Scrolling
- **Install** `@tanstack/react-virtual`
- **Apply** to entity table (can have 200+ rows from API)
- **Apply** to event list in timeline detail panel
- **Apply** to correlation hits list

#### 4.3 Keyboard Shortcuts
- **Install** `react-hotkeys-hook`
- **Global shortcuts:**
  - `Ctrl+K` → Command palette (Sprint 3)
  - `Esc` → Close detail panels, clear selection
  - `1–6` → Quick-switch sidebar sections
- **Table shortcuts:**
  - `↑ / ↓` → Move selection in entity/event tables
  - `Enter` → Open selected item in detail panel
  - `←` → Return to table from detail panel
- **Timeline shortcuts:**
  - `+ / -` → Zoom in/out
  - `← / →` → Pan left/right

#### 4.4 Responsive Breakpoints
- **Mobile sidebar:** hamburger toggle below 768px
- **Stacked layouts:** master-detail becomes stacked (detail below table) below 1024px
- **Timeline:** horizontal scroll with touch support on mobile
- **Graph:** pinch-to-zoom on touch devices
- **KPI strip:** 2 columns on mobile, 5 on desktop

#### 4.5 Animations & Transitions
- Page transition: `animate-fade-up` (already implemented)
- Selection transitions: smooth background color change
- Panel open/close: slide animation (200ms ease-out)
- Graph node hover: scale(1.15) with transition
- Risk badge: subtle pulse on high-risk values

### Verification
- Page loads show skeleton → data fills in without layout shift
- Entity table scrolls smoothly with 200+ rows
- All keyboard shortcuts work as documented
- App is usable (not broken) on tablet-width viewports

---

## Sprint 5 — Reports & Hardening

### Goal
Complete the report workflow and harden the application for production readiness.

### Tasks

#### 5.1 Report Generation
- **Upgrade** report preview with additional sections:
  - Methodology (how the pipeline works — canned text)
  - Timeline chart (mini version of the timeline visualization)
  - Money flow summary with chart
  - Entity relationship summary
  - Risk scoring explanation
- **Add** print stylesheet (`@media print`) for browser-based PDF export
- **Add** "Copy to clipboard" for report text
- **Wire** export buttons when backend adds report API endpoints

#### 5.2 Upload Page
- **Add** clear instructions for manual file placement:
  - Step-by-step guide to placing files in `datasets/raw/<name>/`
  - Expected file formats (Bank: xlsx/csv/pdf, CDR: csv, IPDR: csv)
  - Profile naming conventions
- **Add** dataset refresh button (re-fetches `/v1/datasets` to show newly added folders)
- **Future-proof** with drag-and-drop UI that will wire to upload endpoint when available

#### 5.3 Integration Tests
- **Add** API client tests (mock fetch, verify request construction, error handling)
- **Add** mapper tests (verify DTO → display model transformations, edge cases)
- **Add** route guard tests (verify auth redirect behavior)
- **Add** component smoke tests (key pages render without crash)

#### 5.4 Accessibility Audit
- Run axe-core or similar tool on every page
- Add ARIA labels to icon-only buttons
- Add skip-to-content link
- Verify all interactive elements are keyboard-accessible
- Add `role` attributes where semantic HTML is insufficient
- Verify color contrast ratios

#### 5.5 Performance Audit
- Run Lighthouse on production build
- Audit bundle size with `npx vite-bundle-visualizer`
- Optimize D3 imports (only import needed modules)
- Verify code splitting (lazy routes loading)
- Add Web Worker for graph layout computation if needed

### Verification
- Report preview renders all sections with real data
- Print stylesheet produces a clean PDF from browser
- All tests pass
- Accessibility score ≥ 90 on Lighthouse
- Bundle size < 500KB initial load

---

## Dependency Additions Summary

| Sprint | Package | Purpose |
|--------|---------|---------|
| 1 | `d3-force`, `d3-selection`, `d3-zoom`, `d3-drag` | Force-directed network graph |
| 2 | `d3-scale`, `d3-axis`, `d3-brush` | Zoomable timeline |
| 4 | `@tanstack/react-virtual` | Virtual scrolling |
| 4 | `react-hotkeys-hook` | Keyboard shortcuts |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| D3 force layout performance with 100+ nodes | Medium | High | Progressive rendering; limit visible nodes; Web Worker |
| API latency on first analyze call | High | Medium | Skeleton loaders; "pipeline running" progress UI |
| Backend API gaps (no upload, no report export) | Certain | Medium | Frontend stubs with clear messaging; instructions for manual workflows |
| Timeline overlap with 500+ events at same minute | Medium | Medium | Aggregation at zoom-out; jitter at zoom-in |
| Tailwind v4 compatibility issues | Low | Low | Already working; no migration needed |

---

## Open Questions for You

> [!IMPORTANT]
> 1. **Should Sprint 1 start immediately, or do you want to refine any of the Phase 2 documents first?**

> [!IMPORTANT]
> 2. **Should the D3 network graph use SVG or Canvas rendering?** SVG is easier to style and interact with, but Canvas performs better at 100+ nodes. Recommendation: SVG for now, migrate to Canvas if performance issues arise.

> [!IMPORTANT]
> 3. **Do you want to add any additional pages** (e.g., a dedicated "Correlations" page separate from Overview, an audit log viewer, a case notes/annotations page)?

> [!NOTE]
> 4. **Phase 4 (Documentation Refinement)** was skipped because the frontend analysis confirmed that the existing frontend correctly mirrors the backend API contracts. No documentation updates were needed.
