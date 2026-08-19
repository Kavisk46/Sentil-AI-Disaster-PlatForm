import type { DamageFeatureCollection } from "@sentinelai/shared";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ProvenanceBadge } from "@/components/ui/provenance-badge";
import { boundingBoxAreaKm2, computeFeatureBounds } from "@/lib/geo";

export interface AffectedAreaPanelProps {
  /** The same `DamageMapResponse.feature_collection` the map renders — see
   * `command-map.tsx`. `null` when damage data isn't available. */
  featureCollection: DamageFeatureCollection | null;
  damageAvailable: boolean;
  damageReason: string | null;
  isDamageLoading: boolean;
  isDamageError: boolean;
  damageErrorMessage?: string;
  /** `IncidentBriefing.priority_area` — AI-generated prose, a different
   * provenance category from the bounding box below (see
   * `lib/data-provenance.ts`), so it's labeled and gated independently. */
  priorityArea: string | null;
  isBriefingAvailable: boolean;
  className?: string;
}

/**
 * The one genuinely new data panel this milestone adds. Two independent
 * pieces of real data, each honestly gated and labeled: a calculated
 * bounding-box/area figure derived from real damage-map coordinates
 * (`lib/geo.ts::computeFeatureBounds`/`boundingBoxAreaKm2` — the same
 * "trust the feature collection as given" convention `command-map.tsx`
 * uses), and the AI briefing's free-text `priority_area`. Neither
 * fabricates a value when its source isn't available — see
 * `docs/architecture/frontend.md`, "Data provenance labeling".
 */
export function AffectedAreaPanel({
  featureCollection,
  damageAvailable,
  damageReason,
  isDamageLoading,
  isDamageError,
  damageErrorMessage,
  priorityArea,
  isBriefingAvailable,
  className,
}: AffectedAreaPanelProps) {
  const isGeographic = featureCollection?.coordinate_reference_system === "EPSG:4326";
  const bounds =
    damageAvailable && isGeographic && featureCollection ? computeFeatureBounds(featureCollection) : null;
  const areaKm2 = bounds ? boundingBoxAreaKm2(bounds) : null;

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Affected area</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Mapped extent
            </p>
            <ProvenanceBadge category="calculated" />
          </div>

          {isDamageLoading && <Skeleton className="h-4 w-2/3" />}

          {!isDamageLoading && isDamageError && (
            <Alert variant="destructive">
              <AlertTitle>Affected-area data unavailable</AlertTitle>
              <AlertDescription>{damageErrorMessage ?? "The backend could not be reached."}</AlertDescription>
            </Alert>
          )}

          {!isDamageLoading && !isDamageError && damageAvailable && !isGeographic && (
            <p className="text-muted-foreground text-sm">
              Damage geometry is currently available in image coordinates and cannot yet be placed
              accurately on the geographic map.
            </p>
          )}

          {!isDamageLoading && !isDamageError && !bounds && !(damageAvailable && !isGeographic) && (
            <p className="text-muted-foreground text-sm">
              {damageReason ?? "No mapped damage geometry is available for this analysis yet."}
            </p>
          )}

          {!isDamageLoading && !isDamageError && bounds && areaKm2 !== null && (
            <p className="text-sm">
              <span className="font-semibold tabular-nums">{areaKm2.toFixed(2)} km²</span>{" "}
              <span className="text-muted-foreground">bounding extent of mapped damage</span>
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Priority area
            </p>
            <ProvenanceBadge category="generated" />
          </div>

          {!isBriefingAvailable || !priorityArea ? (
            <p className="text-muted-foreground text-sm">
              A priority-area assessment will be generated once the analysis is complete.
            </p>
          ) : (
            <p className="text-sm">{priorityArea}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
