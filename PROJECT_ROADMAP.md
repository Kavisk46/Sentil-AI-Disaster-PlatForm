# Project Roadmap

This document describes the phased development plan for SentinelAI. Each phase lists its objectives, concrete deliverables, and the outcome that must be true before the next phase begins. Phases are sequential in intent but may overlap in execution once the foundation (Phases 0–1) is complete.

---

## Phase 0 — Research

**Objectives**
- Establish the technical and domain feasibility of AI-assisted disaster damage assessment.
- Survey existing aerial imagery datasets, damage taxonomies, and prior academic/industry work.
- Identify the geospatial, computer vision, and LLM techniques best suited to the platform's goals.

**Deliverables**
- Literature review of relevant computer vision and disaster-response research (`docs/research/literature-review.md`).
- Candidate dataset shortlist with licensing and access notes.
- Initial damage classification taxonomy (e.g., structural severity levels, infrastructure categories).

**Expected Outcomes**
- A documented, evidence-based rationale for the platform's technical approach.
- Clear understanding of data availability and gaps that later phases must plan around.

---

## Phase 1 — Project Foundation

**Objectives**
- Establish the repository, documentation, and contribution standards required for sustained open-source collaboration.
- Define the system architecture at a level sufficient to guide independent backend, frontend, and AI workstreams.

**Deliverables**
- Repository scaffold: directory structure, README, roadmap, contributing guide, code of conduct, changelog, license.
- Architecture documentation (`docs/architecture/`).
- Issue and pull request templates, CI workflow scaffolding.

**Expected Outcomes**
- A new contributor can clone the repository and understand the project's purpose, structure, and standards without external context.
- Architecture decisions are documented before implementation begins, reducing rework in later phases.

---

## Phase 2 — Backend

**Objectives**
- Build the core backend services responsible for data ingestion, persistence, and API access.
- Define the API contract that the frontend and AI engine will integrate against.

**Deliverables**
- FastAPI service scaffold with health checks, configuration management, and structured logging.
- Data models and database schema for incidents, imagery, detections, and briefings (PostgreSQL/PostGIS).
- Versioned REST API surface documented in `docs/api/endpoints.md`.

**Expected Outcomes**
- A running backend that can accept imagery metadata, persist geospatial records, and expose them via a documented API.
- API contracts stable enough for frontend and AI integration to begin in parallel.

---

## Phase 3 — Frontend

**Objectives**
- Build the responder-facing web application for visualizing disaster data.
- Establish the frontend's component, state management, and mapping conventions.

**Deliverables**
- React/TypeScript application scaffold with routing, layout, and design system foundations.
- Interactive map dashboard consuming the backend API.
- Incident and briefing viewer interfaces.

**Expected Outcomes**
- Responders can visually explore affected regions and detected damage through a functional web interface connected to live backend data.

---

## Phase 4 — AI Integration

**Objectives**
- Integrate computer vision models for damage detection and infrastructure classification.
- Integrate a generative AI component for operational briefing synthesis.

**Deliverables**
- Damage detection inference pipeline consuming ingested imagery.
- Infrastructure impact classification pipeline.
- LLM-based briefing generation service consuming structured detection output.

**Expected Outcomes**
- Uploaded imagery is automatically processed into structured damage assessments without manual analyst review.
- Generated briefings accurately reflect the underlying detected findings.

---

## Phase 5 — Maps & Routing

**Objectives**
- Extend the geospatial layer to support hazard-aware routing.
- Provide responders with viable rescue and access routes around detected obstructions.

**Deliverables**
- Road network ingestion and hazard-overlay logic.
- Routing engine that excludes or re-weights impassable segments based on detected damage.
- Route visualization integrated into the frontend map dashboard.

**Expected Outcomes**
- Responders can request a route between two points and receive a path that accounts for real, detected disaster impact rather than assuming an intact road network.

---

## Phase 6 — Decision Support

**Objectives**
- Bring together damage assessment, routing, and briefing generation into a unified operational workflow for incident commanders.
- Introduce prioritization logic to help responders triage where to act first.

**Deliverables**
- Incident prioritization scoring based on damage severity, population impact, and accessibility.
- Unified mission console combining map, briefing, and routing views.
- Exportable situation reports for distribution to response teams.

**Expected Outcomes**
- An incident commander can move from raw imagery to a prioritized, actionable response plan within a single workflow.

---

## Phase 7 — Testing

**Objectives**
- Establish confidence in correctness, performance, and reliability across all services.
- Validate AI model outputs against ground-truth and held-out data.

**Deliverables**
- Automated unit and integration test suites for backend and frontend.
- Model evaluation benchmarks (precision/recall for detection, qualitative review for generated briefings).
- End-to-end test scenarios covering the imagery-to-briefing pipeline.

**Expected Outcomes**
- CI enforces a minimum quality bar on every change.
- Known model performance characteristics and limitations are documented rather than assumed.

---

## Phase 8 — Deployment

**Objectives**
- Package and deploy the platform for use in real or simulated response scenarios.
- Establish operational practices for monitoring and incident response of the platform itself.

**Deliverables**
- Production container images and deployment configuration.
- Observability: structured logging, metrics, and alerting for all services.
- Deployment documentation and runbooks.

**Expected Outcomes**
- The platform can be deployed to a target environment repeatably and is observable in production.

---

## Phase 9 — Research Extensions

**Objectives**
- Pursue the forward-looking research directions identified during earlier phases.
- Improve model robustness, platform scalability, and applicability to a wider range of disaster types.

**Deliverables**
- Prototypes for multi-modal (optical + SAR) damage assessment.
- Change-detection models leveraging pre-/post-disaster imagery pairs.
- Exploration of edge inference and federated learning approaches.

**Expected Outcomes**
- A documented set of validated research extensions, tracked in `docs/research/future-work.md`, that inform the platform's long-term technical direction.
