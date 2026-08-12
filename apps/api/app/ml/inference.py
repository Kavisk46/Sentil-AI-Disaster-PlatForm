"""Orchestrates preprocessing -> model -> postprocessing into a single
damage-analysis pipeline.

    Image -> Preprocessor -> Model -> Postprocessor -> DamageAnalysis

This is the "Inference Service" step called by
`app/services/analysis_processing_service.py` (Milestone 4) — not wired
into any route directly. With today's `TwoStageDamageModel` (an
unavailable localizer + an unchecked-pointed classifier — see
`apps/api/README.md`), `analyze()` always raises `ModelNotAvailableError`
— by design, not a bug: no trained model exists yet, so there is no real
result to return.
"""

from uuid import UUID

from app.ml.model import DamageModel
from app.ml.postprocessing import build_analysis
from app.ml.preprocessing import ImagePreprocessor, load_image
from app.ml.schemas import DamageAnalysis
from app.schemas.analysis import AnalysisStatus


class DamageInferenceEngine:
    def __init__(self, model: DamageModel, preprocessor: ImagePreprocessor | None = None) -> None:
        self._model = model
        self._preprocessor = preprocessor or ImagePreprocessor()

    def analyze(self, analysis_id: UUID, image_content: bytes) -> DamageAnalysis:
        """Run the full pipeline. Raises whatever `self._model.predict()`
        raises (typically `ModelNotAvailableError`) if no genuine result
        can be produced — never returns a fabricated one.

        `model_metadata` is attached here (not by `build_analysis`) since
        this is the one place that holds a reference to the model itself;
        postprocessing only ever sees the model's raw detections.
        """
        image = load_image(image_content)
        processed = self._preprocessor.process(image)
        detections = self._model.predict(processed)
        analysis = build_analysis(analysis_id, AnalysisStatus.COMPLETED, detections)
        return analysis.model_copy(update={"model_metadata": self._model.health()})
