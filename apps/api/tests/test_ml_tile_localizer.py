"""Tests for `TileRegionLocalizer` — deterministic grid tiling, not a
model. See the module docstring in `app/ml/tile_localizer.py` for why
Stage 1 is not (and, per this codebase's own established analysis,
cannot honestly be) a real building-detection model."""

import pytest
from PIL import Image

from app.ml.tile_localizer import TileRegionLocalizer


def test_rejects_a_non_positive_grid_size() -> None:
    with pytest.raises(ValueError, match="grid_size"):
        TileRegionLocalizer(grid_size=0)


def test_single_tile_covers_the_whole_image() -> None:
    localizer = TileRegionLocalizer(grid_size=1)
    image = Image.new("RGB", (100, 200))

    tiles = localizer.locate(image)

    assert len(tiles) == 1
    box = tiles[0].bounding_box
    assert (box.x_min, box.y_min, box.x_max, box.y_max) == (0, 0, 100, 200)


def test_grid_produces_grid_size_squared_non_overlapping_tiles() -> None:
    localizer = TileRegionLocalizer(grid_size=2)
    image = Image.new("RGB", (100, 100))

    tiles = localizer.locate(image)

    assert len(tiles) == 4
    boxes = [t.bounding_box for t in tiles]
    # Every pair of tiles has zero intersection area — a real partition,
    # not overlapping/invented regions.
    for i, box_a in enumerate(boxes):
        for box_b in boxes[i + 1 :]:
            assert box_a.intersection_area(box_b) == 0.0
    # The tiles' combined area covers the whole image, not a subset.
    assert sum(box.area for box in boxes) == pytest.approx(100 * 100)


def test_tiles_are_real_pixel_regions_never_fabricated_locations() -> None:
    localizer = TileRegionLocalizer(grid_size=3)
    image = Image.new("RGB", (90, 90))

    tiles = localizer.locate(image)

    assert len(tiles) == 9
    for tile in tiles:
        box = tile.bounding_box
        assert 0 <= box.x_min < box.x_max <= 90
        assert 0 <= box.y_min < box.y_max <= 90


def test_load_is_a_safe_noop() -> None:
    localizer = TileRegionLocalizer(grid_size=2)

    localizer.load()
    localizer.load()


def test_health_always_reports_ready_and_names_the_grid() -> None:
    localizer = TileRegionLocalizer(grid_size=4)

    status = localizer.health()

    assert status.model_loaded is True
    assert status.model_version == "grid-4x4"
