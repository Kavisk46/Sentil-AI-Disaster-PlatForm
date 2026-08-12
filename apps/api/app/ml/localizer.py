"""Building localization interface — Stage 1 of the two-stage pipeline.

    Image -> [Stage 1: BuildingLocalizer] -> [Stage 2: damage classifier] -> RawDetection

`BuildingLocalizer` is the seam a real building detector plugs into,
mirroring the same load/predict/health shape as `DamageModel`
(`app/ml/model.py`).

No off-the-shelf pretrained detector actually solves this: standard
torchvision detection/segmentation model zoos are trained on COCO or
Pascal VOC, neither of which has a "building" class — so there is no
honest way to produce real building locations without either training a
detector or being given ground-truth locations. `UnavailableBuildingLocalizer`
is the only implementation today; it fails clearly rather than fabricating
a box. See `apps/api/README.md` for what training a real one requires.
"""

from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from app.ml.schemas import ModelStatus
from app.ml.spatial import BoundingBox


@dataclass(frozen=True, slots=True)
class LocalizedBuilding:
    """One building location, before any damage assessment."""

    bounding_box: BoundingBox


class LocalizerNotAvailableError(RuntimeError):
    """Raised by `locate()` when no building-localization model is
    configured/loaded. Kept distinct from `ModelNotAvailableError`
    (`app/ml/model.py`) since localization and classification are
    independently swappable stages that can independently be unavailable
    — `TwoStageDamageModel` (`app/ml/pipeline.py`) normalizes both into
    `ModelNotAvailableError` for any caller relying on the `DamageModel`
    Protocol's documented exception contract."""


class BuildingLocalizer(Protocol):
    def load(self) -> None:
        """Load the localization model. Safe to call repeatedly."""
        ...

    def locate(self, image: Image.Image) -> list[LocalizedBuilding]:
        """Find candidate building locations in `image`.

        Raises `LocalizerNotAvailableError` if no model is loaded — never
        returns a fabricated location.
        """
        ...

    def health(self) -> ModelStatus:
        """Report whether a model is actually loaded and ready."""
        ...


class UnavailableBuildingLocalizer:
    """The only `BuildingLocalizer` implementation as of Milestone 3C.

    No building-localization model has been trained or integrated yet —
    see the module docstring for why no off-the-shelf pretrained model
    can honestly fill this role either. `health()` truthfully reports
    `model_loaded=False`; `locate()` fails clearly rather than fabricating
    a bounding box.
    """

    def __init__(self, model_name: str = "sentinelai-building-localizer") -> None:
        self._model_name = model_name

    def load(self) -> None:
        return None

    def locate(self, image: Image.Image) -> list[LocalizedBuilding]:
        raise LocalizerNotAvailableError(
            "No building-localization model is configured or loaded. "
            "See apps/api/README.md ('Building localization — Stage 1') "
            "for why no off-the-shelf pretrained detector applies here."
        )

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=False,
            model_name=self._model_name,
            model_version="unconfigured",
            device="cpu",
        )
