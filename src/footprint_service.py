from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from src.geo_utils import valid_points
from src.place_service import CATEGORY_OPTIONS, normalize_category


PRIVACY_PRIVATE = {"私密", "仅自己可见"}
DEFAULT_TIMEZONE = "Asia/Shanghai"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}


def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_footprint_schema(conn: sqlite3.Connection, *, seed_demo: bool = True) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '其他',
            city TEXT NOT NULL DEFAULT '',
            district TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            osm_type TEXT,
            osm_id TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_places_osm_unique
        ON places(osm_type, osm_id)
        WHERE osm_type IS NOT NULL AND osm_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checkins (
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
        )
        """
    )
    _add_column(conn, "checkins", "place_id", "INTEGER")
    _add_column(conn, "checkins", "visited_at", "TEXT")
    _add_column(conn, "checkins", "ended_at", "TEXT")
    _add_column(conn, "checkins", "duration_minutes", "INTEGER")
    _add_column(conn, "checkins", "mood", "TEXT NOT NULL DEFAULT ''")
    _add_column(conn, "checkins", "tags", "TEXT NOT NULL DEFAULT '[]'")
    _add_column(conn, "checkins", "source", "TEXT NOT NULL DEFAULT 'manual'")
    _add_column(conn, "checkins", "timezone", f"TEXT NOT NULL DEFAULT '{DEFAULT_TIMEZONE}'")
    _add_column(conn, "checkins", "notes", "TEXT NOT NULL DEFAULT ''")
    _add_column(conn, "checkins", "feed_public", "INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE checkins SET visited_at = created_at WHERE visited_at IS NULL OR visited_at = ''")
    conn.execute("UPDATE checkins SET tags = tags_json WHERE tags = '[]' AND tags_json IS NOT NULL AND tags_json != ''")
    if seed_demo:
        seed_demo_footprints(conn)


def parse_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError):
        payload = [part.strip() for part in str(value).split(",")]
    if not isinstance(payload, list):
        return []
    return [str(item).strip() for item in payload if str(item).strip()]


def serialize_tags(tags: Iterable[str], *, limit: int = 8) -> str:
    clean: list[str] = []
    for tag in tags:
        text = str(tag).strip().lstrip("#")
        if text and text not in clean:
            clean.append(text)
    return json.dumps(clean[:limit], ensure_ascii=False)


def combine_datetime(day: date, value: time | None) -> str:
    return datetime.combine(day, value or time(hour=12, minute=0)).isoformat(timespec="minutes")


def compute_duration_minutes(start_at: str | None, end_at: str | None) -> int | None:
    if not start_at or not end_at:
        return None
    try:
        start = datetime.fromisoformat(start_at)
        end = datetime.fromisoformat(end_at)
    except ValueError:
        return None
    minutes = int((end - start).total_seconds() // 60)
    return minutes if minutes >= 0 else None


def ensure_place(
    conn: sqlite3.Connection,
    *,
    name: str,
    category: str,
    latitude: float,
    longitude: float,
    city: str = "",
    district: str = "",
    address: str = "",
    osm_type: str | None = None,
    osm_id: str | None = None,
    source: str = "manual",
) -> int:
    if osm_type and osm_id:
        row = conn.execute("SELECT id FROM places WHERE osm_type=? AND osm_id=?", (osm_type, str(osm_id))).fetchone()
        if row:
            return int(row["id"])
    row = conn.execute(
        """
        SELECT id FROM places
        WHERE lower(name)=lower(?) AND abs(latitude - ?) < 0.00002 AND abs(longitude - ?) < 0.00002
        """,
        (name, latitude, longitude),
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO places(name, category, city, district, address, latitude, longitude, osm_type, osm_id, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name.strip() or "未命名地点",
            normalize_category(category, name),
            city.strip(),
            district.strip(),
            address.strip(),
            float(latitude),
            float(longitude),
            osm_type,
            str(osm_id) if osm_id else None,
            source,
            _now(),
        ),
    )
    return int(cur.lastrowid)


def add_checkin(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    poi_name: str,
    poi_type: str,
    longitude: float,
    latitude: float,
    activity: str,
    privacy: str,
    tags: Iterable[str],
    visited_at: str | None = None,
    ended_at: str | None = None,
    duration_minutes: int | None = None,
    mood: str = "",
    notes: str = "",
    feed_public: bool = False,
    verified: int = 0,
    place_id: int | None = None,
    source: str = "manual",
    timezone: str = DEFAULT_TIMEZONE,
) -> int:
    ensure_footprint_schema(conn, seed_demo=False)
    category = normalize_category(poi_type, poi_name)
    if place_id is None:
        place_id = ensure_place(
            conn,
            name=poi_name,
            category=category,
            latitude=latitude,
            longitude=longitude,
            source=source,
        )
    created_at = _now()
    actual_visited_at = visited_at or created_at
    actual_duration = duration_minutes if duration_minutes is not None else compute_duration_minutes(actual_visited_at, ended_at)
    clean_tags = serialize_tags(tags)
    cur = conn.execute(
        """
        INSERT INTO checkins(
            user_id, poi_name, poi_type, longitude, latitude, activity, privacy, tags_json, verified, created_at,
            place_id, visited_at, ended_at, duration_minutes, mood, tags, source, timezone, notes, feed_public
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            poi_name.strip(),
            category,
            float(longitude),
            float(latitude),
            activity.strip(),
            privacy,
            clean_tags,
            int(verified),
            created_at,
            place_id,
            actual_visited_at,
            ended_at,
            actual_duration,
            mood.strip(),
            clean_tags,
            source,
            timezone,
            notes.strip(),
            1 if feed_public and privacy not in PRIVACY_PRIVATE else 0,
        ),
    )
    return int(cur.lastrowid)


def _row_to_footprint(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tags_list"] = parse_tags(item.get("tags") or item.get("tags_json"))
    item["visited_at"] = item.get("visited_at") or item.get("created_at")
    item["category"] = normalize_category(item.get("poi_type"), item.get("poi_name"))
    return item


def list_footprints(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    city: str = "全部",
    category: str = "全部",
    tag: str = "",
    only_with_notes: bool = False,
) -> list[dict[str, Any]]:
    ensure_footprint_schema(conn, seed_demo=False)
    sql = """
        SELECT c.*, p.city AS place_city, p.district, p.address, p.name AS place_name
        FROM checkins c
        LEFT JOIN places p ON p.id = c.place_id
        WHERE c.user_id = ?
    """
    params: list[Any] = [int(user_id)]
    if start_date:
        sql += " AND date(COALESCE(c.visited_at, c.created_at)) >= date(?)"
        params.append(start_date.isoformat())
    if end_date:
        sql += " AND date(COALESCE(c.visited_at, c.created_at)) <= date(?)"
        params.append(end_date.isoformat())
    if city and city != "全部":
        sql += " AND COALESCE(NULLIF(p.city, ''), '') = ?"
        params.append(city)
    if category and category != "全部":
        sql += " AND c.poi_type = ?"
        params.append(category)
    if only_with_notes:
        sql += " AND TRIM(COALESCE(c.notes, '')) != ''"
    sql += " ORDER BY datetime(COALESCE(c.visited_at, c.created_at)) DESC, c.id DESC"
    rows = [_row_to_footprint(row) for row in conn.execute(sql, params).fetchall()]
    keyword = tag.strip().lstrip("#").lower()
    if keyword:
        rows = [row for row in rows if keyword in " ".join(row["tags_list"]).lower()]
    return rows


def footprint_stats(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(rows)
    place_keys = [row.get("place_id") or f"{row.get('poi_name')}:{row.get('latitude')}:{row.get('longitude')}" for row in items]
    unique_places = len(set(place_keys))
    place_counts = Counter(place_keys)
    revisits = sum(max(0, count - 1) for count in place_counts.values())
    cities = {str(row.get("place_city") or "").strip() for row in items if str(row.get("place_city") or "").strip()}
    categories = Counter(row.get("category") or row.get("poi_type") or "其他" for row in items)
    return {
        "visits": len(items),
        "unique_places": unique_places,
        "new_places": unique_places,
        "revisits": revisits,
        "active_cities": len(cities),
        "favorite_category": categories.most_common(1)[0][0] if categories else "暂无",
        "revisit_rate": round(revisits / len(items), 3) if items else 0,
    }


def place_atlas(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("place_id") or f"{row.get('poi_name')}:{row.get('latitude')}:{row.get('longitude')}")
        item = grouped.setdefault(
            key,
            {
                "place_id": row.get("place_id"),
                "name": row.get("place_name") or row.get("poi_name"),
                "category": row.get("category") or row.get("poi_type"),
                "city": row.get("place_city") or "",
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "visit_count": 0,
                "last_visited_at": row.get("visited_at") or row.get("created_at"),
                "tags": set(),
            },
        )
        item["visit_count"] += 1
        item["last_visited_at"] = max(str(item["last_visited_at"]), str(row.get("visited_at") or row.get("created_at")))
        item["tags"].update(row.get("tags_list") or [])
    atlas = []
    for item in grouped.values():
        atlas.append({**item, "tags": sorted(item["tags"])})
    return sorted(atlas, key=lambda item: (-int(item["visit_count"]), str(item["last_visited_at"])), reverse=False)


def heatmap_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = str(row.get("visited_at") or row.get("created_at") or "")
        if value:
            counts[value[:10]] += 1
    return [{"date": key, "count": value} for key, value in sorted(counts.items())]


def monthly_stats(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = str(row.get("visited_at") or row.get("created_at") or "")
        if value:
            counts[value[:7]] += 1
    return [{"month": key, "count": value} for key, value in sorted(counts.items())]


def category_distribution(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row.get("category") or row.get("poi_type") or "其他" for row in rows)
    return [{"category": key, "count": value} for key, value in counts.most_common()]


def city_options(conn: sqlite3.Connection, user_id: int) -> list[str]:
    ensure_footprint_schema(conn, seed_demo=False)
    rows = conn.execute(
        """
        SELECT DISTINCT p.city
        FROM checkins c
        LEFT JOIN places p ON p.id = c.place_id
        WHERE c.user_id=? AND TRIM(COALESCE(p.city, '')) != ''
        ORDER BY p.city
        """,
        (int(user_id),),
    ).fetchall()
    return ["全部"] + [str(row["city"]) for row in rows]


def tag_options(rows: Iterable[dict[str, Any]]) -> list[str]:
    tags = sorted({tag for row in rows for tag in row.get("tags_list", [])})
    return [""] + tags


def update_checkin(
    conn: sqlite3.Connection,
    *,
    checkin_id: int,
    user_id: int,
    activity: str,
    privacy: str,
    mood: str,
    notes: str,
    tags: Iterable[str],
) -> bool:
    ensure_footprint_schema(conn, seed_demo=False)
    tags_json = serialize_tags(tags)
    cur = conn.execute(
        """
        UPDATE checkins
        SET activity=?, privacy=?, mood=?, notes=?, tags=?, tags_json=?, feed_public=CASE WHEN ? IN ('私密', '仅自己可见') THEN 0 ELSE feed_public END
        WHERE id=? AND user_id=?
        """,
        (activity.strip(), privacy, mood.strip(), notes.strip(), tags_json, tags_json, privacy, int(checkin_id), int(user_id)),
    )
    return cur.rowcount == 1


def delete_checkin(conn: sqlite3.Connection, *, checkin_id: int, user_id: int) -> bool:
    ensure_footprint_schema(conn, seed_demo=False)
    cur = conn.execute("DELETE FROM checkins WHERE id=? AND user_id=?", (int(checkin_id), int(user_id)))
    return cur.rowcount == 1


def export_csv(rows: Iterable[dict[str, Any]]) -> str:
    items = list(rows)
    output = io.StringIO()
    fieldnames = [
        "id",
        "poi_name",
        "poi_type",
        "activity",
        "privacy",
        "visited_at",
        "duration_minutes",
        "mood",
        "notes",
        "tags",
        "latitude",
        "longitude",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in items:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return output.getvalue()


def export_json(rows: Iterable[dict[str, Any]]) -> str:
    safe_rows = []
    for row in rows:
        safe = dict(row)
        safe["tags"] = row.get("tags_list", [])
        safe_rows.append(safe)
    return json.dumps(safe_rows, ensure_ascii=False, indent=2, default=str)


def public_feed_payload_from_checkin(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("privacy") in PRIVACY_PRIVATE:
        return None
    return {
        "source": "地点打卡",
        "place": row.get("poi_name"),
        "category": row.get("category") or row.get("poi_type"),
        "activity": row.get("activity"),
        "mood": row.get("mood"),
        "tags": row.get("tags_list") or [],
        "visited_at": row.get("visited_at"),
    }


def valid_map_footprints(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return valid_points(rows)


DEMO_FOOTPRINTS = [
    (1, "南京大学仙林校区图书馆", "学习", "南京", 32.1192, 118.9597, "复习 AI 项目", "专注", ["学习", "AI"], -28),
    (1, "先锋书店五台山店", "学习", "南京", 32.0565, 118.7726, "整理课堂笔记", "平静", ["阅读", "自习"], -20),
    (1, "鱼嘴湿地公园", "户外", "南京", 31.9692, 118.7057, "傍晚散步", "放松", ["散步", "户外"], -13),
    (1, "M Stand 新街口", "咖啡", "南京", 32.0413, 118.7848, "写小组作业", "投入", ["咖啡", "作业"], -7),
    (1, "江苏省美术馆", "展览", "南京", 32.0451, 118.7954, "看毕业展", "愉快", ["展览", "艺术"], -3),
    (1, "玄武湖公园", "运动", "南京", 32.0747, 118.8011, "慢跑 5 公里", "轻松", ["跑步", "运动"], -1),
    (2, "南京大学仙林校区图书馆", "学习", "南京", 32.1192, 118.9597, "读论文", "专注", ["RAG", "论文"], -27),
    (2, "玄武湖公园", "运动", "南京", 32.0747, 118.8011, "夜跑", "轻松", ["跑步"], -18),
    (2, "德基广场", "生活", "南京", 32.0450, 118.7846, "朋友聚餐", "开心", ["聚餐"], -9),
    (3, "上海外滩", "户外", "上海", 31.2400, 121.4900, "城市漫步", "放松", ["散步", "摄影"], -24),
    (3, "上海图书馆东馆", "学习", "上海", 31.2037, 121.5473, "产品资料调研", "投入", ["学习", "产品"], -17),
    (3, "Manner Coffee 陆家嘴", "咖啡", "上海", 31.2382, 121.5017, "改 Demo 文案", "专注", ["咖啡", "产品"], -6),
    (4, "紫金山风景区", "户外", "南京", 32.0617, 118.8485, "徒步拍照", "放松", ["摄影", "徒步"], -23),
    (4, "南京奥体中心", "运动", "南京", 32.0090, 118.7269, "羽毛球", "轻松", ["运动"], -12),
    (4, "金陵美术馆", "展览", "南京", 32.0214, 118.7847, "看展", "愉快", ["展览"], -5),
    (5, "浙江大学紫金港图书馆", "学习", "杭州", 30.3088, 120.0868, "刷算法题", "专注", ["算法", "面试"], -26),
    (5, "西湖苏堤", "户外", "杭州", 30.2436, 120.1468, "散步复盘", "平静", ["西湖", "散步"], -15),
    (5, "杭州未来科技城咖啡馆", "咖啡", "杭州", 30.2796, 120.0206, "准备面试", "投入", ["咖啡", "面试"], -2),
    (6, "仙林中心咖啡店", "咖啡", "南京", 32.1050, 118.9120, "画产品原型", "投入", ["设计", "原型"], -22),
    (6, "南京博物院", "展览", "南京", 32.0501, 118.8301, "看展找灵感", "愉快", ["展览", "设计"], -10),
    (7, "苏州金鸡湖", "户外", "苏州", 31.3205, 120.7069, "湖边慢走", "平静", ["散步", "户外"], -25),
    (7, "苏州奥体中心", "运动", "苏州", 31.3055, 120.7484, "力量训练", "充实", ["健身"], -8),
    (8, "上海当代艺术博物馆", "展览", "上海", 31.2404, 121.4812, "看新展", "愉快", ["展览", "艺术"], -21),
    (8, "人民广场桌游店", "生活", "上海", 31.2304, 121.4737, "桌游局", "开心", ["桌游", "社交"], -11),
    (9, "张江人工智能岛", "学习", "上海", 31.2071, 121.6150, "开源项目讨论", "兴奋", ["开源", "AI"], -19),
    (9, "世纪公园", "运动", "上海", 31.2146, 121.5504, "晨跑", "轻松", ["跑步"], -4),
]


def seed_demo_footprints(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) AS n FROM checkins").fetchone()["n"]
    if int(existing or 0) >= 25:
        return
    base = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
    for user_id, name, category, city, lat, lon, activity, mood, tags, offset in DEMO_FOOTPRINTS:
        visited_at = (base + timedelta(days=offset)).isoformat(timespec="minutes")
        place_id = ensure_place(
            conn,
            name=name,
            category=category,
            latitude=lat,
            longitude=lon,
            city=city,
            address=f"{city} · {name}",
            source="demo",
        )
        exists = conn.execute(
            """
            SELECT id FROM checkins
            WHERE user_id=? AND poi_name=? AND date(COALESCE(visited_at, created_at))=date(?)
            """,
            (user_id, name, visited_at),
        ).fetchone()
        if exists:
            continue
        add_checkin(
            conn,
            user_id=user_id,
            poi_name=name,
            poi_type=category,
            longitude=lon,
            latitude=lat,
            activity=activity,
            privacy="公开",
            tags=tags,
            visited_at=visited_at,
            duration_minutes=90,
            mood=mood,
            notes=f"{name} 的课堂演示足迹。",
            feed_public=True,
            verified=1,
            place_id=place_id,
            source="demo",
        )
