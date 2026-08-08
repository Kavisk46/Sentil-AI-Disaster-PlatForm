"""Top-level API router aggregating every unversioned and versioned router.

`main.py` mounts this single router rather than importing `root`, `health`,
and each API version individually — adding a new version (`v2`) or an
unversioned endpoint only ever means a change here, not in the app factory.
"""

from fastapi import APIRouter

from app.api import health, root
from app.api.v1.router import api_v1_router

api_router = APIRouter()
api_router.include_router(root.router)
api_router.include_router(health.router)
# api_v1_router already carries its own "/api/v1" prefix (see
# app/api/v1/router.py) — no prefix is passed here.
api_router.include_router(api_v1_router)
