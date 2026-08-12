"""Great-circle distance between two WGS84 coordinates.

A real, standard calculation (the haversine formula) — not a fabricated or
approximated value. Used by `app.roads.builder` to compute each edge's
`distance` from the two OSM nodes it connects, since OSM way geometry
itself doesn't carry precomputed segment lengths.
"""

import math

_EARTH_RADIUS_METERS = 6_371_000.0


def haversine_distance_meters(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance in meters between `(lat1, lon1)` and
    `(lat2, lon2)`, both WGS84 degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_METERS * c
