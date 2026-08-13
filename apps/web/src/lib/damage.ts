import type { DamageSummary } from "@sentinelai/shared";

export interface DamageBreakdown {
  no_damage: number;
  minor: number;
  major: number;
  destroyed: number;
}

/**
 * `DamageSummary` (from `GET /api/v1/analysis/{id}`) reports
 * `total_buildings`/`damaged_buildings`/`severely_damaged`/`destroyed`,
 * not a count per individual `DamageClass` — so the per-class breakdown
 * the stats panel needs is derived by arithmetic, using the backend's own
 * documented definitions (`app/ml/schemas.py`): `severely_damaged` =
 * `major` + `destroyed`, and `damaged_buildings` covers every class other
 * than `no_damage`. Every input here is a real number from the API;
 * nothing is invented — this is a re-derivation of the same data, not a
 * fabrication of new data. `Math.max(..., 0)` only guards against
 * floating-point/ordering edge cases in unexpected input; well-formed
 * backend responses never actually go negative.
 */
export function deriveDamageBreakdown(summary: DamageSummary): DamageBreakdown {
  const destroyed = summary.destroyed;
  const major = Math.max(summary.severely_damaged - destroyed, 0);
  const minor = Math.max(summary.damaged_buildings - summary.severely_damaged, 0);
  const noDamage = Math.max(summary.total_buildings - summary.damaged_buildings, 0);
  return { no_damage: noDamage, minor, major, destroyed };
}
