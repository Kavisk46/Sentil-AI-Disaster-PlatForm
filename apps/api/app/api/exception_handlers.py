"""Maps service-layer domain exceptions to HTTP responses.

Centralizing this here keeps route handlers thin: a route calls a service
and lets a domain error propagate, rather than wrapping every call in its
own try/except. Registered once, in `app/main.py`.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    ImageTooLargeError,
    InvalidImageContentError,
    UnsupportedImageTypeError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnsupportedImageTypeError)
    async def _handle_unsupported_image_type(
        _: Request, exc: UnsupportedImageTypeError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ImageTooLargeError)
    async def _handle_image_too_large(_: Request, exc: ImageTooLargeError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidImageContentError)
    async def _handle_invalid_image_content(
        _: Request, exc: InvalidImageContentError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )
