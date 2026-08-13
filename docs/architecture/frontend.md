# Frontend Architecture

The frontend is the primary interface responders and incident commanders use
to interact with SentinelAI: exploring affected regions on a map, reviewing
detected damage, requesting rescue routes, and reading generated briefings.

## Responsibilities

- Render an interactive, GIS-backed map of the affected region with damage
  and infrastructure overlays.
- Present AI-generated operational briefings in a readable, decision-ready
  format.
- Allow responders to request and visualize rescue/access routes.
- Provide an incident/mission console that ties map, briefing, and routing
  views together into a single operational workflow.

## Structure

The frontend (`apps/web`) is a Next.js 15 App Router application written in
strict TypeScript and styled with Tailwind CSS v4 and shadcn/ui. Mapping is
handled by MapLibre GL JS rendering GeoJSON layers served by the backend API
(see "Map technology", below).

Top-level organization within `apps/web/src`:

- **`app/`** — App Router routes. `app/dashboard/` is the command center
  (Milestone 8): `layout.tsx` renders the top navigation bar, `page.tsx`
  renders `<CommandCenter />`.
- **`components/command-center/`** — the operational UI: upload/analysis
  controls, incident status bar, damage/road-risk/route-comparison/briefing
  panels, top navigation. `command-center.tsx` is the single orchestrator —
  see "Data flow", below.
- **`components/map/`** — the MapLibre integration (`command-map.tsx`,
  `command-map-loader.tsx`, `map-legend.tsx`).
- **`components/ui`** — shadcn/ui-style primitives (button, card, badge,
  input, alert, skeleton); **`components/providers`** — the app's provider
  composition (theme, TanStack Query).
- **`services/api/`** — typed fetch wrappers per backend resource
  (`analysis.ts`, `road-risk.ts`, `routing.ts`, `summary.ts`). No component
  calls `fetch` directly.
- **`hooks/`** — TanStack Query hooks wrapping `services/api/*`
  (`use-analysis.ts`, `use-road-risk.ts`, `use-routing.ts`,
  `use-incident-summary.ts`).
- **`store/`** — Zustand stores for client-only state that's genuinely
  shared across otherwise-unrelated components (`incident-store.ts`:
  active analysis id, demo mode, selected route points; `ui-store.ts`:
  whether the command-center info panels are expanded). Server data never
  lives here — see "Data flow".
- **`lib/`** — framework-agnostic utilities: the API client
  (`api-client.ts`), route/GeoJSON math (`geo.ts`), damage-count derivation
  (`damage.ts`), the shared risk/damage color-and-label palette
  (`risk-colors.ts`), and demo fixtures (`demo/demo-data.ts`).

Cross-app types mirroring backend response schemas live in
`packages/shared/src/types/*` (`analysis.ts`, `geojson.ts`, `damage-map.ts`,
`roads.ts`, `road-risk.ts`, `routing.ts`, `incident.ts`), re-exported from
`packages/shared/src/index.ts`. Every one of these is a hand-written mirror
of the corresponding Pydantic schema in `apps/api/app/**/schemas.py` — see
each file's docstring for exactly which backend file it mirrors. `any` is
not used anywhere in this milestone's code to bypass that typing.

## Map technology

**MapLibre GL JS**, per the architectural direction already recorded here
before this milestone — no second, competing map library was introduced.
`components/map/command-map.tsx` uses the library directly (no
`react-map-gl` or similar wrapper), giving full control over layer/paint
expressions with one less abstraction layer.

**3D/WebGL, honestly scoped**: the map runs a real WebGL scene with camera
`pitch` (tilt, default 45°) and `bearing` (rotation) enabled and a
`NavigationControl` exposing both — genuine 3D camera movement, not a
decorative 3D shape. Real terrain (a raster-DEM elevation source) and 3D
building extrusions are **not** implemented: MapLibre's terrain support
needs an elevation tile provider, and this project has no such provider
configured (no API key, no vendor chosen) — fabricating one, or extruding
buildings from data the backend doesn't provide, would violate this
project's "never invent geography" principle applied one layer further out.
This is recorded as a known limitation, not silently omitted.

**Basemap style**: defaults to MapLibre's own free "demotiles" style
(`https://demotiles.maplibre.org/style.json`, maintained by the MapLibre
project for exactly this purpose — no account or API key required).
Production deployments that want richer cartography can set
`NEXT_PUBLIC_MAP_STYLE_URL` to a real tile provider's `style.json` without a
code change (see `apps/web/.env.example`).

**SSR safety**: `command-map.tsx` never imports `maplibre-gl` at module
scope — it's loaded with a dynamic `import("maplibre-gl")` inside
`useEffect`, so the module is never evaluated during any server render pass
even if a caller forgets the wrapper. `command-map-loader.tsx` additionally
wraps the component in `next/dynamic(..., { ssr: false })`, which is the
primary mechanism callers are expected to use; the `useEffect`-only load is
defense in depth, not the only safeguard.

## Data flow

```
API (services/api/*)
  -> TanStack Query hooks (hooks/*)
  -> typed response (packages/shared/src/types/*)
  -> command-center.tsx (the one component that calls every hook)
  -> presentational panels / map (props only, no fetching of their own)
```

`components/command-center/command-center.tsx` is the single owner of every
data-fetching hook and of the "which UI state are we in" derivation
(idle/uploading/uploaded/queued/processing/completed/failed — see "Analysis
states"). Every panel below it (`upload-panel.tsx`, `damage-stats-panel.tsx`,
`road-risk-panel.tsx`, `route-comparison-panel.tsx`, `briefing-panel.tsx`)
is purely presentational, receiving already-typed data and callbacks as
props. This keeps `fetch` calls out of every component but the four files
in `services/api/`, and keeps data-shape decisions in exactly one place.

Global (Zustand) state is used only for the two things that are genuinely
shared and don't belong to server-cache or a single component: which
analysis is active + whether demo mode is on + which two points are
selected for a route (`store/incident-store.ts`), and whether the
info-panels rail is expanded on narrow viewports (`store/ui-store.ts`).
Every fetched value — analysis status, damage map, road risk, route
results, the AI briefing — lives in TanStack Query's cache, not in Zustand.

## Damage visualization

Backend source: `GET /api/v1/analysis/{id}/damage-map`
(`DamageMapResponse.feature_collection`, real RFC 7946 GeoJSON — see
`apps/api/app/ml/geospatial/geojson.py`). Rendered as native MapLibre
`circle` (Point geometry) and `fill` (Polygon/bounding-box geometry) layers
— not one DOM element per building — filtered by `["geometry-type"]` so
both geometry kinds share one source.

Damage classes (`no_damage`/`minor`/`major`/`destroyed`) always render with
the same color **and** the same short text code (`ND`/`MN`/`MJ`/`DS` — see
`lib/risk-colors.ts`), and increasing marker size/stacking weight
(`DAMAGE_CLASS_WEIGHT`) for more severe classes, satisfying the
minor-\<major\<destroyed visual-hierarchy requirement without relying on
color alone. `damage-stats-panel.tsx`'s per-class breakdown is *derived*
from `DamageSummary`'s aggregate fields (`damaged_buildings`/
`severely_damaged`/`destroyed`), using the backend's own documented
definitions (`severely_damaged = major + destroyed`) — see `lib/damage.ts`
for the exact arithmetic and why it's not a guess.

`available=false` (analysis not completed, or completed with no mappable
geometry — the honest, common state today, since no real building
localizer exists yet) renders a clear, worded empty state, never a
fabricated map. Demo mode (`lib/demo/demo-data.ts`) is the only place
synthetic damage features exist, and they're centered on a fictional point
in open ocean, never a real place.

## Road-risk visualization

Backend source: `GET /api/v1/analysis/{id}/road-risk`
(`RoadRiskResponse.edges`, real `RoadEdge`s with `risk_score`/`risk_level`/
`accessibility` populated).

**Why this is a list panel, not a map layer covering the whole graph**:
`RoadEdge` identifies an edge by `source_node`/`target_node` id strings, not
coordinates, and no backend endpoint returns the road graph's node
coordinates in general (only `RouteResult.route_geometry`, for nodes a
specific computed route actually visited). Drawing a graph-wide risk
overlay would require inventing node positions, which this project's own
principle ("do not invent precise geographic coordinates") forbids. So
`road-risk-panel.tsx` renders every risky edge as a real, data-dense list
(name/`source→target`, risk badge, accessibility badge, sorted by
severity, capped at 25 rows with a "+N more" note) instead.

Risk and accessibility are always two separate badges, using two
independent visual languages (`RISK_LEVEL_STYLE` — color + `L`/`M`/`H`/`C`;
`ACCESSIBILITY_STYLE` — a different color set + `OPEN`/`RSTR`/`BLKD`/`UNK`
+ a distinct dash pattern reserved for map use) — a `critical`-risk edge
that's still `open`, or a `low`-risk edge that happens to be `blocked` for
an unrelated reason, is never visually conflated into one indicator. This
mirrors the backend's own "risk is not blockage" separation (`app/risk/
__init__.py`).

Where road risk **is** drawn on the map: along a computed route, where real
coordinates exist. `lib/geo.ts::routeToRiskSegments()` pairs each
`edge_sequence[i]` (a real `RoadEdge` with its own `risk_level`) with the
matching consecutive pair of `route_geometry` points, rendered as a colored
halo underneath the bold risk-aware route line — real backend geometry
paired with real backend risk data, never an invented gradient.

## Route visualization / route comparison

Backend source: two independent `POST /api/v1/routing` calls (one per
`RoutingMode`) — the backend's `compare_routes()` is a service-level
capability, not an HTTP endpoint (see `apps/api/README.md`, "Route
comparison methodology"), so there is no single "give me a comparison"
endpoint to call. `services/api/routing.ts::compareRoutes()` fetches both
modes in parallel and `lib/geo.ts::computeRouteComparison()` derives
`distanceDifference`/`riskDifference`/`detourRatio`/`riskReduction` using
the exact same formulas the backend's own `RouteComparison` schema
documents. Every number displayed in `route-comparison-panel.tsx` traces
back to a real API response; nothing is hard-coded, and
`lib/__tests__/geo.test.ts` asserts the arithmetic directly.

On the map: the risk-aware route renders as a bold, high-contrast line
(strong visual emphasis, per the milestone's requirement); the
distance-only baseline renders thin and dashed, kept visible for
comparison rather than hidden. Route points are picked by clicking the
map (first click = start, second = destination — `command-center.tsx`),
stored in `incident-store.ts`, with a "Clear points" control.

## AI briefing

Backend source: `GET`/`POST /api/v1/analysis/{id}/summary`
(`IncidentBriefing` — Milestone 7). `briefing-panel.tsx` always titles the
panel **"AI-Generated Incident Briefing"**, always renders the backend's
own fixed safety disclaimer verbatim (never a paraphrase, never omitted),
and never chooses different UI treatment for `source: "provider"` vs.
`"fallback"` — both are equally non-human-authored from the UI's point of
view, so neither is presented as more authoritative than the other. A
"Regenerate" action calls `POST .../summary`, optionally including the
currently-selected route points as context.

## API integration

Every backend call goes through `lib/api-client.ts` (`apiGet`/`apiPost`/
`apiUpload`, all returning `ApiResult<T>` — `{ok:true,data}` or
`{ok:false,error}`, never throwing) via one of the four
`services/api/*.ts` files, via one of the `hooks/use-*.ts` files. No
component calls `fetch` directly, and no component imports a
`services/api/*` file directly — only hooks do. `apiGet`/`apiPost` prefer
the backend's own `{"detail": "..."}` error message (see
`apps/api/app/api/exception_handlers.py`) over a bare HTTP status line, and
never surface a raw stack trace.

## Performance decisions

- **Native map layers, not DOM markers**: every damage feature and every
  route segment is a MapLibre GL layer entry, not a React-rendered DOM
  element — thousands of features cost one WebGL draw call, not thousands
  of DOM nodes.
- **`setData`, not remount**: the map is created exactly once per mount;
  new data updates existing GeoJSON sources via `setData()` rather than
  tearing down and recreating the WebGL context on every fetch.
- **Single hook owner**: `command-center.tsx` calling every hook once
  (rather than each panel calling its own) avoids duplicate network
  requests for the same resource.
- **`ResizeObserver`**, not a fixed size, keeps the WebGL canvas correctly
  sized inside a flexible/responsive layout without a layout-thrashing
  poll loop.

## Accessibility decisions

- **Non-color risk/damage/accessibility indicators**: every severity/risk/
  accessibility value is always paired with a short text code (`H`, `MJ`,
  `BLKD`, ...) in addition to color — see `lib/risk-colors.ts`.
- **Real semantic controls**: the upload dropzone is a real
  `role="button"` with a keyboard handler (Enter/Space) and a visually
  hidden native `<input type="file">`, not a bare clickable `<div>`; the
  demo-mode toggle is a real `<input type="checkbox" role="switch">`, not
  a styled `<div onClick>`.
- **Live regions**: `role="status"`/`aria-live="polite"` on the analysis
  state indicator and the map's text summary, so state changes are
  announced without the user needing to keep visual focus on them.
- **`prefers-reduced-motion`**: the map opens with zero pitch and
  animates camera moves with zero duration when the OS setting is on;
  loading skeletons use Tailwind's `motion-safe:` variant so their pulse
  animation is skipped entirely under reduced motion — no custom motion
  library was added for this (Tailwind's built-in `motion-safe`/
  `motion-reduce` variants were sufficient).
- **Known, honest limitation**: MapLibre's WebGL canvas itself cannot be
  made screen-reader navigable — no mapping library makes individual
  vector features focusable/readable out of the box. `command-map.tsx`
  instead renders a visually-hidden, `aria-live` text summary of what the
  map currently shows (feature/route counts) as the accessible
  equivalent, rather than claiming full screen-reader parity with the
  visual map.

## Responsive design

- **Desktop (`lg:` and up)**: the full command center — map plus a
  persistent, scrollable info-panel rail (`grid-cols-[minmax(0,1fr)_380px]`).
- **Tablet/narrow desktop**: the info-panel rail is collapsible via a
  "Show/Hide panels" control (`store/ui-store.ts`), so the map can take
  the full viewport when panels aren't needed.
- **Mobile**: everything stacks in a single column in this DOM order —
  incident status bar, map, upload controls, route comparison, AI
  briefing, then damage stats and road risk (the two most
  diagnostic/secondary panels) — matching the milestone's own mobile
  priority list (incident status, map, route, briefing) while still
  surfacing damage/road-risk data rather than hiding it.

## Key Interactions with Other Subsystems

- Consumes the backend API exclusively — no direct database or AI engine access.
- Renders geospatial data returned by the backend as GeoJSON, per the shared data contracts described in [`system-overview.md`](system-overview.md).
- Displays routing results computed by the [routing subsystem](routing.md) as an overlay on the map.

## Status

Milestone 8 ("3D Disaster Command Center") delivered the full operational
UI described above: the command-center page, typed API integration, the
MapLibre map with damage/road-risk/route layers, route comparison, the AI
briefing panel, demo mode, and accessibility/responsive/performance work.
See `PROJECT_ROADMAP.md` for what remains in later phases.
