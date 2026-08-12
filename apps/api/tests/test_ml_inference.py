"""End-to-end pipeline test: Image -> Preprocessor -> Model -> Postprocessor.

With today's only model (`UnavailableDamageModel`), the pipeline must raise
rather than return a result — confirming the whole chain never fabricates
an analysis, not just the model in isolation.
"""

import io
from uuid import uuid4

import pytest
from PIL import Image

from app.core.config import Settings
from app.ml.inference import DamageInferenceEngine
from app.ml.model import ModelNotAvailableError, UnavailableDamageModel
from app.ml.preprocessing import InvalidImageError


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_analyze_raises_when_no_model_is_available() -> None:
    engine = DamageInferenceEngine(model=UnavailableDamageModel(Settings()))

    with pytest.raises(ModelNotAvailableError):
        engine.analyze(uuid4(), _image_bytes())


def test_analyze_rejects_invalid_image_before_reaching_the_model() -> None:
    engine = DamageInferenceEngine(model=UnavailableDamageModel(Settings()))

    with pytest.raises(InvalidImageError):
        engine.analyze(uuid4(), b"not an image")
