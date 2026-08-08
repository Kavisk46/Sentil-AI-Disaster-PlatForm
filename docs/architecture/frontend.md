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
strict TypeScript and styled with Tailwind CSS v4 and shadcn/ui. Mapping
will be handled by MapLibre GL JS rendering GeoJSON layers served by the
backend API, once map views are built in Phase 5.

Top-level organization within `apps/web/src`:

- **`app/`** — App Router routes (map dashboard, incident console, briefing viewer land here as they're built).
- **`components/ui`** — shadcn/ui primitives; **`components/providers`** — the app's provider composition (theme, TanStack Query).
- **`store/`** — Zustand stores for client-only UI state (not server data).
- **`hooks/`** — TanStack Query hooks wrapping the typed API client in `lib/api-client.ts`.
- **`lib/`** — framework-agnostic utilities (class-name merging, the API client).

Cross-app types (e.g. shapes mirroring backend response schemas) live in
`packages/shared`, not duplicated inside `apps/web`.

## Key Interactions with Other Subsystems

- Consumes the backend API exclusively — no direct database or AI engine access.
- Renders geospatial data returned by the backend as GeoJSON, per the shared data contracts described in [`system-overview.md`](system-overview.md).
- Displays routing results computed by the [routing subsystem](routing.md) as an overlay on the map.

## Status

The engineering foundation — App Router shell, providers, theming, and an
empty dashboard route — was delivered in Sprint 1. Operational views (map,
briefings, routing) are built out starting in **Phase 3** of
[`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md).
