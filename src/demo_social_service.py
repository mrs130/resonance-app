from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Iterable


FRIEND_REQUEST_STATUSES = {"pending", "accepted", "rejected", "cancelled"}


def ensure_friend_request_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS friend_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(requester_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_friend_requests_pending_pair
        ON friend_requests(requester_id, receiver_id)
        WHERE status = 'pending'
        """
    )


def parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def send_friend_request(
    conn: sqlite3.Connection,
    requester_id: int,
    receiver_id: int,
    message: str = "",
) -> tuple[bool, str]:
    ensure_friend_request_schema(conn)
    if requester_id == receiver_id:
        return False, "不能给自己发送好友申请。"

    existing = conn.execute(
        """
        SELECT id FROM friend_requests
        WHERE requester_id=? AND receiver_id=? AND status='pending'
        """,
        (requester_id, receiver_id),
    ).fetchone()
    if existing:
        return False, "已经发送过待处理的好友申请。"

    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO friend_requests(requester_id, receiver_id, message, status, created_at, updated_at)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (requester_id, receiver_id, message.strip(), now, now),
    )
    conn.commit()
    return True, "好友申请已发送。"


def update_friend_request_status(
    conn: sqlite3.Connection,
    request_id: int,
    actor_id: int,
    status: str,
) -> tuple[bool, str]:
    ensure_friend_request_schema(conn)
    if status not in FRIEND_REQUEST_STATUSES - {"pending"}:
        return False, "状态不合法。"

    row = conn.execute(
        """
        SELECT requester_id, receiver_id, status
        FROM friend_requests
        WHERE id=?
        """,
        (request_id,),
    ).fetchone()
    if not row:
        return False, "好友申请不存在。"
    if row["status"] != "pending":
        return False, "只能处理待处理的好友申请。"

    requester_id = int(row["requester_id"])
    receiver_id = int(row["receiver_id"])
    if status == "cancelled" and actor_id != requester_id:
        return False, "只有发送者可以取消申请。"
    if status in {"accepted", "rejected"} and actor_id != receiver_id:
        return False, "只有接收者可以处理申请。"

    conn.execute(
        "UPDATE friend_requests SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now().isoformat(timespec="seconds"), request_id),
    )
    conn.commit()
    messages = {
        "accepted": "已通过好友申请。",
        "rejected": "已拒绝好友申请。",
        "cancelled": "已取消好友申请。",
    }
    return True, messages[status]


def get_friend_request_summary(conn: sqlite3.Connection, user_id: int) -> dict[str, int]:
    ensure_friend_request_schema(conn)
    rows = conn.execute(
        """
        SELECT status,
               SUM(CASE WHEN receiver_id=? THEN 1 ELSE 0 END) AS incoming,
               SUM(CASE WHEN requester_id=? THEN 1 ELSE 0 END) AS outgoing
        FROM friend_requests
        WHERE requester_id=? OR receiver_id=?
        GROUP BY status
        """,
        (user_id, user_id, user_id, user_id),
    ).fetchall()
    summary = {"incoming_pending": 0, "outgoing_pending": 0, "accepted": 0, "rejected": 0}
    for row in rows:
        status = row["status"]
        incoming = int(row["incoming"] or 0)
        outgoing = int(row["outgoing"] or 0)
        if status == "pending":
            summary["incoming_pending"] += incoming
            summary["outgoing_pending"] += outgoing
        elif status in summary:
            summary[status] += incoming + outgoing
    return summary


def get_public_feed(
    conn: sqlite3.Connection,
    *,
    current_user_id: int | None = None,
    source: str = "全部",
    same_city_only: bool = False,
    query: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    source_filter = source.strip()
    keyword = query.strip().lower()
    current_city = None
    if same_city_only and current_user_id is not None:
        current = conn.execute("SELECT city FROM users WHERE id=?", (current_user_id,)).fetchone()
        current_city = current["city"] if current else None

    items: list[dict[str, Any]] = []
    if source_filter in {"全部", "生活记录"}:
        rows = conn.execute(
            """
            SELECT l.id, l.user_id, u.nickname, u.city, u.avatar, l.content, l.tags_json,
                   l.mood, l.social_intent, l.privacy, l.created_at
            FROM life_logs l
            JOIN users u ON u.id = l.user_id
            WHERE l.privacy NOT IN ('私密', '绉佸瘑')
            ORDER BY l.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            items.append(
                {
                    "id": f"log-{row['id']}",
                    "source": "生活记录",
                    "user_id": row["user_id"],
                    "nickname": row["nickname"],
                    "city": row["city"],
                    "avatar": row["avatar"],
                    "content": row["content"],
                    "tags": parse_tags(row["tags_json"]),
                    "mood": row["mood"],
                    "social_intent": row["social_intent"],
                    "created_at": row["created_at"],
                }
            )

    if source_filter in {"全部", "地点打卡"}:
        rows = conn.execute(
            """
            SELECT c.id, c.user_id, u.nickname, u.city, u.avatar, c.poi_name, c.poi_type,
                   c.activity, c.tags_json, c.privacy, c.verified, c.created_at
            FROM checkins c
            JOIN users u ON u.id = c.user_id
            WHERE c.privacy NOT IN ('私密', '绉佸瘑')
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            verified_text = "已验证" if int(row["verified"]) else "演示"
            items.append(
                {
                    "id": f"checkin-{row['id']}",
                    "source": "地点打卡",
                    "user_id": row["user_id"],
                    "nickname": row["nickname"],
                    "city": row["city"],
                    "avatar": row["avatar"],
                    "content": f"{row['poi_name']} · {row['activity']} ({verified_text})",
                    "tags": parse_tags(row["tags_json"]),
                    "mood": row["poi_type"],
                    "social_intent": "开放认识附近的人",
                    "created_at": row["created_at"],
                }
            )

    def visible(item: dict[str, Any]) -> bool:
        if current_city and item["city"] != current_city:
            return False
        if not keyword:
            return True
        haystack = " ".join(
            [
                str(item["nickname"]),
                str(item["city"]),
                str(item["content"]),
                str(item["mood"]),
                str(item["social_intent"]),
                " ".join(item["tags"]),
            ]
        ).lower()
        return keyword in haystack

    return sorted([item for item in items if visible(item)], key=lambda item: item["created_at"], reverse=True)[:limit]


def valid_map_points(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        try:
            lon = float(row["longitude"])
            lat = float(row["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            continue
        points.append({**row, "longitude": lon, "latitude": lat})
    return points
