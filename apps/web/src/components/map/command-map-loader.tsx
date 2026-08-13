"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

/**
 * `next/dynamic(..., { ssr: false })` is itself a client-only API, so this
 * wrapper (not `command-map.tsx` directly) is what callers should import —
 * it guarantees the MapLibre component and the `maplibre-gl` module it
 * loads are never pulled into a server render pass. See
 * `docs/architecture/frontend.md`, "Map technology".
 */
export const CommandMapLoader = dynamic(
  () => import("./command-map").then((mod) => mod.CommandMap),
  {
    ssr: false,
    loading: () => <Skeleton className="size-full rounded-none" />,
  },
);
