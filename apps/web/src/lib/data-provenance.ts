/**
 * The "research presentation rule": every piece of information in the UI
 * must be traceable to exactly one of these four categories, so a
 * responder never mistakes a model prediction or an LLM sentence for a
 * measured fact. Styled like `lib/risk-colors.ts` (code + label + color),
 * plus a `description` used as the badge's accessible/hover explanation.
 * See `docs/architecture/frontend.md`, "Data provenance labeling".
 */

export type ProvenanceCategory = "observed" | "predicted" | "calculated" | "generated";

interface ProvenanceStyle {
  code: string;
  label: string;
  description: string;
  className: string;
}

export const PROVENANCE_STYLE: Record<ProvenanceCategory, ProvenanceStyle> = {
  observed: {
    code: "OBS",
    label: "Observed",
    description: "Read directly from the uploaded file — not inferred.",
    className: "text-sky-400 border-sky-500/40 bg-sky-500/10",
  },
  predicted: {
    code: "PRED",
    label: "Predicted",
    description: "Output of the damage-classification model.",
    className: "text-violet-400 border-violet-500/40 bg-violet-500/10",
  },
  calculated: {
    code: "CALC",
    label: "Calculated",
    description: "Deterministically computed from other real data (a documented formula, not a model).",
    className: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  },
  generated: {
    code: "GEN",
    label: "AI-generated",
    description: "Written by the incident-briefing LLM (or its deterministic fallback) — a summary, not a measurement.",
    className: "text-amber-400 border-amber-500/40 bg-amber-500/10",
  },
};
