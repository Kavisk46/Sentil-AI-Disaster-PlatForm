/** Generic (non-geo) display formatters — colocated home parallel to
 * `lib/geo.ts`'s `formatDistanceMeters`/`formatPercent`. */

const UNITS = ["B", "KB", "MB", "GB"] as const;

/** Human-readable file size, e.g. `formatBytes(1536)` -> `"1.5 KB"`. */
export function formatBytes(bytes: number): string {
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < UNITS.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const digits = unitIndex === 0 || value >= 10 ? 0 : 1;
  return `${value.toFixed(digits)} ${UNITS[unitIndex]}`;
}
