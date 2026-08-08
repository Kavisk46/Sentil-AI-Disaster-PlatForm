"""Unit tests for the pure validation functions — no HTTP or UploadFile
construction needed; these operate on plain bytes."""

import io
from typing import BinaryIO

import pytest
from PIL import Image

from app.services.exceptions import (
    ImageTooLargeError,
    InvalidImageContentError,
    UnsupportedImageTypeError,
)
from app.services.image_validation import (
    read_upload_content,
    validate_content_type,
    validate_image_content,
)


def _image_bytes(image_format: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format=image_format)
    return buffer.getvalue()


def test_validate_content_type_accepts_supported_types() -> None:
    validate_content_type("image/png")  # does not raise


def test_validate_content_type_rejects_unsupported_type() -> None:
    with pytest.raises(UnsupportedImageTypeError):
        validate_content_type("application/pdf")


def test_validate_content_type_rejects_missing_type() -> None:
    with pytest.raises(UnsupportedImageTypeError):
        validate_content_type(None)


def test_validate_image_content_returns_pillow_format() -> None:
    assert validate_image_content(_image_bytes("PNG")) == "PNG"
    assert validate_image_content(_image_bytes("JPEG")) == "JPEG"
    assert validate_image_content(_image_bytes("WEBP")) == "WEBP"


def test_validate_image_content_rejects_garbage_bytes() -> None:
    with pytest.raises(InvalidImageContentError):
        validate_image_content(b"this is not an image")


def test_validate_image_content_rejects_unsupported_real_format() -> None:
    """BMP is a real, Pillow-decodable image format we don't support."""
    with pytest.raises(UnsupportedImageTypeError):
        validate_image_content(_image_bytes("BMP"))


class _FakeUpload:
    """Minimal stand-in for `fastapi.UploadFile` — only `.file` is used by
    `read_upload_content`, so a hand-built double avoids depending on
    Starlette's UploadFile construction details."""

    def __init__(self, content: bytes) -> None:
        # Explicitly typed as `BinaryIO` (matching `_HasFile.file` exactly):
        # mypy checks a plain (non-property) Protocol attribute invariantly,
        # so an inferred narrower type like `BytesIO` doesn't structurally
        # match even though it satisfies `BinaryIO` at runtime.
        self.file: BinaryIO = io.BytesIO(content)


def test_read_upload_content_returns_bytes_within_limit() -> None:
    assert read_upload_content(_FakeUpload(b"hello"), max_size_bytes=10) == b"hello"


def test_read_upload_content_rejects_oversized_payload() -> None:
    with pytest.raises(ImageTooLargeError):
        read_upload_content(_FakeUpload(b"x" * 100), max_size_bytes=10)
