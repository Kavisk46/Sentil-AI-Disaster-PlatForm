# @sentinelai/shared

Shared TypeScript types and small framework-agnostic utilities used by more
than one frontend app in this monorepo. Consumed directly from source (no
build step) via each app's `transpilePackages` configuration.

## Contents

- `src/types/api.ts` — types mirroring the backend's infrastructure-level
  response shapes (`HealthStatus`, `ServiceInfo`) and a generic `ApiResult<T>`
  result type for typed fetch wrappers.

This package intentionally contains no domain logic (incidents, imagery,
detections, ...); it exists to keep cross-cutting types in one place as the
number of frontend apps grows.
