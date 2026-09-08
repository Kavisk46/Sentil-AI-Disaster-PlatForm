"""Orchestrates preprocessing -> model -> postprocessing into a single
damage-analysis pipeline.

    Image -> Preprocessor -> Model -> Postprocessor -> DamageAnalysis

This is the "Inference Service" step called by
`app/services/analysis_processing_service.py` (Milestone 4) — not wired
into any route directly. As of Milestone F4, `analyze()` performs real
model inference by default (`app.api.deps.get_damage_model`'s default
wiring — see `apps/api/README.md`, "Milestone F4 — real inference");
`analyze()` only raises `ModelNotAvailableError` when the model has been
explicitly disabled (`Settings.MODEL_ENABLED=False`) or the legacy
fine-tuned-checkpoint path (`MODEL_PROVIDER="legacy_resnet"`) has no
checkpoint configured — never a bug, always an honest "no genuine result
possible" signal.
"""

from uuid import UUID

from app.ml.model import DamageModel
from app.ml.postprocessing import PostprocessingError, build_analysis
from app.ml.preprocessing import ImagePreprocessor, load_image
from app.ml.schemas import DamageAnalysis
from app.schemas.analysis import AnalysisStatus


class DamageInferenceEngine:
    def __init__(
        self,
        model: DamageModel,
        preprocessor: ImagePreprocessor | None = None,
        max_image_dimension: int | None = None,
    ) -> None:
        self._model = model
        self._preprocessor = preprocessor or ImagePreprocessor()
        # Milestone F4: `Settings.MODEL_MAX_IMAGE_DIM` — an explicit
        # decompression-bomb guard checked before any decode-heavy work.
        # `None` (the default for callers that don't pass it, e.g. most
        # existing tests) means no limit, preserving prior behavior.
        self._max_image_dimension = max_image_dimension

    def analyze(self, analysis_id: UUID, image_content: bytes) -> DamageAnalysis:
        """Run the full pipeline. Raises whatever `self._model.predict()`
        raises (`ModelNotAvailableError`/`ModelLoadError`), or
        `ImageDimensionsExceededError`/`InvalidImageError`
        (preprocessing) / `PostprocessingError` (assembly) if no genuine
        result can be produced — never returns a fabricated one.

        `model_metadata` is attached here (not by `build_analysis`) since
        this is the one place that holds a reference to the model itself;
        postprocessing only ever sees the model's raw detections.
        """
        image = load_image(image_content, max_dimension=self._max_image_dimension)
        processed = self._preprocessor.process(image)
        detections = self._model.predict(processed)
        try:
            analysis = build_analysis(analysis_id, AnalysisStatus.COMPLETED, detections)
        except Exception as exc:
            raise PostprocessingError(
                f"Could not assemble a valid analysis from the model's detections: {exc}"
            ) from exc
        return analysis.model_copy(update={"model_metadata": self._model.health()})
