"""Aggregates all v1 endpoint routers into a single router.

Adding a new resource under `/api/v1` should only ever require adding an
endpoints module and including it here — the app factory stays untouched.

Owns the `/api/v1` prefix directly (rather than having it applied by
whichever router includes this one) so the bare `GET /api/v1` route
registered by `status.register()` resolves at construction time, without
depending on inclusion order elsewhere.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import analysis, intelligence, model, roads, routing, status, system
from app.core.constants import API_V1_PREFIX

api_v1_router = APIRouter(prefix=API_V1_PREFIX, tags=["v1"])
status.register(api_v1_router)
api_v1_router.include_router(system.router)
api_v1_router.include_router(analysis.router)
api_v1_router.include_router(model.router)
api_v1_router.include_router(roads.router)
api_v1_router.include_router(routing.router)
api_v1_router.include_router(intelligence.router)
