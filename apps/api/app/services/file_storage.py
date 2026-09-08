"""Object storage abstraction (`FileStorage`).

This *is* the "ObjectStorage" abstraction Milestone F5 asks for — `save`/
`load` (kept, not renamed to `put`/`get`, to avoid a needless rename of
every existing call site) plus `exists`/`delete` (new in F5). The
interface is deliberately narrow (four methods, no listing, no
directories, no metadata) so an S3/R2/GCS-backed implementation is a
straightforward drop-in alongside `LocalObjectStorage` later — see
`docs/architecture/production.md`, "Object storage" — without any
change to `AnalysisService`/`AnalysisProcessingService`/the API layer.

`storage_name` is always a server-generated key (a UUID-derived
filename — see `AnalysisService.create_analysis`), never a
client-supplied filename used as a path — every implementation can
therefore trust it as a single path segment and treat it as an opaque
object key, not a filesystem detail leaking through the abstraction.
"""

from pathlib import Path
from typing import Protocol


class FileStorage(Protocol):
    def save(self, *, storage_name: str, content: bytes) -> None:
        """Persist `content` under `storage_name` (the object-storage
        "put").

        `storage_name` is always server-generated (see
        `AnalysisService.create_analysis`) — never derived from
        client-controlled input — so implementations can trust it as a
        single path segment.
        """
        ...

    def load(self, *, storage_name: str) -> bytes:
        """Read back bytes previously written by `save()` (the
        object-storage "get").

        Raises `FileNotFoundError` if `storage_name` doesn't exist — never
        returns fabricated/placeholder content.
        """
        ...

    def exists(self, *, storage_name: str) -> bool:
        """Whether `storage_name` currently has stored content."""
        ...

    def delete(self, *, storage_name: str) -> None:
        """Remove `storage_name`'s stored content, if any.

        A no-op (not an error) if `storage_name` doesn't exist — deleting
        something already gone is not a failure.
        """
        ...


class LocalFileStorage:
    """Stores files on the local filesystem, under `base_dir`.

    Development-only: appropriate for a single-process, single-machine
    deployment, and swapped for an object-storage implementation of
    `FileStorage` without any change to `AnalysisService`,
    `AnalysisProcessingService`, or the API layer once a real deployment
    target needs one.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def save(self, *, storage_name: str, content: bytes) -> None:
        # Defense in depth: storage_name is always server-generated and
        # never contains a separator, but this refuses to write outside
        # base_dir even if that ever stops being true.
        self._validate_storage_name(storage_name)

        self._base_dir.mkdir(parents=True, exist_ok=True)
        destination = self._base_dir / storage_name
        destination.write_bytes(content)

    def load(self, *, storage_name: str) -> bytes:
        self._validate_storage_name(storage_name)

        source = self._base_dir / storage_name
        if not source.is_file():
            raise FileNotFoundError(f"Stored file not found: {storage_name!r}")
        return source.read_bytes()

    def exists(self, *, storage_name: str) -> bool:
        self._validate_storage_name(storage_name)
        return (self._base_dir / storage_name).is_file()

    def delete(self, *, storage_name: str) -> None:
        self._validate_storage_name(storage_name)
        path = self._base_dir / storage_name
        path.unlink(missing_ok=True)

    @staticmethod
    def _validate_storage_name(storage_name: str) -> None:
        if storage_name != Path(storage_name).name:
            raise ValueError(f"storage_name must be a single path segment: {storage_name!r}")


# Milestone F5 names this abstraction "ObjectStorage" — this alias lets
# new code refer to it by that name (`LocalObjectStorage` is the
# development-default implementation) without renaming the class every
# existing import (`app/api/deps.py`, `tests/conftest.py`, ...) already
# refers to as `LocalFileStorage`. Both names refer to the exact same
# class; there is only one implementation.
LocalObjectStorage = LocalFileStorage
