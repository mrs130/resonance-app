from __future__ import annotations

from src.map_service import NOMINATIM_SEARCH_URL, parse_nominatim_results, search_place


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def test_parse_nominatim_results_skips_invalid_coordinates() -> None:
    results = parse_nominatim_results(
        [
            {"display_name": "南京大学仙林校区", "lat": "32.1192", "lon": "118.9597", "type": "university"},
            {"display_name": "坏数据", "lat": "x", "lon": "118.9"},
        ]
    )

    assert len(results) == 1
    assert results[0].label == "南京大学仙林校区"
    assert results[0].latitude == 32.1192
    assert results[0].longitude == 118.9597


def test_search_place_uses_nominatim_without_real_network() -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse([{"display_name": "上海外滩", "lat": "31.2400", "lon": "121.4900", "type": "waterfront"}])

    results = search_place("上海外滩", requester=fake_get)

    assert results[0].label == "上海外滩"
    assert calls[0]["url"] == NOMINATIM_SEARCH_URL
    assert calls[0]["params"]["q"] == "上海外滩"
    assert "User-Agent" in calls[0]["headers"]


def test_search_place_empty_query_returns_empty_list() -> None:
    assert search_place("   ") == []
