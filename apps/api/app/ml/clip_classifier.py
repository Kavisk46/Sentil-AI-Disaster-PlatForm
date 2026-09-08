"""Stage 2 (damage classification) — real zero-shot inference via a
pretrained CLIP checkpoint.

**This is a general-purpose pretrained vision-language model — it is
NOT trained or fine-tuned on xBD, xView2, or any disaster-specific
dataset.** No training happens anywhere in this codebase (Milestone F4's
explicit non-goal). What makes this a genuine, real inference path rather
than a hardcoded/random one: `open_clip` downloads and loads OpenAI's
actual published CLIP weights (architecture `Settings.MODEL_NAME`,
pretrained tag `Settings.MODEL_VERSION` — default `"ViT-B-32"`/`"openai"`,
served via the Hugging Face Hub), and every prediction is a real forward
pass — a genuine image embedding, compared via real cosine similarity
against four genuine text-prompt embeddings, softmax-normalized. Nothing
here is a lookup table, a random number, or a value chosen to "look
right."

**Confidence interpretation (read this before using `confidence`
downstream):** `RawDetection.confidence` is CLIP's own raw softmax
probability over exactly 4 candidate prompts — the same "real model
output, not a manually assigned value" contract
`TorchDamageClassifier.classify()` already documents. It is emphatically
**not a calibrated probability**: CLIP was never trained or calibrated
for damage-severity classification specifically, so a value of 0.9 does
not mean "90% likely to be the correct damage class." Treat it as a
coarse, relative ranking signal between the 4 candidate prompts for the
same image — nothing stronger. No accuracy/F1/mAP/IoU claim is made
anywhere in this module, and none should be inferred from this docstring.
"""

from typing import Any

import torch
from PIL import Image

from app.core.config import Settings
from app.ml.model import ModelLoadError, ModelNotAvailableError, RawDetection
from app.ml.schemas import DamageClass, ModelStatus

# Order matters: index i's prompt corresponds to _CLASS_ORDER[i]. Kept as a
# single ordered mapping (not two parallel lists) so the pairing can never
# drift apart under a future edit.
_DAMAGE_PROMPTS: dict[DamageClass, str] = {
    DamageClass.NO_DAMAGE: "a satellite photo of an undamaged, intact building",
    DamageClass.MINOR: "a satellite photo of a building with minor visible damage",
    DamageClass.MAJOR: "a satellite photo of a building with major structural damage",
    DamageClass.DESTROYED: (
        "a satellite photo of a completely destroyed, collapsed building or rubble"
    ),
}
_CLASS_ORDER: tuple[DamageClass, ...] = tuple(_DAMAGE_PROMPTS.keys())

# CLIP's own documented logit temperature (`logit_scale`, exp(100) in the
# original paper/checkpoint) — not a tuned constant of this codebase's own
# invention. Reused exactly as OpenAI's reference implementation applies it.
_LOGIT_SCALE = 100.0


class ClipZeroShotDamageClassifier:
    """Stage 2 implementation used when `Settings.MODEL_PROVIDER ==
    "open_clip"` (the Milestone F4 default). See module docstring for the
    full honesty disclosure. Structurally matches
    `app.ml.pipeline.BuildingCropClassifier` (`load`/`classify`/`health`)
    without either module importing the other."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: Any = None
        self._preprocess: Any = None
        self._text_features: torch.Tensor | None = None

    def load(self) -> None:
        """Download (first run only — cached by `open_clip`/Hugging Face
        Hub afterward) and load the real pretrained checkpoint, then
        precompute the 4 damage-prompt text embeddings once.

        Safe to call repeatedly — a no-op once loaded. Raises
        `ModelLoadError` if a genuine load attempt fails (e.g. no network
        on first run, or a corrupt cache) — distinct from
        `ModelNotAvailableError`, which this class never raises from
        `load()` (only `classify()`, if called before `load()`).
        """
        if self._model is not None:
            return

        try:
            import open_clip  # local import: only touched when actually enabled

            device = torch.device(self._settings.MODEL_DEVICE)
            model, _, preprocess = open_clip.create_model_and_transforms(
                self._settings.MODEL_NAME, pretrained=self._settings.MODEL_VERSION
            )
            model = model.to(device)
            model.eval()
            tokenizer = open_clip.get_tokenizer(self._settings.MODEL_NAME)
            text_tokens = tokenizer(list(_DAMAGE_PROMPTS.values())).to(device)
            with torch.no_grad():
                text_features = model.encode_text(text_tokens)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError(
                f"Failed to load CLIP checkpoint '{self._settings.MODEL_NAME}' "
                f"(pretrained='{self._settings.MODEL_VERSION}'): {exc}"
            ) from exc

        self._model = model
        self._preprocess = preprocess
        self._text_features = text_features

    def classify(self, crop: Image.Image) -> RawDetection:
        """Classify a single building-crop-or-tile image.

        Raises `ModelNotAvailableError` if `load()` hasn't succeeded yet.
        `confidence` is CLIP's own softmax output — see module docstring
        for why this is not a calibrated probability.
        """
        if self._model is None or self._preprocess is None or self._text_features is None:
            raise ModelNotAvailableError(
                "No CLIP checkpoint is loaded. call load() first, or check "
                "Settings.MODEL_ENABLED/MODEL_PROVIDER."
            )

        device = torch.device(self._settings.MODEL_DEVICE)
        image_input = self._preprocess(crop).unsqueeze(0).to(device)
        with torch.no_grad():
            image_features = self._model.encode_image(image_input)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            logits = _LOGIT_SCALE * image_features @ self._text_features.T
            probabilities = torch.softmax(logits, dim=-1).squeeze(0)

        predicted_index = int(torch.argmax(probabilities).item())
        confidence = float(probabilities[predicted_index].item())

        return RawDetection(damage_class=_CLASS_ORDER[predicted_index], confidence=confidence)

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=self._model is not None,
            model_name=self._settings.MODEL_NAME,
            model_version=self._settings.MODEL_VERSION,
            device=self._settings.MODEL_DEVICE,
        )
