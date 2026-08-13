"""AI incident intelligence (Milestone 7).

    API -> IncidentIntelligenceService -> Context Builder -> LLM Provider
        -> Schema Validation -> Incident Briefing

Converts SentinelAI's structured, deterministic analysis results (damage
predictions — Milestone 3/5, road risk — Milestone 6B, routing — Milestone
6C) into a concise operational briefing. **The LLM is a communication and
synthesis layer, never the source of truth.** It never decides damage
classification, geographic coordinates, road risk, or route selection —
those are already-computed facts by the time this package sees them; the
LLM's only job is to phrase a narrative *about* those facts, and even that
narrative is validated and filtered before it ever reaches a client (see
"Hallucination controls," below).

## Why an LLM is used at all

A structured `IncidentContext` (counts, ratios, IDs, numbers) is precise
but not what a time-pressured responder wants to read first. An LLM turns
that structure into a short, readable narrative — "the highest-priority
area is X, the selected route avoids N high-risk segments at the cost of
Y meters" — faster than a human would compose the same sentence by hand.
That is the *entire* value this package asks an LLM to provide: phrasing,
not analysis.

## Why the LLM is not the decision-maker

Every fact a responder might act on — how many buildings are destroyed,
which roads are risky, which route was selected — is already a real
number *before* any LLM call happens (`IncidentContext`, assembled by
`context_builder.py` purely from Milestones 3–6C's own outputs).
`incident_severity`, `confidence`, and `affected_structures` in the final
`IncidentBriefing` are **computed deterministically by
`severity.py`/`briefing_builder.py` — never taken from LLM output at
all** — the LLM's returned JSON (`LLMNarrativeOutput`) only ever supplies
the four free-text fields (`priority_area`, `route_summary`,
`key_findings`, `limitations`); the numeric/categorical fields it might
also emit are always overwritten. This makes it structurally impossible
for a hallucinated severity or confidence number to reach a client.

## Files

- `schemas.py` — `IncidentContext` (input), `LLMNarrativeOutput` (the only
  thing an `LLMProvider` produces), `IncidentBriefing` (final output).
- `config.py` — `IncidentConfig`: severity/confidence thresholds, sourced
  from `Settings`.
- `context_builder.py` — `build_incident_context()`: assembles
  `IncidentContext` from `DamageAnalysis`/`RoadRiskResponse`/
  `RouteComparison | None`. Pure data reshaping, no LLM.
- `severity.py` — `classify_incident_severity()`/`classify_confidence()`/
  `build_affected_structures_summary()`: deterministic classification,
  kept in its own module specifically because it must never be delegated
  to the LLM.
- `prompt.py` — `PROMPT_VERSION` (`"incident_summary_v1"`), the system
  prompt, and `build_user_message()` (delimits `IncidentContext` as DATA
  — see "Prompt injection defense," below).
- `provider.py` — `LLMProvider` Protocol + `LLMProviderError`/
  `LLMTimeoutError`.
- `mock_provider.py` — `MockLLMProvider`: deterministic, offline, for
  tests.
- `fallback.py` — `build_fallback_narrative()` (pure template function)
  and `DeterministicSummaryProvider` (an `LLMProvider` that just calls
  it) — the default production provider, and the safety net every other
  provider falls back to on failure.
- `anthropic_provider.py` — `AnthropicLLMProvider`: the one real,
  network-calling provider implemented this milestone, isolated entirely
  behind `LLMProvider` — never invoked by the test suite or by default
  configuration.
- `validator.py` — `parse_llm_output()`: raw text -> `LLMNarrativeOutput`
  or `None` (never raises).
- `grounding.py` — `filter_unsupported_claims()`: rejects narratives that
  mention banned, unsupported topics (casualties, weather, evacuation
  orders, tsunami/flood timing, ...) or look like an invented coordinate.
- `briefing_builder.py` — `assemble_briefing()`: combines a validated,
  grounded `LLMNarrativeOutput` (or the deterministic fallback) with the
  deterministically-computed severity/confidence/affected-structures and
  a fixed safety disclaimer into the final `IncidentBriefing`.

`app.services.incident_intelligence_service.IncidentIntelligenceService`
is the DI-facing orchestration (analysis/road-risk/routing lookups,
provider selection) — see that module for the full request pipeline and
how "malformed output"/"timeout"/"provider error"/"unsupported claim"
each fall back to the same deterministic narrative.

## Prompt injection defense

`IncidentContext` deliberately contains **no user-controlled free text**
(no original filename, no arbitrary string fields) — the safest defense
against prompt injection is to never place untrusted text where a model
might treat it as instructions, rather than trying to sanitize it
perfectly after the fact. `build_user_message()` still wraps the
structured JSON context in an explicit `<incident_context>` delimiter
with an instruction that its contents are DATA, not directives — defense
in depth, and future-proofing against a later milestone adding a
free-text field.

## Do not implement (this milestone)

Hazard prediction, tsunami prediction, flood forecasting, evacuation
recommendation, autonomous emergency decisions, live emergency alerts,
frontend changes, or 3D visualization. All later milestones (or, for
autonomous decisions/live alerts, explicitly never this project's role —
see "Safety" in apps/api/README.md).
"""
