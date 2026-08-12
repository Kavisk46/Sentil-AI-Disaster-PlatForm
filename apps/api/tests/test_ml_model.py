"""Model interface and the "no trained model" behavior.

No GPU, no downloads, no network — `UnavailableDamageModel` never touches
any of those; it exists precisely to fail clearly instead.
"""

import pytest
from PIL import Image

from app.core.config import Settings
from app.ml.model import ModelNotAvailableError, UnavailableDamageModel


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "MODEL_NAME": "sentinelai-damage-classifier",
        "MODEL_VERSION": "unconfigured",
        "MODEL_DEVICE": "cpu",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_health_reports_model_not_loaded_by_default() -> None:
    model = UnavailableDamageModel(_settings())

    status = model.health()

    assert status.model_loaded is False
    assert status.model_name == "sentinelai-damage-classifier"
    assert status.model_version == "unconfigured"
    assert status.device == "cpu"


def test_health_still_reports_unloaded_even_if_model_path_is_configured() -> None:
    """Setting MODEL_PATH alone must not make the API claim a model is
    available — no model-loading backend exists yet (see model.py)."""
    model = UnavailableDamageModel(_settings(MODEL_PATH="/some/future/weights.pt"))

    model.load()

    assert model.health().model_loaded is False


def test_predict_raises_instead_of_fabricating_a_result() -> None:
    model = UnavailableDamageModel(_settings())
    image = Image.new("RGB", (8, 8))

    with pytest.raises(ModelNotAvailableError):
        model.predict(image)


def test_predict_error_message_points_to_the_architecture_docs() -> None:
    model = UnavailableDamageModel(_settings())

    with pytest.raises(ModelNotAvailableError, match="No trained damage-detection model"):
        model.predict(Image.new("RGB", (8, 8)))


def test_load_does_not_raise() -> None:
    """Loading must be safe to call even with nothing to load — it reports
    unavailability through health()/predict(), not by crashing the app."""
    model = UnavailableDamageModel(_settings())

    model.load()
    model.load()  # calling it again must also be safe
