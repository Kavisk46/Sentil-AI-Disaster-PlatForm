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
  (`analysis.ts`, `road-risk.ts`, `routing.ts`, `summary.ts`,
  `intelligence.ts` (F2, disaster-scoped), `analysis-intelligence.ts`
  (F3, analysis-scoped)). No component calls `fetch` directly.
- **`hooks/`** — TanStack Query hooks wrapping `services/api/*`
  (`use-analysis.ts`, `use-road-risk.ts`, `use-routing.ts`,
  `use-incident-summary.ts`, `use-intelligence.ts` (F2),
  `use-analysis-intelligence.ts` (F3) — see "Search & response
  intelligence", below).
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
`roads.ts`, `road-risk.ts`, `routing.ts`, `incident.ts`, `intelligence.ts`
(F2), `analysis-intelligence.ts` (F3)), re-exported from
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

## Landing page and hero map

`app/page.tsx` renders `components/landing/landing-page.tsx` — the first
stage of the flow (hero + upload only, no dashboard chrome). A successful
upload, or choosing "View live demo" (which sets `isDemoMode` in
`incident-store.ts`), navigates to `/dashboard` via `next/navigation`'s
`useRouter().push()`. `/dashboard` remains independently loadable and
already handles "no active analysis, demo mode off" on its own (the
existing inline upload prompt), so the landing page is never the only way
into the app.

The hero visual reuses `command-map.tsx` — the same MapLibre technology
the dashboard uses, not a second map library or a fabricated 3D scene.
Four additive, default-preserving props (none passed by the dashboard,
so its behavior is unchanged) stage it decoratively:

- `initialView` — a fixed starting camera. The landing hero centers on
  open ocean (`components/landing/landing-hero-map.tsx`'s
  `OPEN_OCEAN_VIEW`), the same "never a real place" convention
  `lib/demo/demo-data.ts` uses for its fictional `ORIGIN` — nothing about
  this page should read as surveillance of, or a claim about, any real
  location. The basemap itself (MapLibre's free "demotiles" style) has no
  satellite imagery, only abstract low-detail cartography, so a fixed
  decorative camera position doesn't risk depicting a real disaster site.
- `interactive={false}` — passed straight through to MapLibre's own
  `interactive` map option, disabling every built-in mouse/touch/keyboard
  handler and skipping `NavigationControl`/`ScaleControl`/the click
  listener. The hero is not meant to be operated.
- `autoRotate` — a slow `requestAnimationFrame` bearing drift, cancelled
  on unmount, skipped entirely under `prefers-reduced-motion` (same
  `window.matchMedia` check the existing pitch/fitBounds motion code
  already used).
- `decorative` — sets `aria-hidden="true"` on the map wrapper and skips
  the `aria-live` feature-count summary paragraph (see "Accessibility
  decisions" below).

No damage/route data is ever passed to the hero instance.

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

## Analysis stage tracking

`components/command-center/analysis-stage-tracker.tsx` renders three
rows — Image received, Preprocessing, Damage analysis — not the full
seven-stage list a literal reading of the milestone brief might suggest
(which also lists Spatial analysis, Risk assessment, Route optimization,
Incident briefing). This is a deliberate honesty-over-literalism choice:

- **Risk assessment, Route optimization, and Incident briefing are not
  sequential backend sub-stages.** They're three independently-fetched
  resources (`useRoadRisk`/`useRouteComparison`/`useIncidentSummary`),
  all gated on the *same single* condition (`status === "completed"`),
  never on each other. Rendering them as rows in one linear progress bar
  would tell a responder "the backend hasn't gotten there yet" for
  something that's actually available immediately — Route optimization
  in particular needs the user to pick two map points first, which has
  nothing to do with backend pipeline progress. Each already has its own
  honest `available`/`reason` state on its own panel (`RoadRiskPanel`,
  `RouteComparisonPanel`, `BriefingPanel`) — that's where their readiness
  belongs, not duplicated into a second, misleading representation here.
- **Spatial analysis** (georeferencing damage geometry) is folded into
  "Damage analysis": it's an attribute of the same `completed`-gated
  output (`DamageMapResponse`), not a separately timestamped
  `AnalysisStatus` value.
- **Preprocessing** has no backend signal at all — `AnalysisStatus` jumps
  straight from `queued` to `processing` — so it's always rendered as an
  honest "Not yet available" row (muted text, dashed "N/A" badge), never
  a fake completed step.

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

## Search & response intelligence (Milestone F3)

`components/command-center/intelligence-panel.tsx` — added to the
existing results grid (`results-panel-grid.tsx`, ordered last,
`order-4 lg:order-7`) as a sixth, additive section, not a redesign.
Answers the F3 brief's five questions directly: **What do we know? /
Where should we act first? / What can reach there? / What should we do?
/ How certain are we?** — the fifth never via a fabricated confidence
number; every uncertainty is shown as its qualitative
`low`/`moderate`/`high`/`unknown` level, with a numeric percentage
rendered only on the rare occasion `Uncertainty.confidence` is
genuinely non-null (never invented client-side).

**Data source, by mode** — `command-center.tsx` normalizes both into
one prop shape before `intelligence-panel.tsx` ever sees them, so the
panel itself never branches on which mode produced its data, only on
what's actually available:

- **ANALYSIS mode** — `hooks/use-analysis-intelligence.ts`
  (`useAnalysisIntelligenceContext`/`useAnalysisSearchZones`/
  `useAnalysisRecommendations`), gated on `isCompleted` exactly like
  `useRoadRisk`/`useIncidentSummary`. Real analysis-derived search
  zones/recommendations (`is_simulated: false`), with resource
  candidates that are still `resources_are_demo: true` — no real
  resource-ingestion system exists (see `docs/architecture/intelligence.md`,
  "Milestone F3").
- **DEMO mode** — `lib/demo/demo-data.ts`'s `DEMO_SEARCH_ZONES`/
  `DEMO_RECOMMENDATIONS`/`DEMO_RESOURCE_CANDIDATES`, hand-authored
  fixtures in the same style as every other `DEMO_*` constant in that
  file (mirroring, not fetching, the backend's own deterministic demo
  scenario) — Demo mode never touches the network for this panel either.

**Sections** (all within one `Card`, not five separate panels — this is
one coherent story, not five independent facts):

1. **Where should we act first?** — every scored `SearchZone`, ranked,
   as clickable priority badges (reusing `SEARCH_PRIORITY_STYLE`, the
   same 4-level color+code scale `RISK_LEVEL_STYLE` already
   established). Selecting one drives the "Why" section below;
   defaults to the top-priority zone.
2. **Why** — the selected zone's `reasons`, `missing_factors` ("not
   scored — data unavailable"), `supporting_evidence`, and
   `uncertainty` — never "a person is located here," always "why this
   zone is [priority level]."
3. **What can reach it?** — resource-capability-match candidates for
   the top-priority zone only (matching the backend's own scope — see
   "Route feasibility" below): eligible/ineligible, missing
   capabilities, availability, reachability, and `route_feasibility`
   (`computed`/`route_unavailable`/`not_applicable`), each candidate
   individually badged "SIM" (simulated) regardless of the panel-level
   label.
4. **Recommended action** — every ranked `Recommendation`, with its
   rationale, required capabilities, uncertainty, and limitations —
   never an unexplained action.
5. **Limitations** — always rendered, composed from real signals:
   the context-unavailable reason (if any), roads-unavailable (if any),
   an explicit "resources are a simulated demo pool" disclosure, and a
   static "no ground-truth confirmation" caveat that applies to every
   search zone unconditionally.

**A fifth provenance category**: `lib/data-provenance.ts`'s
`ProvenanceCategory` gains `"simulated"` (badge code `SIM`), distinct
from the existing `observed`/`predicted`/`calculated`/`generated` four
and from the app-wide "Demo mode" banner (`incident-status-bar.tsx`) —
this panel is the one place a `simulated` resource candidate can appear
in the *same* render as `calculated` (real) search zones, so it needed
its own, independent label rather than reusing the page-level Demo Mode
signal.

## Map layers (Milestone F3)

`command-map.tsx` gains two additive, default-`null` props — `/dashboard`
without them behaves exactly as before:

- **`searchZones`** — plotted only for zones whose `geometry_crs` is
  genuinely `"EPSG:4326"` (`searchZonesFeatureCollection()` silently
  drops anything else, the same fail-safe convention `affected-area-panel.tsx`
  already established for damage geometry — never plots an IMAGE-space
  or untagged coordinate as if it were real geography). Rendered as a
  soft priority-colored halo under a solid core circle, colored via
  `SEARCH_PRIORITY_STYLE` (the same palette the panel's badges use, so
  map and panel always agree visually).
- **`recommendedRoute`** — the top candidate's computed route
  (`AnalysisCapabilityMatch.route`, only when `route_feasibility.status
  === "computed"`), styled as a distinct magenta dashed line so it's
  never visually confused with the user-driven distance-only/risk-aware
  comparison routes above it. `null`/not-found renders nothing — never
  an invented path.

Both participate in the existing `fitBounds` auto-framing and the
`aria-live` text summary alongside damage/route data, and
`map-legend.tsx` gains a "Search priority" swatch section plus a
"Recommended (to top zone)" route-legend row.

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

The panel is structured into the sections the milestone brief requests,
each honestly mapped onto — or, for two of them, honestly *not* mapped
onto — the real `IncidentBriefing` fields:

| Requested section | Backend mapping |
|---|---|
| Situation | Groups `incident_severity` + `affected_structures` (both Calculated, not AI-generated) |
| Affected areas | `priority_area` (AI-generated) |
| Major risks | **No backend field.** Rendered as an explicit "Not exposed by backend" section |
| Key findings *(not in the original list, kept for `key_findings`)* | `key_findings` — kept under its own real heading rather than folded into "Major risks", so evidence text is never presented as a distinct risk-model output |
| Recommended route | `route_summary` (AI-generated), with a note pointing to the Rescue Accessibility panel's real numeric metrics |
| Reasoning | **No backend field.** Rendered as an explicit "Not exposed by backend" section — never a synthesized-sounding rationale built from `key_findings` |
| Data confidence | `confidence` — a 4-value category (`low`/`moderate`/`high`/`unknown`) only; the backend has no numeric confidence score anywhere, so none is ever displayed |
| Limitations | `limitations`, unchanged |

The two "not exposed" sections use the same muted/dashed visual language
as `analysis-stage-tracker.tsx`'s "Not yet available" rows, so the
pattern for "this concept doesn't exist in the current API" reads
consistently everywhere it appears.

## Data provenance labeling

Every panel carries a `ProvenanceBadge` (`components/ui/provenance-badge.tsx`)
naming which of four categories (`lib/data-provenance.ts`) its content
belongs to, so a responder never mistakes a model prediction, a
deterministic calculation, or an LLM sentence for a directly-observed
fact:

| Category | Meaning | Examples |
|---|---|---|
| Observed | Read directly from the uploaded file | Filename, byte size, pixel dimensions (`upload-dropzone.tsx`) |
| Predicted | Output of the damage-classification model | `BuildingDamage.damage_class`/`.confidence`, `DamageStatsPanel`'s counts, damage-map features |
| Calculated | Deterministic formula over other real data — not a trained model | `RoadEdge.risk_score`/`.risk_level` (a documented formula over damage proximity, `app/risk/`), `RouteComparisonPanel`'s distance/risk/detour numbers (`lib/geo.ts::computeRouteComparison`), the Affected Area panel's bounding-box figure (`lib/geo.ts::computeFeatureBounds`/`boundingBoxAreaKm2`), F3's `SearchZone`/`Recommendation` scores |
| AI-generated | LLM (or its deterministic fallback template) prose | `IncidentBriefing.priority_area`/`.route_summary`/`.key_findings`/`.limitations` |
| Simulated *(F3)* | A deterministic demo/placeholder entity — real neither as measurement nor as inference | Every F3 resource candidate (`resources_are_demo: true`, always); the whole intelligence panel in Demo mode |

One easy mistake to avoid: `IncidentBriefing.incident_severity`,
`.confidence`, and `.affected_structures` are **not** AI-generated —
`app/incident/severity.py` computes all three deterministically from real
`BuildingDamage`/`DamageSummary` data server-side and silently discards
any LLM output that tries to set those keys (see "AI briefing" below).
They're labeled "Calculated", the same category as the road-risk and
route-comparison numbers, not "AI-generated".

## API integration

Every backend call goes through `lib/api-client.ts` (`apiGet`/`apiPost`/
`apiUpload`, all returning `ApiResult<T>` — `{ok:true,data}` or
`{ok:false,error}`, never throwing) via one of the `services/api/*.ts`
files, via one of the `hooks/use-*.ts` files. No component calls `fetch`
directly, and no component imports a `services/api/*` file directly —
only hooks do. `apiGet`/`apiPost` prefer the backend's own
`{"detail": "..."}` error message (see
`apps/api/app/api/exception_handlers.py`) over a bare HTTP status line, and
never surface a raw stack trace.

**Model readiness (Milestone F4)**: `services/api/model.ts`/
`hooks/use-model-status.ts` poll `GET /api/v1/model/status` (30s
interval, same cadence `use-api-health.ts` already uses) and render a
small "Model:" indicator in `top-bar.tsx`, next to the existing "API:"
connectivity indicator — deliberately a separate signal, never
conflated: a healthy API can still report a disabled or not-yet-loaded
model, and the indicator shows exactly that (`Disabled`/`Not loaded`/
`Ready (<model name>)`/`Unknown` on a backend error), never a fabricated
"ready" state.

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
- **Decorative hero map**: the landing hero passes `decorative` to
  `command-map.tsx`, which sets `aria-hidden="true"` on the wrapper and
  skips the `aria-live` summary entirely (and, via `interactive={false}`,
  never renders unreachable/`tabIndex={-1}`-patched controls — the
  controls simply aren't added) — announcing "No damage data loaded" on a
  marketing page with nothing loaded would be noise, not accessibility.
- **Stage tracker live region**: `analysis-stage-tracker.tsx` scopes
  `role="status"`/`aria-live="polite"` to only the currently-active row's
  status text, not the whole list — avoids re-announcing all three rows
  on every 2-second status poll.
- **Real headings in the briefing panel**: the six/seven briefing
  sections (see "AI briefing" above) are real `<h4>` elements, including
  the two "not exposed by backend" ones — a screen-reader user navigating
  by heading can jump straight to "Reasoning" and hear the honest answer,
  rather than the section silently not existing.
- **Real upload progress semantics**: `components/ui/progress.tsx` sets
  `role="progressbar"` with real `aria-valuenow`/`aria-valuemin`/
  `aria-valuemax` only when a genuine byte-progress fraction is known
  (from `xhr.upload.onprogress` — see "API integration"); indeterminate
  state omits `aria-valuenow` entirely rather than reporting a guess.

## Responsive design

- **Desktop (`lg:` and up)**: the full command center — map plus a
  persistent, scrollable info-panel rail (`grid-cols-[minmax(0,1fr)_380px]`).
- **Tablet/narrow desktop**: the info-panel rail is collapsible via a
  "Show/Hide panels" control (`store/ui-store.ts`), so the map can take
  the full viewport when panels aren't needed.
- **Mobile**: everything stacks in a single column, visually reprioritized
  via Tailwind `order-*`/`lg:order-*` utilities (not conditional
  rendering — nothing is hidden, only reordered): incident status bar,
  road risk, route comparison, AI briefing, then the map, upload/analysis
  workspace, damage stats, and affected area — matching the milestone's
  mobile priority list (status/risk/route/summary first) without dumping
  the full desktop dashboard at the top. **Disclosed trade-off**: CSS
  `order` changes visual position but not DOM/tab order, so a
  keyboard/screen-reader user on mobile still encounters these blocks in
  source order (upload/analysis workspace, then the results panels in
  their desktop sequence) rather than the reprioritized visual order. The
  alternative (a media-query-gated conditional render matching visual and
  tab order exactly) would need a new `useMediaQuery` hook, risks an SSR/
  client hydration mismatch on first paint, and duplicates JSX — judged
  not worth it for reordering seven blocks.

## Key Interactions with Other Subsystems

- Consumes the backend API exclusively — no direct database or AI engine access.
- Renders geospatial data returned by the backend as GeoJSON, per the shared data contracts described in [`system-overview.md`](system-overview.md).
- Displays routing results computed by the [routing subsystem](routing.md) as an overlay on the map.

## Status

Milestone 8 ("3D Disaster Command Center") delivered the full operational
UI described above: the command-center page, typed API integration, the
MapLibre map with damage/road-risk/route layers, route comparison, the AI
briefing panel, demo mode, and accessibility/responsive/performance work.

**Frontend F1** ("Disaster Command Center" polish) built on that
foundation without duplicating or bypassing it: a landing/upload page
reusing the existing map technology as a decorative hero; upload preview/
size/dimensions/real-progress/retry (`upload-dropzone.tsx`, extracted
from `upload-panel.tsx`); an honest 3-row analysis stage tracker; a new
Affected Area panel computing a real bounding-box figure from existing
damage-map geometry; a restructured AI briefing panel mapping the
requested sections onto real fields (with two sections explicitly marked
"not exposed by backend" rather than invented); a data-provenance badge
system distinguishing observed/predicted/calculated/AI-generated
information everywhere; a dark, glass-surfaced visual pass
(`--glass-*` tokens in `globals.css`); and mobile priority reordering.
No backend contract changed — every new number traces back to an
existing endpoint or a documented client-side calculation.

**Frontend F3** ("Analysis-Aware Intelligence" integration) added the
"Search & response intelligence" panel (`intelligence-panel.tsx`), two
new MapLibre layers (search zones, recommended route), typed
analysis-scoped hooks/services (`use-analysis-intelligence.ts`,
`services/api/analysis-intelligence.ts`), a fifth data-provenance
category (`simulated`), and hand-authored Demo-mode intelligence
fixtures — all additive to F1's existing command-center layout, with no
existing panel's prop contract changed. See "Search & response
intelligence" and "Map layers", above.

**Frontend F4** ("Real AI Inference & Model Serving" integration) made
only the minimal changes Milestone F4's own brief calls for — no
redesign: a "Model:" readiness indicator in `top-bar.tsx`
(`hooks/use-model-status.ts`/`services/api/model.ts`, mirroring
`use-api-health.ts`'s existing pattern exactly), distinct from general
API connectivity. `DamageAnalysis.model_metadata` (already returned by
the existing `GET /api/v1/analysis/{id}` endpoint) needed no new
frontend plumbing at all — it flows through unchanged.

See `PROJECT_ROADMAP.md` for what remains in later phases.
