"""Upload validation.

Client-supplied metadata (declared Content-Type, filename) is never trusted
on its own. `validate_content_type` is a cheap early rejection based on what
the client *claims*; `validate_image_content` is the authoritative check —
it decodes the actual bytes with Pillow and only accepts the result if the
real, sniffed format is in our supported set, closing the gap where a
client sends a mismatched or spoofed `Content-Type` header.
"""

from io import BytesIO
from typing import BinaryIO, Protocol

from PIL import Image, UnidentifiedImageError

from app.core.constants import ALLOWED_IMAGE_CONTENT_TYPES, IMAGE_FORMAT_EXTENSIONS
from app.services.exceptions import (
    ImageTooLargeError,
    InvalidImageContentError,
    UnsupportedImageTypeError,
)


class _HasFile(Protocol):
    """Structural type for anything exposing a readable `.file` — matches
    `fastapi.UploadFile` without importing FastAPI into this module."""

    file: BinaryIO


def validate_content_type(content_type: str | None) -> None:
    """Reject a declared Content-Type outside the supported set, up front."""
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise UnsupportedImageTypeError(content_type or "unknown")


def read_upload_content(upload: _HasFile, max_size_bytes: int) -> bytes:
    """Read an upload's bytes, bounded to `max_size_bytes + 1`.

    Reading one byte past the limit — rather than the whole file — lets an
    oversized upload be rejected without ever buffering the full payload
    into memory, regardless of how large it actually is.
    """
    content = upload.file.read(max_size_bytes + 1)
    if len(content) > max_size_bytes:
        raise ImageTooLargeError(max_bytes=max_size_bytes)
    return content


def validate_image_content(content: bytes) -> str:
    """Verify `content` decodes as a supported image; return its Pillow format.

    Uses `Image.open()` + `.verify()` (rather than fully decoding pixel
    data) to confirm the bytes are a structurally valid image without the
    cost of a full decode — sufficient for ingestion-time validation.
    """
    try:
        image = Image.open(BytesIO(content))
        detected_format = image.format
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageContentError() from exc

    if detected_format not in IMAGE_FORMAT_EXTENSIONS:
        raise UnsupportedImageTypeError(detected_format or "unknown")

    return detected_format
