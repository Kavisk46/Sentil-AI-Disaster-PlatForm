"""The predictive-hazard interface — deliberately unimplemented.

This milestone (F2) implements **no** predictive hazard model. Project
constraint: "Do not implement advanced ML prediction yet unless the
existing architecture absolutely requires an interface for it" and "If no
prediction model exists, the API must clearly return 'unavailable' rather
than fake a probability."

`unavailable_prediction()` is the only way this codebase constructs a
`HazardPrediction` today. A future real model plugs in by adding a second
constructor (e.g. `predict_from_model(...)`) that populates `probability`/
`severity`/`model_source` from a genuine, calibrated model — the schema
(`app.intelligence.schemas.HazardPrediction`) does not change.
"""

from datetime import datetime
from uuid import uuid4

from app.intelligence.schemas import (
    HazardPrediction,
    HazardPredictionStatus,
    HazardType,
    Uncertainty,
    UncertaintyLevel,
)
from app.ml.geospatial.geometry import Geometry

_NO_MODEL_REASON = "No predictive hazard model is configured in this deployment."


def unavailable_prediction(
    hazard_type: HazardType,
    target_area: Geometry,
    forecast_window_start: datetime,
    forecast_window_end: datetime,
) -> HazardPrediction:
    """Build the honest "no prediction available" result for
    `hazard_type` over `target_area`/the given forecast window.
    `probability`/`severity`/`model_source` are always `None` — never a
    guessed probability standing in for a real forecast."""
    return HazardPrediction(
        prediction_id=uuid4(),
        hazard_type=hazard_type,
        target_area=target_area,
        forecast_window_start=forecast_window_start,
        forecast_window_end=forecast_window_end,
        status=HazardPredictionStatus.UNAVAILABLE,
        probability=None,
        severity=None,
        model_source=None,
        evidence=[],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.UNKNOWN,
            confidence=None,
            reason=_NO_MODEL_REASON,
            missing_information=["trained hazard forecasting model"],
            source_limitations=["This milestone implements no predictive ML model by design."],
        ),
    )


def is_available(prediction: HazardPrediction) -> bool:
    """Whether `prediction` carries a real forecast. Always `False` for
    anything `unavailable_prediction()` produced — provided as a single,
    documented place to check rather than every caller re-deriving it
    from `status`."""
    return prediction.status is HazardPredictionStatus.AVAILABLE
