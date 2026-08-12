"""Damage-classification model — Stage 2 of the two-stage pipeline.

    [Stage 1: BuildingLocalizer] -> building crop
        -> [Stage 2: TorchDamageClassifier] -> RawDetection

A ResNet18 backbone with its final layer replaced by a 4-class head
(`no_damage` / `minor` / `major` / `destroyed`) — see `apps/api/README.md`
("Selected baseline model") for why this architecture and this
formulation were chosen over the alternatives compared in the Milestone
3C analysis.

IMPORTANT — this file never downloads anything, under any configuration:
`build_resnet_classifier()` always constructs the architecture with
`weights=None` (random initialization), never a pretrained-weights enum
that would trigger a download. A real, usable model requires a fine-tuned
checkpoint file at `Settings.MODEL_PATH`, produced by an external training
run (see `apps/api/README.md`, "Training vs. inference") and loaded here
via `torch.load()` from the local filesystem only. Until that file exists,
`TorchDamageClassifier.classify()` raises `ModelNotAvailableError` —
exactly the same honesty contract `UnavailableDamageModel` already
provides, just backed by real (if not yet trained) inference code.
"""

from typing import cast

import torch
from PIL import Image
from torch import nn
from torchvision.models import resnet18
from torchvision.transforms import functional as tv_functional

from app.core.config import Settings
from app.ml.model import ModelNotAvailableError, RawDetection
from app.ml.preprocessing import ImagePreprocessor, PreprocessConfig
from app.ml.schemas import DamageClass, ModelStatus

# Order must match the training label encoding a checkpoint was produced
# with — see apps/api/README.md ("Training configuration").
_CLASS_ORDER: tuple[DamageClass, ...] = (
    DamageClass.NO_DAMAGE,
    DamageClass.MINOR,
    DamageClass.MAJOR,
    DamageClass.DESTROYED,
)

# Standard ImageNet channel statistics — the correct normalization to pair
# with an ImageNet-pretrained ResNet backbone during external training.
# This is exactly the model-specific normalization
# `app.ml.preprocessing.PreprocessConfig` deliberately leaves unspecified.
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)

_INPUT_SIZE = (224, 224)


def build_resnet_classifier(num_classes: int = len(_CLASS_ORDER)) -> nn.Module:
    """Construct the classifier architecture — always randomly initialized.

    Exported as a standalone function so both this adapter (for inference)
    and a future external training script import the *same* architecture
    definition, rather than risking two definitions drifting apart. A
    checkpoint produced by training against a different architecture will
    fail to load here loudly (a `state_dict` shape mismatch), not silently.
    """
    # torchvision's model-builder functions type-erase to `Any` internally
    # (a legacy-interface decorator), so `model.fc` below is accessed as
    # `Any` (needed — `nn.Module`'s own stub types `.fc` too loosely to
    # know it's a `Linear`). `cast` at the return boundary is deliberate,
    # not a workaround: it asserts the real, concrete runtime type without
    # narrowing `model`'s type earlier and breaking `.fc.in_features`.
    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return cast(nn.Module, model)


class TorchDamageClassifier:
    """The only real (if not yet trained) `DamageModel`-style Stage 2
    implementation as of Milestone 3C.

    Not itself a `DamageModel` (`app/ml/model.py`) — it classifies a
    single already-located building crop, not a whole image. `predict()`
    over a whole image is `TwoStageDamageModel`'s job
    (`app/ml/pipeline.py`), composing this with a `BuildingLocalizer`.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: nn.Module | None = None
        self._preprocessor = ImagePreprocessor(PreprocessConfig(target_size=_INPUT_SIZE))

    def load(self) -> None:
        """Load a fine-tuned checkpoint from `Settings.MODEL_PATH`, if any.

        Reads a local file only — never downloads. If `MODEL_PATH` is
        unset or the file doesn't exist, leaves the classifier unavailable
        rather than falling back to an untrained (and therefore
        meaningless) model.
        """
        model_path = self._settings.MODEL_PATH
        if model_path is None or not model_path.is_file():
            self._model = None
            return

        model = build_resnet_classifier()
        state_dict = torch.load(model_path, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
        model.eval()
        self._model = model

    def classify(self, crop: Image.Image) -> RawDetection:
        """Classify a single building crop.

        Raises `ModelNotAvailableError` if no checkpoint has been loaded.
        Confidence is the model's own softmax probability for the
        predicted class — genuine model output, never assigned manually.
        See `apps/api/README.md` ("Confidence interpretation") for why
        this is not a calibrated probability.
        """
        if self._model is None:
            raise ModelNotAvailableError(
                "No trained damage-classification checkpoint is configured or "
                "loaded (Settings.MODEL_PATH). See apps/api/README.md "
                "('Training vs. inference') for how one is produced."
            )

        processed = self._preprocessor.process(crop)
        tensor = tv_functional.to_tensor(processed)
        tensor = tv_functional.normalize(tensor, mean=_IMAGENET_MEAN, std=_IMAGENET_STD)
        batch = tensor.unsqueeze(0)

        with torch.no_grad():
            logits = self._model(batch)
            probabilities = torch.softmax(logits, dim=1).squeeze(0)

        predicted_index = int(torch.argmax(probabilities).item())
        confidence = float(probabilities[predicted_index].item())

        return RawDetection(
            damage_class=_CLASS_ORDER[predicted_index],
            confidence=confidence,
        )

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=self._model is not None,
            model_name=self._settings.MODEL_NAME,
            model_version=self._settings.MODEL_VERSION,
            device=self._settings.MODEL_DEVICE,
        )
