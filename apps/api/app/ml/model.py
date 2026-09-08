"""Damage-detection model interface.

`DamageModel` is the seam a real, trained computer-vision model plugs into
without changing `app/ml/inference.py` — or, later, any API route. This
mirrors the same Protocol-based swap pattern already used elsewhere in this
codebase (`FileStorage`, `AnalysisRepository` in `app/services/`).

No model is trained or bundled in this milestone.
`UnavailableDamageModel` is the only implementation: it fails clearly
(raises `ModelNotAvailableError`) rather than fabricating a prediction, and
`health()` truthfully reports `model_loaded=False`. A real implementation
(e.g. `TorchDamageModel`, loading fine-tuned weights from
`Settings.MODEL_PATH`) is added later without this file's `DamageModel`
Protocol, `app/ml/inference.py`, or the API layer needing to change.
"""

from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from app.core.config import Settings
from app.ml.schemas import DamageClass, ModelStatus
from app.ml.spatial import BoundingBox


@dataclass(frozen=True, slots=True)
class RawDetection:
    """One model-space detection, before postprocessing assigns it a
    `building_id` and folds it into a `DamageSummary`.

    Deliberately lower-level than `BuildingDamage`: a real model's raw
    output is class logits/indices and pixel-space geometry, not a
    validated, semantically-labeled Pydantic schema — translating between
    the two is exactly postprocessing's job (`app/ml/postprocessing.py`).
    Mapping a model's own internal label scheme to the canonical
    `DamageClass` is the model adapter's responsibility, so `damage_class`
    is already normalized by the time postprocessing sees it.

    `bounding_box` is `None` for any model that only classifies a known
    region (no localization of its own) — the smallest backwards-compatible
    extension needed for future geospatial output (see
    `apps/api/README.md`, "Geospatial future support"). Never populate this
    with an invented location; leave it `None` if the model didn't produce
    a real one.
    """

    damage_class: DamageClass
    confidence: float
    bounding_box: BoundingBox | None = None


class ModelNotAvailableError(RuntimeError):
    """Raised by `predict()` when no trained model is configured/loaded."""


class ModelLoadError(RuntimeError):
    """Raised by `load()` when a real load attempt was actually made but
    genuinely failed (e.g. a network error downloading a pretrained
    checkpoint, or a corrupt/incompatible checkpoint file) — distinct from
    `ModelNotAvailableError`, which means "no model is configured, no load
    was ever attempted." Milestone F4 (see `app/ml/clip_classifier.py`,
    `app/ml/tile_localizer.py`); maps to `AnalysisErrorCode.MODEL_LOAD_FAILURE`
    (`app/services/analysis_processing_service.py`)."""


class DamageModel(Protocol):
    def load(self) -> None:
        """Load model weights. Safe to call repeatedly; a no-op once loaded."""
        ...

    def predict(self, image: Image.Image) -> list[RawDetection]:
        """Run inference on a single preprocessed image.

        Raises `ModelNotAvailableError` if no model is loaded — never
        returns a fabricated result.
        """
        ...

    def health(self) -> ModelStatus:
        """Report whether a model is actually loaded and ready."""
        ...


class UnavailableDamageModel:
    """The only `DamageModel` implementation as of Milestone 3A.

    Exists so the rest of the architecture — dependency injection, and
    eventually a real endpoint — has a concrete object to depend on today,
    one that is honest about not being able to produce real predictions
    rather than fabricating them. `load()` deliberately never succeeds:
    no model-loading backend (e.g. PyTorch weight loading) has been
    implemented yet, independent of whether `Settings.MODEL_PATH` is set.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def load(self) -> None:
        return None

    def predict(self, image: Image.Image) -> list[RawDetection]:
        raise ModelNotAvailableError(
            "No trained damage-detection model is configured or loaded. "
            "Milestone 3A establishes the inference architecture only — "
            "see apps/api/README.md and docs/architecture/ai-engine.md."
        )

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=False,
            model_name=self._settings.MODEL_NAME,
            model_version=self._settings.MODEL_VERSION,
            device=self._settings.MODEL_DEVICE,
        )
