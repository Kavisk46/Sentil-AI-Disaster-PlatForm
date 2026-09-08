"""DI wiring for the ML layer.

Deliberately never exercises the real `MODEL_ENABLED=True`/`open_clip`
path here — that would require network access and a slow first-time
checkpoint download (see `tests/test_ml_real_inference_integration.py`
for the dedicated, real test proving that path actually works). These
tests only prove the wiring *shape* — that the right concrete types are
selected for each configuration — using `MODEL_ENABLED=False`, which is
fast and network-free.
"""

from app.api.deps import (
    get_building_localizer,
    get_damage_classifier,
    get_damage_inference_engine,
    get_damage_model,
)
from app.core.config import Settings
from app.ml.classifier import TorchDamageClassifier
from app.ml.inference import DamageInferenceEngine
from app.ml.localizer import UnavailableBuildingLocalizer
from app.ml.pipeline import TwoStageDamageModel


def test_get_building_localizer_is_unavailable_when_model_disabled() -> None:
    localizer = get_building_localizer(Settings(MODEL_ENABLED=False))

    assert isinstance(localizer, UnavailableBuildingLocalizer)


def test_get_damage_classifier_is_the_legacy_torch_classifier_when_model_disabled() -> None:
    classifier = get_damage_classifier(Settings(MODEL_ENABLED=False))

    assert isinstance(classifier, TorchDamageClassifier)
    # No checkpoint configured by default -> honestly unavailable, not a
    # fabricated "ready" model.
    assert classifier.health().model_loaded is False


def test_get_damage_classifier_uses_legacy_torch_classifier_for_legacy_provider() -> None:
    classifier = get_damage_classifier(
        Settings(MODEL_ENABLED=True, MODEL_PROVIDER="legacy_resnet")
    )

    assert isinstance(classifier, TorchDamageClassifier)


def test_get_damage_model_composes_both_stages() -> None:
    settings = Settings(MODEL_ENABLED=False)
    localizer = get_building_localizer(settings)
    classifier = get_damage_classifier(settings)

    model = get_damage_model(localizer, classifier)

    assert isinstance(model, TwoStageDamageModel)


def test_get_damage_inference_engine_wires_the_model_in() -> None:
    settings = Settings(MODEL_ENABLED=False)
    localizer = get_building_localizer(settings)
    classifier = get_damage_classifier(settings)
    model = get_damage_model(localizer, classifier)

    engine = get_damage_inference_engine(model, settings)

    assert isinstance(engine, DamageInferenceEngine)


def test_disabled_wiring_is_cached_across_calls() -> None:
    """The config-keyed cache (app/api/deps.py) must return the *same*
    instance for the same configuration — never reconstruct (and, for a
    real provider, re-download/re-load) on every call."""
    settings = Settings(MODEL_ENABLED=False)

    first = get_damage_classifier(settings)
    second = get_damage_classifier(settings)

    assert first is second
