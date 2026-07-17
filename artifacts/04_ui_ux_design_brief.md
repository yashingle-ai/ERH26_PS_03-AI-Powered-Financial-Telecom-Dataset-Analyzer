# UI/UX Design Brief

**Project:** ERakshak — Frontend Redesign
**Version:** 1.0 · 2026-07-17

---

## Design Philosophy

> **"Design this like a modern enterprise forensic investigation platform rather than a generic dashboard."**

ERakshak is a **forensic command center**, not a consumer app. The primary users are investigators who spend hours correlating evidence across bank statements, call records, and IP logs. Every pixel must serve an analytical purpose.

### Reference Platforms (Inspiration)
- **Palantir Gotham** — dense, analyst-first, dark interface with node-link exploration
- **Bloomberg Terminal** — information density, keyboard-driven, monospace data
- **Maltego** — entity-relationship graph investigation workflow
- **Splunk SIEM** — timeline analysis, correlation search, alert management

### What This Is NOT
- Not a marketing dashboard with large cards and pretty gradients
- Not a consumer app with playful animations and rounded everything
- Not a minimal MVP — it must feel production-grade and trustworthy

---

## Design Principles

### 1. Density Over Decoration
- Maximize visible data per viewport. Analysts scroll less, decide faster.
- Avoid oversized cards, excessive padding, or decorative whitespace.
- Tables are the primary display pattern — not card grids.
- Show 8–15 rows without scrolling. Headers are compact (10px mono uppercase).

### 2. Provenance-First
- Every data point traces back to its source file, sheet, and row number.
- Provenance is not hidden behind tooltips — it's visible inline or one click away.
- This is a **legal/forensic requirement** — analysts must defend findings in court.

### 3. Three-Source Fusion Is Visible
- The Bank ↔ CDR ↔ IPDR intersection is the product's core value.
- Color-code consistently: **Teal** = transaction/bank, **Amber** = call/CDR, **Violet** = IP/IPDR.
- Timeline, entity detail, and graph must visually distinguish all three sources.

### 4. Risk Is Quantified, Not Dramatized
- Show exact scores (0–100), not just "High" badges.
- Display the scoring breakdown: rule weight + ML anomaly + specific rule that fired.
- Color bands: `Low (0–39)` = muted teal, `Medium (40–69)` = amber, `High (70–100)` = crimson.

### 5. Keyboard-First, Mouse-Second
- Power users navigate with keyboard shortcuts (Ctrl+K for search, arrow keys for table navigation).
- Click targets are generous enough for mouse use, but the interface rewards keyboard fluency.

### 6. Progressive Disclosure
- Surface the most important insight at the top level.
- Detail is one click/selection away, not hidden behind multiple modals.
- Master-detail pattern is the primary navigation model (left = list, right = detail panel).

---

## Visual Language

### Color System

| Token | Color | Usage |
|-------|-------|-------|
| `--background` | `oklch(0.19 0.03 250)` — Deep navy | Page background |
| `--surface` | `oklch(0.22 0.03 250)` — Slightly lighter navy | Card/panel backgrounds |
| `--surface-raised` | `oklch(0.26 0.03 250)` | Hover states, elevated surfaces |
| `--foreground` | `oklch(0.95 0.01 240)` — Near white | Primary text |
| `--muted-foreground` | `oklch(0.68 0.02 245)` | Secondary text, labels |
| `--primary` | `oklch(0.72 0.11 190)` — Teal | Primary accent, links, active states |
| `--border` | `oklch(0.32 0.02 250)` | Table/panel borders |

### Risk Colors

| Band | Token | Color | Hex Approx |
|------|-------|-------|------------|
| Low (0–39) | `--risk-low` | `oklch(0.70 0.10 190)` | Muted teal |
| Medium (40–69) | `--risk-med` | `oklch(0.78 0.15 75)` | Warm amber |
| High (70–100) | `--risk-high` | `oklch(0.62 0.22 22)` | Crimson red |

### Event Type Colors

| Type | Token | Color |
|------|-------|-------|
| Transaction (Bank) | `--evt-txn` | Teal (same as primary) |
| Call (CDR) | `--evt-call` | Amber |
| IP Session (IPDR) | `--evt-ip` | Violet |

### Typography

| Use | Font | Weight | Size | Style |
|-----|------|--------|------|-------|
| **Body text** | IBM Plex Sans | 400 | 14px | — |
| **Headings** | IBM Plex Sans | 600–700 | 18–28px | -0.01em tracking |
| **Data values** | IBM Plex Mono | 400–500 | 11–13px | Tabular nums, slashed zero |
| **Labels** | IBM Plex Mono | 500 | 10px | UPPERCASE, tracking 0.2em |
| **KPI values** | IBM Plex Mono | 600 | 24px | — |

### Spacing Scale

| Token | px | Usage |
|-------|----|-------|
| `xs` | 2 | Inline gaps |
| `sm` | 4 | Tight padding |
| `md` | 8 | Standard padding |
| `lg` | 16 | Section spacing |
| `xl` | 24 | Panel padding |
| `2xl` | 32 | Page margins |

### Border Radius
- `--radius: 0.5rem` (8px) — standard rounded corners
- Cards/panels: `rounded-lg` (8px)
- Badges/pills: `rounded` (6px)
- Buttons: `rounded-md` (6px)
- Avatar/icons: `rounded-full` where circular

### Background Treatment
- **Fixed gradient background**: radial ellipses at top-left and bottom-right create a subtle depth effect
- **Grid overlay** (`.grid-bg`): 32px grid lines at low opacity for technical feel
- **Glass surfaces** (`.glass`): translucent backgrounds with `backdrop-filter: blur(8px)` for elevated panels

---

## Component Patterns

### Data Tables (Primary Pattern)
- Compact rows (py-2 to py-3, not py-4+)
- Monospace header labels, 10px uppercase with wide tracking
- Right-align numeric columns
- Hover highlight (`hover:bg-accent/40`)
- Selected row highlight (`data-[selected=true]:bg-primary/10`)
- No zebra striping — too busy. Use borders only.

### Master-Detail Layout
- Left panel: 55–65% width — scrollable list/table
- Right panel: 35–45% width — sticky detail for selected item
- Resizable divider (via `react-resizable-panels`)
- Detail panel updates instantly on selection — no page transition

### KPI Strips
- Horizontal row of 4–5 compact boxes
- Layout: Label (mono, 10px, uppercase) → Value (mono, 24px, semibold) → Subtitle (11px, muted)
- Use sparingly — only on Overview and Investigations pages

### Risk Badge
- Inline pill: colored background + text + score number
- `riskBand(score)` determines color: low/med/high
- Compact: fits within table cells without expanding row height

### Risk Gauge
- Circular arc (0–100) shown in entity detail panel
- Color fill matches risk band
- Score displayed in center

### Provenance Tags
- Inline monospace text: `source_file.xlsx:R442`
- Clicking expands to show full provenance object (source_file, sheet, row, offset, profile)
- Muted color — always visible but not distracting

### Event Chips
- Small colored dots on the timeline track
- Color = event type (txn=teal, call=amber, ip=violet)
- Size: 12×12px with ring-2 ring-background for visibility against track
- Click = select → populates Event Detail panel

### Identifier Pills
- Horizontal layout in entity detail: `TYPE → value`
- Type label in primary color, value in monospace foreground
- Border + subtle background to separate from surrounding content

---

## Screen-Specific Design Guidelines

### Login
- **Dark atmospheric background** with grid overlay and radial gradient glow
- **Hero text** (large, display-weight "ERakshak.") on left; **glass card** login form on right
- Credential hint: "(admin / adminpass)" visible for dev/demo mode
- Error messages in crimson pill
- Subtle animations: `animate-fade-up` on hero, `pulse-ring` on logo icon

### Investigations
- **Full-width data table** as the primary element
- KPI strip at top (4 boxes: cases, events, high-risk, API status)
- Search bar with filter chips (status: All/Ready/Analyzing/Ingested)
- Risk band badges in filter bar
- Table rows link to `/overview` and set the active investigation

### Overview
- **Dense command layout** — no wasted space
- Top: 5 KPI cards in a horizontal row
- Middle: 2-column grid — Money Flow Area Chart (60%) + Risk Distribution Bar Chart (40%)
- Bottom: 2-column grid — Top Entities Table (55%) + Correlation Hits List (45%)
- Header with quick-action buttons: Timeline, Network, Export Report

### Timeline
- **Full-width horizontal timeline** — a 24-hour axis with 3 stacked swimlanes
- Hour markers every 3 hours, tick marks every hour
- Correlation windows rendered as semi-transparent teal bands spanning all tracks
- Event dots clickable → Event Detail panel on the right (320px fixed width)
- Track visibility toggles in header (txn / call / ip)
- Event count shown in description: "Showing 245 of 1,204 events"

### Network Graph
- **Large canvas** (full height minus header) with SVG node-link diagram
- Mode toggle: Money Flow / Communication
- Node rendering: circles with size ∝ risk, color = risk band, glyph inside (◈ account, ☎ phone, ◉ entity)
- Edge rendering: solid lines with directional arrows (money/comm), dashed lines (shared_id)
- Legend: bottom-left overlay card
- Node detail panel: right side (320px), shows risk, id, kind, neighbor list with edge weights
- **Future enhancement**: D3 force-directed layout replacing static circular layout

### Entity Explorer
- **Master-detail** layout (55/45 split)
- Left: searchable entity table with kind icons, primary identifier, txn count, risk badge
- Right: entity profile — name, kind, volume, Risk Gauge, Resolved Identifiers list, Risk Factors (rule flags with weights), action buttons
- Identifier list shows all merged identifiers with type labels
- IP note: "* IP sessions are retained as evidence, never used as a merge key"

### Detections
- **Filtered card list** — not a table (each detection has multi-line content)
- Filter bar: All / High / Medium / Low toggle
- Each card: icon (ShieldAlert), rule name, severity badge, weight indicator, description paragraph, entity/evidence counts
- Sorted by weight descending

### Reports
- **Print-preview layout** — white background, dark text, formal typography
- Left: document preview (light background, structured sections, monospace labels)
- Right: summary panel
- Export buttons in header (currently showing toast "not wired")
- Sections: Case Narrative → Top Entities table → Correlation Hits list

### Settings
- Form layout with grouped sections
- Window W slider/input
- API URL display
- Theme toggle (future)

---

## Interaction Patterns

### Navigation
- **Sidebar** (collapsible) — 3 sections: Case, Analysis, Output
- **Topbar** — case context (dataset name, window, actions)
- Sidebar collapses to icon-only mode on narrow viewports
- Footer shows timezone + window config

### Selection Model
- Single-selection in tables and graphs
- Selection updates the detail panel immediately
- Selection state is per-page (not global)
- Future: shift+click for multi-select in entity table

### Keyboard Shortcuts (Target)
| Key | Action |
|-----|--------|
| `Ctrl+K` / `⌘+K` | Open command palette (global search) |
| `↑ / ↓` | Navigate table rows |
| `Enter` | Open selected entity/event detail |
| `Esc` | Close panels, clear selection |
| `1–9` | Quick-switch sidebar sections |

### Tooltips
- Show on hover after 300ms delay
- Content: full identifier values, exact timestamps, precise amounts
- Style: dark popover with border, monospace text

---

## Accessibility Requirements

| Requirement | Implementation |
|-------------|----------------|
| **Color contrast** | All text meets WCAG AA (4.5:1 ratio) against dark backgrounds |
| **Keyboard navigation** | All interactive elements are focusable and activatable via keyboard |
| **Screen reader** | Semantic HTML (tables, lists, headings hierarchy); ARIA labels on icon-only buttons |
| **Focus indicators** | `ring` utility on focus-visible states |
| **Motion** | Respect `prefers-reduced-motion` — disable `animate-fade-up` and `pulse-ring` |
| **Text sizing** | Minimum 10px for labels, 12px for data values, 14px for body text |

---

## Responsive Behavior

| Breakpoint | Layout |
|------------|--------|
| `< 768px` | Sidebar hidden (hamburger toggle); single-column layouts; detail panels collapse to bottom drawers |
| `768–1024px` | Sidebar collapsed to icons; 2-column grids become stacked; timeline scrolls horizontally |
| `> 1024px` | Full layout — sidebar expanded, master-detail panels, wide timeline |
| `> 1440px` | Content capped at `max-w-7xl` (1280px) and centered |

**Primary target:** Desktop browsers at 1280px+ width. Mobile is secondary but should not break.
