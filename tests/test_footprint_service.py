from __future__ import annotations

import sqlite3
from datetime import date

from src.footprint_service import (
    add_checkin,
    category_distribution,
    city_options,
    compute_duration_minutes,
    delete_checkin,
    ensure_footprint_schema,
    export_csv,
    export_json,
    footprint_stats,
    heatmap_rows,
    list_footprints,
    monthly_stats,
    place_atlas,
    public_feed_payload_from_checkin,
    seed_demo_footprints,
    update_checkin,
)


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            nickname TEXT NOT NULL,
            city TEXT NOT NULL DEFAULT '',
            bio TEXT NOT NULL DEFAULT '',
            social_goal TEXT NOT NULL DEFAULT '',
            avatar TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO users(id, nickname) VALUES (1, 'Alice'), (2, 'Bob');
        """
    )
    ensure_footprint_schema(conn, seed_demo=False)
    return conn


def add_sample(conn: sqlite3.Connection, user_id: int = 1, *, privacy: str = "公开", day: str = "2026-06-01") -> int:
    checkin_id = add_checkin(
        conn,
        user_id=user_id,
        poi_name="南京大学图书馆",
        poi_type="学习",
        longitude=118.9597,
        latitude=32.1192,
        activity="自习",
        privacy=privacy,
        tags=["学习", "AI"],
        visited_at=f"{day}T10:00",
        ended_at=f"{day}T11:30",
        mood="专注",
        notes="今天效率不错",
        feed_public=True,
    )
    conn.commit()
    return checkin_id


def test_list_footprints_only_returns_current_user() -> None:
    conn = make_conn()
    add_sample(conn, 1)
    add_sample(conn, 2)

    rows = list_footprints(conn, user_id=1)

    assert len(rows) == 1
    assert rows[0]["user_id"] == 1


def test_update_and_delete_cannot_touch_other_user_checkin() -> None:
    conn = make_conn()
    checkin_id = add_sample(conn, 2)

    updated = update_checkin(
        conn,
        checkin_id=checkin_id,
        user_id=1,
        activity="改掉",
        privacy="公开",
        mood="开心",
        notes="x",
        tags=["x"],
    )
    deleted = delete_checkin(conn, checkin_id=checkin_id, user_id=1)

    assert updated is False
    assert deleted is False
    assert len(list_footprints(conn, user_id=2)) == 1


def test_date_filter_and_sorting_use_visited_at() -> None:
    conn = make_conn()
    add_sample(conn, day="2026-05-01")
    add_sample(conn, day="2026-06-02")
    add_sample(conn, day="2026-06-10")

    rows = list_footprints(conn, user_id=1, start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))

    assert [row["visited_at"][:10] for row in rows] == ["2026-06-10", "2026-06-02"]


def test_stats_revisit_rate_is_zero_safe() -> None:
    assert footprint_stats([])["revisit_rate"] == 0


def test_stats_counts_revisits() -> None:
    conn = make_conn()
    add_sample(conn, day="2026-06-01")
    add_sample(conn, day="2026-06-02")

    stats = footprint_stats(list_footprints(conn, user_id=1))

    assert stats["visits"] == 2
    assert stats["unique_places"] == 1
    assert stats["revisits"] == 1


def test_legacy_checkin_falls_back_to_created_at() -> None:
    conn = make_conn()
    conn.execute(
        """
        INSERT INTO checkins(user_id, poi_name, poi_type, longitude, latitude, activity, privacy, tags_json, verified, created_at)
        VALUES (1, '旧地点', '其他', 118, 32, '旧活动', '公开', '[]', 0, '2026-01-01T09:00')
        """
    )
    ensure_footprint_schema(conn, seed_demo=False)

    row = list_footprints(conn, user_id=1)[0]

    assert row["visited_at"] == "2026-01-01T09:00"


def test_atlas_heatmap_monthly_and_category_aggregation() -> None:
    conn = make_conn()
    add_sample(conn, day="2026-05-31")
    add_sample(conn, day="2026-06-01")

    rows = list_footprints(conn, user_id=1)

    assert place_atlas(rows)[0]["visit_count"] == 2
    assert {item["date"] for item in heatmap_rows(rows)} == {"2026-05-31", "2026-06-01"}
    assert {item["month"] for item in monthly_stats(rows)} == {"2026-05", "2026-06"}
    assert category_distribution(rows)[0]["category"] == "学习"


def test_export_contains_only_rows_passed_in() -> None:
    conn = make_conn()
    add_sample(conn, 1)
    add_sample(conn, 2)
    rows = list_footprints(conn, user_id=1)

    assert "南京大学图书馆" in export_csv(rows)
    exported = export_json(rows)
    assert '"user_id": 2' not in exported


def test_private_checkin_has_no_public_feed_payload() -> None:
    conn = make_conn()
    add_sample(conn, privacy="私密")
    row = list_footprints(conn, user_id=1)[0]

    assert public_feed_payload_from_checkin(row) is None


def test_duration_rejects_negative_range() -> None:
    assert compute_duration_minutes("2026-06-01T11:00", "2026-06-01T10:00") is None


def test_demo_seed_creates_rich_dataset() -> None:
    conn = make_conn()
    seed_demo_footprints(conn)

    count = conn.execute("SELECT COUNT(*) AS n FROM checkins").fetchone()["n"]
    categories = {row["poi_type"] for row in conn.execute("SELECT DISTINCT poi_type FROM checkins").fetchall()}

    assert count >= 25
    assert {"学习", "咖啡", "运动", "展览", "户外", "生活"}.issubset(categories)


def test_city_options_includes_all_even_when_empty() -> None:
    conn = make_conn()

    assert city_options(conn, 1) == ["全部"]
