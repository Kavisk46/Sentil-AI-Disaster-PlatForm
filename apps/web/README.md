# SentinelAI Frontend

Next.js 15 (App Router) frontend: a landing/upload page and a "command
center" analysis workspace, backed by the real `apps/api` FastAPI backend
(no mock data in the real flow — see "Demo mode" below).

See [`docs/architecture/frontend.md`](../../docs/architecture/frontend.md)
for the full architecture, data-flow, and design-system rationale.

## Local development

From the repository root (this app is part of an npm workspace):

```bash
npm install
cp apps/web/.env.example apps/web/.env.local
npm run dev --workspace=apps/web
```

Open http://localhost:3000 — the landing page (hero + upload). A successful
upload, or turning on Demo Mode, navigates to `/dashboard`, the analysis
workspace (map, damage/risk/route/briefing/search-and-response-intelligence
panels). `/dashboard` is also directly loadable on its own.

**Note on the default backend configuration**: since Milestone F4, the
default configuration (`MODEL_ENABLED=True`, `MODEL_PROVIDER=open_clip`)
runs **real** CPU inference — deterministic tile localization plus
zero-shot CLIP (`ViT-B-32`/`openai`) damage classification, not a model
trained on disaster imagery (see the root [`README.md`](../../README.md#aiml-approach)).
A real upload therefore genuinely processes and completes; the checkpoint
downloads once on first use (network required that one time, then
cached). With no road network loaded, routing/road-risk will still
honestly report unavailable regardless of model configuration.
Uploads can still end in a `failed` (`MODEL_LOAD_FAILURE`) status on a
fully offline environment where the checkpoint cannot be downloaded — an
honest failure, not a frontend bug. **Demo Mode** (the toggle in the top
bar) is the way to see the fully populated UI without depending on a
real upload, network access, or a loaded road network; it's always
clearly labeled and never silently substituted for real data.

## Project layout

```
src/
├── app/                        # App Router routes
│   ├── layout.tsx                # Root layout — wraps the app in AppProviders
│   ├── page.tsx                   # Landing/upload page (see components/landing/)
│   └── dashboard/                  # The command-center analysis workspace
├── components/
│   ├── landing/                    # Hero map, upload entry point, minimal top bar
│   ├── command-center/             # The operational UI (upload, analysis, results panels)
│   ├── map/                        # MapLibre integration
│   ├── providers/                  # ThemeProvider, QueryProvider, composed in AppProviders
│   └── ui/                         # shadcn/ui-style primitives
├── services/api/                 # Typed fetch/XHR wrappers per backend resource
├── hooks/                        # TanStack Query hooks wrapping services/api/*
├── store/                        # Zustand stores (client-only UI state, never fetched data)
└── lib/                          # API client, geo/damage/format helpers, color/provenance palettes, demo fixtures
```

## Commands

```bash
npm run dev --workspace=apps/web         # dev server
npm run build --workspace=apps/web       # production build
npm run lint --workspace=apps/web        # eslint
npm run typecheck --workspace=apps/web   # tsc --noEmit
npm run test --workspace=apps/web        # vitest
```
