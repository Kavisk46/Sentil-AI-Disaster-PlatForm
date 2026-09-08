"""Milestone F4 — the mandatory real, end-to-end integration test:

    real image -> real preprocessing -> real CLIP model invocation
    -> structured BuildingDamage -> F3 analysis-aware intelligence

This is NOT a mock. `Settings(MODEL_ENABLED=True, MODEL_PROVIDER="open_clip")`
selects the exact same wiring `app/api/deps.py` uses by default in
production — a real pretrained CLIP checkpoint (downloaded once, cached
by `open_clip`/Hugging Face Hub afterward) actually runs a forward pass
over a real, freshly-generated test image. `MODEL_TILE_GRID=1` keeps this
to a single real inference call (not four) — enough to prove the path
works without unnecessarily multiplying CPU time.

Needs network access on an uncached machine (first run only — see
"Manual real-inference verification" in apps/api/README.md for measured
timing). If the checkpoint genuinely cannot be downloaded/loaded here
(e.g. a fully offline CI runner), the analysis honestly ends
`MODEL_LOAD_FAILURE` rather than crashing — this test recognizes that
case and skips with a clear reason, per this milestone's own allowance
for environments where the production model "cannot reliably
download/load during CI." It does not silently mock the pipeline instead.

Milestone F5 also relies on this file for its own mandatory requirement
(a real end-to-end path proving upload -> persistence -> queue -> worker
-> real F4 model -> BuildingDamage -> persisted result -> F3-compatible
intelligence): `analysis_app_factory` (see `tests/conftest.py`) enqueues
through `JobQueue`/`InMemoryJobQueue` and processes with a worker-shaped
`AnalysisProcessingService` — the same F5 architecture
`app/worker/tasks.py` uses in production, just invoked synchronously
instead of via a real Redis-backed worker process. This test does not
need its own separate F5 copy; it already exercises that path with a
real model, and asserts on the enqueue step explicitly below.
"""

import io
import time
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api.deps import get_spatial_repository
from app.core.config import Settings
from app.intelligence.analysis_adapter import IntelligenceContextUnavailableReason
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.schemas import BuildingDamage, DamageClass


def _real_settings() -> Settings:
    return Settings(
        MODEL_ENABLED=True,
        MODEL_PROVIDER="open_clip",
        MODEL_TILE_GRID=1,
        MODEL_DEVICE="cpu",
    )


def _post_real_image(client: TestClient) -> str:
    buffer = io.BytesIO()
    # A genuinely varied (not flat-color) test image — real pixel content
    # for the model to actually process, not a degenerate all-one-color
    # input. Not a real disaster photo — this test proves the *pipeline*
    # runs for real, not that the prediction is operationally meaningful
    # (see the module docstring and apps/api/README.md's confidence
    # disclosure for why that distinction matters).
    image = Image.new("RGB", (256, 256))
    pixels = image.load()
    assert pixels is not None
    for x in range(256):
        for y in range(256):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
    image.save(buffer, format="PNG")

    response = client.post(
        "/api/v1/analysis", files={"image": ("real_test_scene.png", buffer.getvalue(), "image/png")}
    )
    assert response.status_code == 201
    return response.json()["analysis_id"]  # type: ignore[no-any-return]


def test_real_clip_inference_reaches_f3_intelligence(
    analysis_app_factory,  # type: ignore[no-untyped-def]
) -> None:
    app: FastAPI = analysis_app_factory(_real_settings())
    client = TestClient(app)

    start = time.perf_counter()
    analysis_id = _post_real_image(client)

    # F5: the upload went through the real enqueue path (`JobQueue`), not
    # a direct synchronous call — see the module docstring above.
    assert str(app.state.test_job_queue.enqueued[0]) == analysis_id

    body = client.get(f"/api/v1/analysis/{analysis_id}").json()
    total_time = time.perf_counter() - start

    if body["status"] == "failed" and body["failure"]["code"] == "MODEL_LOAD_FAILURE":
        pytest.skip(
            "Real CLIP checkpoint could not be downloaded/loaded in this "
            f"environment (likely no network): {body['failure']['message']}"
        )

    print(f"\n[F4 real-inference integration] total request+inference time: {total_time:.2f}s")

    # --- Real model inference actually happened -----------------------
    assert body["status"] == "completed", body
    assert body["model_metadata"]["model_loaded"] is True
    # TwoStageDamageModel.health() composes both stages' names — see
    # app/ml/pipeline.py. "deterministic-tile-localizer" confirms Stage 1
    # (real, deterministic tiling); "ViT-B-32" confirms Stage 2 (the real
    # pretrained CLIP checkpoint actually loaded).
    assert body["model_metadata"]["model_name"] == "deterministic-tile-localizer+ViT-B-32"
    assert body["model_metadata"]["model_version"] == "openai"
    assert body["model_metadata"]["device"] == "cpu"

    assert len(body["buildings"]) == 1  # MODEL_TILE_GRID=1 -> exactly one region
    building = body["buildings"][0]
    # A genuine model prediction — one of the four real classes, and a
    # real (non-fabricated) confidence in [0, 1]. Never asserted to equal
    # a specific class: which one CLIP picks for this synthetic image is
    # real model output, not something this test dictates.
    assert building["damage_class"] in {c.value for c in DamageClass}
    assert 0.0 <= building["confidence"] <= 1.0
    # Real inference never georeferences (no georeferencing metadata
    # source exists for an ordinary upload) — CRS safety: image
    # coordinates are never claimed to be geographic.
    assert building["coordinate_reference_system"] == "IMAGE"
    assert building["georeferenced"] is False

    # --- CRS safety: geographic intelligence stays honestly unavailable ---
    intelligence_body = client.get(f"/api/v1/analysis/{analysis_id}/intelligence").json()
    assert intelligence_body["context_available"] is False
    assert (
        intelligence_body["context_unavailable_reason"]
        == IntelligenceContextUnavailableReason.NO_GEOREFERENCE.value
    )

    # --- Re-seed as georeferenced (the same trick test_road_risk.py and
    # test_analysis_intelligence_api.py already use, since the real
    # pipeline never georeferences on its own) to prove the real
    # prediction's *content* (damage_class/confidence) genuinely flows
    # into F3 once geographic evidence exists — not a fabricated location. ---
    spatial_repository = app.dependency_overrides[get_spatial_repository]()
    georeferenced_building = BuildingDamage(**building).model_copy(
        update={
            "geometry": {"type": "point", "coordinates": (12.34, 56.78)},
            "coordinate_reference_system": CoordinateReferenceSystem.WGS84,
            "georeferenced": True,
        }
    )
    spatial_repository.save_buildings(UUID(analysis_id), [georeferenced_building])

    intelligence_body_after = client.get(f"/api/v1/analysis/{analysis_id}/intelligence").json()
    assert intelligence_body_after["context_available"] is True
    assert intelligence_body_after["affected_area_count"] == 1

    search_zones_body = client.get(
        f"/api/v1/analysis/{analysis_id}/intelligence/search-zones"
    ).json()
    assert search_zones_body["context_available"] is True
    [zone] = search_zones_body["search_zones"]
    # The real model's damage_class genuinely drove this zone's scoring —
    # not a fabricated priority.
    assert zone["priority_level"] in {"low", "moderate", "high", "critical"}
    assert zone["is_simulated"] is False
