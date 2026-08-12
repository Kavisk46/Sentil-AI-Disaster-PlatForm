from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import (
    get_analysis_repository,
    get_damage_model,
    get_file_storage,
    get_spatial_repository,
)
from app.core.config import Settings, get_settings
from app.main import create_app
from app.ml.model import DamageModel
from app.services.analysis_repository import InMemoryAnalysisRepository
from app.services.file_storage import LocalFileStorage
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
    upload directory or the shared in-memory repository `client` uses.

    Accepts an optional `Settings` override, so a single test can exercise
    e.g. a tiny `MAX_UPLOAD_SIZE_MB` without mutating real configuration,
    and an optional `model` override (a *test-only* `DamageModel` fake —
    see `test_analysis_lifecycle.py`) so lifecycle tests can exercise the
    `completed`/`failed` paths deterministically without a real trained
    model. Production wiring (`app/api/deps.py`) never uses a fake model;
    this override only ever exists inside a test process.
    """

    def _make(settings: Settings | None = None, *, model: DamageModel | None = None) -> FastAPI:
        app = create_app()
        if settings is not None:
            app.dependency_overrides[get_settings] = lambda: settings
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
        if model is not None:
            app.dependency_overrides[get_damage_model] = lambda: model
        return app

    return _make


@pytest.fixture
def analysis_client(analysis_app_factory: Callable[..., FastAPI]) -> TestClient:
    return TestClient(analysis_app_factory(None))
