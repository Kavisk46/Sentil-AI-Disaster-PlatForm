# @sentinelai/config

Shared, versioned tooling configuration for every JS/TypeScript app and
package in this monorepo, so lint/format/compiler rules are defined once and
consumed everywhere rather than drifting between `apps/web` and future apps.

## Contents

- `eslint.config.js` — base flat ESLint config (JS + TypeScript rules).
- `prettier.config.js` — shared Prettier config, including Tailwind class sorting.
- `typescript/base.json` — strict base `tsconfig` for any TS package.
- `typescript/nextjs.json` — extends `base.json` with Next.js-specific compiler options.

## Usage

From a consuming package (e.g. `apps/web`):

```js
// eslint.config.mjs
import baseConfig from "@sentinelai/config/eslint";
export default [...baseConfig /* app-specific overrides */];
```

```jsonc
// tsconfig.json
{ "extends": "@sentinelai/config/typescript/nextjs" }
```
