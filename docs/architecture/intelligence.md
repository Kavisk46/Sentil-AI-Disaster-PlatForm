# Disaster Intelligence Core Architecture (Milestones F2-F3)

The Disaster Intelligence Core is the domain model and deterministic
decision layer for SentinelAI's future response-orchestration pipeline.
It establishes the typed vocabulary (`Disaster`, `Observation`,
`AffectedArea`, `SearchZone`, `Hazard`, `Resource`, `RescueTeam`,
`Infrastructure`, `Route`, `HazardPrediction`, `Recommendation`,
`Evidence`, `Uncertainty`) and a first, fully deterministic
implementation of search prioritization, capability matching, and
response recommendation — with clean interfaces for a real ML/LLM model
to replace any of them later, without an API-contract change.

## Responsibilities

- Represent a disaster and everything observed/assessed about it as
  clean, typed domain concepts — reusing existing geometry, damage,
  accessibility, and routing types rather than duplicating them.
- Rank candidate search/rescue areas from observed evidence, with every
  score fully explainable and never a claim that a person is located
  there.
- Match response resources to a target by capability, availability,
  reachability, and route operability — kept as four separate,
  inspectable answers, never one opaque score.
- Generate ranked, rule-based response recommendations, each traceable
  to concrete evidence.
- Make uncertainty and missing information explicit everywhere, rather
  than hidden behind a default value.
- Provide the demo scenario and API surface needed to exercise this
  pipeline end-to-end today, while remaining honest that no ML
  prediction or LLM is used anywhere in this milestone.

## Pipeline

```
Disaster observations                    Observation
        |                                     |
Multimodal intelligence         (not implemented this milestone)
        |                                     |
Damage / hazard understanding        AffectedArea, Hazard
        |                                     |          [app.ml / app.risk — existing]
Search-zone prioritization                SearchZone
        |                                     |          [app.intelligence.search_priority]
Resource + capability matching     CapabilityMatchResult
        |                                     |          [app.intelligence.capability_matching]
Accessibility-aware routing                  Route
        |                                     |          [app.routing — existing, reused as-is]
Recommended response                   Recommendation
        |                                     |          [app.intelligence.recommendation]
Evidence + uncertainty              Evidence, Uncertainty
                                                          [attached to every assessed entity above]
```

Every arrow left of "Search-zone prioritization" already existed before
F2 (`app.ml`'s damage classification, `app.risk`'s road-risk formula).
F2's own new code starts at search-zone prioritization and reuses
`app.routing`'s real routing engine unmodified for the "Accessibility-
aware routing" stage (`Route` wraps a real `RouteResult`, never
reinventing pathfinding).

## Domain model

Thirteen typed concepts (`app/intelligence/schemas.py`), each a Pydantic
`BaseModel`:

| Concept | Reuses | Notes |
|---|---|---|
| `Disaster` | — | Top-level incident every other entity is scoped to. `location`/`start_time` optional — never fabricated when the current system can't provide them. |
| `Observation` | — | A piece of *observed* information — explicitly **not** a prediction (see `HazardPrediction`). |
| `AffectedArea` | `DamageClass`, `AccessibilityStatus` | Derived from observations. `affected_population` only ever set from a real source, never estimated. |
| `SearchZone` | — | Ranked candidate for investigation — never a claim a person is located there. See "Search-priority scoring," below. |
| `Hazard` | — | A current/observed hazard — distinct from a *predicted* one (`HazardPrediction`). |
| `Resource` | — | A response capability (drone, ambulance, team, ...). |
| `RescueTeam` | `Resource` (composition) | Adds personnel/skills/equipment/medical/terrain fields a non-human asset doesn't need — not a duplicate of `Resource`. |
| `Infrastructure` | `AccessibilityStatus` | Roads, bridges, hospitals, shelters, ... |
| `Route` | `RouteResult` (`app.routing.schemas`) | Wraps the real routing engine's result — no second pathfinder. `estimated_time_seconds` is always `None`: no travel-time model exists. |
| `HazardPrediction` | — | Interface-only — see "Hazard prediction," below. |
| `Recommendation` | — | The engine's ranked output — see "Recommendation engine," below. |
| `Evidence` | — | Links an assessment back to what justified it. |
| `Uncertainty` | — | Explicit trust representation — see "Uncertainty," below. |

`CapabilityMatchResult` is a fourteenth type but deliberately **not** one
of the 13 core concepts — it's the computed, explainable output of
capability matching, not a primary domain entity.

Every geometry-carrying field (`Geometry`, from
`app.ml.geospatial.geometry` — reused, not duplicated) is paired with an
explicit `*_crs: CoordinateReferenceSystem` field defaulting to `IMAGE`
(non-geographic) — the same discipline `BuildingDamage` already
established, so nothing in this new domain layer can silently treat
pixel coordinates as geographic ones. `app.intelligence.capability_matching`
refuses to compute a real-world distance for any geometry not explicitly
tagged `WGS84`.

Every entity carries `is_simulated: bool`, defaulting to `False` — the
mechanism that guarantees demo/synthetic data
(`app.intelligence.demo_scenario`) is never presented as live
information.

## Search-priority scoring

`app/intelligence/search_priority.py` — a **deterministic baseline
heuristic**, explicitly not a validated search-and-rescue triage model
(the same honesty `app.risk.formula`, Milestone 6B, already established
for road risk):

```
priority_score = sum(value_i * weight_i for available factors)
                  / sum(weight_i for available factors)
```

Four factors, each independently documented in the module:

1. **Damage severity** — reuses `app.ml.geospatial.priority.compute_damage_priority`/
   `priority_rank` (the existing damage-only ordinal scale), normalized to `[0, 1]`.
2. **Accessibility** — `BLOCKED`/`RESTRICTED` areas score *higher* (people
   less able to reach help on their own) than `OPEN` ones — a documented,
   debatable modeling choice, not the only reasonable interpretation.
3. **Population exposure** — only used when `AffectedArea.affected_population`
   is genuinely set; never estimated.
4. **Evidence strength** — derived from `AffectedArea.uncertainty.level`
   and the number of corroborating evidence items.

Every weight is sourced from `SearchPriorityConfig`
(`app/intelligence/config.py`, itself from `Settings.SEARCH_PRIORITY_*`)
— nothing is hardcoded inline, and the config's `__post_init__` rejects
weights that don't sum to 1.0.

**Missing factors are never fabricated.** When a factor's underlying
data is unavailable (e.g. no population figure, or `accessibility is
None`/`UNKNOWN`), it is omitted from the sum entirely and the remaining
weights are renormalized — never treated as `0` (would silently
penalize the zone) or `1` (would silently inflate it). Every omission is
recorded in `SearchZone.missing_factors`, appears in `SearchZone.reasons`,
and escalates `SearchZone.uncertainty` one level. `SearchZone.uncertainty.confidence`
is always `None` — this is a heuristic-derived score, not a calibrated
probability.

## Capability matching

`app/intelligence/capability_matching.py` answers four questions
**separately**, never collapsed into one opaque score:

1. **Can this resource perform the task?** — exact `ResourceCapability`
   set comparison (a closed, coarse vocabulary specifically so this is
   exact, not fuzzy).
2. **Can it reach the target?** — great-circle distance
   (`app.roads.geo_utils.haversine_distance_meters`, reused directly),
   computed *only* when both the resource's location and the target's
   geometry are explicitly tagged `WGS84`. Otherwise `UNKNOWN` — never
   guessed from numbers that might be pixels.
3. **Is the route operational?** — a documented simplification: assessed
   from the resource's own `operational_constraints`
   (`blocking=True` marks it known-not-operational), not a full
   per-candidate routing-engine query. A real implementation would
   additionally query `app.routing`/`app.risk` for hazard-aware
   feasibility per candidate — out of scope for this milestone's
   deterministic-baseline goal.
4. **Is the resource currently available?** — `Resource.availability == AVAILABLE`, nothing else.

**Nearest resource != necessarily best resource**: `rank_candidates()`
sorts *eligible* candidates (all four gates passed) ahead of ineligible
ones, and only uses distance as a final tiebreak among otherwise-equal
eligible candidates — a capability mismatch or unavailability always
outranks proximity, by construction, not by convention.

## Recommendation engine

`app/intelligence/recommendation.py` — three independent, composable
rules, **no LLM, no ML model**:

1. **Search-zone response** — a `HIGH`/`CRITICAL` `SearchZone` gets a
   reconnaissance recommendation (evidence incomplete/uncertain), a
   ground-team deployment recommendation (sufficient evidence + an
   eligible resource — see capability matching), or an escalation
   recommendation (no eligible resource). Which of the three fires is
   itself evidence-driven.
2. **Infrastructure inspection** — a non-operational bridge/road/tunnel
   is flagged for inspection before dispatch.
3. **Hazard avoidance** — a `HIGH`/`CRITICAL` hazard recommends avoiding
   the route through it.

If nothing meets the action threshold, the engine returns one explicit
`hold_pending_more_information` recommendation rather than a bare empty
list that could be mistaken for an engine failure.

Every `Recommendation` carries a non-empty `rationale`, a required
(non-optional) `supporting_evidence` list, and an `uncertainty` object —
`Recommendation -> Evidence -> Observation`, never `Recommendation ->
unexplained output`.

## Hazard prediction — deliberately unimplemented

`app/intelligence/hazard_prediction.py::unavailable_prediction()` is the
**only** constructor this codebase uses for `HazardPrediction` — always
`status=UNAVAILABLE`, `probability=None`, `severity=None`,
`model_source=None`. No predictive hazard model exists in this
milestone (project constraint: "Do not implement advanced ML prediction
yet"). The schema exists so a real, calibrated model can be plugged in
later (a second constructor, e.g. `predict_from_model(...)`) without any
API-contract change.

## Evidence and provenance

`Evidence` links an assessment or recommendation back to the concrete
thing that justified it: a `source_type` (a closed vocabulary —
`observation`, `damage_analysis`, `road_risk_analysis`,
`routing_result`, `resource_registry`, `demo_scenario`), an
`originating_subsystem` (dotted module path), a `timestamp`, a
human-readable `summary`, and an optional `data_ref` (e.g. a building id
or edge id) for traceability back to the underlying record. Every
`AffectedArea`/`Hazard`/`Infrastructure`/`SearchZone`/`Recommendation`
carries `evidence`/`supporting_evidence` — this is structural, not
decorative: the chain from a recommendation back to the observation
behind it is always inspectable.

## Uncertainty

`Uncertainty` makes trust explicit rather than implicit: a qualitative
`level` (`low`/`moderate`/`high`/`unknown` — engineering categories, not
a validated statistical scale, the same honesty `RiskLevel`/
`DamagePriority`/`IncidentSeverity` already established), an optional
numeric `confidence` set **only** when a genuinely calibrated value
exists (never invented — as of F2, this is always `None`, since no
calibrated model exists anywhere in this milestone), a `reason`, and
`missing_information`/`source_limitations` lists. `SearchZone`'s and
`Recommendation`'s own `uncertainty` are heuristic-derived, so their
`confidence` is always `None` too — a formula's output score is not a
calibrated probability, even though it's a real number in `[0, 1]`.

## Demo scenario

`app/intelligence/demo_scenario.py::build_demo_scenario()` builds one
fully deterministic, `is_simulated=True` scenario — see the module's own
docstring for the exact entities and why each one exists (a
capable-but-unavailable resource, a mismatched-and-unreachable resource,
exactly one eligible resource, a non-operational bridge). Every id is
generated via `uuid5(NAMESPACE_URL, ...)` from a fixed name string, not
`uuid4()`, so the scenario is byte-for-byte identical across every
process run — the mechanism that makes `docs/../apps/api/tests/test_intelligence_domain.py`'s
determinism tests possible. Coordinates are centered on `(1.5, 1.5)`,
the same fictional open-ocean point `apps/web/src/lib/demo/demo-data.ts`
uses, so this scenario can never be mistaken for a real place.

Seeded once into `InMemoryIntelligenceRepository` at process start
(`app/api/deps.py`) — deliberately different from
`InMemoryRoadNetworkRepository`'s "starts empty, stays empty" convention,
because F2 has no real-disaster ingestion endpoint yet; without this
seed the API would be permanently unreachable. Safe precisely because
every entity is unambiguously `is_simulated=True`.

## API

Four read-only endpoints under `/api/v1/intelligence/{disaster_id}...`
(`app/api/v1/endpoints/intelligence.py`) — see
[`docs/api/endpoints.md`](../api/endpoints.md) for the full request/response
reference. `disaster_id`, not `incident_id`/`analysis_id`: a `Disaster`
is a broader concept than one image analysis, so it gets its own
identifier rather than overloading an existing one's meaning.

## Known limitations

- No ML-based search or hazard prediction — every score/recommendation
  is a documented, deterministic formula, not a trained model.
- No LLM anywhere in this pipeline.
- No real-disaster ingestion — only the deterministic demo scenario is
  servable in F2.
- Capability matching's "is the route operational" check is a
  simplification (known blocking constraints only), not a full
  per-candidate routing-engine query.
- No persistence — `InMemoryIntelligenceRepository` is process-local,
  matching every other repository in this codebase today.
- `SearchZone`/`Recommendation` weights and thresholds are
  uncalibrated, documented defaults — not fit to any real
  search-and-rescue outcome data.

## Future ML/LLM integration

Every stage in this pipeline is a documented interface a real model can
replace without changing its callers:

- **Search-priority scoring** — `score_search_zone()` could be replaced
  (or augmented as a fifth factor) by a trained model's own output,
  as long as it still produces a `SearchZoneFactor` (or is omitted when
  unavailable, per the existing missing-factor contract).
- **Hazard prediction** — `hazard_prediction.py` already defines the
  full `HazardPrediction` schema; a real model needs only a second
  constructor function producing `status=AVAILABLE` with a genuine
  `probability`.
- **Capability matching** — the "is the route operational" gate could
  call a real per-candidate routing-engine query once that's in scope,
  without changing `CapabilityMatchResult`'s shape.
- **Recommendation engine** — an LLM or multimodal model could replace
  or augment the rule-based engine, as long as it still emits
  `Recommendation`s with the same required `rationale`/
  `supporting_evidence`/`uncertainty` fields — the same "LLM as
  narrator, never silent decision-maker" boundary `app.incident`
  already established for the AI briefing (Milestone 7).

## Future evaluation

See [`docs/research/future-work.md`](../research/future-work.md),
"Multimodal Disaster-Response Intelligence: Baseline Registry," for the
research question, the B0–B4 baseline comparison this deterministic
engine is the control condition for, and the evaluation metrics future
work should report. **No experiments have been run and no performance
claims are made in this milestone.**

## Key Interactions with Other Subsystems

- Reuses `app.ml`'s damage taxonomy, `app.ml.geospatial`'s geometry/CRS
  system, `app.roads`'s accessibility model, and `app.routing`'s real
  routing engine — introduces no parallel versions of any of them.
- Consumed by `app/api/v1/endpoints/intelligence.py` (F2, disaster-scoped)
  and, as of F3, `app/api/v1/endpoints/analysis.py`'s
  `.../intelligence[...]` routes (analysis-scoped) — see "Milestone F3,"
  below.
- The frontend has typed, tested API-client/hook plumbing for both:
  `services/api/intelligence.ts`/`hooks/use-intelligence.ts` (F2,
  disaster-scoped, still not wired into any panel — no UI naturally
  consumes a bare `disaster_id` outside the demo scenario), and
  `services/api/analysis-intelligence.ts`/`hooks/use-analysis-intelligence.ts`
  (F3, analysis-scoped, wired into `intelligence-panel.tsx` in the
  command center) — see `docs/architecture/frontend.md`, "Search &
  response intelligence."

## Milestone F3 — Analysis-Aware Intelligence

F2 built the domain model and deterministic engines against a
hand-authored demo scenario only; nothing consumed *real* analysis
output. F3 adds exactly one integration layer — it does not touch
`app.intelligence`'s scoring/matching/recommendation math, and it does
not replace the existing analysis pipeline:

```
User Upload -> Analysis -> Damage/Risk/Infrastructure Observations
            -> Intelligence Context -> Search Priority
            -> Resource Capability Matching -> Route Feasibility
            -> Response Recommendation -> Command Center UI
```

### The analysis_id / disaster_id relationship

A `Disaster` (F2) and an `Analysis` (Milestones 1-7) are genuinely
different domain concepts — an analysis is one image's damage
classification run; a disaster can span many analyses, observations, and
resources over time. F3 does **not** rename one into the other, add a
shared table, or store a foreign key. Instead,
`app.intelligence.analysis_adapter.derive_disaster_id(analysis_id) ->
UUID` is a pure, deterministic `uuid5(NAMESPACE_URL,
f"https://sentinelai.analysis/{analysis_id}")` derivation — recomputed
fresh on every request, never persisted, never cached. This was chosen
over the alternatives considered:

- **Rename `analysis_id` to `disaster_id`** — rejected: destroys the
  domain distinction the F2 brief explicitly asked to preserve.
- **A stored mapping table** — rejected: adds a persistence concern and
  a migration path for a relationship that's actually pure and
  computable; every other repository in this codebase is intentionally
  process-local/in-memory, and a stored id mapping would be the first
  exception for no real benefit.
- **A derived, non-persisted function** (chosen) — smallest possible
  solution: given the same `analysis_id`, `derive_disaster_id` always
  returns the same `disaster_id`, in every process, forever (same
  determinism technique `demo_scenario.py::_id()` already uses), with
  zero storage and zero migration surface.

An analysis-derived `disaster_id` is disjoint from the F2 demo
scenario's own `disaster_id` — the two id spaces are namespaced apart by
construction (`.../analysis/{id}` vs `.../demo/f2/...`), so they can
never collide.

### Analysis -> Intelligence Context adapter

`app/intelligence/analysis_adapter.py::build_context_from_analysis(analysis,
buildings, road_risk) -> AnalysisContextResult` is the **only** place
real analysis data becomes an F2 `DisasterScenario`. It consumes
already-fetched domain objects (`DamageAnalysis`, `list[BuildingDamage]`,
`RoadRiskResponse`) — never raw HTTP, following the existing
`RoadRiskService`/`RoutingService` convention of composing services, not
re-parsing responses.

Mapping, field by field:

| F3 input | F2 output | Notes |
|---|---|---|
| `DamageAnalysis.status`/`.failure` | `AnalysisContextResult.unavailable_reason` | Not `COMPLETED` -> `ANALYSIS_NOT_COMPLETED`; `FAILED` with `MODEL_UNAVAILABLE`/`INFERENCE_FAILURE` -> the same code, reused verbatim from `AnalysisErrorCode` rather than inventing a parallel one. |
| `BuildingDamage` (georeferenced, WGS84 only) | `AffectedArea` | Non-georeferenced or non-WGS84-tagged buildings are silently excluded, never coerced — see "CRS safety," below. Zero buildings, or zero *georeferenced* buildings, produce `INSUFFICIENT_EVIDENCE`/`NO_GEOREFERENCE` respectively rather than an empty-but-"available" scenario. |
| `BuildingDamage.confidence` | `AffectedArea.uncertainty.level` | Mapped to a qualitative `LOW`/`MODERATE`/`HIGH` band (`>=0.8`/`>=0.5`/below) — `confidence` itself is never copied into `Uncertainty.confidence` (that field stays `None`, the same F2 discipline for a non-calibrated score). |
| `RoadRiskResponse.edges` | `Infrastructure` | Only when `road_risk.available`; each edge's `RiskLevel` maps to an `InfrastructureStatus` (`CRITICAL`/`HIGH`/`MODERATE` -> non-operational/degraded, `LOW` -> operational). Geometry is a documented, honest placeholder (`geometry_crs=IMAGE`, a zero-sized `BoundingBoxGeometry`) — the analysis pipeline doesn't expose real road-segment coordinates outside a computed route, so this is never rendered as if it were geographic (see `command-map.tsx`, which only ever plots `EPSG:4326`-tagged geometry). |
| — | `Disaster` | Synthesized fresh per request: `id=derive_disaster_id(...)`, `is_simulated=False`, `provenance` names the source analysis explicitly. |
| — | `Resource` pool | Reuses `build_demo_scenario().resources` verbatim — no real resource-ingestion system exists (see "DEMO vs ANALYSIS," below). |
| — | `Observation`, `Hazard`, `Route` | Always empty tuples — F3 does not fabricate observations, hazards, or precomputed routes that don't exist. |

Once a `DisasterScenario` exists, F3 reuses F2's own engines completely
unmodified: `IntelligenceService.score_zones_for_scenario()`/
`.recommendations_for_scenario()` (extracted from the previously-inlined
`get_search_zones`/`get_recommendations` bodies specifically so both the
F2 disaster-scoped path and this new analysis-derived path share one
implementation — see the extraction's doc comment in
`app/services/intelligence_service.py`). There is no second scoring
engine.

### Route feasibility — "can this resource actually reach this zone?"

`app/services/analysis_intelligence_service.py::_match_candidates_for_zone`/
`_attempt_route` answer this literally, not just "what's nearest," for
the single top-ranked, otherwise-eligible candidate against the single
top-priority search zone (bounded scope — not every resource × every
zone, which would be both expensive and out of proportion to what the
UI needs). A real route is computed via the exact same
`RoutingService.route()` engine `POST /api/v1/routing` uses — no second
pathfinder, no invented geometry:

- Roads not loaded for this analysis -> `route_unavailable`.
- Candidate resource has no known location, or either the resource's or
  the zone's geometry isn't tagged `EPSG:4326` -> `route_unavailable`
  (never treats an untagged/IMAGE-space coordinate as geographic).
- Otherwise -> `computed`, carrying the real `RouteResult` (which may
  itself report `found=false` — a computed-but-not-found route is still
  `"computed"`, distinct from "never attempted").

Every other ranked candidate gets `not_applicable` — computed only for
the top candidate, by design, not silently omitted.

### DEMO vs ANALYSIS

The app has two independent data modes, both already established by F1;
F3 extends the same split rather than inventing a third:

- **DEMO mode** — `apps/web/src/lib/demo/demo-data.ts`'s
  `DEMO_SEARCH_ZONES`/`DEMO_RECOMMENDATIONS`/`DEMO_RESOURCE_CANDIDATES`,
  hand-authored fixtures mirroring the shape (not a live fetch of) the
  backend's own `build_demo_scenario()` — consistent with every other
  `DEMO_*` fixture in that file: Demo mode never touches the network.
  `is_simulated: true` throughout.
- **ANALYSIS mode** — real `GET /api/v1/analysis/{analysis_id}/intelligence[...]`
  responses. `is_simulated: false` for the analysis-derived entities
  themselves (search zones, recommendations) — but `resources_are_demo:
  true` **always**, independently, because no real resource-ingestion
  system exists yet. This is the one place both flags matter
  simultaneously: a real analysis's real search zones can be paired with
  admittedly-fake resource candidates, and the UI (`intelligence-panel.tsx`)
  labels each independently (a panel-level "CALC" vs "SIM" badge for the
  zones/recommendations, and a per-row "SIM" badge on every resource
  candidate, regardless of the panel-level label) — never collapsed into
  one flag, and never presented as real telemetry.

### API

Three new analysis-scoped, read-only endpoints under
`/api/v1/analysis/{analysis_id}/intelligence...`
(`app/api/v1/endpoints/analysis.py`) — additive to, and independent of,
F2's four `disaster_id`-scoped endpoints, which are unchanged. See
[`docs/api/endpoints.md`](../api/endpoints.md) for the full request/response
reference.

## Status

Milestone F2 ("Disaster Intelligence Core") delivered the domain model,
the deterministic search-priority/capability-matching/recommendation
pipeline, the demo scenario, the four disaster-scoped read-only API
endpoints, and typed frontend plumbing. Milestone F3 ("Analysis-Aware
Intelligence") connects that pipeline to the real analysis pipeline's
outputs — the `analysis_adapter`, three new analysis-scoped endpoints,
route-feasibility enrichment, and full command-center UI integration
(map layers, the "Search & response intelligence" panel, DEMO/ANALYSIS
labeling). No ML prediction, no LLM, and no real-disaster/resource
ingestion exist yet in either milestone — see "Known limitations,"
above, and "Future ML/LLM integration" for the intended extension
points, which apply equally to the F3 analysis-derived path (it reuses
F2's engines unmodified).
