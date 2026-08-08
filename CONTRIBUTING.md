# Contributing to SentinelAI

Thank you for considering a contribution to SentinelAI. This document describes how the project is branched, how commits and pull requests are structured, and the coding standards contributors are expected to follow.

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Table of Contents

- [Branch Strategy](#branch-strategy)
- [Commit Message Convention](#commit-message-convention)
- [Coding Standards](#coding-standards)
- [Folder Organization](#folder-organization)
- [Issue Workflow](#issue-workflow)
- [Pull Request Workflow](#pull-request-workflow)

## Branch Strategy

SentinelAI uses a trunk-based workflow with short-lived feature branches.

- `main` is the always-releasable trunk. Direct commits to `main` are not permitted.
- All work happens on a branch created from `main`, named using the pattern:

  ```
  <type>/<short-description>
  ```

  Where `<type>` matches one of the commit types below, for example:

  ```
  feat/damage-detection-api
  fix/routing-graph-null-edge
  docs/architecture-overview
  chore/update-dependencies
  ```

- Branches should be scoped to a single logical change and kept short-lived. Rebase onto `main` regularly to avoid large, conflict-prone merges.
- Once merged, branches are deleted. History is kept linear where practical; prefer rebase over merge commits for updating a branch with `main`.

## Commit Message Convention

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <short summary>

<optional body>

<optional footer>
```

**Allowed types:**

| Type | Use for |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation-only changes |
| `style` | Formatting changes with no code meaning change |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `test` | Adding or correcting tests |
| `chore` | Tooling, dependency, or build-process changes |
| `ci` | Changes to CI configuration |

**Examples:**

```
feat(api): add incident ingestion endpoint
fix(web): exclude edges flagged as impassable from the route overlay
docs(architecture): document AI engine data flow
```

Commits should be atomic and describe *why* a change was made when the reason is not obvious from the diff alone.

## Coding Standards

**Backend (`apps/api` — Python / FastAPI)**
- Follow [PEP 8](https://peps.python.org/pep-0008/); format and lint with `ruff` (`ruff format .` / `ruff check .`).
- Type-check with `mypy --strict`; every public function and Pydantic model must carry full type hints.
- Prefer explicit, narrow exceptions over broad `except Exception` handling.
- Follow Clean Architecture layering: `app/core` (settings/logging, no framework imports beyond what's needed), `app/api` (routers, versioned under `app/api/v1`), `app/middleware`, `app/schemas`. New business/domain logic should get its own layer rather than being added to routers directly.

**Frontend (`apps/web` — Next.js / React / TypeScript)**
- Format with `prettier` (via the root `format` script); lint with `eslint` using the shared config in `packages/config`.
- `strict` TypeScript is enforced repo-wide (`packages/config/typescript/base.json`); avoid `any`.
- Server state (API data) belongs in TanStack Query; client-only UI state belongs in a Zustand store (`src/store/`) — don't duplicate one in the other.
- Co-locate component styles and tests with the component they belong to.

**AI (`packages/ai` — Python / PyTorch, from Phase 4)**
- Follow the same Python standards as the backend.
- Document model inputs, outputs, and expected tensor shapes in docstrings.
- Keep data preprocessing, training, and inference code in clearly separated modules.

**General**
- Keep functions and modules focused on a single responsibility.
- Write self-documenting code; add comments only to explain non-obvious rationale, not to restate what the code does.
- No commented-out code or unused imports in merged changes.

## Folder Organization

The repository is an npm-workspaces monorepo organized by app and shared package:

- `apps/` — deployable applications: `web` (frontend) and `api` (backend). Each owns its full dependency manifest (`package.json` / `pyproject.toml`).
- `packages/` — code shared across apps: `shared` (TypeScript types), `config` (lint/format/tsconfig presets), `ai` (reserved for the future Python AI engine).
- `docs/` — all project documentation, organized by topic (architecture, API, research).
- `datasets/` — dataset documentation and small sample data only; large raw datasets are never committed (see `datasets/README.md`).
- `docker/` — one Dockerfile per service, referenced by the root `docker-compose.yml`.
- `scripts/` — developer and operational scripts shared across workstreams.
- `.github/` — issue templates, pull request template, and CI workflows.

New top-level directories should not be introduced without discussion in an issue first, to keep the repository structure predictable for contributors.

## Issue Workflow

1. **Search first.** Check open and closed issues before filing a new one to avoid duplicates.
2. **Use the templates.** Bug reports and feature requests each have a dedicated template under `.github/ISSUE_TEMPLATE/`. Fill in all requested context.
3. **Labeling.** Maintainers will triage new issues with priority, type, and area labels. Contributors may suggest labels but should not rely on self-assignment before triage.
4. **Claiming work.** Comment on the issue before starting work to avoid duplicate effort. Issues without an assignee are considered open for anyone to pick up.

## Pull Request Workflow

1. **Branch from `main`** using the naming convention above, and keep the change scoped to one issue or logical unit of work.
2. **Fill out the PR template.** Describe what changed, why, and how it was verified.
3. **Link the related issue** using a closing keyword (e.g., `Closes #123`) where applicable.
4. **Pass CI.** All required checks must pass before a review is requested.
5. **Request review.** At least one maintainer approval is required before merge.
6. **Address feedback** with additional commits on the same branch; avoid force-pushing over review history until review is complete.
7. **Merge strategy.** Pull requests are squash-merged into `main` so the commit history on `main` remains one entry per change.

Thank you for helping build SentinelAI.
