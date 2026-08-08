"""Shared FastAPI dependencies for the API layer.

Centralizing dependency providers here (rather than defining them inline
per-router) means a route only needs to declare the `*Dep` type alias it
wants, and swapping an implementation (e.g. for tests, via
`app.dependency_overrides`) never requires touching route code.
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
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
