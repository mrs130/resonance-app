from __future__ import annotations

import json
import sqlite3

from src.demo_social_service import (
    ensure_friend_request_schema,
    get_public_feed,
    send_friend_request,
    update_friend_request_status,
    valid_map_points,
)


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            nickname TEXT NOT NULL,
            city TEXT NOT NULL,
            bio TEXT NOT NULL DEFAULT '',
            social_goal TEXT NOT NULL DEFAULT '',
            avatar TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE life_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            privacy TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            mood TEXT NOT NULL,
            social_intent TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            poi_name TEXT NOT NULL,
            poi_type TEXT NOT NULL,
            longitude REAL NOT NULL,
            latitude REAL NOT NULL,
            activity TEXT NOT NULL,
            privacy TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            verified INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO users(id,nickname,city,avatar) VALUES (?,?,?,?)",
        [(1, "Alice", "南京", "A"), (2, "Bob", "南京", "B"), (3, "Cora", "上海", "C")],
    )
    ensure_friend_request_schema(conn)
    return conn


def test_cannot_send_friend_request_to_self() -> None:
    conn = make_conn()

    ok, message = send_friend_request(conn, 1, 1, "hello")

    assert ok is False
    assert "自己" in message


def test_cannot_send_duplicate_pending_friend_request() -> None:
    conn = make_conn()

    first_ok, _ = send_friend_request(conn, 1, 2, "hello")
    second_ok, second_message = send_friend_request(conn, 1, 2, "again")

    assert first_ok is True
    assert second_ok is False
    assert "已经发送" in second_message


def test_accept_and_reject_only_work_for_pending_requests() -> None:
    conn = make_conn()
    send_friend_request(conn, 1, 2, "hello")
    request_id = conn.execute("SELECT id FROM friend_requests").fetchone()["id"]

    accepted, _ = update_friend_request_status(conn, request_id, 2, "accepted")
    rejected, message = update_friend_request_status(conn, request_id, 2, "rejected")

    assert accepted is True
    assert rejected is False
    assert "待处理" in message


def test_private_life_log_is_not_in_public_feed() -> None:
    conn = make_conn()
    conn.executemany(
        """
        INSERT INTO life_logs(user_id,content,privacy,tags_json,mood,social_intent,created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        [
            (1, "公开学习动态", "公开", json.dumps(["AI"], ensure_ascii=False), "专注", "找学习搭子", "2026-01-01T10:00:00"),
            (1, "私密日记", "私密", json.dumps(["日常"], ensure_ascii=False), "平静", "暂不匹配", "2026-01-01T11:00:00"),
        ],
    )

    feed = get_public_feed(conn, current_user_id=1)
    contents = [item["content"] for item in feed]

    assert "公开学习动态" in contents
    assert "私密日记" not in contents


def test_valid_map_points_skip_invalid_coordinates() -> None:
    points = valid_map_points(
        [
            {"name": "valid", "longitude": "118.9", "latitude": "32.1"},
            {"name": "bad-number", "longitude": "x", "latitude": "32.1"},
            {"name": "out-of-range", "longitude": "118.9", "latitude": "120"},
        ]
    )

    assert [point["name"] for point in points] == ["valid"]
