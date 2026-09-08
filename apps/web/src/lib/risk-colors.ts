import type {
  AccessibilityStatus,
  ConfidenceLevel,
  DamageClass,
  IncidentSeverity,
  RiskLevel,
  SearchPriorityLevel,
} from "@sentinelai/shared";

/**
 * Single source of truth for every color/label pairing used to represent
 * damage severity, road risk, road accessibility, incident severity, and
 * confidence — both in React (Tailwind arbitrary-value classes reading
 * `.hex`) and in MapLibre paint expressions (which need real color
 * strings, not Tailwind class names, so a CSS-variable indirection would
 * not work for the map layers).
 *
 * Every level also carries a short, non-color `code` and a full `label` —
 * risk/severity must never be communicated by color alone (WCAG 1.4.1),
 * per the milestone's own accessibility requirement.
 */

interface LevelStyle {
  code: string;
  label: string;
  hex: string;
  /** Tailwind text/border color classes matching `hex`, for badges. */
  className: string;
}

export const DAMAGE_CLASS_STYLE: Record<DamageClass, LevelStyle> = {
  no_damage: {
    code: "ND",
    label: "No damage",
    hex: "#64748b",
    className: "text-slate-400 border-slate-500/40 bg-slate-500/10",
  },
  minor: {
    code: "MN",
    label: "Minor",
    hex: "#eab308",
    className: "text-yellow-400 border-yellow-500/40 bg-yellow-500/10",
  },
  major: {
    code: "MJ",
    label: "Major",
    hex: "#f97316",
    className: "text-orange-400 border-orange-500/40 bg-orange-500/10",
  },
  destroyed: {
    code: "DS",
    label: "Destroyed",
    hex: "#ef4444",
    className: "text-red-400 border-red-500/40 bg-red-500/10",
  },
};

/** Relative visual weight for damage classes — larger map markers and
 * higher stacking order for more severe classes (minor < major < destroyed). */
export const DAMAGE_CLASS_WEIGHT: Record<DamageClass, number> = {
  no_damage: 0,
  minor: 1,
  major: 2,
  destroyed: 3,
};

export const RISK_LEVEL_STYLE: Record<RiskLevel, LevelStyle> = {
  low: {
    code: "L",
    label: "Low",
    hex: "#22c55e",
    className: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  },
  moderate: {
    code: "M",
    label: "Moderate",
    hex: "#eab308",
    className: "text-yellow-400 border-yellow-500/40 bg-yellow-500/10",
  },
  high: {
    code: "H",
    label: "High",
    hex: "#f97316",
    className: "text-orange-400 border-orange-500/40 bg-orange-500/10",
  },
  critical: {
    code: "C",
    label: "Critical",
    hex: "#ef4444",
    className: "text-red-400 border-red-500/40 bg-red-500/10",
  },
};

/**
 * Accessibility uses a deliberately distinct visual language from risk
 * (icon shape + dash pattern, not just another color scale) so the two
 * concepts are never visually conflated — see the module docstring.
 */
export const ACCESSIBILITY_STYLE: Record<
  AccessibilityStatus,
  LevelStyle & { dashArray: number[] | null }
> = {
  open: {
    code: "OPEN",
    label: "Open",
    hex: "#38bdf8",
    className: "text-sky-400 border-sky-500/40 bg-sky-500/10",
    dashArray: null,
  },
  restricted: {
    code: "RSTR",
    label: "Restricted",
    hex: "#a78bfa",
    className: "text-violet-400 border-violet-500/40 bg-violet-500/10",
    dashArray: [2, 1.5],
  },
  blocked: {
    code: "BLKD",
    label: "Blocked",
    hex: "#94a3b8",
    className: "text-slate-300 border-slate-400/40 bg-slate-400/10",
    dashArray: [0.5, 1.5],
  },
  unknown: {
    code: "UNK",
    label: "Unknown",
    hex: "#64748b",
    className: "text-slate-500 border-slate-600/40 bg-slate-600/10",
    dashArray: null,
  },
};

export const INCIDENT_SEVERITY_STYLE: Record<IncidentSeverity, LevelStyle> = {
  low: RISK_LEVEL_STYLE.low,
  moderate: RISK_LEVEL_STYLE.moderate,
  high: RISK_LEVEL_STYLE.high,
  critical: RISK_LEVEL_STYLE.critical,
  unknown: {
    code: "?",
    label: "Unknown",
    hex: "#64748b",
    className: "text-slate-400 border-slate-500/40 bg-slate-500/10",
  },
};

export const CONFIDENCE_STYLE: Record<ConfidenceLevel, LevelStyle> = {
  high: RISK_LEVEL_STYLE.low,
  moderate: RISK_LEVEL_STYLE.moderate,
  low: RISK_LEVEL_STYLE.high,
  unknown: INCIDENT_SEVERITY_STYLE.unknown,
};

/** F3: search-zone priority uses the exact same 4-level scale/colors as
 * road risk — both are "how urgent is this" scales, so reusing
 * `RISK_LEVEL_STYLE` keeps the visual language consistent across panels
 * (same reasoning `INCIDENT_SEVERITY_STYLE` already applies above). */
export const SEARCH_PRIORITY_STYLE: Record<SearchPriorityLevel, LevelStyle> = RISK_LEVEL_STYLE;

export const ROUTE_MODE_STYLE = {
  risk_aware: { hex: "#38bdf8", label: "Risk-aware", className: "text-sky-400" },
  distance_only: { hex: "#94a3b8", label: "Distance-only", className: "text-slate-400" },
} as const;
