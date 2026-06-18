from __future__ import annotations

from src.place_service import is_same_place, normalize_category, normalize_place_payload


def test_category_normalization_from_name_and_type() -> None:
    assert normalize_category("library", "南京大学图书馆") == "学习"
    assert normalize_category("park", "玄武湖公园") == "户外"
    assert normalize_category("unknown", "神秘地点") == "其他"


def test_normalize_place_payload_skips_invalid_coordinates() -> None:
    assert normalize_place_payload({"display_name": "坏地点", "lat": "x", "lon": "118"}) is None


def test_places_with_same_osm_identity_are_same() -> None:
    left = {"name": "A", "latitude": 1, "longitude": 2, "osm_type": "node", "osm_id": "10"}
    right = {"name": "B", "latitude": 3, "longitude": 4, "osm_type": "node", "osm_id": "10"}

    assert is_same_place(left, right) is True


def test_manual_place_identity_works_without_osm_id() -> None:
    left = {"name": "Manual", "latitude": 32.111111, "longitude": 118.999999}
    right = {"name": "manual", "latitude": 32.111112, "longitude": 119.0}

    assert is_same_place(left, right) is True
