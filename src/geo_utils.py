from __future__ import annotations

import math
from typing import Iterable, Mapping, Any


DEFAULT_MAP_CENTER = (32.0603, 118.7969)

CATEGORY_COLORS = {
    "学习": "#2563eb",
    "咖啡": "#a16207",
    "运动": "#16a34a",
    "展览": "#7c3aed",
    "户外": "#059669",
    "生活": "#f97316",
    "其他": "#64748b",
}


def is_valid_coordinate(latitude: Any, longitude: Any) -> bool:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def valid_points(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        latitude = row.get("latitude")
        longitude = row.get("longitude")
        if not is_valid_coordinate(latitude, longitude):
            continue
        points.append({**dict(row), "latitude": float(latitude), "longitude": float(longitude)})
    return points


def map_center(rows: Iterable[Mapping[str, Any]], default: tuple[float, float] = DEFAULT_MAP_CENTER) -> tuple[float, float]:
    points = valid_points(rows)
    if not points:
        return default
    return (
        sum(float(point["latitude"]) for point in points) / len(points),
        sum(float(point["longitude"]) for point in points) / len(points),
    )


def map_bounds(rows: Iterable[Mapping[str, Any]]) -> dict[str, float] | None:
    points = valid_points(rows)
    if not points:
        return None
    lats = [float(point["latitude"]) for point in points]
    lons = [float(point["longitude"]) for point in points]
    return {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
    }


def category_color(category: str | None) -> str:
    return CATEGORY_COLORS.get(str(category or "其他"), CATEGORY_COLORS["其他"])
