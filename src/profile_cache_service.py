from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any


PROFILE_CACHE_FIELDS = ("id", "nickname", "city", "bio", "social_goal", "onboarding_completed", "updated_at")


def ensure_profile_cache_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_profile_cache (
            id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL DEFAULT '',
            nickname TEXT NOT NULL DEFAULT '',
            city TEXT NOT NULL DEFAULT '',
            bio TEXT NOT NULL DEFAULT '',
            social_goal TEXT NOT NULL DEFAULT '',
            onboarding_completed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )


def save_cached_profile(
    conn: sqlite3.Connection,
    profile: dict[str, Any],
    *,
    user_email: str = "",
) -> dict[str, Any]:
    ensure_profile_cache_schema(conn)
    user_id = str(profile.get("id") or "").strip()
    if not user_id:
        raise ValueError("missing user id")

    cached = {
        "id": user_id,
        "nickname": str(profile.get("nickname") or "").strip(),
        "city": str(profile.get("city") or "").strip(),
        "bio": str(profile.get("bio") or "").strip(),
        "social_goal": str(profile.get("social_goal") or "").strip(),
        "onboarding_completed": bool(profile.get("onboarding_completed")),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn.execute(
        """
        INSERT INTO auth_profile_cache(
            id, user_email, nickname, city, bio, social_goal, onboarding_completed, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            user_email=excluded.user_email,
            nickname=excluded.nickname,
            city=excluded.city,
            bio=excluded.bio,
            social_goal=excluded.social_goal,
            onboarding_completed=excluded.onboarding_completed,
            updated_at=excluded.updated_at
        """,
        (
            cached["id"],
            user_email,
            cached["nickname"],
            cached["city"],
            cached["bio"],
            cached["social_goal"],
            int(cached["onboarding_completed"]),
            cached["updated_at"],
        ),
    )
    conn.commit()
    return cached


def fetch_cached_profile(conn: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
    ensure_profile_cache_schema(conn)
    row = conn.execute(
        """
        SELECT id, nickname, city, bio, social_goal, onboarding_completed, updated_at
        FROM auth_profile_cache
        WHERE id=?
        """,
        (str(user_id),),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "nickname": row["nickname"],
        "city": row["city"],
        "bio": row["bio"],
        "social_goal": row["social_goal"],
        "onboarding_completed": bool(row["onboarding_completed"]),
        "created_at": None,
        "updated_at": row["updated_at"],
    }
