"""Wall-clock latency measurement over real pipeline stages.

**Every number here is an actual measured duration** — `LatencyRecorder`
wraps real code execution with `time.perf_counter()`; it never inserts a
synthetic or assumed value. A stage that doesn't run (e.g. hazard
assessment — SentinelAI has no hazard subsystem, see
`research.experiments.hazards`) simply never appears in the recorded
timings, rather than being given a fabricated duration.

These measurements reflect whatever fixture and machine ran them — they
are not a claim about production latency on real imagery or production
hardware; see research/README.md, "Limitations."
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class StageTiming:
    stage: str
    duration_ms: float


@dataclass(slots=True)
class LatencyRecorder:
    """Records one `StageTiming` per `measure()` call, in call order.
    Intended for one sequential pipeline run at a time — not thread-safe,
    matching this codebase's own synchronous, single-request pipeline
    (`app.services.analysis_processing_service` and friends)."""

    timings: list[StageTiming] = field(default_factory=list)

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.timings.append(StageTiming(stage=stage, duration_ms=elapsed_ms))

    @property
    def total_ms(self) -> float:
        return sum(timing.duration_ms for timing in self.timings)

    def as_dict(self) -> dict[str, float]:
        return {timing.stage: timing.duration_ms for timing in self.timings}
