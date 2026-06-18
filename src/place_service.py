from __future__ import annotations

from typing import Any, Mapping

from src.geo_utils import is_valid_coordinate


CATEGORY_OPTIONS = ["学习", "咖啡", "运动", "展览", "户外", "生活", "其他"]

CATEGORY_KEYWORDS = {
    "学习": ["library", "university", "school", "college", "study", "图书馆", "大学", "学校", "自习", "书店"],
    "咖啡": ["cafe", "coffee", "tea", "咖啡", "茶", "奶茶"],
    "运动": ["gym", "stadium", "sports", "fitness", "run", "体育", "健身", "球场", "运动", "跑步"],
    "展览": ["museum", "gallery", "exhibition", "art", "美术馆", "博物馆", "展览", "画廊"],
    "户外": ["park", "mountain", "trail", "garden", "lake", "公园", "山", "湖", "景区", "户外"],
    "生活": ["restaurant", "mall", "shop", "store", "bar", "餐厅", "商场", "购物", "饭店", "影院"],
}


def normalize_category(raw_category: str | None = None, name: str | None = None) -> str:
    haystack = f"{raw_category or ''} {name or ''}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            return category
    if raw_category in CATEGORY_OPTIONS:
        return str(raw_category)
    return "其他"


def normalize_place_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    lat = payload.get("lat", payload.get("latitude"))
    lon = payload.get("lon", payload.get("longitude"))
    if not is_valid_coordinate(lat, lon):
        return None

    name = str(payload.get("name") or payload.get("display_name") or payload.get("label") or "未命名地点").strip()
    address = payload.get("display_name") or payload.get("address") or name
    raw_category = str(payload.get("type") or payload.get("class") or payload.get("category") or "")
    address_data = payload.get("address") if isinstance(payload.get("address"), dict) else {}
    city = (
        address_data.get("city")
        or address_data.get("town")
        or address_data.get("state")
        or payload.get("city")
        or ""
    )
    district = address_data.get("suburb") or address_data.get("district") or payload.get("district") or ""

    osm_type = payload.get("osm_type")
    osm_id = payload.get("osm_id")
    return {
        "name": name,
        "category": normalize_category(raw_category, name),
        "city": str(city),
        "district": str(district),
        "address": str(address),
        "latitude": float(lat),
        "longitude": float(lon),
        "osm_type": str(osm_type) if osm_type not in (None, "") else None,
        "osm_id": str(osm_id) if osm_id not in (None, "") else None,
        "source": str(payload.get("source") or "nominatim"),
    }


def place_identity(place: Mapping[str, Any]) -> str:
    osm_type = place.get("osm_type")
    osm_id = place.get("osm_id")
    if osm_type and osm_id:
        return f"osm:{osm_type}:{osm_id}"
    name = str(place.get("name") or "").strip().lower()
    lat = round(float(place.get("latitude", 0)), 5)
    lon = round(float(place.get("longitude", 0)), 5)
    return f"manual:{name}:{lat}:{lon}"


def is_same_place(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return place_identity(left) == place_identity(right)
