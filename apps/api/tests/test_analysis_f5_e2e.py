"""End-to-end and idempotency tests for the F5 upload -> persist -> queue
-> worker -> completed pipeline.

Exercises the real `POST /api/v1/analysis` -> `JobQueue.enqueue_analysis`
-> `AnalysisProcessingService.process()` -> `GET /api/v1/analysis/{id}`
path through `analysis_app_factory` (see `tests/conftest.py`) — the
worker side is a real `AnalysisProcessingService`, wired exactly the way
`app/worker/tasks.py` wires its own, just invoked synchronously by
`InMemoryJobQueue` instead of a real Redis-backed worker process. No
real Redis/PostgreSQL/CLIP model anywhere in this file.
"""

import io
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.ml.model import RawDetection
from app.ml.schemas import DamageClass, ModelStatus


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(50, 60, 70)).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeCompletingModel:
    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        return [RawDetection(damage_class=DamageClass.MAJOR, confidence=0.8)]

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=True, model_name="fake-test-model", model_version="test", device="cpu"
        )


def _post_analysis(client: TestClient) -> str:
    response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", _image_bytes(), "image/png")}
    )
    assert response.status_code == 201
    analysis_id: str = response.json()["analysis_id"]
    return analysis_id


def test_upload_persists_stores_enqueues_and_processes_end_to_end(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    app = analysis_app_factory(model=_FakeCompletingModel())
    client = TestClient(app)

    analysis_id = _post_analysis(client)

    # 1. The F5 enqueue path actually ran (not just its downstream effect).
    assert str(app.state.test_job_queue.enqueued[0]) == analysis_id

    # 2. The worker (here, InMemoryJobQueue's synchronous processor) ran
    #    the real AnalysisProcessingService and the result is retrievable.
    body = client.get(f"/api/v1/analysis/{analysis_id}").json()
    assert body["status"] == "completed"
    assert body["buildings"][0]["damage_class"] == "major"
    assert body["buildings"][0]["confidence"] == 0.8

    # 3. The result is durably persisted, not held only in the HTTP
    #    response — a second GET returns the exact same result.
    second = client.get(f"/api/v1/analysis/{analysis_id}").json()
    assert second == body


def test_post_returns_quickly_with_the_queued_status_before_the_result_exists(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    """The `201` response itself must reflect the hand-off state
    (`queued`), never a result the worker hasn't produced yet — even
    though `InMemoryJobQueue` happens to process synchronously in tests,
    the response body is built *before* enqueuing (see
    `app/api/v1/endpoints/analysis.py::create_analysis`)."""
    app = analysis_app_factory(model=_FakeCompletingModel())
    client = TestClient(app)

    response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", _image_bytes(), "image/png")}
    )

    assert response.status_code == 201
    assert response.json()["status"] == "queued"


def test_processing_the_same_analysis_twice_does_not_duplicate_buildings(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    """Idempotency: a duplicate job delivery (or a manual re-run) for an
    analysis already `completed` must be a safe no-op — see
    `AnalysisProcessingService.process()`'s terminal-state guard and
    `docs/architecture/production.md`, "Idempotency / retries"."""
    app = analysis_app_factory(model=_FakeCompletingModel())
    client = TestClient(app)
    analysis_id = _post_analysis(client)

    first = client.get(f"/api/v1/analysis/{analysis_id}").json()
    assert len(first["buildings"]) == 1

    # Re-enqueue the exact same analysis_id — simulates a duplicate
    # message delivery from the queue.
    app.state.test_job_queue.enqueue_analysis(__import__("uuid").UUID(analysis_id))

    second = client.get(f"/api/v1/analysis/{analysis_id}").json()
    assert len(second["buildings"]) == 1
    assert second["buildings"] == first["buildings"]


def test_job_queue_processor_is_a_real_analysis_processing_service(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    """`InMemoryJobQueue`'s processor here must be a real, independently
    wired `AnalysisProcessingService` — not the API's own read-only copy
    (which uses `UnavailableDamageModel` and would never actually
    process anything) — see `tests/conftest.py`'s own docstring for why
    this mirrors what `app/worker/tasks.py` does in production."""
    app = analysis_app_factory(model=_FakeCompletingModel())
    client = TestClient(app)

    analysis_id = _post_analysis(client)
    body = client.get(f"/api/v1/analysis/{analysis_id}").json()

    # A real model actually ran — proven by a genuine, non-fabricated
    # prediction from _FakeCompletingModel reaching the response, not by
    # the ever-unavailable API-side placeholder model.
    assert body["status"] == "completed"
    assert body["model_metadata"]["model_name"] == "fake-test-model"
