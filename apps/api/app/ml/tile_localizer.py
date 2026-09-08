"""Stage 1 (building localization) — deterministic grid tiling.

**This is NOT a machine-learning model, and it does not detect
buildings.** See `apps/api/README.md` ("Why Stage 1 has no real ML
implementation") for the full reasoning this codebase already
established: every standard pretrained object-detection/segmentation
model zoo (COCO, Pascal VOC) is trained on classes that do not include
"building," so wrapping one and implying it locates buildings would be
dishonest — exactly the failure mode `UnavailableBuildingLocalizer`
(`app/ml/localizer.py`) was built to avoid.

`TileRegionLocalizer` instead proposes a deterministic NxN grid of image
tiles as *candidate regions* for Stage 2's real model to classify. Every
`LocalizedBuilding.bounding_box` here is a genuine, correctly-computed
tile boundary — never an invented location — but it represents "a region
of the uploaded image," not a verified individual building. This is the
Milestone F4 default (`Settings.MODEL_ENABLED=True`,
`MODEL_PROVIDER="open_clip"`); `UnavailableBuildingLocalizer` remains the
implementation for `MODEL_PROVIDER="legacy_resnet"` (which still requires
a real building detector nobody has built) and for
`Settings.MODEL_ENABLED=False`.
"""

from PIL import Image

from app.ml.localizer import LocalizedBuilding
from app.ml.schemas import ModelStatus
from app.ml.spatial import BoundingBox


class TileRegionLocalizer:
    """Deterministically partitions an image into a `grid_size` x
    `grid_size` grid of equal-sized tiles.

    Always "ready" — there is no weight file to load and no failure mode
    beyond a degenerate configuration (`grid_size < 1`, rejected by
    `Settings`'s own validator), so `health()` always reports
    `model_loaded=True` and `load()` is a no-op.
    """

    def __init__(self, grid_size: int) -> None:
        if grid_size < 1:
            raise ValueError("grid_size must be >= 1.")
        self._grid_size = grid_size

    def load(self) -> None:
        return None

    def locate(self, image: Image.Image) -> list[LocalizedBuilding]:
        width, height = image.size
        tile_width = width / self._grid_size
        tile_height = height / self._grid_size

        tiles: list[LocalizedBuilding] = []
        for row in range(self._grid_size):
            for col in range(self._grid_size):
                box = BoundingBox(
                    x_min=col * tile_width,
                    y_min=row * tile_height,
                    x_max=(col + 1) * tile_width,
                    y_max=(row + 1) * tile_height,
                )
                if box.width <= 0 or box.height <= 0:
                    # Degenerate only for a zero-sized input image — never
                    # produced for any real upload (already validated
                    # non-empty before reaching here).
                    continue
                tiles.append(LocalizedBuilding(bounding_box=box))
        return tiles

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=True,
            model_name="deterministic-tile-localizer",
            model_version=f"grid-{self._grid_size}x{self._grid_size}",
            device="cpu",
        )
