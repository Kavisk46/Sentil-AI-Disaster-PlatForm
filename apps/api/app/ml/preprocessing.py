"""Image loading and preprocessing, ahead of model inference.

Deliberately stops at "a resized, RGB `PIL.Image`" rather than producing a
tensor: which array/tensor library a real model needs (numpy, torch, ...)
and its exact normalization (channel mean/std, value scaling) are that
model's concern, introduced alongside it — not assumed here. See
`apps/api/README.md` for why.
"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError


class InvalidImageError(ValueError):
    """Raised when raw bytes can't be decoded as an image at all."""


def load_image(content: bytes) -> Image.Image:
    """Decode raw bytes into a `PIL.Image`, fully loaded into memory.

    Unlike `app.services.image_validation` (which only needs to *verify*
    an upload is a real image), this actually decodes pixel data, since
    the result is about to be resized and fed to a model.
    """
    try:
        image = Image.open(BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("File content could not be decoded as an image.") from exc
    return image


def to_rgb(image: Image.Image) -> Image.Image:
    """Normalize any Pillow image mode (RGBA, palette, grayscale, ...) to RGB."""
    if image.mode == "RGB":
        return image
    return image.convert("RGB")


@dataclass(frozen=True, slots=True)
class PreprocessConfig:
    """Parameters governing `ImagePreprocessor`.

    `target_size` is model-specific (it changes whenever the model
    changes), so it's a constructor argument here rather than a
    `Settings`/environment value — see `apps/api/README.md`.
    """

    target_size: tuple[int, int] = (512, 512)


class ImagePreprocessor:
    """Resizes and RGB-normalizes an image ahead of model inference."""

    def __init__(self, config: PreprocessConfig | None = None) -> None:
        self._config = config or PreprocessConfig()

    def process(self, image: Image.Image) -> Image.Image:
        rgb_image = to_rgb(image)
        return rgb_image.resize(self._config.target_size, Image.Resampling.LANCZOS)
