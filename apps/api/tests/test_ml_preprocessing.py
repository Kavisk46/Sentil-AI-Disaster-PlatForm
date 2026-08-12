"""Preprocessing behavior — pure Pillow operations, no GPU/network/downloads."""

import io

import pytest
from PIL import Image

from app.ml.preprocessing import (
    ImagePreprocessor,
    InvalidImageError,
    PreprocessConfig,
    load_image,
    to_rgb,
)


def _image_bytes(mode: str, size: tuple[int, int], image_format: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size).save(buffer, format=image_format)
    return buffer.getvalue()


def test_load_image_decodes_valid_bytes() -> None:
    image = load_image(_image_bytes("RGB", (10, 10)))

    assert image.size == (10, 10)


def test_load_image_rejects_garbage_bytes() -> None:
    with pytest.raises(InvalidImageError):
        load_image(b"not an image")


def test_to_rgb_converts_rgba_to_rgb() -> None:
    rgba_image = Image.new("RGBA", (4, 4))

    result = to_rgb(rgba_image)

    assert result.mode == "RGB"


def test_to_rgb_converts_grayscale_to_rgb() -> None:
    grayscale_image = Image.new("L", (4, 4))

    result = to_rgb(grayscale_image)

    assert result.mode == "RGB"


def test_to_rgb_is_a_noop_for_already_rgb_images() -> None:
    rgb_image = Image.new("RGB", (4, 4))

    result = to_rgb(rgb_image)

    assert result is rgb_image


def test_image_preprocessor_resizes_to_configured_target() -> None:
    preprocessor = ImagePreprocessor(PreprocessConfig(target_size=(64, 64)))
    source = Image.new("RGB", (200, 100))

    processed = preprocessor.process(source)

    assert processed.size == (64, 64)
    assert processed.mode == "RGB"


def test_image_preprocessor_converts_non_rgb_input() -> None:
    preprocessor = ImagePreprocessor(PreprocessConfig(target_size=(32, 32)))
    source = Image.new("RGBA", (200, 100))

    processed = preprocessor.process(source)

    assert processed.mode == "RGB"


def test_image_preprocessor_uses_default_config_when_none_given() -> None:
    preprocessor = ImagePreprocessor()
    source = Image.new("RGB", (10, 10))

    processed = preprocessor.process(source)

    assert processed.size == PreprocessConfig().target_size
