import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a minimal, self-contained `.next/standalone` build (only the
  // files actually needed at runtime) so the Docker image doesn't have to
  // ship the full node_modules tree — see docker/web.Dockerfile.
  output: "standalone",

  // This monorepo's workspace packages are consumed as TypeScript source
  // (no build step of their own), so Next must transpile them itself
  // rather than expecting pre-built JS in node_modules.
  transpilePackages: ["@sentinelai/shared"],
};

export default nextConfig;
