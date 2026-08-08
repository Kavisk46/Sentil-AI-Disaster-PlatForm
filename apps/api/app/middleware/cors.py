"""CORS configuration.

Kept as its own function (rather than inlined in the app factory) so the
policy — which origins, methods, and headers are allowed — is defined and
reviewed in exactly one place.
"""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import Settings


def add_cors_middleware(app: FastAPI, settings: Settings) -> None:
    origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
    app.add_middleware(
        CORSMiddleware,
        # Credentialed requests cannot be paired with a wildcard origin per the
        # CORS spec, so an empty allow-list means "no cross-origin access"
        # rather than silently falling back to "*".
        allow_origins=origins,
        allow_credentials=bool(origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
