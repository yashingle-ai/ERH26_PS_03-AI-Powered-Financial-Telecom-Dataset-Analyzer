# Frontend Review & Critique

**Project:** ERakshak — Existing Frontend Analysis
**Version:** 1.0 · 2026-07-17

---

## Executive Summary

The existing frontend is a **competent v1 implementation** that successfully connects to the backend API and renders real investigation data. The design language (deep navy, teal accent, monospace data labels) is appropriate for a forensic tool. However, it has significant gaps in **data visualization quality** (static SVG graph, no true force layout), **interactivity** (no per-entity filtering, no keyboard shortcuts, no command palette), and **professional polish** (loading states are minimal, error states are identical, no skeletons, no empty state illustrations).

**Verdict:** The foundation is solid. The architecture, routing, state management, and API layer are well-implemented. The visual layer and interaction model need substantial upgrades.

---

## Architecture Assessment

### ✅ What's Done Well

| Area | Observation |
|------|-------------|
| **Routing** | TanStack Router with file-based convention; auth guards via `beforeLoad`; proper head management for SEO |
| **State management** | Clean separation: React Query for server state, Context for investigation state, URL for page state |
| **API client** | Fully typed `api.ts` with error handling, auth headers, 401 redirect, and consistent error parsing |
| **Data hooks** | `useAnalyze()`, `useEntities()`, `useEvents()`, `useGraph()` — scoped by dataset + window, with stale time |
| **Mappers** | Separate mapper layer transforms backend DTOs to display models — good separation of concerns |
| **Design tokens** | CSS custom properties with oklch colors, risk bands, event type colors — consistent and extensible |
| **Component library** | shadcn/ui primitives properly installed (Radix + CVA); sensible defaults |

### ⚠️ What Needs Improvement

| Area | Issue | Impact |
|------|-------|--------|
| **Mock data still present** | [mock-data.ts](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/lib/mock-data.ts) exports 340 lines of hardcoded mock data. Several components import types from it. | Confusion about what's live vs. mock. Should be deleted once all pages use API data. |
| **Type definitions split** | Display types (`Entity`, `Event`, `GraphNode`, etc.) are defined in `mock-data.ts` instead of a dedicated types file | Poor discoverability; creates a dependency on the mock file |
| **No error boundary per route** | Only the root error boundary exists. Route-level errors crash the entire app. | Should have per-route error boundaries |
| **No loading skeletons** | All loading states are a centered spinner with text. No skeleton screens to maintain layout stability. | Jarring layout shifts on data load |

---

## Data Layer Assessment

### ✅ Correct

- All 5 API endpoints are wired with typed hooks
- Query keys correctly include `(dataset, windowMinutes)` for cache isolation
- `staleTime: 60_000` prevents unnecessary re-fetching
- Mapper functions handle null/missing fields with fallbacks

### ⚠️ Issues

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 1 | **No per-entity event filtering** | `useEvents()` fetches all events (up to 500). No `entity_id` param available on API. Client-side filtering not implemented. | **Critical** — per-entity timeline is the core workflow |
| 2 | **Entity kind derivation is fragile** | [mappers.ts:31-40](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/lib/mappers.ts#L31-L40) uses string matching on label ("traders", "llp") to detect merchants | **Medium** — should use entity_type from backend when available |
| 3 | **Correlation hit score is fabricated** | [mappers.ts:101](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/lib/mappers.ts#L101) creates a synthetic score: `70 + window_minutes/2`. Not from backend. | **Medium** — misleading to investigators |
| 4 | **No retry logic** | React Query retries are at default (3), but no exponential backoff configuration | **Low** |
| 5 | **No prefetching** | Navigation doesn't prefetch next page's data | **Low** — nice optimization |

---

## Visual Design Assessment

### ✅ Strong Points

- **Color palette** is professional and appropriate — deep navy with teal accent reads as "forensic intelligence"
- **Typography** (IBM Plex Sans + Mono) is excellent — mono for data, sans for labels
- **Risk color system** (teal/amber/crimson) is clear and color-blind-accessible
- **Table styling** is dense and scannable — compact rows, mono headers, right-aligned numbers
- **Login page** is atmospheric and memorable — gradient glow, grid background, glass card

### ⚠️ Issues

| # | Issue | Severity |
|---|-------|----------|
| 5 | **Graph is static circular layout** — nodes placed on a circle using trigonometry. No force simulation, no physics, no dragging. Looks like a placeholder diagram, not an investigation tool. | **Critical** |
| 6 | **No zoom/pan on graph or timeline** — both visualizations are fixed-viewport. Can't zoom into dense clusters or scroll through 24h of events. | **High** |
| 7 | **Timeline dots are tiny and overlapping** — 12×12px dots at the same minute overlap without any collision avoidance. Dense datasets will be unreadable. | **High** |
| 8 | **KPI cards overused** — both Investigations and Overview pages have KPI strips. The Overview has 5 identical boxes that could be a more compact inline strip. | **Medium** |
| 9 | **No empty state illustrations** — when there's no data, pages show plain text "No items". Should have a purposeful empty state. | **Medium** |
| 10 | **Report preview is hard to distinguish from the app** — the "white paper" report is rendered inline with subtle borders. It should feel more like a print preview. | **Low** |

---

## Page-by-Page Critique

### Login Page — **Grade: A**
- Atmospheric design with gradient glow and grid background
- Glass card login form is polished
- Clear error messaging
- Pre-filled credentials for dev mode
- **Improvement:** Add a "connecting to API…" health check indicator

### Investigations Page — **Grade: B+**
- Good data density — all critical fields visible in the table
- KPI summary at top provides context
- Search and filter controls are present
- **Issues:** Status filters don't actually filter (just styled buttons). Risk band badges in the filter bar are decorative. `useQueries` triggers parallel analyze calls for every dataset — could be expensive.

### Overview Page — **Grade: B**
- Good layout — KPIs → charts → tables/lists
- Money flow area chart is well-styled with gradients
- Risk distribution bar chart works
- Entity table is compact and useful
- Correlation hits list shows the key evidence
- **Issues:** Action buttons in header are generic. No way to filter by entity. No date range selector for the money flow chart. Correlation hit entities show only one entity (should show pair).

### Timeline Page — **Grade: C+**
- Concept is correct — 24h axis with 3 tracks
- Track toggle buttons work
- Correlation window bands are visually clear
- **Critical issues:** No entity filter → shows ALL events → overwhelming. No zoom → can't inspect dense clusters. No time labels on event dots. Detail panel is very basic — just key-value pairs. Events overlap without jitter.

### Network Graph Page — **Grade: C**
- The concept is right (node-link diagram with money + comm overlays)
- Mode toggle works
- Node selection and neighbor list work
- Legend is present
- **Critical issues:** **Circular layout is unacceptable for production.** No force simulation. No drag. No zoom/pan. Large graphs will be an overlapping mess. Node glyphs (◈ ☎ ◉) are hard to distinguish at small sizes. "Expand subgraph" button does nothing.

### Entity Explorer — **Grade: B+**
- Master-detail layout is correct
- Search works (client-side across labels + identifiers)
- Detail panel shows identifiers, risk gauge, flags, actions
- Kind icons are helpful
- **Issues:** "Open timeline" and "Show on graph" buttons don't pass the entity ID — they navigate without filter context. Volume display assumes lakhs (could be misleading for very large or very small values). No sort controls on the table.

### Detections Page — **Grade: B**
- Card list with severity filtering is appropriate
- Rule aggregation from entity flags is clever
- Weight display is useful
- **Issues:** No link from detection → affected entities. Evidence count is just the number of detail strings, not actual evidence items. Cards could use expandable detail sections.

### Reports Page — **Grade: B-**
- Print preview concept is good — white background with formal styling
- Case narrative auto-generates from analyze data
- **Issues:** Preview is very minimal (3 sections). No STR template. Export buttons are non-functional (expected, since API doesn't have export endpoints). No print stylesheet for actual browser printing.

### Upload Page — **Not reviewed in depth**
- Non-functional (no backend upload endpoint)
- Should show clear instructions about `datasets/raw/` folder structure until API is wired

### Settings Page — **Not reviewed in depth**
- Basic form layout — acceptable for current scope

---

## Prioritized Improvements

### 🔴 Critical (Must-Fix for Professional Quality)

| # | Issue | Solution |
|---|-------|----------|
| C1 | **Network graph uses static circular layout** | Implement D3 force-directed simulation with drag, zoom/pan, and progressive rendering |
| C2 | **No per-entity filtering on timeline or events** | Add entity_id as a route search param; filter events client-side; add entity selector to timeline |
| C3 | **Upload page is non-functional** | Either wire to a backend upload endpoint or provide clear file-placement instructions |
| C4 | **Mock data types still imported** | Move display types to a dedicated `types.ts`; delete mock data file |

### 🟠 High Priority

| # | Issue | Solution |
|---|-------|----------|
| H1 | **No zoom/pan on timeline** | Implement brush zoom or scroll zoom on the 24h axis |
| H2 | **No virtual scrolling for large entity lists** | Add `@tanstack/react-virtual` for tables with 100+ rows |
| H3 | **Loading states are generic spinners** | Implement skeleton loaders that match the page layout |
| H4 | **Timeline events overlap without jitter** | Add vertical jitter or stacking for events at the same minute |
| H5 | **Graph node sizing doesn't use centrality/degree** | Size nodes by degree; color by risk; use centrality for layout weight |
| H6 | **Navigation doesn't preserve entity context** | "Open timeline" from entity explorer should navigate with `?entity=<id>` |

### 🟡 Medium Priority

| # | Issue | Solution |
|---|-------|----------|
| M1 | **Correlation hit score is fabricated** | Show window delta time or remove the score; don't invent numbers |
| M2 | **Status filters on Investigations page don't work** | Wire filter buttons to actual filtering logic |
| M3 | **No command palette** | `cmdk` is already installed — implement Ctrl+K global search |
| M4 | **No keyboard shortcuts** | Add arrow key table navigation, Esc to close panels |
| M5 | **Entity kind detection uses label heuristics** | Prefer `entity_type` from backend; fall back to identifier composition |
| M6 | **No detection → entity drill-down** | Link "N entities" on detection cards to filtered entity list |
| M7 | **No responsive breakpoints implemented** | Add mobile sidebar toggle and stacked layouts |

### 🟢 Low Priority

| # | Issue | Solution |
|---|-------|----------|
| L1 | **No empty state illustrations** | Add purposeful empty states with guidance text |
| L2 | **Report preview is minimal** | Add more sections: methodology, timeline chart, money-flow summary |
| L3 | **No date range selector on money flow chart** | Add a time range brush or dropdown |
| L4 | **No toast notifications for successful operations** | Add success toasts for login, analysis completion |
| L5 | **No dark/light theme toggle** | Currently dark-only; add toggle in settings (low priority for analyst tool) |

---

## Code Quality Notes

| Metric | Assessment |
|--------|-----------|
| **TypeScript strictness** | Good — types are defined and used consistently |
| **Component size** | Acceptable — largest is `_app.overview.tsx` at 225 lines. Should decompose into smaller components. |
| **Code duplication** | Some — loading/error patterns are copy-pasted across pages. Should extract shared components. |
| **Naming conventions** | Consistent — file-based routing names, PascalCase components, camelCase functions |
| **Test coverage** | None — no frontend tests exist. Should add at minimum: API client tests, mapper tests, key interaction tests. |
| **Bundle size** | Not measured — should audit with `npx vite-bundle-visualizer` |
| **Accessibility** | Minimal — tables use proper `<th>` elements, but no ARIA labels, no skip links, no focus management |
