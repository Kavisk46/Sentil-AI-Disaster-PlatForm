"""Shared FastAPI dependencies for the API layer.

Centralizing dependency providers here (rather than defining them inline
per-router) means a route only needs to declare the `*Dep` type alias it
wants, and swapping an implementation (e.g. for tests, via
`app.dependency_overrides`) never requires touching route code.
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.analysis_repository import AnalysisRepository, InMemoryAnalysisRepository
from app.services.analysis_service import AnalysisService
from app.services.file_storage import FileStorage, LocalFileStorage
from app.services.system_service import SystemService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_system_service(settings: SettingsDep) -> SystemService:
    """Sample DI scaffold: construct a service from injected Settings.

    Future services follow the same shape — a `get_*_service` provider
    function, depended on by routes via an `Annotated[..., Depends(...)]`
    alias below.
    """
    return SystemService(settings)


SystemServiceDep = Annotated[SystemService, Depends(get_system_service)]


# Module-level singleton: an in-memory repository must be the *same*
# instance across requests to remember anything between calls at all — a
# fresh instance per request would make every analysis vanish immediately
# after being created. Replaced by a database-backed repository (and a
# request-scoped session dependency) once persistence is introduced.
_analysis_repository = InMemoryAnalysisRepository()


def get_analysis_repository() -> AnalysisRepository:
    return _analysis_repository


def get_file_storage(settings: SettingsDep) -> FileStorage:
    return LocalFileStorage(base_dir=settings.UPLOAD_DIR)


def get_analysis_service(
    settings: SettingsDep,
    repository: Annotated[AnalysisRepository, Depends(get_analysis_repository)],
    file_storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> AnalysisService:
    return AnalysisService(settings=settings, repository=repository, file_storage=file_storage)


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]
