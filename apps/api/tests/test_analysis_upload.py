"""Tests for `POST /api/v1/analysis` — image ingestion (Milestone 2).

Uses `analysis_client` / `analysis_app_factory` (see conftest.py), which
isolate storage to a pytest tmp_path and use a fresh in-memory repository
per test — the real runtime upload directory is never touched.
"""

import io
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings


def _make_image_bytes(image_format: str, size: tuple[int, int] = (16, 16)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(120, 40, 200)).save(buffer, format=image_format)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("pillow_format", "content_type", "filename"),
    [
        ("JPEG", "image/jpeg", "aerial.jpg"),
        ("PNG", "image/png", "aerial.png"),
        ("WEBP", "image/webp", "aerial.webp"),
    ],
)
def test_upload_accepts_supported_image_types(
    analysis_client: TestClient, pillow_format: str, content_type: str, filename: str
) -> None:
    content = _make_image_bytes(pillow_format)

    response = analysis_client.post(
        "/api/v1/analysis",
        files={"image": (filename, content, content_type)},
    )

    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["analysis_id"])
    # "queued", not "uploaded": Milestone 4 immediately dispatches the
    # analysis for processing before this response is returned — see
    # apps/api/README.md ("Analysis lifecycle").
    assert body["status"] == "queued"
    assert body["filename"] == filename
    # No storage path, content type, or size leaked into the response.
    assert set(body.keys()) == {"analysis_id", "status", "filename"}


def test_upload_missing_file_returns_422(analysis_client: TestClient) -> None:
    response = analysis_client.post("/api/v1/analysis")

    assert response.status_code == 422


def test_upload_unsupported_mime_type_returns_415(analysis_client: TestClient) -> None:
    response = analysis_client.post(
        "/api/v1/analysis",
        files={"image": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 415


def test_upload_oversized_file_returns_413(
    analysis_app_factory: Callable[[Settings | None], FastAPI],
) -> None:
    client = TestClient(analysis_app_factory(Settings(MAX_UPLOAD_SIZE_MB=0)))
    content = _make_image_bytes("PNG")

    response = client.post(
        "/api/v1/analysis",
        files={"image": ("big.png", content, "image/png")},
    )

    assert response.status_code == 413


def test_upload_invalid_image_content_returns_400(analysis_client: TestClient) -> None:
    # Correct JPEG magic bytes, garbage after — passes the declared
    # Content-Type check but must fail Pillow's actual decode.
    corrupted = b"\xff\xd8\xff" + b"this is not a real jpeg body"

    response = analysis_client.post(
        "/api/v1/analysis",
        files={"image": ("broken.jpg", corrupted, "image/jpeg")},
    )

    assert response.status_code == 400


def test_upload_rejects_spoofed_content_type(analysis_client: TestClient) -> None:
    """A declared image/png Content-Type on bytes that are actually a BMP
    (a format we don't support) must still be rejected — the declared
    header is never trusted on its own."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format="BMP")

    response = analysis_client.post(
        "/api/v1/analysis",
        files={"image": ("fake.png", buffer.getvalue(), "image/png")},
    )

    assert response.status_code == 415


def test_upload_generates_unique_analysis_ids(analysis_client: TestClient) -> None:
    content = _make_image_bytes("PNG")

    first = analysis_client.post(
        "/api/v1/analysis", files={"image": ("a.png", content, "image/png")}
    )
    second = analysis_client.post(
        "/api/v1/analysis", files={"image": ("b.png", content, "image/png")}
    )

    assert first.json()["analysis_id"] != second.json()["analysis_id"]


def test_upload_sanitizes_path_traversal_filename(analysis_client: TestClient) -> None:
    content = _make_image_bytes("PNG")

    response = analysis_client.post(
        "/api/v1/analysis",
        files={"image": ("../../etc/passwd.png", content, "image/png")},
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "passwd.png"


def test_upload_writes_file_under_configured_storage_dir(
    analysis_app_factory: Callable[[Settings | None], FastAPI], tmp_path: Path
) -> None:
    client = TestClient(analysis_app_factory(None))
    content = _make_image_bytes("PNG")

    response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", content, "image/png")}
    )

    analysis_id = response.json()["analysis_id"]
    stored_files = list(tmp_path.glob(f"{analysis_id}.*"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == content
