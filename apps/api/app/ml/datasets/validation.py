"""Dataset integrity validation.

Every failure here is an explicit exception, never a silent skip or a
log line no one reads. A dataset loader that quietly drops broken samples
produces a model trained on a biased, undocumented subset of the data —
worse than refusing to load at all, since the bias isn't visible anywhere.
"""

from pathlib import Path

from app.ml.preprocessing import InvalidImageError, load_image


class DatasetValidationError(Exception):
    """Base class for every dataset-integrity error in this package."""


class MissingImageError(DatasetValidationError):
    """An expected image file doesn't exist on disk."""


class MissingAnnotationError(DatasetValidationError):
    """An expected annotation file doesn't exist on disk."""


class InvalidImageFileError(DatasetValidationError):
    """A file exists but doesn't decode as an image."""


class MalformedAnnotationError(DatasetValidationError):
    """An annotation file exists but isn't structured as expected."""


def validate_image_exists(path: Path) -> None:
    if not path.is_file():
        raise MissingImageError(f"Image file not found: {path}")


def validate_annotation_exists(path: Path) -> None:
    if not path.is_file():
        raise MissingAnnotationError(f"Annotation file not found: {path}")


def validate_image_file(path: Path) -> None:
    """Confirm `path` actually decodes as an image, not just that it exists.

    Delegates the decode check to `app.ml.preprocessing.load_image` — the
    same Pillow-based check a real image goes through before inference —
    rather than re-implementing it.
    """
    try:
        load_image(path.read_bytes())
    except InvalidImageError as exc:
        raise InvalidImageFileError(f"File is not a valid image: {path}") from exc
