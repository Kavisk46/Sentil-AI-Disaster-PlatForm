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

## Intended Structure

The frontend is a React and TypeScript single-page application, built with
Vite and styled with Tailwind CSS. Mapping is handled by MapLibre GL JS
rendering GeoJSON layers served by the backend API.

Planned top-level organization within `frontend/`:

- **Routes/pages** — top-level views (map dashboard, incident console, briefing viewer).
- **Components** — reusable presentational and container components.
- **Map layers** — MapLibre layer and source configuration for imagery, damage, and route overlays.
- **API client** — a typed client generated from or matching the backend's API contract.
- **State management** — client state for the current incident, selected region, and active overlays.

## Key Interactions with Other Subsystems

- Consumes the backend API exclusively — no direct database or AI engine access.
- Renders geospatial data returned by the backend as GeoJSON, per the shared data contracts described in [`system-overview.md`](system-overview.md).
- Displays routing results computed by the [routing subsystem](routing.md) as an overlay on the map.

## Status

Frontend implementation begins in **Phase 3** of [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md). This document will be expanded with concrete component and state-management conventions as that phase begins.
