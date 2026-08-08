# Builds the SentinelAI frontend (apps/web) using Next.js's standalone
# output. Build context is the repo root: this is an npm workspaces
# monorepo, so the frontend's dependency graph includes packages/shared and
# packages/config, and `npm ci` needs the whole workspace manifest to
# resolve them correctly.

FROM node:22-alpine AS base

FROM base AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared/package.json packages/shared/package.json
COPY packages/config/package.json packages/config/package.json
RUN npm ci

FROM base AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace=apps/web

# Next's standalone output only includes the production dependencies each
# route actually traces to, so the runtime image never carries devDependencies
# or the rest of the monorepo's source.
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

COPY --from=builder /repo/apps/web/public ./apps/web/public
COPY --from=builder /repo/apps/web/.next/standalone ./
COPY --from=builder /repo/apps/web/.next/static ./apps/web/.next/static

EXPOSE 3000

CMD ["node", "apps/web/server.js"]
