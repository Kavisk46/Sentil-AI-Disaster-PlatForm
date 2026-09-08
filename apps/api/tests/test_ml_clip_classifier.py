"""Unit tests for `ClipZeroShotDamageClassifier` — the real tensor
pipeline (normalize -> cosine similarity -> softmax -> argmax), exercised
against a small, deterministic, **TEST-ONLY** stand-in for the `open_clip`
library itself (injected via `sys.modules`), not a mock of this
classifier's own logic. Every line of `ClipZeroShotDamageClassifier.load()`/
`.classify()` still runs for real against real `torch` tensors — only the
pretrained-checkpoint download/load is swapped out, so this stays fast
and network-free. See `tests/test_ml_real_inference_integration.py` for
the real, network-using end-to-end proof with the genuine pretrained
checkpoint.
"""

import sys
from types import SimpleNamespace

import pytest
import torch
from PIL import Image

from app.core.config import Settings
from app.ml.clip_classifier import ClipZeroShotDamageClassifier
from app.ml.model import ModelLoadError, ModelNotAvailableError
from app.ml.schemas import DamageClass


class _FakeClipModel(torch.nn.Module):
    """Deterministic stand-in: `encode_text` returns 4 orthonormal unit
    vectors (one per damage-class prompt, in order); `encode_image`
    always returns the same fixed unit vector aligned with index 0
    (NO_DAMAGE) — so the resulting softmax is a real, computed
    near-one-hot distribution, not a hand-picked result."""

    def encode_text(self, tokens: torch.Tensor) -> torch.Tensor:
        return torch.eye(tokens.shape[0], 8)

    def encode_image(self, pixel_values: torch.Tensor) -> torch.Tensor:
        vector = torch.zeros(1, 8)
        vector[0, 0] = 1.0
        return vector


def _install_fake_open_clip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = SimpleNamespace(
        create_model_and_transforms=lambda name, pretrained: (
            _FakeClipModel(),
            None,
            lambda image: torch.zeros(3, 8, 8),
        ),
        get_tokenizer=lambda name: (lambda prompts: torch.zeros(len(prompts), 4, dtype=torch.long)),
    )
    monkeypatch.setitem(sys.modules, "open_clip", fake_module)


def test_classify_before_load_raises_model_not_available() -> None:
    classifier = ClipZeroShotDamageClassifier(Settings())

    with pytest.raises(ModelNotAvailableError):
        classifier.classify(Image.new("RGB", (16, 16)))


def test_health_before_load_reports_not_loaded() -> None:
    classifier = ClipZeroShotDamageClassifier(
        Settings(MODEL_NAME="ViT-B-32", MODEL_VERSION="openai")
    )

    status = classifier.health()

    assert status.model_loaded is False
    assert status.model_name == "ViT-B-32"
    assert status.model_version == "openai"
    assert status.device == "cpu"


def test_load_and_classify_runs_the_real_tensor_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_open_clip(monkeypatch)
    classifier = ClipZeroShotDamageClassifier(Settings())

    classifier.load()
    detection = classifier.classify(Image.new("RGB", (32, 32)))

    # The fake image embedding is exactly aligned with the NO_DAMAGE
    # prompt's text embedding (index 0) — a real cosine-similarity +
    # softmax computation over genuine tensors, not a hardcoded result.
    assert detection.damage_class == DamageClass.NO_DAMAGE
    assert 0.0 <= detection.confidence <= 1.0
    assert detection.confidence > 0.9  # near-one-hot given orthonormal prompts


def test_load_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_open_clip(monkeypatch)
    classifier = ClipZeroShotDamageClassifier(Settings())

    classifier.load()
    classifier.load()  # must not raise or re-fetch

    assert classifier.health().model_loaded is True


def test_health_after_load_reports_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_open_clip(monkeypatch)
    classifier = ClipZeroShotDamageClassifier(Settings())

    classifier.load()

    assert classifier.health().model_loaded is True


def test_load_failure_raises_model_load_error_not_model_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuine load attempt that fails (e.g. no network) must be
    distinguishable from "never configured" — see
    `AnalysisErrorCode.MODEL_LOAD_FAILURE` vs `.MODEL_UNAVAILABLE`."""

    def _broken_create_model_and_transforms(name: str, pretrained: str) -> None:
        raise OSError("simulated network failure")

    fake_module = SimpleNamespace(
        create_model_and_transforms=_broken_create_model_and_transforms,
        get_tokenizer=lambda name: (lambda prompts: torch.zeros(len(prompts), 4)),
    )
    monkeypatch.setitem(sys.modules, "open_clip", fake_module)
    classifier = ClipZeroShotDamageClassifier(Settings())

    with pytest.raises(ModelLoadError):
        classifier.load()

    assert classifier.health().model_loaded is False
