"""System metadata service.

Assembles the read-only, non-sensitive metadata returned by the `/`,
`/api/v1`, and `/api/v1/system/info` endpoints. Deliberately trivial for
the backend foundation milestone — this is the seam later services (e.g. an
IncidentService) will follow: constructed from `Settings` (or other
injected collaborators) and exposed through a `get_*_service` dependency
rather than instantiated directly inside a route.
"""

from app.core.config import Settings
from app.schemas.system import ApiVersionStatus, ProjectInfo, ServiceInfo


class SystemService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_project_info(self) -> ProjectInfo:
        return ProjectInfo(
            name=self._settings.APP_NAME,
            description=self._settings.APP_DESCRIPTION,
            version=self._settings.APP_VERSION,
            docs_url="/docs",
        )

    def get_service_info(self) -> ServiceInfo:
        return ServiceInfo(
            name=self._settings.APP_NAME,
            version=self._settings.APP_VERSION,
            environment=self._settings.ENVIRONMENT,
        )

    def get_api_version_status(self) -> ApiVersionStatus:
        return ApiVersionStatus(version=self._settings.APP_VERSION, status="available")
