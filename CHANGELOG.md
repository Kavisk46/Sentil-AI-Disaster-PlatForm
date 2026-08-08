# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet.

## [0.2.0] - 2026-07-19

### Added
- Sprint 1 — engineering foundation. Restructured the repository into an
  npm-workspaces monorepo: `apps/web`, `apps/api`, `packages/shared`,
  `packages/config`, `packages/ai`.
- Backend (`apps/api`): FastAPI application factory with Clean Architecture
  layering (`app/core`, `app/api`, `app/middleware`, `app/schemas`),
  environment-based settings, structured logging, CORS and request-logging
  middleware, versioned routing under `/api/v1`, an unversioned `/health`
  endpoint, and a pytest suite.
- Frontend (`apps/web`): Next.js 15 App Router project with React 19, strict
  TypeScript, Tailwind CSS v4, shadcn/ui primitives, a TanStack Query
  provider, a Zustand UI store, a theme provider (light/dark), and an empty
  dashboard route that verifies backend connectivity via `/health`.
- Docker: `docker/api.Dockerfile`, `docker/web.Dockerfile`, and a
  `docker-compose.yml` that runs both services together.
- `.env.example` for both `apps/api` and `apps/web`.

### Changed
- Moved `frontend/` → `apps/web`, `backend/` → `apps/api`, `ai/` → `packages/ai`.

## [0.1.0] - 2026-07-18

### Added
- Initial repository foundation: project structure for `frontend/`, `backend/`, `ai/`, `datasets/`, `docs/`, `docker/`, and `scripts/`.
- Core project documentation: `README.md`, `PROJECT_ROADMAP.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.
- Architecture, API, and research documentation placeholders under `docs/`.
- GitHub issue templates, pull request template, and CI lint workflow.
- Root `docker-compose.yml` scaffold and `.gitignore` for the project's technology stack.

[Unreleased]: https://github.com/<your-org>/sentinel-ai/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/<your-org>/sentinel-ai/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/<your-org>/sentinel-ai/releases/tag/v0.1.0
