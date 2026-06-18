from __future__ import annotations

from src.geo_utils import haversine_km, is_valid_coordinate, map_center, valid_points


def test_valid_points_skip_invalid_coordinates() -> None:
    rows = [
        {"name": "ok", "latitude": "32.1", "longitude": "118.9"},
        {"name": "bad", "latitude": "x", "longitude": "118.9"},
        {"name": "range", "latitude": "91", "longitude": "118.9"},
    ]

    assert [row["name"] for row in valid_points(rows)] == ["ok"]


def test_map_center_uses_default_when_empty() -> None:
    assert map_center([]) == (32.0603, 118.7969)


def test_coordinate_and_distance_helpers() -> None:
    assert is_valid_coordinate(32.1, 118.9) is True
    assert is_valid_coordinate(120, 118.9) is False
    assert 260 < haversine_km(32.0603, 118.7969, 31.2304, 121.4737) < 290
