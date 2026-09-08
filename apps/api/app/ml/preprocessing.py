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
    """Raised when raw bytes can't be decoded as an image at all. Maps to
    `AnalysisErrorCode.INVALID_IMAGE` (Milestone F4)."""


class ImageDimensionsExceededError(ValueError):
    """Raised when an image's pixel dimensions exceed
    `Settings.MODEL_MAX_IMAGE_DIM` (Milestone F4) — an explicit,
    configurable decompression-bomb guard, checked from the image header
    *before* the expensive full-pixel decode (`.load()`) below. Maps to
    `AnalysisErrorCode.PREPROCESSING_FAILURE`, distinct from
    `InvalidImageError` (which means "not a real image at all")."""


def load_image(content: bytes, *, max_dimension: int | None = None) -> Image.Image:
    """Decode raw bytes into a `PIL.Image`, fully loaded into memory.

    Unlike `app.services.image_validation` (which only needs to *verify*
    an upload is a real image), this actually decodes pixel data, since
    the result is about to be resized and fed to a model.

    `max_dimension`, when given, rejects an image whose width or height
    exceeds it — checked against `Image.open()`'s header-only `.size`
    (no full pixel decode needed to read it), so a pathologically large
    announced image is rejected before `.load()` ever allocates its full
    decoded pixel buffer.
    """
    try:
        image = Image.open(BytesIO(content))
        if max_dimension is not None and (
            image.width > max_dimension or image.height > max_dimension
        ):
            raise ImageDimensionsExceededError(
                f"Image dimensions {image.width}x{image.height} exceed the "
                f"maximum allowed ({max_dimension}px per side)."
            )
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
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
