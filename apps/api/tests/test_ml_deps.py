"""DI wiring for the ML layer — not yet consumed by any route, but must
resolve correctly so a future endpoint can depend on it directly."""

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


def test_get_building_localizer_returns_the_unavailable_implementation() -> None:
    localizer = get_building_localizer()

    assert isinstance(localizer, UnavailableBuildingLocalizer)


def test_get_damage_classifier_returns_a_loaded_torch_classifier() -> None:
    classifier = get_damage_classifier(Settings())

    assert isinstance(classifier, TorchDamageClassifier)
    # No checkpoint configured by default -> honestly unavailable, not a
    # fabricated "ready" model.
    assert classifier.health().model_loaded is False


def test_get_damage_model_composes_both_stages() -> None:
    localizer = get_building_localizer()
    classifier = get_damage_classifier(Settings())

    model = get_damage_model(localizer, classifier)

    assert isinstance(model, TwoStageDamageModel)


def test_get_damage_inference_engine_wires_the_model_in() -> None:
    localizer = get_building_localizer()
    classifier = get_damage_classifier(Settings())
    model = get_damage_model(localizer, classifier)

    engine = get_damage_inference_engine(model)

    assert isinstance(engine, DamageInferenceEngine)
