from __future__ import annotations

import sqlite3

from src.profile_cache_service import ensure_profile_cache_schema, fetch_cached_profile, save_cached_profile


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_profile_cache_schema(conn)
    return conn


def test_save_and_fetch_cached_profile() -> None:
    conn = make_conn()
    profile = {
        "id": "user-1",
        "nickname": "mrs",
        "city": "南京",
        "bio": "喜欢学习和跑步",
        "social_goal": "找学习搭子",
        "onboarding_completed": True,
    }

    save_cached_profile(conn, profile, user_email="mrs@example.com")
    cached = fetch_cached_profile(conn, "user-1")

    assert cached is not None
    assert cached["nickname"] == "mrs"
    assert cached["city"] == "南京"
    assert cached["onboarding_completed"] is True


def test_save_cached_profile_updates_existing_row() -> None:
    conn = make_conn()
    save_cached_profile(conn, {"id": "user-1", "nickname": "old", "onboarding_completed": True})
    save_cached_profile(conn, {"id": "user-1", "nickname": "new", "onboarding_completed": True})

    cached = fetch_cached_profile(conn, "user-1")

    assert cached is not None
    assert cached["nickname"] == "new"


def test_fetch_cached_profile_missing_user_returns_none() -> None:
    conn = make_conn()

    assert fetch_cached_profile(conn, "missing") is None
