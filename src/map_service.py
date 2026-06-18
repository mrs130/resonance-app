from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import requests


NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Resonance Streamlit classroom prototype"


@dataclass(frozen=True)
class GeocodeResult:
    label: str
    latitude: float
    longitude: float
    category: str


def parse_nominatim_results(payload: list[dict[str, Any]]) -> list[GeocodeResult]:
    results: list[GeocodeResult] = []
    for item in payload:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        label = str(item.get("display_name") or item.get("name") or "未知地点")
        category = str(item.get("type") or item.get("class") or "地点")
        results.append(GeocodeResult(label=label, latitude=lat, longitude=lon, category=category))
    return results


def search_place(
    query: str,
    *,
    limit: int = 5,
    requester: Callable[..., Any] = requests.get,
) -> list[GeocodeResult]:
    keyword = query.strip()
    if not keyword:
        return []

    response = requester(
        NOMINATIM_SEARCH_URL,
        params={
            "q": keyword,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": max(1, min(limit, 10)),
            "accept-language": "zh-CN,zh,en",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    return parse_nominatim_results(payload)
