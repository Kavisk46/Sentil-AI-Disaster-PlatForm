from app.ml.spatial import BoundingBox


def test_width_height_area() -> None:
    box = BoundingBox(x_min=10, y_min=20, x_max=30, y_max=50)

    assert box.width == 20
    assert box.height == 30
    assert box.area == 600


def test_degenerate_box_has_zero_area() -> None:
    """A box with x_max < x_min (e.g. from a bad prediction) must not
    report a nonsensical negative area."""
    box = BoundingBox(x_min=30, y_min=30, x_max=10, y_max=10)

    assert box.width == 0
    assert box.height == 0
    assert box.area == 0


def test_iou_of_identical_boxes_is_one() -> None:
    box = BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10)

    assert box.iou(box) == 1.0


def test_iou_of_disjoint_boxes_is_zero() -> None:
    a = BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10)
    b = BoundingBox(x_min=20, y_min=20, x_max=30, y_max=30)

    assert a.iou(b) == 0.0


def test_iou_of_partially_overlapping_boxes() -> None:
    a = BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10)  # area 100
    b = BoundingBox(x_min=5, y_min=0, x_max=15, y_max=10)  # area 100, overlap 5x10=50

    # union = 100 + 100 - 50 = 150; iou = 50/150
    assert abs(a.iou(b) - (50 / 150)) < 1e-9


def test_iou_is_symmetric() -> None:
    a = BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10)
    b = BoundingBox(x_min=4, y_min=4, x_max=14, y_max=14)

    assert a.iou(b) == b.iou(a)
