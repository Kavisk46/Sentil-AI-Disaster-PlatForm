# Literature Review

This document tracks the research basis for SentinelAI's technical approach
to aerial-imagery-based disaster damage assessment. It is a living document,
maintained as part of **Phase 0 — Research** in
[`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md), and revisited as the AI
engine is implemented in Phase 4.

## Scope

The review focuses on four areas directly relevant to the platform:

1. **Building damage assessment from aerial/satellite imagery** — supervised
   classification of structural damage severity from post-disaster imagery,
   including approaches built on the xBD dataset and similar benchmarks for
   damage severity classification.
2. **Infrastructure and road network damage detection** — segmentation and
   detection approaches for identifying blocked, damaged, or destroyed roads
   and critical infrastructure in disaster-affected imagery.
3. **Change detection** — techniques that compare pre- and post-disaster
   imagery pairs to isolate damage, rather than classifying post-disaster
   imagery in isolation.
4. **Disaster-aware routing** — pathfinding approaches that incorporate
   dynamic, real-world hazard constraints rather than assuming a static,
   intact road network.

## Working Conclusions

- **Damage severity classification** is well studied as a supervised computer
  vision problem, and benefits significantly from models pretrained on
  general aerial/satellite imagery before fine-tuning on disaster-specific
  labels, given the relative scarcity of labeled post-disaster imagery.
- **Change detection** (pre/post image pairs) consistently outperforms
  single-image classification when pre-disaster imagery is available,
  motivating its inclusion as a research extension rather than a Phase 4
  requirement, since pre-disaster imagery is not always accessible in time.
- **Road network damage detection** is comparatively less mature than
  building damage assessment in the published literature, and is expected to
  require the most iteration during Phase 4–5 implementation.
- **Hazard-aware routing** is most effectively modeled as a weighted or
  constrained shortest-path problem over a standard road graph, with hazard
  data as a dynamic overlay rather than a change to the routing algorithm
  itself — keeping the platform able to use well-established, mature
  pathfinding techniques.

## Open Questions Carried Into Later Phases

- What confidence threshold should gate a detected hazard being used to
  exclude a road segment from routing, given the cost of both false
  positives (unnecessarily blocking a viable route) and false negatives
  (routing responders into a hazard)?
- How should the platform handle regions with no available pre-disaster
  imagery, where change detection is not possible?

These questions directly motivate the research extensions tracked in
[`future-work.md`](future-work.md).
