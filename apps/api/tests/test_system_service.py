"""Unit tests for SystemService, exercised directly — no HTTP layer involved.

This is the payoff of keeping logic out of routes: the service is testable
as plain Python.
"""

from app.core.config import Settings
from app.services.system_service import SystemService


def _service() -> SystemService:
    settings = Settings(APP_NAME="Test API", APP_VERSION="9.9.9", ENVIRONMENT="test")
    return SystemService(settings)


def test_get_project_info() -> None:
    info = _service().get_project_info()

    assert info.name == "Test API"
    assert info.version == "9.9.9"
    assert info.docs_url == "/docs"


def test_get_service_info() -> None:
    info = _service().get_service_info()

    assert info.name == "Test API"
    assert info.environment == "test"


def test_get_api_version_status() -> None:
    status = _service().get_api_version_status()

    assert status.version == "9.9.9"
    assert status.status == "available"
