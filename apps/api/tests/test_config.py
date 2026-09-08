"""Tests for `Settings`' model-related configuration (Milestone F4).

Pure config construction only — no DI, no model load, no network. See
`tests/test_ml_deps.py` for wiring-shape tests and
`tests/test_ml_real_inference_integration.py` for the real, network-using
end-to-end proof.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_model_is_enabled_by_default_with_the_open_clip_provider() -> None:
    """The real, out-of-the-box production default: a fresh `Settings()`
    (no environment overrides) is real-inference-enabled — see
    apps/api/README.md, "Milestone F4 — real inference"."""
    settings = Settings()

    assert settings.MODEL_ENABLED is True
    assert settings.MODEL_PROVIDER == "open_clip"


def test_model_device_defaults_to_cpu() -> None:
    settings = Settings()

    assert settings.MODEL_DEVICE == "cpu"


def test_model_can_be_explicitly_disabled() -> None:
    settings = Settings(MODEL_ENABLED=False)

    assert settings.MODEL_ENABLED is False


def test_legacy_provider_is_a_valid_configuration() -> None:
    settings = Settings(MODEL_PROVIDER="legacy_resnet")

    assert settings.MODEL_PROVIDER == "legacy_resnet"


def test_invalid_model_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(MODEL_PROVIDER="not-a-real-provider")


def test_model_tile_grid_rejects_zero_or_negative() -> None:
    with pytest.raises(ValidationError):
        Settings(MODEL_TILE_GRID=0)


def test_model_max_image_dim_rejects_zero_or_negative() -> None:
    with pytest.raises(ValidationError):
        Settings(MODEL_MAX_IMAGE_DIM=-1)


def test_model_path_defaults_to_unset() -> None:
    settings = Settings()

    assert settings.MODEL_PATH is None
