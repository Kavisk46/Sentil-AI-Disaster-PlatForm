from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import (
    get_analysis_repository,
    get_building_localizer,
    get_damage_classifier,
    get_damage_model,
    get_file_storage,
    get_job_queue,
    get_spatial_repository,
)
from app.core.config import Settings, get_settings
from app.main import create_app
from app.ml.inference import DamageInferenceEngine
from app.ml.model import DamageModel
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.analysis_repository import InMemoryAnalysisRepository
from app.services.file_storage import LocalFileStorage
from app.services.job_queue import InMemoryJobQueue
from app.services.spatial_repository import InMemorySpatialRepository


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def analysis_app_factory(
    tmp_path: Path,
) -> Callable[..., FastAPI]:
    """Factory for a FastAPI app with upload storage and analysis records
    isolated to a pytest ``tmp_path`` — never touches the real runtime
    upload directory, a real PostgreSQL database, or a real Redis queue.

    Accepts an optional `Settings` override, so a single test can exercise
    e.g. a tiny `MAX_UPLOAD_SIZE_MB` without mutating real configuration,
    and an optional `model` override (a *test-only* `DamageModel` fake —
    see `test_analysis_lifecycle.py`) so lifecycle tests can exercise the
    `completed`/`failed` paths deterministically without a real trained
    model.

    Milestone F5: `POST /api/v1/analysis` now enqueues onto a `JobQueue`
    (`app/services/job_queue.py`) instead of using FastAPI
    `BackgroundTasks`, and the API's own `AnalysisProcessingService` (used
    for reads only — see `app/api/deps.py::get_analysis_processing_service`)
    never touches the model at all. To keep this fixture's long-standing
    behavior — a `TestClient` POST fully completes processing before a
    later GET is checked, deterministically, no real Redis or worker
    process required — `get_job_queue` is overridden with an
    `InMemoryJobQueue` whose processor is a *separate*
    `AnalysisProcessingService`, built here exactly the way the real F5
    worker builds its own (see `app/worker/tasks.py`): same repositories,
    a real inference engine wired from `model` (or the production
    localizer/classifier wiring, respecting `MODEL_ENABLED`, when `model`
    is not given).
    """

    def _make(settings: Settings | None = None, *, model: DamageModel | None = None) -> FastAPI:
        app = create_app()
        # Milestone F4: the real default (`Settings.MODEL_ENABLED=True`)
        # downloads/loads a real pretrained CLIP checkpoint — network
        # access and ~1-2 minutes on a cold cache. Every test in this
        # suite that doesn't care about real inference (upload validation,
        # unrelated endpoints, ...) uses this factory with no explicit
        # `settings`, and must stay fast and network-free — exactly this
        # module's own historical guarantee (see `test_analysis_lifecycle.py`'s
        # "No GPU, no downloaded model, no internet access anywhere in
        # this file"). So the *default* here explicitly disables real
        # inference; a test that wants to exercise it passes its own
        # `Settings(MODEL_ENABLED=True, ...)`.
        resolved_settings = settings or Settings(MODEL_ENABLED=False)
        app.dependency_overrides[get_settings] = lambda: resolved_settings
        app.dependency_overrides[get_file_storage] = lambda: LocalFileStorage(base_dir=tmp_path)
        # Must be a single instance shared across the whole app, not a
        # fresh one per call: FastAPI re-invokes dependency overrides on
        # every request, so a `lambda: InMemoryAnalysisRepository()` here
        # would silently discard everything written by a prior POST before
        # a later GET on the same client ever saw it.
        repository = InMemoryAnalysisRepository()
        app.dependency_overrides[get_analysis_repository] = lambda: repository
        # Same reasoning as `get_analysis_repository` above, plus: without
        # this override every test app would share `app.api.deps`'s
        # module-level `_spatial_repository` singleton, leaking spatial
        # data across tests within the same pytest process.
        spatial_repository = InMemorySpatialRepository()
        app.dependency_overrides[get_spatial_repository] = lambda: spatial_repository

        file_storage = LocalFileStorage(base_dir=tmp_path)

        # Lazy: only actually constructed (and, for a real `open_clip`
        # config, only actually loaded) the first time a test's upload
        # genuinely reaches the enqueue step. A validation-only test
        # (413/415/400/422 — rejected by `AnalysisService.create_analysis`
        # before any enqueue happens) must never pay this cost — even a
        # `Settings(MAX_UPLOAD_SIZE_MB=...)` override that leaves
        # `MODEL_ENABLED` at its (now `True`) class default must not
        # silently attempt a real network model load just because the
        # fixture was constructed.
        _worker_processing_service: AnalysisProcessingService | None = None

        def _get_worker_processing_service() -> AnalysisProcessingService:
            nonlocal _worker_processing_service
            if _worker_processing_service is None:
                if model is not None:
                    inference_model: DamageModel = model
                else:
                    localizer = get_building_localizer(resolved_settings)
                    classifier = get_damage_classifier(resolved_settings)
                    inference_model = get_damage_model(localizer, classifier)
                inference_engine = DamageInferenceEngine(
                    model=inference_model,
                    max_image_dimension=resolved_settings.MODEL_MAX_IMAGE_DIM,
                )
                _worker_processing_service = AnalysisProcessingService(
                    repository=repository,
                    file_storage=file_storage,
                    inference_engine=inference_engine,
                    spatial_repository=spatial_repository,
                )
            return _worker_processing_service

        # A single shared instance (not a fresh one per dependency
        # resolution) — same reasoning as `repository`/`spatial_repository`
        # above, plus it lets a test inspect `job_queue.enqueued` after a
        # POST to directly verify the F5 enqueue path ran, not just its
        # downstream effect.
        job_queue = InMemoryJobQueue(
            processor=lambda analysis_id: _get_worker_processing_service().process(analysis_id)
        )
        app.dependency_overrides[get_job_queue] = lambda: job_queue
        # Exposed for tests that want to assert on the F5 enqueue path
        # directly (e.g. `app.state.test_job_queue.enqueued`) rather than
        # only its downstream effect.
        app.state.test_job_queue = job_queue
        return app

    return _make


@pytest.fixture
def analysis_client(analysis_app_factory: Callable[..., FastAPI]) -> TestClient:
    return TestClient(analysis_app_factory(None))
