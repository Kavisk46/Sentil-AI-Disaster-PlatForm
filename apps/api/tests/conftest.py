from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_analysis_repository, get_file_storage
from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.analysis_repository import InMemoryAnalysisRepository
from app.services.file_storage import LocalFileStorage


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def analysis_app_factory(tmp_path: Path) -> Callable[[Settings | None], FastAPI]:
    """Factory for a FastAPI app with upload storage and analysis records
    isolated to a pytest ``tmp_path`` — never touches the real runtime
    upload directory or the shared in-memory repository `client` uses.

    Accepts an optional `Settings` override, so a single test can exercise
    e.g. a tiny `MAX_UPLOAD_SIZE_MB` without mutating real configuration.
    """

    def _make(settings: Settings | None = None) -> FastAPI:
        app = create_app()
        if settings is not None:
            app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_file_storage] = lambda: LocalFileStorage(base_dir=tmp_path)
        app.dependency_overrides[get_analysis_repository] = lambda: InMemoryAnalysisRepository()
        return app

    return _make


@pytest.fixture
def analysis_client(analysis_app_factory: Callable[[Settings | None], FastAPI]) -> TestClient:
    return TestClient(analysis_app_factory(None))
