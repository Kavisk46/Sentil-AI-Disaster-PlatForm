"""File storage abstraction.

`FileStorage` is deliberately minimal — this milestone only ever writes a
newly-uploaded file, so `save()` is the only method it needs. Reading or
deleting a stored file will be added to the protocol (and implemented by a
future S3/R2/GCS-backed class alongside `LocalFileStorage`) only once a
later milestone actually requires it.
"""

from pathlib import Path
from typing import Protocol


class FileStorage(Protocol):
    def save(self, *, storage_name: str, content: bytes) -> None:
        """Persist `content` under `storage_name`.

        `storage_name` is always server-generated (see
        `AnalysisService.create_analysis`) — never derived from
        client-controlled input — so implementations can trust it as a
        single path segment.
        """
        ...


class LocalFileStorage:
    """Stores files on the local filesystem, under `base_dir`.

    Development-only: appropriate for a single-process, single-machine
    deployment, and swapped for an object-storage implementation of
    `FileStorage` without any change to `AnalysisService` or the API layer
    once a real deployment target needs one.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def save(self, *, storage_name: str, content: bytes) -> None:
        # Defense in depth: storage_name is always server-generated and
        # never contains a separator, but this refuses to write outside
        # base_dir even if that ever stops being true.
        if storage_name != Path(storage_name).name:
            raise ValueError(f"storage_name must be a single path segment: {storage_name!r}")

        self._base_dir.mkdir(parents=True, exist_ok=True)
        destination = self._base_dir / storage_name
        destination.write_bytes(content)
