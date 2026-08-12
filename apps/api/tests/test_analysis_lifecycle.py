"""Tests for the analysis lifecycle (Milestone 4): upload -> queued ->
processing -> completed/failed, and `GET /api/v1/analysis/{analysis_id}`.

Fake `DamageModel`/`FileStorage` implementations here are test-only
doubles — see `app/ml/model.py` for the real (honest, currently
unavailable) implementations production code actually uses. No GPU, no
downloaded model, no internet access anywhere in this file.
"""

import io
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from PIL import Image
from starlette.datastructures import Headers

from app.api.deps import get_analysis_repository
from app.core.config import Settings
from app.ml.inference import DamageInferenceEngine
from app.ml.model import ModelNotAvailableError, RawDetection
from app.ml.schemas import DamageClass, DamageSummary, ModelStatus
from app.schemas.analysis import AnalysisStatus
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.analysis_repository import (
    AnalysisNotFoundError,
    AnalysisRecord,
    InMemoryAnalysisRepository,
)
from app.services.analysis_service import AnalysisService
from app.services.file_storage import FileStorage


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(50, 60, 70)).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeCompletingModel:
    """Deterministically returns one prediction — proves the `completed`
    path end-to-end without a real trained model."""

    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        return [RawDetection(damage_class=DamageClass.MAJOR, confidence=0.83)]

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=True, model_name="fake-test-model", model_version="test", device="cpu"
        )


class _FakeFailingModel:
    """Raises an unexpected (non-`ModelNotAvailableError`) exception — the
    generic `INFERENCE_FAILURE` path, distinct from `MODEL_UNAVAILABLE`."""

    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        raise RuntimeError("simulated inference crash")

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=True, model_name="fake-test-model", model_version="test", device="cpu"
        )


class _AlwaysUnavailableModel:
    """Same behavior as production's `UnavailableDamageModel`, reused here
    directly to confirm `AnalysisProcessingService` relies on the
    *existing* `ModelNotAvailableError` contract rather than inventing a
    parallel one."""

    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        raise ModelNotAvailableError("no model")

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=False, model_name="x", model_version="unconfigured", device="cpu"
        )


class _InMemoryFileStorage:
    """Minimal in-memory `FileStorage` double — no filesystem, no network."""

    def __init__(self, content: bytes = b"") -> None:
        self._content = content

    def save(self, *, storage_name: str, content: bytes) -> None:
        self._content = content

    def load(self, *, storage_name: str) -> bytes:
        return self._content


def _make_record(analysis_id: UUID, status: AnalysisStatus) -> AnalysisRecord:
    now = datetime.now(UTC)
    return AnalysisRecord(
        analysis_id=analysis_id,
        status=status,
        original_filename="a.png",
        storage_name=f"{analysis_id}.png",
        content_type="image/png",
        size_bytes=10,
        created_at=now,
        updated_at=now,
    )


def _post_analysis(client: TestClient) -> str:
    response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", _image_bytes(), "image/png")}
    )
    assert response.status_code == 201
    analysis_id: str = response.json()["analysis_id"]
    return analysis_id


# ---------------------------------------------------------------------------
# 1. Create analysis / 2. Retrieve analysis
# ---------------------------------------------------------------------------


def test_create_analysis_returns_an_id_that_can_be_retrieved(analysis_client: TestClient) -> None:
    analysis_id = _post_analysis(analysis_client)

    response = analysis_client.get(f"/api/v1/analysis/{analysis_id}")

    assert response.status_code == 200
    assert response.json()["analysis_id"] == analysis_id


# ---------------------------------------------------------------------------
# 3. Unknown / invalid analysis ID
# ---------------------------------------------------------------------------


def test_get_unknown_analysis_id_returns_404(analysis_client: TestClient) -> None:
    response = analysis_client.get(f"/api/v1/analysis/{uuid4()}")

    assert response.status_code == 404


def test_get_invalid_analysis_id_returns_422(analysis_client: TestClient) -> None:
    """Not a UUID at all — FastAPI's own path-parameter validation, not a
    404 (which implies "well-formed id, but no such record")."""
    response = analysis_client.get("/api/v1/analysis/not-a-uuid")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. Uploaded state
# ---------------------------------------------------------------------------


def test_uploaded_is_the_initial_status_before_enqueueing() -> None:
    """AnalysisService alone (no AnalysisProcessingService involved) still
    only ever produces `uploaded` — unchanged since Milestone 2."""
    repository = InMemoryAnalysisRepository()
    service = AnalysisService(
        settings=Settings(), repository=repository, file_storage=_InMemoryFileStorage()
    )
    upload = UploadFile(
        file=io.BytesIO(_image_bytes()),
        filename="a.png",
        headers=Headers(raw=[(b"content-type", b"image/png")]),
    )

    response = service.create_analysis(upload)

    record = repository.get(response.analysis_id)
    assert record is not None
    assert record.status == AnalysisStatus.UPLOADED


# ---------------------------------------------------------------------------
# 5. Processing state (observed at the moment inference actually runs)
# ---------------------------------------------------------------------------


def test_status_is_processing_at_the_moment_inference_runs() -> None:
    """Exercises AnalysisProcessingService.process() directly: the fake
    model's predict() checks the repository's own status, proving it's
    already PROCESSING by the time inference actually runs — without
    needing real concurrency or polling."""
    repository = InMemoryAnalysisRepository()
    analysis_id = uuid4()
    repository.create(_make_record(analysis_id, AnalysisStatus.UPLOADED))
    observed_status: list[AnalysisStatus] = []

    class _ObservingModel:
        def load(self) -> None:
            return None

        def predict(self, image: object) -> list[RawDetection]:
            record = repository.get(analysis_id)
            assert record is not None
            observed_status.append(record.status)
            return [RawDetection(damage_class=DamageClass.NO_DAMAGE, confidence=0.99)]

        def health(self) -> ModelStatus:
            return ModelStatus(
                model_loaded=True, model_name="observer", model_version="test", device="cpu"
            )

    service = AnalysisProcessingService(
        repository=repository,
        file_storage=_InMemoryFileStorage(_image_bytes()),
        inference_engine=DamageInferenceEngine(model=_ObservingModel()),
    )

    service.process(analysis_id)

    assert observed_status == [AnalysisStatus.PROCESSING]


# ---------------------------------------------------------------------------
# 6. Completed state
# ---------------------------------------------------------------------------


def test_completed_analysis_has_a_real_result(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    app = analysis_app_factory(model=_FakeCompletingModel())
    client = TestClient(app)

    analysis_id = _post_analysis(client)
    body = client.get(f"/api/v1/analysis/{analysis_id}").json()

    assert body["status"] == "completed"
    assert body["summary"] is not None
    assert body["summary"]["total_buildings"] == 1
    assert body["buildings"][0]["damage_class"] == "major"
    assert body["buildings"][0]["confidence"] == 0.83
    assert body["model_metadata"]["model_name"] == "fake-test-model"
    assert body["failure"] is None


# ---------------------------------------------------------------------------
# 7. Failed state (general) / 8. Model unavailable
# ---------------------------------------------------------------------------


def test_default_wiring_fails_with_model_unavailable(analysis_client: TestClient) -> None:
    """No model override — exercises the *real*, production DI wiring
    (UnavailableBuildingLocalizer), not a fake."""
    analysis_id = _post_analysis(analysis_client)

    body = analysis_client.get(f"/api/v1/analysis/{analysis_id}").json()

    assert body["status"] == "failed"
    assert body["failure"]["code"] == "MODEL_UNAVAILABLE"
    assert body["summary"] is None
    assert body["buildings"] == []


# ---------------------------------------------------------------------------
# 9. Inference failure
# ---------------------------------------------------------------------------


def test_unexpected_inference_error_fails_with_inference_failure_code(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    app = analysis_app_factory(model=_FakeFailingModel())
    client = TestClient(app)

    analysis_id = _post_analysis(client)
    body = client.get(f"/api/v1/analysis/{analysis_id}").json()

    assert body["status"] == "failed"
    assert body["failure"]["code"] == "INFERENCE_FAILURE"
    # The raw exception text must never reach the client — only the
    # generic, safe message.
    assert "simulated inference crash" not in body["failure"]["message"]


# ---------------------------------------------------------------------------
# 10. Result persistence
# ---------------------------------------------------------------------------


def test_completed_result_is_persisted_across_multiple_gets(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    app = analysis_app_factory(model=_FakeCompletingModel())
    client = TestClient(app)
    analysis_id = _post_analysis(client)

    first = client.get(f"/api/v1/analysis/{analysis_id}").json()
    second = client.get(f"/api/v1/analysis/{analysis_id}").json()

    assert first == second


# ---------------------------------------------------------------------------
# 11. Status transitions
# ---------------------------------------------------------------------------


def test_status_transitions_advance_updated_at() -> None:
    repository = InMemoryAnalysisRepository()
    analysis_id = uuid4()
    now = datetime.now(UTC)
    repository.create(_make_record(analysis_id, AnalysisStatus.UPLOADED))

    queued = repository.update_status(analysis_id, AnalysisStatus.QUEUED)
    assert queued.status == AnalysisStatus.QUEUED
    assert queued.updated_at >= now

    processing = repository.update_status(analysis_id, AnalysisStatus.PROCESSING)
    assert processing.status == AnalysisStatus.PROCESSING
    assert processing.updated_at >= queued.updated_at


def test_update_status_on_unknown_analysis_raises() -> None:
    repository = InMemoryAnalysisRepository()

    with pytest.raises(AnalysisNotFoundError):
        repository.update_status(uuid4(), AnalysisStatus.QUEUED)


def test_save_result_sets_completed_with_no_failure() -> None:
    repository = InMemoryAnalysisRepository()
    analysis_id = uuid4()
    repository.create(_make_record(analysis_id, AnalysisStatus.PROCESSING))

    completed = repository.save_result(
        analysis_id,
        summary=DamageSummary(
            total_buildings=0, damaged_buildings=0, severely_damaged=0, destroyed=0
        ),
        buildings=[],
        model_metadata=ModelStatus(
            model_loaded=True, model_name="x", model_version="1", device="cpu"
        ),
    )

    assert completed.status == AnalysisStatus.COMPLETED
    assert completed.failure is None


def test_save_failure_sets_failed_with_no_result() -> None:
    from app.schemas.analysis import AnalysisErrorCode, AnalysisFailure

    repository = InMemoryAnalysisRepository()
    analysis_id = uuid4()
    repository.create(_make_record(analysis_id, AnalysisStatus.PROCESSING))

    failed = repository.save_failure(
        analysis_id,
        AnalysisFailure(code=AnalysisErrorCode.MODEL_UNAVAILABLE, message="no model"),
    )

    assert failed.status == AnalysisStatus.FAILED
    assert failed.summary is None
    assert failed.failure is not None
    assert failed.failure.code == AnalysisErrorCode.MODEL_UNAVAILABLE


# ---------------------------------------------------------------------------
# Reuses the existing ModelNotAvailableError / DamageInferenceEngine
# contract rather than inventing a parallel one
# ---------------------------------------------------------------------------


def test_processing_service_handles_model_not_available_end_to_end() -> None:
    repository = InMemoryAnalysisRepository()
    analysis_id = uuid4()
    repository.create(_make_record(analysis_id, AnalysisStatus.UPLOADED))

    processing_service = AnalysisProcessingService(
        repository=repository,
        file_storage=_InMemoryFileStorage(_image_bytes()),
        inference_engine=DamageInferenceEngine(model=_AlwaysUnavailableModel()),
    )

    processing_service.process(analysis_id)

    result = processing_service.get_analysis(analysis_id)
    assert result.status == AnalysisStatus.FAILED
    assert result.failure is not None
    assert result.failure.code.value == "MODEL_UNAVAILABLE"


def test_process_is_a_noop_for_an_unknown_analysis_id() -> None:
    """process() never raises — there is no HTTP client to return an
    error to by the time a background task runs."""
    repository = InMemoryAnalysisRepository()
    processing_service = AnalysisProcessingService(
        repository=repository,
        file_storage=_InMemoryFileStorage(),
        inference_engine=DamageInferenceEngine(model=_FakeCompletingModel()),
    )

    processing_service.process(uuid4())  # must not raise


def test_process_is_a_noop_for_an_already_terminal_analysis() -> None:
    """Guards against e.g. a duplicate background-task dispatch reprocessing
    (and potentially overwriting) an already-terminal result.

    Deliberately checks a *call counter*, not an exception raised from
    inside predict() — process() catches broad exceptions from inference
    and would silently convert a misbehaving "raise if called" double into
    a FAILED status instead of failing this test loudly.
    """
    repository = InMemoryAnalysisRepository()
    analysis_id = uuid4()
    repository.create(_make_record(analysis_id, AnalysisStatus.COMPLETED))
    predict_call_count = 0

    class _CountingModel:
        def load(self) -> None:
            return None

        def predict(self, image: object) -> list[RawDetection]:
            nonlocal predict_call_count
            predict_call_count += 1
            return [RawDetection(damage_class=DamageClass.NO_DAMAGE, confidence=0.5)]

        def health(self) -> ModelStatus:
            return ModelStatus(
                model_loaded=True, model_name="x", model_version="1", device="cpu"
            )

    processing_service = AnalysisProcessingService(
        repository=repository,
        file_storage=_InMemoryFileStorage(),
        inference_engine=DamageInferenceEngine(model=_CountingModel()),
    )

    processing_service.process(analysis_id)  # must not re-run inference

    assert predict_call_count == 0
    record = repository.get(analysis_id)
    assert record is not None
    assert record.status == AnalysisStatus.COMPLETED


def test_get_analysis_raises_not_found_for_unknown_id() -> None:
    file_storage: FileStorage = _InMemoryFileStorage()
    service = AnalysisProcessingService(
        repository=InMemoryAnalysisRepository(),
        file_storage=file_storage,
        inference_engine=DamageInferenceEngine(model=_FakeCompletingModel()),
    )

    with pytest.raises(AnalysisNotFoundError):
        service.get_analysis(uuid4())


def test_get_analysis_repository_dependency_is_overridable(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    """Sanity check on the test fixture itself: confirms
    get_analysis_repository is a real, overridable dependency (used by
    other tests in this suite via analysis_app_factory)."""
    app = analysis_app_factory()
    assert get_analysis_repository in app.dependency_overrides
