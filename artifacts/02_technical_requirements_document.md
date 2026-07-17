# Technical Requirements Document (TRD)

**Project:** ERakshak — Frontend Redesign
**Version:** 1.0 · 2026-07-17

---

## 1. Frontend Framework

### Decision: React 19 + Vite + TanStack Router + TanStack Query

**Already in place.** The existing frontend uses this exact stack. No migration needed.

| Layer | Choice | Justification |
|-------|--------|---------------|
| **UI Library** | React 19 | Latest stable; concurrent features; hooks-first API |
| **Build** | Vite 8 | Fast HMR; ESM-native; plugin ecosystem |
| **Routing** | TanStack Router | Type-safe file-based routing; loader/beforeLoad guards; head management |
| **Server State** | TanStack Query v5 | Cache, dedup, retry, stale-while-revalidate; perfect for the read-heavy investigation UX |
| **Bundler** | Bun (runtime) | Already configured; fast installs |

**Rationale:** These are production-grade choices aligned with the PS suggestion (React + D3). TanStack Router provides type-safe routing with search params — critical for shareable investigation deep-links (e.g., `/entities?entity=e-001&tab=timeline`). TanStack Query handles the API-centric data layer cleanly.

---

## 2. State Management

### Three-tier model

| Tier | Tool | Contains |
|------|------|----------|
| **Server state** | TanStack Query | All backend data: entities, events, graph, correlations, risk scores. Query keys scoped by `(dataset, windowMinutes)`. Stale time 60s. |
| **UI state** | React Context + `useState` | Active investigation context (dataset, window), sidebar state, selected entity, selected event, filter states, panel visibility |
| **URL state** | TanStack Router search params | Current page, active entity ID, active tab, filter params — enables deep-linking and browser back/forward |

### Investigation Context (already implemented)

```typescript
type InvestigationContextValue = {
  dataset: string | null;        // Active dataset folder name
  windowMinutes: number;         // Correlation window W
  setDataset: (ds: string) => void;
  setWindowMinutes: (w: number) => void;
};
```

Persisted to `localStorage` across sessions. All query hooks consume this context automatically.

### State NOT to manage client-side
- Entity data, event data, graph data → always from server via React Query
- Auth tokens → `localStorage` (already implemented)
- Never duplicate backend computation on the frontend

---

## 3. Routing

### Route Structure

```
/                         → Redirect to /login or /investigations
/login                    → Authentication (public)
/_app                     → Auth-guarded layout (sidebar + topbar)
  /investigations         → Dataset list (case registry)
  /overview               → Case overview (KPIs, charts, top risk, correlation hits)
  /upload                 → File upload & ingestion management
  /timeline               → Unified timeline (24h axis, 3 tracks)
  /network                → Network graph (money-flow + communication overlay)
  /entities               → Entity explorer (table + detail panel)
  /detections             → Aggregated detection rules with severity filtering
  /reports                → Report preview + export
  /settings               → Configuration (window W, theme, API)
```

### Navigation Guards
- `/_app` layout runs `beforeLoad` that checks `isAuthenticated()` → redirects to `/login` if false
- 401 responses from any API call clear the session and redirect to `/login`
- Default redirect: `/` → `/investigations`

### Deep-link Strategy
- Entity IDs as search params: `/entities?id=<entity_id>&tab=identifiers`
- Timeline entity filter: `/timeline?entity=<entity_id>`
- Network node focus: `/network?node=<entity_id>&mode=money`
- All params are optional — pages work without them

---

## 4. Component Architecture

### Design System Layers

```
Primitives (shadcn/ui)
  └─ Design Tokens (colors, typography, spacing)
      └─ Domain Components (RiskBadge, ProvenanceTag, EntityRow)
          └─ Composite Surfaces (EntityDetailPanel, TimelineTrack)
              └─ Page Layouts (OverviewPage, EntityExplorerPage)
```

### Component Categories

| Category | Examples | Principle |
|----------|----------|-----------|
| **Primitives** | Button, Input, Table, Dialog, Tooltip | shadcn/ui (Radix + CVA). No modifications to primitives. |
| **Data Display** | RiskBadge, RiskGauge, ProvenanceTag, EventChip, IdentifierPill | Small, single-responsibility. Accept data props, no fetching. |
| **Containers** | EntityTable, TimelineCanvas, GraphCanvas, CorrelationList | Manage layout and selection state. May compose data display components. |
| **Panels** | EntityDetailPanel, EventInspector, NodeInspector | Right-side detail views. Accept a selected item, display full details. |
| **Visualizations** | TimelineView, NetworkGraph, MoneyFlowChart, RiskDistribution | D3.js or Recharts. Encapsulate rendering logic. Accept data + callbacks. |
| **Pages** | Each route file is a page. Orchestrate containers + panels. | Pages own the layout grid. Fetch data via hooks. |

### Rules
- Components never call API directly — they receive data as props or consume React Query hooks
- No business logic in components — mappers and utils handle transformations
- All components must handle loading, empty, and error states

---

## 5. API Communication Strategy

### Typed Client (already implemented)

[api.ts](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/lib/api.ts) provides a fully typed API client:

```typescript
const api = {
  login(username, password): Promise<TokenResponse>
  health(): Promise<{status: string}>
  datasets(): Promise<{datasets: string[]}>
  analyze(dataset, windowMinutes, persist): Promise<AnalyzeResponse>
  entities(dataset, window, limit, offset): Promise<{total, items}>
  events(dataset, window, limit, offset, eventType?): Promise<{total, items}>
  graph(dataset, window): Promise<GraphPayload>
}
```

### Request Lifecycle
1. Build request with auth header (`Bearer <token>`)
2. On 401 → clear session, redirect to login
3. Parse response as JSON; extract error schema `{error: {code, message}}`
4. Throw `ApiError` on non-ok responses

### Data Hooks (already implemented)

[use-investigation-data.ts](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/frontend/src/hooks/use-investigation-data.ts):

| Hook | Query Key | API Call |
|------|-----------|----------|
| `useDatasets()` | `["datasets"]` | `GET /v1/datasets` |
| `useAnalyze(ds?)` | `["analyze", ds, windowMinutes]` | `POST /v1/analyze` |
| `useEntities(ds?)` | `["entities", ds, windowMinutes]` | `GET /v1/entities/{ds}` |
| `useEvents(ds?)` | `["events", ds, windowMinutes]` | `GET /v1/events/{ds}` |
| `useGraph(ds?)` | `["graph", ds, windowMinutes]` | `GET /v1/graph/{ds}` |

### Caching Strategy
- `staleTime: 60_000` (60 seconds) — prevents re-fetching during a session
- Query keys include `(dataset, windowMinutes)` — changing either triggers a fresh fetch
- Pipeline results are cached server-side via `@lru_cache(maxsize=8)` — second requests for the same dataset+window are fast

### Future Additions Needed
- **Retry with backoff** on 5xx errors (React Query supports this)
- **Request cancellation** on component unmount
- **Prefetching** on navigation intent (hover on sidebar link → prefetch)

---

## 6. Database / Provider Assumptions

- Backend uses **SQLite** (default) or **PostgreSQL** (via `DATABASE_URL`) — frontend is agnostic
- All data access is through the FastAPI REST API — no direct database connections
- File uploads go to `datasets/raw/` on the server filesystem — no blob storage from frontend

---

## 7. Third-Party Libraries

### Already installed (keep)

| Library | Purpose | Version |
|---------|---------|---------|
| `@tanstack/react-query` | Server state management | ^5.101 |
| `@tanstack/react-router` | Type-safe routing | ^1.170 |
| `@tanstack/react-start` | SSR capabilities | ^1.168 |
| `recharts` | Statistical charts (area, bar) | ^2.15 |
| `lucide-react` | Icon set | ^0.575 |
| `sonner` | Toast notifications | ^2.0 |
| `react-resizable-panels` | Resizable split panels | ^4.6 |
| `date-fns` | Date formatting | ^4.1 |
| `zod` | Runtime validation | ^3.24 |
| `shadcn/ui` primitives | UI components (via Radix) | various |
| `tailwindcss v4` | Utility CSS | ^4.2 |

### To add

| Library | Purpose | Justification |
|---------|---------|---------------|
| `d3-force` + `d3-selection` | Force-directed graph layout | NetworkX-style graph rendering; PS requirement |
| `@tanstack/react-virtual` | Virtualized lists/tables | Entity lists can have 500+ rows |
| `react-hotkeys-hook` | Keyboard shortcuts | Investigator efficiency (Ctrl+K search, arrow navigation) |
| `downshift` or `cmdk` | Command palette | Already has `cmdk` — use for global search |

### Do NOT add
- State management libraries (Redux, Zustand, Jotai) — React Query + Context is sufficient
- Animation libraries (Framer Motion) — CSS transitions and D3 transitions suffice
- Full charting suites (Chart.js, Highcharts) — Recharts covers the needed charts; D3 covers custom visualizations

---

## 8. Folder Structure

```
frontend/src/
├── components/
│   ├── ui/                    # shadcn/ui primitives (unchanged)
│   ├── domain/                # ERakshak-specific components
│   │   ├── risk-badge.tsx
│   │   ├── provenance-tag.tsx
│   │   ├── event-chip.tsx
│   │   ├── identifier-pill.tsx
│   │   └── entity-row.tsx
│   ├── panels/                # Detail/inspector panels
│   │   ├── entity-detail-panel.tsx
│   │   ├── event-inspector.tsx
│   │   └── node-inspector.tsx
│   ├── visualizations/        # Charts and graphs
│   │   ├── timeline-canvas.tsx
│   │   ├── network-graph.tsx
│   │   ├── money-flow-chart.tsx
│   │   └── risk-distribution.tsx
│   ├── layout/                # Shell components
│   │   ├── app-sidebar.tsx
│   │   ├── case-topbar.tsx
│   │   └── page-header.tsx
│   └── shared/                # Cross-cutting
│       ├── loading-state.tsx
│       ├── error-state.tsx
│       └── empty-state.tsx
├── hooks/
│   ├── use-investigation-data.ts
│   ├── use-keyboard-shortcuts.ts
│   └── use-mobile.tsx
├── lib/
│   ├── api.ts                 # Typed API client
│   ├── auth.ts                # Token management
│   ├── mappers.ts             # Backend DTO → frontend model
│   ├── investigation-context.tsx
│   ├── constants.ts           # Enums, risk bands, event types
│   └── utils.ts               # Formatting helpers
├── routes/                    # File-based routing (TanStack Router)
│   ├── __root.tsx
│   ├── index.tsx
│   ├── login.tsx
│   ├── _app.tsx               # Auth-guarded layout
│   ├── _app.investigations.tsx
│   ├── _app.overview.tsx
│   ├── _app.upload.tsx
│   ├── _app.timeline.tsx
│   ├── _app.network.tsx
│   ├── _app.entities.tsx
│   ├── _app.detections.tsx
│   ├── _app.reports.tsx
│   └── _app.settings.tsx
├── styles.css                 # Design tokens + global styles
├── router.tsx
└── server.ts
```

---

## 9. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Backend API base URL |

### Should add

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_DEFAULT_DATASET` | `smoke` | Default dataset on first visit |
| `VITE_DEFAULT_WINDOW` | `10` | Default correlation window (minutes) |
| `VITE_APP_TITLE` | `ERakshak` | Branding |
| `VITE_ENABLE_MOCK` | `false` | Enable mock data fallback when API unreachable |

---

## 10. Performance Strategy

| Concern | Strategy |
|---------|----------|
| **Large entity tables (500+ rows)** | Virtual scrolling via `@tanstack/react-virtual` |
| **Graph rendering (100+ nodes)** | Canvas-based rendering via D3; limit visible nodes; progressive disclosure |
| **Timeline rendering (500+ events)** | Virtualized event markers; aggregate at zoom-out levels |
| **Route loading** | Lazy route components via TanStack Router file conventions |
| **Bundle size** | Tree-shaking; dynamic imports for D3 modules; avoid importing full libraries |
| **API waterfalls** | Parallel fetches where possible; prefetch on navigation intent |
| **Re-renders** | `useMemo` for expensive computations; `React.memo` for pure display components |
| **First paint** | Critical CSS inlined; font preloading (IBM Plex Sans/Mono already preconnected) |

---

## 11. Error Handling Strategy

### Levels

| Level | Handler | Behavior |
|-------|---------|----------|
| **Network** | `api.ts` request function | Catches fetch failures; surfaces as `ApiError` |
| **Auth** | 401 interceptor | Clears session; redirects to `/login` |
| **API error** | React Query `error` state | Each page renders an error banner with the API error message |
| **Component** | TanStack Router `errorComponent` | Root-level error boundary catches unhandled throws |
| **Not found** | TanStack Router `notFoundComponent` | Custom 404 with link back to investigations |

### Error Display Pattern
```tsx
if (error) {
  return <ErrorBanner message={(error as Error).message} />;
}
```

All API errors follow the backend's consistent schema: `{error: {code: number, message: string}}`.

### Toast Notifications
- Success: pipeline completed, report exported
- Warning: partial data, high reject count
- Error: API unreachable, authentication failed

---

## 12. Technical Constraints

1. **Backend must be running** — the frontend has no embedded mock server. All data comes from the FastAPI backend.
2. **CORS origins are whitelisted** — frontend must run on `localhost:5173` (Vite dev default) or be added to `ERAKSHAK_CORS_ORIGINS`.
3. **No SSR for authenticated routes** — TanStack Start provides SSR capability, but auth-guarded routes render client-side only (`typeof window !== "undefined"` checks).
4. **Tailwind v4** — uses the new `@theme inline` and `@utility` syntax. Not backward-compatible with v3.
5. **Bun as package manager** — `bun.lock` is committed. Contributors need Bun installed.
6. **No WebSocket** — all data fetching is REST polling. Long-running pipeline analysis blocks the request.
7. **JWT tokens have no refresh mechanism** — sessions expire; users must re-login.
