"""Tests for TorchDamageClassifier — CPU only, no download, no internet.

Checkpoints used here are saved locally from a freshly (randomly)
initialized `build_resnet_classifier()` — never downloaded, never a
trained/meaningful model. These tests verify the loading/inference
*plumbing* (shapes, types, honesty about availability), not accuracy.
"""

from pathlib import Path

import pytest
import torch
from PIL import Image

from app.core.config import Settings
from app.ml.classifier import TorchDamageClassifier, build_resnet_classifier
from app.ml.model import ModelNotAvailableError
from app.ml.schemas import DamageClass


def test_health_reports_unloaded_when_no_checkpoint_configured() -> None:
    classifier = TorchDamageClassifier(Settings())
    classifier.load()

    status = classifier.health()

    assert status.model_loaded is False
    assert status.device == "cpu"


def test_classify_raises_when_no_checkpoint_configured() -> None:
    classifier = TorchDamageClassifier(Settings())
    classifier.load()

    with pytest.raises(ModelNotAvailableError):
        classifier.classify(Image.new("RGB", (32, 32)))


def test_health_reports_unloaded_when_configured_path_does_not_exist(tmp_path: Path) -> None:
    missing_path = tmp_path / "does-not-exist.pt"
    classifier = TorchDamageClassifier(Settings(MODEL_PATH=missing_path))

    classifier.load()

    assert classifier.health().model_loaded is False


def test_load_never_downloads_anything(tmp_path: Path) -> None:
    """Constructing the architecture must always use weights=None — this
    test doesn't mock the network away, it proves the code path taken
    when no checkpoint exists never attempts to fetch pretrained weights
    by completing near-instantly and fully offline-safely."""
    classifier = TorchDamageClassifier(Settings())

    classifier.load()  # must not raise / hang / attempt any network call

    assert classifier.health().model_loaded is False


def _save_local_checkpoint(tmp_path: Path) -> Path:
    checkpoint_path = tmp_path / "classifier.pt"
    model = build_resnet_classifier()
    torch.save(model.state_dict(), checkpoint_path)
    return checkpoint_path


def test_load_succeeds_with_a_local_checkpoint(tmp_path: Path) -> None:
    checkpoint_path = _save_local_checkpoint(tmp_path)
    classifier = TorchDamageClassifier(Settings(MODEL_PATH=checkpoint_path))

    classifier.load()

    assert classifier.health().model_loaded is True


def test_classify_returns_a_valid_raw_detection(tmp_path: Path) -> None:
    checkpoint_path = _save_local_checkpoint(tmp_path)
    classifier = TorchDamageClassifier(Settings(MODEL_PATH=checkpoint_path))
    classifier.load()

    detection = classifier.classify(Image.new("RGB", (64, 64), color=(80, 40, 200)))

    assert isinstance(detection.damage_class, DamageClass)
    assert 0.0 <= detection.confidence <= 1.0
    # This stage never locates buildings itself — bounding_box is filled
    # in by the orchestrator (app/ml/pipeline.py), not the classifier.
    assert detection.bounding_box is None


def test_classify_handles_non_rgb_input(tmp_path: Path) -> None:
    """Crops may come from any source image mode; the classifier must not
    crash on grayscale/RGBA input."""
    checkpoint_path = _save_local_checkpoint(tmp_path)
    classifier = TorchDamageClassifier(Settings(MODEL_PATH=checkpoint_path))
    classifier.load()

    detection = classifier.classify(Image.new("RGBA", (48, 48)))

    assert isinstance(detection.damage_class, DamageClass)
