"""Image ingestion endpoint.

`POST /api/v1/analysis` accepts an aerial/satellite image and returns an
analysis identifier the client can use to track it in a later milestone.
This milestone only ingests and records the upload — no AI processing
happens here (see `AnalysisStatus.UPLOADED`).

The route does nothing but translate HTTP <-> schema and delegate to
`AnalysisService`; validation, storage, and error handling all live in the
service layer and `app/api/exception_handlers.py`.
"""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import AnalysisServiceDep
from app.schemas.analysis import AnalysisCreateResponse

router = APIRouter(prefix="/analysis", tags=["analysis"])

# Annotated (rather than `image: UploadFile = File(...)`) matches this
# codebase's DI convention elsewhere (see `*Dep` aliases in app/api/deps.py)
# and avoids relying on a mutable default-argument value.
ImageUpload = Annotated[
    UploadFile, File(description="Aerial/satellite image (JPEG, PNG, or WEBP).")
]


@router.post(
    "",
    response_model=AnalysisCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image for analysis",
)
def create_analysis(
    analysis_service: AnalysisServiceDep,
    image: ImageUpload,
) -> AnalysisCreateResponse:
    return analysis_service.create_analysis(image)
