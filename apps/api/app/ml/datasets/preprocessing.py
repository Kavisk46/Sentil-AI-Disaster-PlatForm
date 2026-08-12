"""Preprocessing hooks for dataset samples, ahead of training.

Resize/normalize deliberately reuse `app.ml.preprocessing.ImagePreprocessor`
— the exact same preprocessing a live inference request goes through —
rather than a separate training-time implementation, so the two can't
silently drift apart. Augmentation has no equivalent at inference time, so
it gets its own hook here.

No model-specific choices (exact resize dimensions, normalization
statistics, which augmentations to apply) are hard-coded — see
`app.ml.preprocessing.PreprocessConfig` for why, and
`apps/api/README.md`.
"""

from typing import Protocol

from app.ml.datasets.schemas import DatasetSample
from app.ml.preprocessing import ImagePreprocessor, PreprocessConfig

__all__ = ["AugmentationHook", "ImagePreprocessor", "NoOpAugmentation", "PreprocessConfig"]


class AugmentationHook(Protocol):
    """Applied to a loaded `DatasetSample` — random flips/crops/color jitter,
    for example — only during training, never at inference time."""

    def __call__(self, sample: DatasetSample) -> DatasetSample: ...


class NoOpAugmentation:
    """The only `AugmentationHook` implementation today: returns the sample
    unchanged. A real augmentation pipeline is introduced alongside actual
    model training, once there's a model whose sensitivities (rotation,
    color, scale) it should be tuned for."""

    def __call__(self, sample: DatasetSample) -> DatasetSample:
        return sample
