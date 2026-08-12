"""Dataset abstraction every disaster-damage dataset implements.

`DisasterDamageDataset` is the seam a dataset other than xBD — a different
public disaster-imagery dataset, or a private/internal one — plugs into
without changing anything that consumes it. Same Protocol-based swap
pattern used elsewhere in this codebase for `DamageModel`
(`app/ml/model.py`) and `FileStorage` (`app/services/file_storage.py`).

Sample loading and annotation loading are deliberately separate methods
(not one combined call): a caller that only needs to enumerate/validate a
split shouldn't be forced to parse every annotation file to do it.
"""

from pathlib import Path
from typing import Protocol

from app.ml.datasets.schemas import BuildingAnnotation, DatasetSample, DatasetSplit, ImageSample


class DisasterDamageDataset(Protocol):
    @property
    def root(self) -> Path:
        """Local filesystem root the dataset is read from.

        Never a URL or remote reference — datasets are not downloaded
        automatically (see `apps/api/README.md`); the caller is
        responsible for the data already existing at `root`.
        """
        ...

    def list_samples(self, split: DatasetSplit) -> list[str]:
        """Return sample identifiers belonging to `split`, without loading
        any of them."""
        ...

    def load_image_sample(self, split: DatasetSplit, sample_id: str) -> ImageSample:
        """Resolve one sample's image/annotation paths, validating that
        the referenced files actually exist."""
        ...

    def load_annotations(self, sample: ImageSample) -> list[BuildingAnnotation]:
        """Parse `sample`'s annotation file into building-level labels."""
        ...


def load_sample(
    dataset: DisasterDamageDataset, split: DatasetSplit, sample_id: str
) -> DatasetSample:
    """Convenience composition of `load_image_sample` + `load_annotations`."""
    image_sample = dataset.load_image_sample(split, sample_id)
    buildings = dataset.load_annotations(image_sample)
    return DatasetSample(image=image_sample, buildings=buildings)
