import pytest
from PIL import Image

from app.ml.localizer import LocalizerNotAvailableError, UnavailableBuildingLocalizer


def test_health_reports_not_loaded_by_default() -> None:
    localizer = UnavailableBuildingLocalizer()

    status = localizer.health()

    assert status.model_loaded is False
    assert status.model_name == "sentinelai-building-localizer"


def test_locate_raises_instead_of_fabricating_a_box() -> None:
    localizer = UnavailableBuildingLocalizer()
    image = Image.new("RGB", (16, 16))

    with pytest.raises(LocalizerNotAvailableError):
        localizer.locate(image)


def test_load_does_not_raise() -> None:
    localizer = UnavailableBuildingLocalizer()

    localizer.load()
    localizer.load()  # calling it again must also be safe
