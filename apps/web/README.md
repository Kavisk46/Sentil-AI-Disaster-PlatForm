# SentinelAI Frontend

Next.js 15 (App Router) frontend. Sprint 1 delivers the engineering
foundation: providers (theme, TanStack Query), a Zustand UI store, shadcn/ui
primitives, and an empty dashboard shell — no operational UI yet.

See [`docs/architecture/frontend.md`](../../docs/architecture/frontend.md)
for the architecture and folder conventions.

## Local development

From the repository root (this app is part of an npm workspace):

```bash
npm install
cp apps/web/.env.example apps/web/.env.local
npm run dev --workspace=apps/web
```

Open http://localhost:3000 — it redirects to `/dashboard`, which shows the
provider/state wiring and a live backend status check against `apps/api`'s
`/health` endpoint.

## Project layout

```
src/
├── app/                   # App Router routes
│   ├── layout.tsx          # Root layout — wraps the app in AppProviders
│   └── dashboard/           # Empty dashboard shell (Sprint 1)
├── components/
│   ├── providers/            # ThemeProvider, QueryProvider, composed in AppProviders
│   └── ui/                    # shadcn/ui primitives
├── store/                  # Zustand stores (client-only UI state)
├── hooks/                  # TanStack Query hooks
└── lib/                    # cn() helper, typed API client
```

## Commands

```bash
npm run dev --workspace=apps/web         # dev server
npm run build --workspace=apps/web       # production build
npm run lint --workspace=apps/web        # eslint
npm run typecheck --workspace=apps/web   # tsc --noEmit
```
