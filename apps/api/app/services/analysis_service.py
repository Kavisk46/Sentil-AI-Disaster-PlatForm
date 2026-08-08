"""Analysis ingestion service.

Orchestrates upload validation, storage, and in-memory metadata creation
for `POST /api/v1/analysis`:

    API route -> AnalysisService -> FileStorage
                      |
                      v
              image_validation

No AI processing happens here — this milestone only records that an image
was received (`AnalysisStatus.UPLOADED`).
"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings
from app.core.constants import IMAGE_FORMAT_EXTENSIONS
from app.schemas.analysis import AnalysisCreateResponse, AnalysisStatus
from app.services.analysis_repository import AnalysisRecord, AnalysisRepository
from app.services.file_storage import FileStorage
from app.services.image_validation import (
    read_upload_content,
    validate_content_type,
    validate_image_content,
)
from app.utils.sanitize import sanitize_filename


class AnalysisService:
    def __init__(
        self,
        settings: Settings,
        repository: AnalysisRepository,
        file_storage: FileStorage,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._file_storage = file_storage

    def create_analysis(self, upload: UploadFile) -> AnalysisCreateResponse:
        # 1. Validate declared metadata first — a cheap rejection before
        #    touching the file's bytes.
        validate_content_type(upload.content_type)
        content = read_upload_content(upload, self._settings.max_upload_size_bytes)

        # 2. Validate the bytes are actually a supported image, regardless
        #    of what the client claimed.
        image_format = validate_image_content(content)

        # 3. Server-generated identifiers only — never derived from
        #    client-controlled input, so no path traversal or extension
        #    spoofing is possible.
        analysis_id = uuid4()
        extension = IMAGE_FORMAT_EXTENSIONS[image_format]
        storage_name = f"{analysis_id}{extension}"

        self._file_storage.save(storage_name=storage_name, content=content)

        record = AnalysisRecord(
            analysis_id=analysis_id,
            status=AnalysisStatus.UPLOADED,
            original_filename=sanitize_filename(upload.filename),
            storage_name=storage_name,
            content_type=upload.content_type or "",
            size_bytes=len(content),
            created_at=datetime.now(UTC),
        )
        self._repository.create(record)

        return AnalysisCreateResponse(
            analysis_id=record.analysis_id,
            status=record.status,
            filename=record.original_filename,
        )
