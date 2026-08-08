"""Analysis metadata storage.

Behind a small repository interface (`AnalysisRepository`) rather than a
dict exposed directly, so a PostgreSQL-backed implementation can replace
`InMemoryAnalysisRepository` in a later milestone without changing
`AnalysisService` or any route — see PROJECT_ROADMAP.md.
"""

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.schemas.analysis import AnalysisStatus


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    """Server-side metadata for one uploaded analysis.

    Never returned as-is over the API — `storage_name` in particular is a
    filesystem implementation detail. See `AnalysisCreateResponse` for what
    the API actually exposes.
    """

    analysis_id: UUID
    status: AnalysisStatus
    original_filename: str
    storage_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class AnalysisRepository(Protocol):
    def create(self, record: AnalysisRecord) -> None: ...
    def get(self, analysis_id: UUID) -> AnalysisRecord | None: ...


class InMemoryAnalysisRepository:
    """Process-local, non-persistent store.

    Fine for local development and tests; records vanish on restart. A
    single instance must be shared across requests within a process (see
    `app/api/deps.py`) — a fresh instance per request would forget every
    analysis immediately after creating it.
    """

    def __init__(self) -> None:
        self._records: dict[UUID, AnalysisRecord] = {}
        self._lock = threading.Lock()

    def create(self, record: AnalysisRecord) -> None:
        with self._lock:
            self._records[record.analysis_id] = record

    def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        with self._lock:
            return self._records.get(analysis_id)
