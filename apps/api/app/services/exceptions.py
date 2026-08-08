"""Domain-level errors raised by the service layer.

Deliberately plain Python exceptions with no FastAPI/HTTP import, so
services stay testable without the HTTP layer (see `app/core` and existing
services, none of which import from `fastapi`). Translated to HTTP
responses centrally by `app/api/exception_handlers.py`, so routes never
need their own try/except.
"""


class AnalysisError(Exception):
    """Base class for analysis-ingestion errors."""


class UnsupportedImageTypeError(AnalysisError):
    """Raised when a declared or Pillow-detected image type isn't supported."""

    def __init__(self, content_type: str) -> None:
        self.content_type = content_type
        super().__init__(
            f"Unsupported image type: {content_type!r}. Supported types: JPEG, PNG, WEBP."
        )


class ImageTooLargeError(AnalysisError):
    """Raised when an upload exceeds the configured maximum size."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"Image exceeds the maximum allowed size of {max_bytes} bytes.")


class InvalidImageContentError(AnalysisError):
    """Raised when the uploaded bytes cannot be decoded as an image at all."""

    def __init__(self) -> None:
        super().__init__("File content could not be decoded as a valid image.")
