
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    import folium
    from folium.plugins import MarkerCluster
    from streamlit_folium import st_folium
except ImportError:
    folium = None
    MarkerCluster = None
    st_folium = None
    FOLIUM_IMPORT_ERROR = "folium 或 streamlit-folium 未安装在当前 Streamlit 运行环境。"
else:
    FOLIUM_IMPORT_ERROR = ""

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.auth_service import (
    can_enter_main_app,
    clear_auth_session,
    is_logged_in,
    save_auth_session,
    sign_in_with_password,
    sign_out,
    sign_up_with_password,
    validate_login_input,
    validate_registration_input,
)
from src.config import get_supabase_config
from src.demo_social_service import (
    ensure_friend_request_schema,
    get_friend_request_summary,
    get_public_feed,
    parse_tags as parse_json_tags,
    send_friend_request,
    update_friend_request_status,
    valid_map_points,
)
from src.footprint_service import add_checkin, combine_datetime, compute_duration_minutes, ensure_footprint_schema
from src.map_service import GeocodeResult, search_place
from src.profile_cache_service import (
    ensure_profile_cache_schema,
    fetch_cached_profile,
    save_cached_profile,
)
from src.profile_service import fetch_current_profile, update_onboarding_profile
from src.supabase_client import create_supabase_client, restore_supabase_session
from views.footprint import render_footprint_page

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "data" / "resonance.db"
AMAP_KEY = os.getenv("AMAP_WEB_SERVICE_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

st.set_page_config(
    page_title="共振 Resonance",
    page_icon="🪐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --ink: #102033;
        --muted: #64748b;
        --line: #e5e7eb;
        --paper: #ffffff;
        --soft: #f7fafc;
        --blue: #2563eb;
        --green: #059669;
        --orange: #f97316;
        --purple: #7c3aed;
    }
    html, body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(180deg, #f8fafc 0%, #eef6ff 42%, #f8fafc 100%);
        color: var(--ink);
    }
    .block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1240px;}
    [data-testid="stSidebar"] {background: #102033;}
    [data-testid="stSidebar"] * {color: #f8fafc;}
    [data-testid="stSidebar"] .stButton button {
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,.24);
        background: rgba(255,255,255,.08);
    }
    .hero {
        padding: 28px 30px;
        border: 1px solid rgba(37, 99, 235, .16);
        border-radius: 14px;
        background:
            linear-gradient(135deg, rgba(37,99,235,.14), rgba(5,150,105,.10)),
            #ffffff;
        box-shadow: 0 16px 42px rgba(15, 23, 42, 0.08);
        margin-bottom: 16px;
    }
    .hero h1 {font-size: 2.05rem; margin: 0 0 8px 0; letter-spacing: 0;}
    .hero p {font-size: 1rem; color: #475569; margin: 0; max-width: 760px;}
    .card {
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 16px;
        background: rgba(255,255,255,.96);
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        margin-bottom: 12px;
    }
    .activity-card {
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 15px 16px;
        background: #ffffff;
        margin-bottom: 12px;
        box-shadow: 0 5px 18px rgba(15, 23, 42, 0.05);
    }
    .activity-meta {
        color: var(--muted);
        font-size: .88rem;
        margin-top: 6px;
    }
    .tag {
        display: inline-block;
        padding: 3px 9px;
        border-radius: 999px;
        background: #e0f2fe;
        color: #075985;
        font-size: 0.8rem;
        margin: 2px 5px 2px 0;
    }
    .status-pill {
        display: inline-block;
        padding: 4px 9px;
        border-radius: 999px;
        background: #ecfdf5;
        color: #047857;
        font-size: .78rem;
        font-weight: 650;
    }
    .map-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 8px 0 14px 0;
    }
    .legend-item {
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 5px 10px;
        background: #ffffff;
        color: #334155;
        font-size: .82rem;
    }
    .privacy {
        padding: 9px 12px;
        background: #f8fafc;
        border-left: 4px solid #64748b;
        border-radius: 8px;
        color: #475569;
        font-size: .9rem;
    }
    .match-score {
        font-size: 2rem;
        font-weight: 750;
        letter-spacing: 0;
    }
    .muted {color: #64748b;}
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 12px 14px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------- Database ---------------------------

def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            nickname TEXT NOT NULL,
            city TEXT NOT NULL,
            bio TEXT NOT NULL,
            social_goal TEXT NOT NULL,
            avatar TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS life_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            privacy TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            mood TEXT NOT NULL,
            social_intent TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

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
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )
    ensure_friend_request_schema(conn)
    ensure_profile_cache_schema(conn)
    ensure_footprint_schema(conn, seed_demo=False)
    count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count == 0:
        seed_demo_data(conn)
    ensure_footprint_schema(conn, seed_demo=True)
    conn.commit()
    conn.close()


def seed_demo_data(conn: sqlite3.Connection) -> None:
    users = [
        (1, "小原", "南京", "环境专业转 AI，最近在做视觉与 Agent 项目。", "找学习搭子和项目伙伴", "🧑🏻‍💻"),
        (2, "林栖", "南京", "做自然语言处理，习惯晚间学习，也喜欢慢跑。", "找能长期共学的伙伴", "👩🏻‍💻"),
        (3, "阿拓", "上海", "独立开发者，正在做 AI 工具产品。", "找产品与技术合作者", "🧑🏻‍🚀"),
        (4, "木也", "南京", "摄影、徒步、城市漫游，周末喜欢户外。", "找周末活动伙伴", "📷"),
        (5, "迟青", "杭州", "研究生，准备算法实习，关注多模态与 RAG。", "找面试互助搭子", "🧠"),
        (6, "南星", "南京", "产品设计学生，常在咖啡馆画原型。", "找开发搭档参加比赛", "🎨"),
        (7, "川屿", "苏州", "健身与阅读爱好者，正在建立规律作息。", "找互相监督的习惯伙伴", "🏃"),
        (8, "一白", "南京", "喜欢桌游、展览和小型线下活动。", "拓展稳定的小圈子", "🎲"),
        (9, "晞禾", "上海", "数据分析师，周末做开源项目。", "找开源协作伙伴", "📊"),
    ]
    now = datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO users(id,nickname,city,bio,social_goal,avatar,created_at) VALUES (?,?,?,?,?,?,?)",
        [(*u, now) for u in users],
    )

    logs = [
        (1, "今天继续做遥感图像分类，模型终于跑通了。晚上想复习一下 Agent 工具调用。", ["AI", "计算机视觉", "Agent", "学习"], "有成就感", "寻找项目伙伴"),
        (1, "在图书馆整理三天项目方案，希望找一个执行力强的人一起做。", ["项目", "图书馆", "共学"], "专注", "寻找共学搭子"),
        (2, "晚上看完了 RAG 评估的文章，准备把检索模块接到课程项目里。", ["RAG", "NLP", "学习"], "专注", "寻找共学搭子"),
        (2, "玄武湖慢跑五公里，最近想恢复规律运动。", ["跑步", "运动", "规律生活"], "轻松", "寻找运动伙伴"),
        (3, "给个人 AI 工具加了订阅页，下一步想找人一起打磨用户体验。", ["AI产品", "独立开发", "创业"], "兴奋", "寻找产品合作者"),
        (4, "周末去了紫金山拍照，想约人下次一起走一条轻量徒步路线。", ["摄影", "徒步", "户外"], "放松", "寻找活动伙伴"),
        (5, "复盘了一轮算法面试题，发现多模态部分还需要补课。", ["算法面试", "多模态", "学习"], "略焦虑", "寻找面试搭子"),
        (6, "在咖啡馆画了一个生活记录 App 的原型，希望认识会前端的人。", ["产品设计", "App", "前端"], "投入", "寻找开发搭档"),
        (7, "连续早起第六天，晚上读了半小时非虚构。", ["早起", "阅读", "习惯"], "平静", "寻找监督伙伴"),
        (8, "看了新展，晚上和朋友玩了桌游。更喜欢四五个人的小活动。", ["展览", "桌游", "小型社交"], "愉快", "寻找兴趣朋友"),
        (9, "给开源数据工具提了一个 PR，周末计划继续完善文档。", ["开源", "数据分析", "编程"], "满足", "寻找开源伙伴"),
    ]
    conn.executemany(
        """
        INSERT INTO life_logs(user_id,content,privacy,tags_json,mood,social_intent,created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        [
            (uid, content, "仅用于匹配", json.dumps(tags, ensure_ascii=False), mood, intent, now)
            for uid, content, tags, mood, intent in logs
        ],
    )

    checkins = [
        (1, "南京大学仙林校区图书馆", "图书馆", 118.9597, 32.1192, "学习 AI 项目", ["学习", "AI"], 1),
        (2, "南京大学仙林校区图书馆", "图书馆", 118.9597, 32.1192, "阅读论文", ["阅读", "RAG"], 1),
        (2, "玄武湖公园", "公园", 118.8011, 32.0747, "慢跑", ["跑步", "运动"], 1),
        (4, "紫金山风景区", "景区", 118.8485, 32.0617, "徒步摄影", ["摄影", "徒步"], 1),
        (6, "仙林中心咖啡店", "咖啡馆", 118.9120, 32.1050, "画产品原型", ["产品设计", "App"], 0),
        (8, "江苏省美术馆", "展馆", 118.7954, 32.0451, "看展", ["展览", "艺术"], 1),
    ]
    conn.executemany(
        """
        INSERT INTO checkins(user_id,poi_name,poi_type,longitude,latitude,activity,privacy,tags_json,verified,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (uid, name, ptype, lon, lat, activity, "仅用于匹配",
             json.dumps(tags, ensure_ascii=False), verified, now)
            for uid, name, ptype, lon, lat, activity, tags, verified in checkins
        ],
    )


def query_df(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def get_user(user_id: int) -> dict[str, Any]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row)


# --------------------------- AI / local analysis ---------------------------

KEYWORD_TAGS = {
    "AI": ["ai", "人工智能", "大模型", "llm"],
    "Agent": ["agent", "智能体", "工具调用"],
    "RAG": ["rag", "检索增强", "知识库"],
    "计算机视觉": ["视觉", "图像", "遥感", "检测", "分割"],
    "编程": ["python", "代码", "开发", "前端", "后端", "编程"],
    "项目": ["项目", "比赛", "竞赛", "作品"],
    "学习": ["学习", "论文", "课程", "复习", "面试"],
    "跑步": ["跑步", "慢跑", "五公里"],
    "健身": ["健身", "力量训练", "运动"],
    "户外": ["徒步", "爬山", "公园", "户外"],
    "摄影": ["摄影", "拍照", "相机"],
    "阅读": ["阅读", "读书", "看书"],
    "产品设计": ["产品", "原型", "用户体验", "设计"],
    "开源": ["开源", "github", "pull request", "pr"],
    "展览": ["展览", "看展", "美术馆", "博物馆"],
    "桌游": ["桌游", "剧本杀"],
    "规律生活": ["早起", "作息", "规律", "打卡"],
}

MOOD_RULES = {
    "有成就感": ["终于", "跑通", "完成", "成功", "搞定"],
    "兴奋": ["期待", "兴奋", "太好了", "很开心"],
    "放松": ["散步", "慢跑", "徒步", "放松", "轻松"],
    "焦虑": ["焦虑", "担心", "来不及", "压力"],
    "疲惫": ["累", "疲惫", "熬夜"],
    "专注": ["专注", "学习", "整理", "复习", "写代码"],
}

SOCIAL_RULES = {
    "寻找项目伙伴": ["项目伙伴", "一起做项目", "开发搭档", "合作者"],
    "寻找共学搭子": ["学习搭子", "共学", "一起学习", "互相监督"],
    "寻找运动伙伴": ["跑步搭子", "运动伙伴", "一起跑", "健身搭子"],
    "寻找活动伙伴": ["一起去", "约人", "活动伙伴", "同行"],
    "暂不匹配": ["不想社交", "独处", "暂不匹配"],
}


def local_analyze_text(text: str) -> dict[str, Any]:
    lowered = text.lower()
    tags = []
    for tag, words in KEYWORD_TAGS.items():
        if any(word.lower() in lowered for word in words):
            tags.append(tag)
    if not tags:
        tags = ["日常"]

    mood = "平静"
    for name, words in MOOD_RULES.items():
        if any(word in text for word in words):
            mood = name
            break

    social_intent = "开放认识新朋友"
    for intent, words in SOCIAL_RULES.items():
        if any(word in text for word in words):
            social_intent = intent
            break

    return {
        "tags": tags[:8],
        "mood": mood,
        "social_intent": social_intent,
        "summary": text[:60] + ("…" if len(text) > 60 else ""),
        "engine": "本地规则",
    }


def analyze_text(text: str) -> dict[str, Any]:
    if not DEEPSEEK_API_KEY or OpenAI is None:
        return local_analyze_text(text)

    prompt = f"""
你是生活记录结构化助手。仅根据用户文本提取低敏感度、适合朋友匹配的信息。
不得推断政治、宗教、疾病、性取向、精确住址等敏感属性。

输出严格 JSON：
{{
  "tags": ["最多8个简短标签"],
  "mood": "平静/专注/放松/兴奋/疲惫/焦虑/其他",
  "social_intent": "寻找项目伙伴/寻找共学搭子/寻找运动伙伴/寻找活动伙伴/开放认识新朋友/暂不匹配",
  "summary": "不超过45字的中性摘要"
}}

用户文本：
{text}
"""
    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "你只输出合法 JSON，不要添加 Markdown。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            stream=False,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        return {
            "tags": [str(x)[:20] for x in data.get("tags", [])][:8] or ["日常"],
            "mood": str(data.get("mood", "平静"))[:20],
            "social_intent": str(data.get("social_intent", "开放认识新朋友"))[:30],
            "summary": str(data.get("summary", text[:45]))[:60],
            "engine": f"DeepSeek · {DEEPSEEK_MODEL}",
        }
    except Exception as exc:
        fallback = local_analyze_text(text)
        fallback["engine"] = f"本地规则（API失败：{type(exc).__name__}）"
        return fallback


# --------------------------- Map ---------------------------

DEMO_POIS = [
    {"name": "南京大学仙林校区图书馆", "type": "图书馆", "location": "118.959700,32.119200", "distance": "120"},
    {"name": "仙林湖公园", "type": "公园", "location": "118.904800,32.131500", "distance": "720"},
    {"name": "大学城共享自习室", "type": "自习室", "location": "118.956200,32.116900", "distance": "350"},
    {"name": "仙林中心咖啡店", "type": "咖啡馆", "location": "118.952500,32.112900", "distance": "560"},
    {"name": "羊山公园", "type": "公园", "location": "118.935400,32.115800", "distance": "980"},
]


def search_nearby_pois(longitude: float, latitude: float, keyword: str, radius: int) -> tuple[list[dict], str]:
    if not AMAP_KEY:
        return DEMO_POIS, "演示数据（配置高德 Key 后自动切换真实 POI）"

    params = {
        "key": AMAP_KEY,
        "location": f"{longitude:.6f},{latitude:.6f}",
        "radius": radius,
        "keywords": keyword,
        "offset": 20,
        "page": 1,
        "extensions": "base",
        "output": "JSON",
    }
    try:
        response = requests.get(
            "https://restapi.amap.com/v3/place/around",
            params=params,
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("status")) != "1":
            raise RuntimeError(payload.get("info", "高德 API 返回失败"))
        pois = payload.get("pois", [])
        return pois, "高德地图实时 POI"
    except Exception as exc:
        return DEMO_POIS, f"高德 API 暂不可用，已切换演示数据（{type(exc).__name__}）"


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


# --------------------------- Matching ---------------------------

def parse_tags(value: str) -> list[str]:
    try:
        data = json.loads(value)
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def collect_user_features(user_id: int) -> dict[str, Any]:
    user = get_user(user_id)
    logs = query_df(
        "SELECT content,tags_json,social_intent,created_at FROM life_logs WHERE user_id=? AND privacy!='私密' ORDER BY created_at DESC LIMIT 20",
        (user_id,),
    )
    checkins = query_df(
        "SELECT poi_name,poi_type,activity,tags_json,created_at FROM checkins WHERE user_id=? AND privacy!='私密' ORDER BY created_at DESC LIMIT 20",
        (user_id,),
    )

    tags: list[str] = []
    texts = [user["bio"], user["social_goal"]]
    intents = [user["social_goal"]]
    poi_types: list[str] = []

    for _, row in logs.iterrows():
        texts.append(str(row["content"]))
        tags.extend(parse_tags(str(row["tags_json"])))
        intents.append(str(row["social_intent"]))

    for _, row in checkins.iterrows():
        texts.extend([str(row["poi_name"]), str(row["activity"])])
        poi_types.append(str(row["poi_type"]))
        tags.extend(parse_tags(str(row["tags_json"])))

    return {
        "user": user,
        "text": " ".join(texts + tags + intents + poi_types),
        "tags": sorted(set(tags)),
        "intents": sorted(set(intents)),
        "poi_types": sorted(set(poi_types)),
    }


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def calculate_matches(current_user_id: int) -> list[dict[str, Any]]:
    users = query_df("SELECT id FROM users ORDER BY id")
    ids = [int(x) for x in users["id"].tolist()]
    feature_map = {uid: collect_user_features(uid) for uid in ids}
    corpus = [feature_map[uid]["text"] for uid in ids]

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
    matrix = vectorizer.fit_transform(corpus)
    similarities = cosine_similarity(matrix)

    current_idx = ids.index(current_user_id)
    current = feature_map[current_user_id]
    results = []

    for idx, uid in enumerate(ids):
        if uid == current_user_id:
            continue
        other = feature_map[uid]
        semantic = float(similarities[current_idx, idx])
        tag_overlap = jaccard(set(current["tags"]), set(other["tags"]))
        intent_overlap = jaccard(set(current["intents"]), set(other["intents"]))
        place_overlap = jaccard(set(current["poi_types"]), set(other["poi_types"]))
        same_city = 1.0 if current["user"]["city"] == other["user"]["city"] else 0.35

        score = 100 * (
            0.38 * semantic
            + 0.24 * tag_overlap
            + 0.18 * intent_overlap
            + 0.10 * place_overlap
            + 0.10 * same_city
        )
        score = max(20.0, min(96.0, score + 28.0))

        common_tags = sorted(set(current["tags"]) & set(other["tags"]))
        common_places = sorted(set(current["poi_types"]) & set(other["poi_types"]))
        reasons = []
        if common_tags:
            reasons.append("共同关注：" + "、".join(common_tags[:4]))
        if common_places:
            reasons.append("常去相似场所：" + "、".join(common_places[:3]))
        if current["user"]["city"] == other["user"]["city"]:
            reasons.append(f"都在{current['user']['city']}活动")
        if not reasons:
            reasons.append("近期生活语义和社交目标存在一定相似性")

        complementary = []
        other_unique = [t for t in other["tags"] if t not in current["tags"]]
        if other_unique:
            complementary.append("对方还擅长/关注：" + "、".join(other_unique[:3]))
        else:
            complementary.append("生活兴趣较为接近，适合从共同话题开始")

        icebreaker_topic = common_tags[0] if common_tags else "最近正在做的事"
        results.append(
            {
                "user_id": uid,
                "nickname": other["user"]["nickname"],
                "avatar": other["user"]["avatar"],
                "city": other["user"]["city"],
                "bio": other["user"]["bio"],
                "goal": other["user"]["social_goal"],
                "score": round(score),
                "reasons": reasons,
                "complementary": complementary,
                "icebreaker": f"可以从“{icebreaker_topic}”聊起：你最近在这方面遇到的最大问题是什么？",
                "tags": other["tags"][:8],
            }
        )

    return sorted(results, key=lambda x: x["score"], reverse=True)


# --------------------------- Rendering helpers ---------------------------

def render_tags(tags: list[str]) -> None:
    if not tags:
        st.caption("暂无标签")
        return
    html = "".join(f'<span class="tag">{tag}</span>' for tag in tags)
    st.markdown(html, unsafe_allow_html=True)


def privacy_help() -> None:
    st.markdown(
        """
        <div class="privacy">
        <b>隐私默认原则：</b>“私密”记录不参与匹配；“仅用于匹配”只提取抽象标签，不向其他用户展示原文；
        “公开”才会显示在公开动态中。原型不会公开实时精确位置。
        </div>
        """,
        unsafe_allow_html=True,
    )


def recent_logs(user_id: int, limit: int = 5) -> pd.DataFrame:
    return query_df(
        """
        SELECT content AS 记录, mood AS 状态, social_intent AS 社交意愿,
               privacy AS 权限, created_at AS 时间
        FROM life_logs WHERE user_id=? ORDER BY created_at DESC LIMIT ?
        """,
        (user_id, limit),
    )


def query_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def render_activity_card(item: dict[str, Any]) -> None:
    tags = "".join(f'<span class="tag">{tag}</span>' for tag in item.get("tags", [])[:5])
    st.markdown(
        f"""
        <div class="activity-card">
            <div><b>{item.get('avatar', '')} {item.get('nickname', '')}</b>
                <span class="muted"> · {item.get('city', '')} · {item.get('source', '')}</span>
            </div>
            <div style="margin-top:8px">{item.get('content', '')}</div>
            <div style="margin-top:8px">{tags}</div>
            <div class="activity-meta">{item.get('mood', '')} · {item.get('social_intent', '')} · {item.get('created_at', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_demo_map_points(user_id: int, type_filter: str = "全部") -> list[dict[str, Any]]:
    checkin_rows = query_rows(
        """
        SELECT c.id, c.user_id, u.nickname, u.avatar, c.poi_name, c.poi_type,
               c.longitude, c.latitude, c.activity, c.tags_json, c.verified, c.created_at
        FROM checkins c
        JOIN users u ON u.id = c.user_id
        WHERE c.privacy NOT IN ('私密', '绉佸瘑')
        ORDER BY c.created_at DESC
        """
    )
    points: list[dict[str, Any]] = []
    for row in checkin_rows:
        tags = parse_json_tags(str(row.get("tags_json", "")))
        kind = "我的打卡" if int(row["user_id"]) == user_id else "匹配用户常去"
        points.append(
            {
                "source": kind,
                "category": str(row.get("poi_type", "地点")),
                "name": row.get("poi_name"),
                "activity": row.get("activity"),
                "nickname": row.get("nickname"),
                "avatar": row.get("avatar"),
                "longitude": row.get("longitude"),
                "latitude": row.get("latitude"),
                "tags": tags,
                "verified": bool(row.get("verified")),
            }
        )

    for poi in DEMO_POIS:
        try:
            lon, lat = str(poi["location"]).split(",")
        except Exception:
            continue
        points.append(
            {
                "source": "推荐 POI",
                "category": poi.get("type", "地点"),
                "name": poi.get("name", "推荐地点"),
                "activity": f"距离约 {poi.get('distance', '?')} m",
                "nickname": "Resonance",
                "avatar": "◎",
                "longitude": lon,
                "latitude": lat,
                "tags": [poi.get("type", "地点")],
                "verified": False,
            }
        )

    valid_points = valid_map_points(points)
    if type_filter == "全部":
        return valid_points

    keywords = {
        "学习": ["学习", "图书馆", "自习", "RAG", "AI", "NLP"],
        "咖啡": ["咖啡"],
        "运动": ["跑步", "运动", "公园", "健身"],
        "展览": ["展览", "美术", "展馆"],
        "户外": ["户外", "徒步", "公园", "景区"],
    }.get(type_filter, [])

    def matches(point: dict[str, Any]) -> bool:
        text = " ".join(
            [
                str(point.get("category", "")),
                str(point.get("name", "")),
                str(point.get("activity", "")),
                " ".join(point.get("tags", [])),
            ]
        )
        return any(keyword in text for keyword in keywords)

    return [point for point in valid_points if matches(point)]


def create_explore_map(points: list[dict[str, Any]], search_result: GeocodeResult | None = None) -> Any:
    if search_result:
        center_lat = search_result.latitude
        center_lon = search_result.longitude
        zoom_start = 15
    else:
        center_lat = sum(point["latitude"] for point in points) / len(points) if points else 32.1192
        center_lon = sum(point["longitude"] for point in points) / len(points) if points else 118.9597
        zoom_start = 12
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap 免费底图", control=True).add_to(fmap)
    folium.TileLayer("CartoDB positron", name="浅色备用底图", control=True).add_to(fmap)
    marker_parent = MarkerCluster(name="地点") if MarkerCluster else fmap
    if MarkerCluster:
        marker_parent.add_to(fmap)

    colors = {"我的打卡": "blue", "匹配用户常去": "purple", "推荐 POI": "orange", "公开活动": "green"}
    for point in points:
        popup = folium.Popup(
            f"""
            <b>{point.get('name', '')}</b><br>
            {point.get('avatar', '')} {point.get('nickname', '')}<br>
            {point.get('activity', '')}<br>
            {' / '.join(point.get('tags', [])[:4])}<br>
            来源：{point.get('source', '')}
            """,
            max_width=280,
        )
        folium.Marker(
            location=[point["latitude"], point["longitude"]],
            tooltip=f"{point.get('source', '')} · {point.get('name', '')}",
            popup=popup,
            icon=folium.Icon(color=colors.get(point.get("source"), "green"), icon="info-sign"),
        ).add_to(marker_parent)

    if search_result:
        folium.Marker(
            location=[search_result.latitude, search_result.longitude],
            tooltip=f"搜索结果 · {search_result.category}",
            popup=folium.Popup(f"<b>{search_result.label}</b><br>搜索定位结果", max_width=320),
            icon=folium.Icon(color="red", icon="search"),
        ).add_to(fmap)

    folium.LayerControl().add_to(fmap)
    return fmap


def render_basic_streamlit_map(points: list[dict[str, Any]], search_result: GeocodeResult | None = None) -> None:
    map_df = pd.DataFrame(
        [
            {
                "lat": point["latitude"],
                "lon": point["longitude"],
                "地点": point.get("name", ""),
                "来源": point.get("source", ""),
                "活动": point.get("activity", ""),
            }
            for point in points
        ]
    )
    if search_result:
        map_df = pd.concat(
            [
                pd.DataFrame(
                    [
                        {
                            "lat": search_result.latitude,
                            "lon": search_result.longitude,
                            "地点": search_result.label,
                            "来源": "搜索结果",
                            "活动": search_result.category,
                        }
                    ]
                ),
                map_df,
            ],
            ignore_index=True,
        )
    st.map(map_df, latitude="lat", longitude="lon", size=60, color="#2563eb")
    st.caption("当前使用基础地图模式。安装 folium 和 streamlit-folium 后会自动切换为可点击弹窗地图。")


def search_local_map_points(query: str, points: list[dict[str, Any]]) -> list[GeocodeResult]:
    keyword = query.strip().lower()
    if not keyword:
        return []
    results: list[GeocodeResult] = []
    for point in points:
        haystack = " ".join(
            [
                str(point.get("name", "")),
                str(point.get("category", "")),
                str(point.get("activity", "")),
                str(point.get("source", "")),
                " ".join(point.get("tags", [])),
            ]
        ).lower()
        if keyword in haystack:
            results.append(
                GeocodeResult(
                    label=f"{point.get('name', '地点')} · {point.get('source', '本地点位')}",
                    latitude=float(point["latitude"]),
                    longitude=float(point["longitude"]),
                    category=str(point.get("category", "本地点位")),
                )
            )
    return results[:6]


def get_friend_request_rows(user_id: int, view: str) -> list[dict[str, Any]]:
    if view == "收到的申请":
        condition = "fr.receiver_id=? AND fr.status='pending'"
        params = (user_id,)
    elif view == "发出的申请":
        condition = "fr.requester_id=? AND fr.status='pending'"
        params = (user_id,)
    elif view == "已通过":
        condition = "(fr.requester_id=? OR fr.receiver_id=?) AND fr.status='accepted'"
        params = (user_id, user_id)
    else:
        condition = "(fr.requester_id=? OR fr.receiver_id=?) AND fr.status='rejected'"
        params = (user_id, user_id)

    return query_rows(
        f"""
        SELECT fr.*, rq.nickname AS requester_name, rq.avatar AS requester_avatar,
               rc.nickname AS receiver_name, rc.avatar AS receiver_avatar
        FROM friend_requests fr
        JOIN users rq ON rq.id = fr.requester_id
        JOIN users rc ON rc.id = fr.receiver_id
        WHERE {condition}
        ORDER BY fr.updated_at DESC
        """,
        params,
    )


# --------------------------- Pages ---------------------------

def page_home(user_id: int, current_profile: dict[str, Any] | None = None, auth_mode: str = "demo") -> None:
    user = get_user(user_id)
    if current_profile:
        user = {
            **user,
            "nickname": current_profile.get("nickname") or user["nickname"],
            "city": current_profile.get("city") or user["city"],
            "bio": current_profile.get("bio") or user["bio"],
            "social_goal": current_profile.get("social_goal") or user["social_goal"],
    }
    features = collect_user_features(user_id)
    matches = calculate_matches(user_id)
    conn = get_conn()
    try:
        feed = get_public_feed(conn, current_user_id=user_id, limit=4)
        friend_summary = get_friend_request_summary(conn, user_id)
    finally:
        conn.close()
    map_points = get_demo_map_points(user_id)

    st.markdown(
        f"""
        <div class="hero">
            <h1>{user['avatar']} 你好，{user['nickname']}</h1>
            <p>在地图上发现附近的学习、运动、展览和咖啡地点；用动态记录真实生活，再从共同场景里找到更自然的朋友连接。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if auth_mode == "supabase":
        st.info("当前账号资料来自 Supabase；地图、动态和好友申请仍是本地原型数据，用于交作业演示。")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("画像标签", len(features["tags"]))
    c2.metric("附近点位", len(map_points))
    c3.metric("待处理申请", friend_summary["incoming_pending"])
    c4.metric("最高匹配", f"{matches[0]['score']}%" if matches else "暂无")

    left, right = st.columns([1.35, 1])
    with left:
        st.subheader("最新动态")
        if not feed:
            st.info("还没有可展示的动态。")
        for item in feed:
            render_activity_card(item)
    with right:
        st.subheader("今日推荐")
        if matches:
            top = matches[0]
            st.markdown(
                f"""
                <div class="card">
                    <div style="font-size:2rem">{top['avatar']}</div>
                    <h3 style="margin:4px 0">{top['nickname']} · {top['city']}</h3>
                    <div class="match-score">{top['score']}%</div>
                    <p class="muted">{top['reasons'][0]}</p>
                    <span class="status-pill">适合从共同兴趣开启对话</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.subheader("附近地图预览")
        for point in map_points[:4]:
            st.markdown(
                f"""
                <div class="card">
                    <b>{point.get('name')}</b><br>
                    <span class="muted">{point.get('source')} · {point.get('activity')}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    return

    user = get_user(user_id)
    if current_profile:
        user = {
            **user,
            "nickname": current_profile.get("nickname") or user["nickname"],
            "city": current_profile.get("city") or user["city"],
            "bio": current_profile.get("bio") or user["bio"],
            "social_goal": current_profile.get("social_goal") or user["social_goal"],
        }
    features = collect_user_features(user_id)
    logs_count = int(query_df("SELECT COUNT(*) AS n FROM life_logs WHERE user_id=?", (user_id,)).iloc[0]["n"])
    check_count = int(query_df("SELECT COUNT(*) AS n FROM checkins WHERE user_id=?", (user_id,)).iloc[0]["n"])
    matches = calculate_matches(user_id)

    if auth_mode == "supabase":
        st.info("当前昵称和资料来自 Supabase profiles；生活记录、地点打卡和朋友匹配仍是待迁移的本地原型数据，不代表当前真实账号数据。")

    st.markdown(
        f"""
        <div class="hero">
            <h1>{user['avatar']} 你好，{user['nickname']}</h1>
            <p>记录真实生活，让系统基于长期状态和活动节奏推荐更合适的朋友。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("生活记录", logs_count)
    c2.metric("地点打卡", check_count)
    c3.metric("画像标签", len(features["tags"]))
    c4.metric("最高匹配", f"{matches[0]['score']}%" if matches else "—")

    left, right = st.columns([1.35, 1])
    with left:
        st.subheader("最近生活")
        df = recent_logs(user_id)
        if df.empty:
            st.info("还没有记录。先写下今天发生的事。")
        else:
            for _, row in df.iterrows():
                st.markdown(
                    f"""
                    <div class="card">
                    <b>{row['记录']}</b><br>
                    <span class="muted">{row['状态']} · {row['社交意愿']} · {row['权限']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with right:
        st.subheader("动态生活画像")
        st.write(user["bio"])
        render_tags(features["tags"])
        st.caption(f"当前目标：{user['social_goal']}")
        st.divider()
        st.subheader("今日推荐")
        if matches:
            top = matches[0]
            st.markdown(
                f"""
                <div class="card">
                    <div style="font-size:2rem">{top['avatar']}</div>
                    <b>{top['nickname']} · {top['city']}</b>
                    <div class="match-score">{top['score']}%</div>
                    <span class="muted">{top['reasons'][0]}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.subheader("最近打卡")
    checks = query_df(
        """
        SELECT poi_name AS 地点, poi_type AS 类型, activity AS 活动,
               CASE verified WHEN 1 THEN '已验证' ELSE '演示/未验证' END AS 状态,
               created_at AS 时间
        FROM checkins WHERE user_id=? ORDER BY created_at DESC LIMIT 8
        """,
        (user_id,),
    )
    if checks.empty:
        st.info("暂无打卡。")
    else:
        st.dataframe(checks, width="stretch", hide_index=True)


def page_explore_map(user_id: int, auth_mode: str = "demo") -> None:
    st.title("探索地图")
    st.caption("输入地点即可搜索定位 · OpenStreetMap 免费底图 · 不需要注册地图账号")
    if auth_mode == "supabase":
        st.info("Supabase 模式下地图仍使用演示点位，不会写入真实账号位置数据。")

    all_points = get_demo_map_points(user_id, "全部")

    with st.form("place_search_form"):
        search_cols = st.columns([4, 1])
        place_query = search_cols[0].text_input(
            "搜索地点",
            value=st.session_state.get("place_query", ""),
            placeholder="例如：南京大学仙林校区、上海外滩、北京故宫",
        )
        submitted = search_cols[1].form_submit_button("搜索", type="primary", width="stretch")

    if submitted:
        st.session_state["place_query"] = place_query.strip()
        if not place_query.strip():
            st.warning("请输入要搜索的地点。")
            st.session_state["place_search_results"] = []
        else:
            local_results = search_local_map_points(place_query, all_points)
            with st.spinner("正在搜索地点..."):
                try:
                    remote_results = search_place(place_query, limit=6)
                except Exception:
                    remote_results = []
                    if not local_results:
                        st.error("地点搜索暂时不可用，请稍后再试，或换一个更具体的关键词。")
            st.session_state["place_search_results"] = local_results + remote_results

    search_results = st.session_state.get("place_search_results", [])
    selected_search_result: GeocodeResult | None = None
    if search_results:
        labels = [f"{idx + 1}. {result.label}" for idx, result in enumerate(search_results)]
        selected_label = st.selectbox("选择搜索结果", labels)
        selected_search_result = search_results[labels.index(selected_label)]
        st.success(f"已定位：{selected_search_result.label}")

    filters = st.columns([1, 1, 2])
    type_filter = filters[0].selectbox("地点类型", ["全部", "学习", "咖啡", "运动", "展览", "户外"])
    show_table = filters[1].toggle("显示点位列表", value=True)
    filters[2].markdown(
        """
        <div class="map-legend">
            <span class="legend-item">蓝色：我的打卡</span>
            <span class="legend-item">紫色：匹配用户常去</span>
            <span class="legend-item">橙色：推荐 POI</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    points = get_demo_map_points(user_id, type_filter)
    if not points:
        st.warning("当前筛选下没有可展示的地图点位。")
        return

    if folium is None or st_folium is None:
        st.warning(f"{FOLIUM_IMPORT_ERROR} 已自动切换到基础地图模式。")
        render_basic_streamlit_map(points, selected_search_result)
    else:
        fmap = create_explore_map(points, selected_search_result)
        try:
            st_folium(fmap, height=560, returned_objects=[], use_container_width=True)
        except TypeError:
            st_folium(fmap, height=560, returned_objects=[])
        except Exception:
            st.warning("交互地图组件暂时没有加载成功，已自动切换到基础地图模式。")
            render_basic_streamlit_map(points, selected_search_result)

    if show_table:
        rows = [
            {
                "来源": point.get("source"),
                "地点": point.get("name"),
                "活动": point.get("activity"),
                "用户": point.get("nickname"),
                "类型": point.get("category"),
            }
            for point in points
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def page_feed(user_id: int, auth_mode: str = "demo") -> None:
    st.title("动态")
    st.caption("展示非私密的生活记录和地点打卡，用于交作业演示社交发现体验。")
    if auth_mode == "supabase":
        st.info("动态流仍来自本地 SQLite 原型数据，暂未迁移到 Supabase。")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    source = c1.selectbox("类型", ["全部", "生活记录", "地点打卡"])
    same_city = c2.checkbox("同城")
    limit = c3.selectbox("数量", [10, 20, 50], index=1)
    keyword = c4.text_input("搜索关键词 / 标签", placeholder="AI、跑步、咖啡、展览...")

    conn = get_conn()
    try:
        items = get_public_feed(
            conn,
            current_user_id=user_id,
            source=source,
            same_city_only=same_city,
            query=keyword,
            limit=int(limit),
        )
    finally:
        conn.close()

    if not items:
        st.warning("当前条件下没有动态。")
        return
    for item in items:
        render_activity_card(item)


def page_friend_requests(user_id: int, auth_mode: str = "demo") -> None:
    st.title("好友申请")
    st.caption("本页是本地 SQLite 原型功能：可发送、接受、拒绝和取消好友申请。")
    if auth_mode == "supabase":
        st.info("好友申请暂未迁移到 Supabase，当前用于课堂演示。")

    conn = get_conn()
    try:
        summary = get_friend_request_summary(conn, user_id)
    finally:
        conn.close()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("收到待处理", summary["incoming_pending"])
    c2.metric("发出待处理", summary["outgoing_pending"])
    c3.metric("已通过", summary["accepted"])
    c4.metric("已拒绝", summary["rejected"])

    view = st.radio("申请箱", ["收到的申请", "发出的申请", "已通过", "已拒绝"], horizontal=True)
    rows = get_friend_request_rows(user_id, view)
    if not rows:
        st.info("这里暂时没有申请。")
        return

    for row in rows:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(
                    f"**{row['requester_avatar']} {row['requester_name']} → {row['receiver_avatar']} {row['receiver_name']}**"
                )
                st.write(row.get("message") or "想和你成为好友。")
                st.caption(f"状态：{row['status']} · {row['updated_at']}")
            with right:
                if view == "收到的申请":
                    if st.button("接受", key=f"accept_{row['id']}", width="stretch"):
                        conn = get_conn()
                        try:
                            ok, message = update_friend_request_status(conn, int(row["id"]), user_id, "accepted")
                        finally:
                            conn.close()
                        st.success(message) if ok else st.error(message)
                        st.rerun()
                    if st.button("拒绝", key=f"reject_{row['id']}", width="stretch"):
                        conn = get_conn()
                        try:
                            ok, message = update_friend_request_status(conn, int(row["id"]), user_id, "rejected")
                        finally:
                            conn.close()
                        st.success(message) if ok else st.error(message)
                        st.rerun()
                elif view == "发出的申请":
                    if st.button("取消", key=f"cancel_{row['id']}", width="stretch"):
                        conn = get_conn()
                        try:
                            ok, message = update_friend_request_status(conn, int(row["id"]), user_id, "cancelled")
                        finally:
                            conn.close()
                        st.success(message) if ok else st.error(message)
                        st.rerun()


def page_log(user_id: int) -> None:
    st.title("✍️ 记录生活")
    st.caption("不必写成正式日记。一两句话也能逐步形成动态画像。")
    privacy_help()

    with st.form("life_log_form", clear_on_submit=True):
        content = st.text_area(
            "今天发生了什么？",
            height=180,
            placeholder="例：晚上在图书馆学习 Agent，想找一个也在做 AI 项目的人一起交流。",
        )
        privacy = st.selectbox("记录权限", ["私密", "仅用于匹配", "公开"], index=1)
        submitted = st.form_submit_button("分析并保存", type="primary", width="stretch")

    if submitted:
        if len(content.strip()) < 5:
            st.error("记录至少写 5 个字。")
            return
        with st.spinner("正在提取低敏感度生活标签…"):
            analysis = analyze_text(content.strip())
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO life_logs(user_id,content,privacy,tags_json,mood,social_intent,created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                user_id,
                content.strip(),
                privacy,
                json.dumps(analysis["tags"], ensure_ascii=False),
                analysis["mood"],
                analysis["social_intent"],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        conn.close()

        st.success("记录已保存。")
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("**提取标签**")
            render_tags(analysis["tags"])
        with c2:
            st.markdown(f"**状态：** {analysis['mood']}")
            st.markdown(f"**社交意愿：** {analysis['social_intent']}")
            st.caption(f"分析引擎：{analysis['engine']}")

    st.divider()
    st.subheader("我的记录")
    df = recent_logs(user_id, 30)
    st.dataframe(df, width="stretch", hide_index=True)


def page_checkin(user_id: int) -> None:
    st.title("📍 地点打卡")
    st.caption("原型支持高德 Web 服务 API；未配置 Key 时使用演示 POI。")
    privacy_help()

    c1, c2 = st.columns(2)
    with c1:
        longitude = st.number_input("经度", value=118.959700, format="%.6f")
    with c2:
        latitude = st.number_input("纬度", value=32.119200, format="%.6f")

    c3, c4 = st.columns([2, 1])
    with c3:
        keyword = st.text_input("附近地点关键词（可空）", placeholder="图书馆 / 咖啡 / 公园")
    with c4:
        radius = st.selectbox("搜索半径", [500, 1000, 2000, 5000], index=1)

    if st.button("查询附近地点", type="primary", width="stretch"):
        pois, source = search_nearby_pois(longitude, latitude, keyword.strip(), radius)
        st.session_state["nearby_pois"] = pois
        st.session_state["poi_source"] = source

    pois = st.session_state.get("nearby_pois", DEMO_POIS)
    source = st.session_state.get("poi_source", "演示数据")

    map_rows = [{"lat": latitude, "lon": longitude, "name": "当前位置"}]
    for poi in pois:
        try:
            lon_str, lat_str = str(poi["location"]).split(",")
            map_rows.append({"lat": float(lat_str), "lon": float(lon_str), "name": poi.get("name", "POI")})
        except Exception:
            continue
    st.map(pd.DataFrame(map_rows), latitude="lat", longitude="lon", size=45)
    st.caption(f"地点来源：{source}")

    labels = []
    poi_map: dict[str, dict] = {}
    for idx, poi in enumerate(pois):
        label = f"{poi.get('name','未知地点')}｜{poi.get('type','其他')}｜约 {poi.get('distance','?')} m"
        labels.append(label)
        poi_map[label] = poi

    with st.form("checkin_form", clear_on_submit=False):
        selected = st.selectbox("选择打卡地点", labels)
        activity = st.text_input("正在做什么？", placeholder="学习 Python / 慢跑 / 看展")
        privacy = st.selectbox("打卡权限", ["私密", "仅用于匹配", "公开"], index=1)
        submitted = st.form_submit_button("保存打卡", type="primary", width="stretch")

    if submitted:
        if not activity.strip():
            st.error("请填写活动。")
            return
        poi = poi_map[selected]
        try:
            poi_lon, poi_lat = [float(x) for x in str(poi["location"]).split(",")]
        except Exception:
            st.error("地点坐标无效。")
            return

        distance = haversine_m(longitude, latitude, poi_lon, poi_lat)
        verified = int(distance <= 300 and bool(AMAP_KEY))
        analysis = analyze_text(f"{poi.get('name')} {poi.get('type')} {activity}")
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO checkins(user_id,poi_name,poi_type,longitude,latitude,activity,privacy,tags_json,verified,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                str(poi.get("name", "未知地点")),
                str(poi.get("type", "其他")),
                poi_lon,
                poi_lat,
                activity.strip(),
                privacy,
                json.dumps(analysis["tags"], ensure_ascii=False),
                verified,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        conn.close()
        if verified:
            st.success(f"打卡成功，设备坐标距地点约 {distance:.0f} 米，标记为“位置已验证”。")
        else:
            st.success("打卡成功。当前为演示/未验证状态。")
        render_tags(analysis["tags"])


def page_matches(user_id: int) -> None:
    st.title("🧭 朋友匹配")
    st.caption("匹配基于非私密记录的语义、兴趣标签、社交目标、场所类型和城市兼容度。")
    matches = calculate_matches(user_id)

    filters = st.columns(3)
    same_city_only = filters[0].checkbox("仅同城")
    min_score = filters[1].slider("最低匹配度", 20, 95, 55)
    limit = filters[2].selectbox("显示人数", [3, 5, 8], index=1)

    current = get_user(user_id)
    visible = [
        m for m in matches
        if m["score"] >= min_score and (not same_city_only or m["city"] == current["city"])
    ][:limit]

    if not visible:
        st.warning("当前筛选条件下没有匹配结果。")
        return

    for rank, match in enumerate(visible, start=1):
        with st.container(border=True):
            c1, c2, c3 = st.columns([0.7, 3.2, 1.1])
            c1.markdown(f"<div style='font-size:3rem'>{match['avatar']}</div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"### {rank}. {match['nickname']} · {match['city']}")
                st.write(match["bio"])
                render_tags(match["tags"])
            with c3:
                st.markdown(f"<div class='match-score'>{match['score']}%</div>", unsafe_allow_html=True)
                st.caption("综合匹配度")

            st.markdown("**为什么推荐**")
            for reason in match["reasons"]:
                st.write("• " + reason)
            for item in match["complementary"]:
                st.write("• " + item)
            st.info("💬 " + match["icebreaker"])
            default_topic = match["tags"][0] if match["tags"] else "这些话题"
            message = st.text_input(
                "申请留言",
                value=f"你好，我也对{default_topic}感兴趣，想认识一下。",
                key=f"friend_message_{match['user_id']}",
            )
            if st.button("发送好友申请", key=f"friend_request_{match['user_id']}", type="primary"):
                conn = get_conn()
                try:
                    ok, result_message = send_friend_request(conn, user_id, int(match["user_id"]), message)
                finally:
                    conn.close()
                st.success(result_message) if ok else st.warning(result_message)


def page_settings() -> None:
    st.title("⚙️ 配置与隐私")
    st.subheader("当前能力状态")
    status = pd.DataFrame(
        [
            {
                "模块": "生活记录分析",
                "状态": "DeepSeek API" if DEEPSEEK_API_KEY else "本地规则回退",
                "说明": f"模型：{DEEPSEEK_MODEL}" if DEEPSEEK_API_KEY else "无需联网，可直接演示",
            },
            {
                "模块": "附近 POI",
                "状态": "高德实时 API" if AMAP_KEY else "内置演示 POI",
                "说明": "Web 服务 Key 已配置" if AMAP_KEY else "在 .env 中配置 AMAP_WEB_SERVICE_KEY",
            },
            {
                "模块": "朋友匹配",
                "状态": "可用",
                "说明": "TF-IDF 语义相似度 + 规则加权",
            },
            {
                "模块": "数据存储",
                "状态": "本地 SQLite",
                "说明": str(DB_PATH),
            },
        ]
    )
    st.dataframe(status, width="stretch", hide_index=True)

    st.subheader("隐私边界")
    st.markdown(
        """
        - 原始记录默认不公开；“私密”内容完全不参与匹配。
        - “仅用于匹配”只用于生成抽象画像，其他用户不看到原文。
        - 不展示实时精确位置；正式产品应采用区域模糊化与延迟公开。
        - 不根据记录推断政治、宗教、疾病、性取向等敏感属性。
        - 本原型没有真实账号、聊天和内容审核，不能直接作为生产社交平台上线。
        """
    )

    st.subheader("重置演示数据库")
    st.caption("会删除你在本地新增的记录，并恢复内置模拟数据。")
    if st.button("重置数据", type="secondary"):
        if DB_PATH.exists():
            DB_PATH.unlink()
        init_db()
        st.success("演示数据已恢复。")
        st.rerun()


# --------------------------- Auth / onboarding ---------------------------

DEMO_USER_SESSION_KEY = "demo_user_id"
PROTOTYPE_USER_ID = 1


def enter_demo_mode() -> None:
    clear_auth_session(st.session_state)
    st.session_state["auth_mode"] = "demo"
    st.session_state.setdefault(DEMO_USER_SESSION_KEY, PROTOTYPE_USER_ID)


def render_auth_gate(supabase_client: Any | None, supabase_enabled: bool, status_message: str) -> None:
    st.title("Resonance")
    st.caption("请登录、注册，或进入演示模式体验本地原型。")

    if not supabase_enabled:
        st.warning(status_message)
        if st.button("进入演示模式", type="primary", width="stretch"):
            enter_demo_mode()
            st.rerun()
        st.stop()

    login_tab, register_tab, demo_tab = st.tabs(["登录", "注册", "演示模式"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("邮箱")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", type="primary", width="stretch")
        if submitted:
            errors = validate_login_input(email, password)
            if errors:
                for error in errors:
                    st.error(error)
            else:
                result = sign_in_with_password(supabase_client, email, password)
                if result.ok and result.user and result.session:
                    save_auth_session(st.session_state, result)
                    st.success("登录成功。")
                    st.rerun()
                else:
                    st.error(result.message)

    with register_tab:
        with st.form("register_form"):
            nickname = st.text_input("昵称")
            email = st.text_input("邮箱", key="register_email")
            password = st.text_input("密码", type="password", key="register_password")
            confirm_password = st.text_input("确认密码", type="password")
            submitted = st.form_submit_button("注册", type="primary", width="stretch")
        if submitted:
            errors = validate_registration_input(nickname, email, password, confirm_password)
            if errors:
                for error in errors:
                    st.error(error)
            else:
                result = sign_up_with_password(supabase_client, nickname, email, password)
                if result.ok:
                    if result.user and result.session:
                        save_auth_session(st.session_state, result)
                        st.success("注册成功，已登录。")
                        st.rerun()
                    else:
                        st.success("注册成功。请检查邮箱完成验证后再登录。")
                else:
                    st.error(result.message)

    with demo_tab:
        st.info("演示模式只使用本地 SQLite 模拟数据，不需要注册，也不会混用真实账号数据。")
        if st.button("进入演示模式", type="secondary", width="stretch"):
            enter_demo_mode()
            st.rerun()

    st.stop()


def render_onboarding_page(supabase_client: Any, profile: dict[str, Any] | None) -> None:
    st.title("完善资料")
    st.caption("这些信息会保存到你自己的 Supabase profiles 记录中。")

    with st.form("onboarding_form"):
        nickname = st.text_input("昵称", value=str((profile or {}).get("nickname") or ""))
        city = st.text_input("城市", value=str((profile or {}).get("city") or ""))
        bio = st.text_area("简介", value=str((profile or {}).get("bio") or ""), height=120)
        social_goal = st.text_area("社交目标", value=str((profile or {}).get("social_goal") or ""), height=100)
        submitted = st.form_submit_button("保存并进入应用", type="primary", width="stretch")

    if submitted:
        if not nickname.strip():
            st.error("昵称不能为空。")
            st.stop()
        try:
            updated = update_onboarding_profile(
                supabase_client,
                str(st.session_state.get("user_id", "")),
                nickname=nickname,
                city=city,
                bio=bio,
                social_goal=social_goal,
            )
        except Exception:
            st.error("资料保存失败，请稍后再试。")
            st.stop()

        st.session_state["profile"] = updated
        st.success("资料已保存。")
        st.rerun()

    st.stop()


# --------------------------- Main ---------------------------

def page_checkin(user_id: int) -> None:
    st.title("地点打卡")
    st.caption("输入地点名称搜索，选择结果后填写活动即可保存打卡。搜索使用 OpenStreetMap 免费服务，不需要地图账号。")
    privacy_help()

    search_points = get_demo_map_points(user_id, "全部")

    with st.form("checkin_place_search_form"):
        cols = st.columns([4, 1])
        place_query = cols[0].text_input(
            "搜索地点",
            value=st.session_state.get("checkin_place_query", ""),
            placeholder="例如：南京大学仙林校区、星巴克、上海外滩、北京故宫",
        )
        submitted_search = cols[1].form_submit_button("搜索", type="primary", width="stretch")

    if submitted_search:
        st.session_state["checkin_place_query"] = place_query.strip()
        local_results = search_local_map_points(place_query, search_points)
        remote_results: list[GeocodeResult] = []
        if place_query.strip():
            with st.spinner("正在搜索地点..."):
                try:
                    remote_results = search_place(place_query, limit=8)
                except Exception:
                    if not local_results:
                        st.error("地点搜索暂时不可用。可以换一个更具体的地点名，或检查网络后重试。")
        else:
            st.warning("请输入地点名称。")
        st.session_state["checkin_place_results"] = local_results + remote_results

    results = st.session_state.get("checkin_place_results", [])
    selected_result: GeocodeResult | None = None

    if results:
        labels = [f"{idx + 1}. {result.label}" for idx, result in enumerate(results)]
        selected_label = st.selectbox("选择打卡地点", labels)
        selected_result = results[labels.index(selected_label)]
    else:
        st.info("先搜索一个地点。课堂演示可试：南京大学仙林校区、图书馆、咖啡、公园。")

    if selected_result:
        st.markdown(
            f"""
            <div class="card">
                <b>{selected_result.label}</b><br>
                <span class="muted">{selected_result.category} · {selected_result.longitude:.6f}, {selected_result.latitude:.6f}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        preview_points = [
            {
                "latitude": selected_result.latitude,
                "longitude": selected_result.longitude,
                "name": selected_result.label,
                "source": "搜索结果",
                "activity": selected_result.category,
            }
        ]
        try:
            render_basic_streamlit_map(preview_points)
        except Exception:
            st.caption("地图预览暂时不可用，但地点坐标已可用于保存打卡。")

    with st.form("checkin_save_form", clear_on_submit=False):
        activity = st.text_input("正在做什么？", placeholder="学习 Python / 复习数学 / 咖啡自习 / 跑步 / 看展")
        privacy = st.selectbox("打卡权限", ["仅用于匹配", "公开", "私密"], index=0)
        submitted = st.form_submit_button("保存打卡", type="primary", width="stretch")

    if submitted:
        if not selected_result:
            st.error("请先搜索并选择一个地点。")
            return
        if not activity.strip():
            st.error("请填写正在做什么。")
            return

        analysis = analyze_text(f"{selected_result.label} {selected_result.category} {activity}")
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO checkins(user_id,poi_name,poi_type,longitude,latitude,activity,privacy,tags_json,verified,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                selected_result.label,
                selected_result.category,
                selected_result.longitude,
                selected_result.latitude,
                activity.strip(),
                privacy,
                json.dumps(analysis["tags"], ensure_ascii=False),
                0,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        conn.close()
        st.success("打卡已保存。")
        render_tags(analysis["tags"])


def page_checkin_v2(user_id: int) -> None:
    st.title("地点打卡")
    st.caption("输入地点名称搜索，选中后保存为你的足迹。搜索使用 OpenStreetMap/Nominatim 免费服务，不需要地图账号或 API Key。")
    privacy_help()

    search_points = get_demo_map_points(user_id, "全部")
    with st.form("checkin_v2_search_form"):
        cols = st.columns([4, 1])
        place_query = cols[0].text_input(
            "搜索地点",
            value=st.session_state.get("checkin_v2_place_query", ""),
            placeholder="例如：南京大学仙林校区、星巴克、上海外滩、北京故宫",
        )
        submitted_search = cols[1].form_submit_button("搜索", type="primary", width="stretch")

    if submitted_search:
        st.session_state["checkin_v2_place_query"] = place_query.strip()
        local_results = search_local_map_points(place_query, search_points)
        remote_results: list[GeocodeResult] = []
        if place_query.strip():
            with st.spinner("正在搜索地点..."):
                try:
                    remote_results = search_place(place_query, limit=8)
                except Exception:
                    if not local_results:
                        st.error("地点搜索暂时不可用。可以换一个更具体的地点名，或稍后重试。")
        else:
            st.warning("请输入地点名称。")
        st.session_state["checkin_v2_place_results"] = local_results + remote_results

    results = st.session_state.get("checkin_v2_place_results", [])
    selected_result: GeocodeResult | None = None
    if results:
        labels = [f"{idx + 1}. {result.label}" for idx, result in enumerate(results)]
        selected_label = st.selectbox("选择打卡地点", labels)
        selected_result = results[labels.index(selected_label)]
        st.markdown(
            f"""
            <div class="card">
                <b>{selected_result.label}</b><br>
                <span class="muted">{selected_result.category} · {selected_result.longitude:.6f}, {selected_result.latitude:.6f}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        try:
            render_basic_streamlit_map(
                [
                    {
                        "latitude": selected_result.latitude,
                        "longitude": selected_result.longitude,
                        "name": selected_result.label,
                        "source": "搜索结果",
                        "activity": selected_result.category,
                    }
                ]
            )
        except Exception:
            st.caption("地图预览暂时不可用，但地点坐标仍可保存。")
    else:
        st.info("先搜索一个地点。课堂演示可试：南京大学仙林校区、图书馆、咖啡、公园、上海外滩。")

    with st.form("checkin_v2_save_form", clear_on_submit=False):
        cols = st.columns([1, 1, 1])
        visited_day = cols[0].date_input("到访日期", value=date.today())
        visited_time = cols[1].time_input("开始时间", value=time(hour=15, minute=0))
        ended_time = cols[2].time_input("结束时间", value=time(hour=16, minute=30))
        activity = st.text_input("做了什么", placeholder="学习 Python / 复习数学 / 咖啡自习 / 跑步 / 看展")
        cols2 = st.columns([1, 1, 1])
        mood = cols2[0].text_input("心情", placeholder="专注、放松、开心")
        privacy = cols2[1].selectbox("可见范围", ["公开", "仅用于匹配", "私密"], index=1)
        feed_public = cols2[2].checkbox("生成公开动态", value=False)
        tag_text = st.text_input("标签", placeholder="最多 8 个，用逗号分隔，例如：学习, AI, 咖啡")
        notes = st.text_area("备注", placeholder="可以写一点这次打卡发生了什么", height=100)
        submitted = st.form_submit_button("保存打卡", type="primary", width="stretch")

    if submitted:
        if not selected_result:
            st.error("请先搜索并选择一个地点。")
            return
        if not activity.strip():
            st.error("请填写这次打卡做了什么。")
            return

        visited_at = combine_datetime(visited_day, visited_time)
        ended_at = combine_datetime(visited_day, ended_time)
        duration = compute_duration_minutes(visited_at, ended_at)
        if duration is None:
            ended_at = None
        analysis = analyze_text(f"{selected_result.label} {selected_result.category} {activity} {notes}")
        manual_tags = [part.strip() for part in re.split(r"[,，#\s]+", tag_text) if part.strip()]
        tags = manual_tags or analysis["tags"]
        conn = get_conn()
        try:
            add_checkin(
                conn,
                user_id=user_id,
                poi_name=selected_result.label,
                poi_type=selected_result.category,
                longitude=selected_result.longitude,
                latitude=selected_result.latitude,
                activity=activity,
                privacy=privacy,
                tags=tags,
                visited_at=visited_at,
                ended_at=ended_at,
                duration_minutes=duration,
                mood=mood,
                notes=notes,
                feed_public=feed_public,
                verified=0,
                source="nominatim",
            )
            conn.commit()
        finally:
            conn.close()
        st.success("打卡已保存，已经出现在“足迹”页。")
        render_tags(tags[:8])


def page_record_hub(user_id: int) -> None:
    st.title("记录")
    tabs = st.tabs(["生活记录", "地点打卡"])
    with tabs[0]:
        page_log(user_id)
    with tabs[1]:
        page_checkin_v2(user_id)


def page_discover_hub(user_id: int, auth_mode: str = "demo") -> None:
    st.title("发现")
    tabs = st.tabs(["朋友匹配", "好友申请", "探索地图"])
    with tabs[0]:
        page_matches(user_id)
    with tabs[1]:
        page_friend_requests(user_id, auth_mode)
    with tabs[2]:
        page_explore_map(user_id, auth_mode)


def page_footprint_hub(user_id: int, auth_mode: str = "demo") -> None:
    conn = get_conn()
    try:
        render_footprint_page(conn, user_id, auth_mode=auth_mode)
    finally:
        conn.close()


def render_onboarding_page(supabase_client: Any, profile: dict[str, Any] | None) -> None:
    st.title("完善资料")
    st.caption("优先保存到 Supabase profiles；如果后端策略暂时不允许更新，会为本次课堂演示暂存在浏览器会话里。")

    with st.form("onboarding_form_v2"):
        nickname = st.text_input("昵称", value=str((profile or {}).get("nickname") or ""))
        city = st.text_input("城市", value=str((profile or {}).get("city") or ""))
        bio = st.text_area("简介", value=str((profile or {}).get("bio") or ""), height=120)
        social_goal = st.text_area("社交目标", value=str((profile or {}).get("social_goal") or ""), height=100)
        submitted = st.form_submit_button("保存并进入应用", type="primary", width="stretch")

    if submitted:
        if not nickname.strip():
            st.error("昵称不能为空。")
            st.stop()

        fallback_profile = {
            "id": str(st.session_state.get("user_id", "")),
            "nickname": nickname.strip(),
            "city": city.strip(),
            "bio": bio.strip(),
            "social_goal": social_goal.strip(),
            "onboarding_completed": True,
            "created_at": None,
            "updated_at": None,
        }

        try:
            updated = update_onboarding_profile(
                supabase_client,
                str(st.session_state.get("user_id", "")),
                nickname=nickname,
                city=city,
                bio=bio,
                social_goal=social_goal,
            )
        except Exception:
            updated = fallback_profile
            st.session_state["profile_save_mode"] = "session_fallback"
            st.warning("Supabase 资料保存暂时失败，已为本次演示暂存资料并进入应用。")
        else:
            if not updated:
                updated = fallback_profile
                st.session_state["profile_save_mode"] = "session_fallback"
                st.warning("Supabase 没有返回已保存资料，已为本次演示暂存资料并进入应用。")
            else:
                st.session_state["profile_save_mode"] = "supabase"
                st.success("资料已保存到 Supabase。")

        st.session_state["profile"] = updated
        st.session_state["onboarding_profile_fallback"] = updated
        conn = get_conn()
        try:
            save_cached_profile(
                conn,
                updated,
                user_email=str(st.session_state.get("user_email", "")),
            )
        finally:
            conn.close()
        st.rerun()

    st.stop()

init_db()

supabase_config = get_supabase_config()
supabase_state = create_supabase_client(supabase_config)

if not supabase_state.enabled and st.session_state.get("auth_mode") != "demo":
    enter_demo_mode()

if supabase_state.enabled and is_logged_in(st.session_state):
    restore_supabase_session(
        supabase_state.client,
        st.session_state.get("access_token"),
        st.session_state.get("refresh_token"),
    )

if st.session_state.get("auth_mode") != "demo" and not is_logged_in(st.session_state):
    render_auth_gate(supabase_state.client, supabase_state.enabled, supabase_state.message)

auth_mode = st.session_state.get("auth_mode", "demo")
current_profile: dict[str, Any] | None = None

if auth_mode == "supabase":
    try:
        current_profile = fetch_current_profile(supabase_state.client, str(st.session_state.get("user_id", "")))
        st.session_state["profile"] = current_profile
    except Exception:
        st.error("读取个人资料失败，请稍后再试。")
        if st.button("退出登录", type="secondary"):
            sign_out(supabase_state.client, st.session_state)
            st.rerun()
        st.stop()

    fallback_profile = st.session_state.get("onboarding_profile_fallback")
    if not (current_profile or {}).get("onboarding_completed") and (fallback_profile or {}).get("onboarding_completed"):
        current_profile = fallback_profile
        st.session_state["profile"] = fallback_profile
    if not (current_profile or {}).get("onboarding_completed"):
        conn = get_conn()
        try:
            cached_profile = fetch_cached_profile(conn, str(st.session_state.get("user_id", "")))
        finally:
            conn.close()
        if (cached_profile or {}).get("onboarding_completed"):
            current_profile = cached_profile
            st.session_state["profile"] = cached_profile
            st.session_state["profile_save_mode"] = "local_cache"

    if not can_enter_main_app(st.session_state, current_profile):
        with st.sidebar:
            st.markdown("# Resonance")
            st.caption("Supabase 账号")
            if st.button("退出登录", type="secondary", width="stretch"):
                sign_out(supabase_state.client, st.session_state)
                st.rerun()
        render_onboarding_page(supabase_state.client, current_profile)

users_df = query_df("SELECT id,nickname,avatar,city FROM users ORDER BY id")
user_labels = {
    f"{row['avatar']} {row['nickname']} 路 {row['city']}": int(row["id"])
    for _, row in users_df.iterrows()
}

with st.sidebar:
    st.markdown("# Resonance")
    if auth_mode == "supabase":
        st.caption("Supabase 模式")
        st.write(st.session_state.get("user_email", ""))
        current_user_id = PROTOTYPE_USER_ID
        st.info("原型记录与匹配使用本地沙盒数据，待迁移到 Supabase。")
        if st.button("退出登录", type="secondary", width="stretch"):
            sign_out(supabase_state.client, st.session_state)
            st.rerun()
    else:
        st.caption("演示模式")
        selected_label = st.selectbox("当前演示用户", list(user_labels.keys()))
        current_user_id = user_labels[selected_label]
        st.info("演示模式只使用本地 SQLite 模拟数据。")
        if supabase_state.enabled and st.button("返回登录 / 注册", type="secondary", width="stretch"):
            clear_auth_session(st.session_state)
            st.rerun()

    st.divider()
    page = st.radio(
        "导航",
        ["🏠 首页", "✍️ 记录", "🗺️ 足迹", "🤝 发现", "📰 动态", "👤 我的"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("MVP 原型 · 不自动提交 Git")

if auth_mode == "supabase" and page != "🏠 首页":
    st.warning("当前页面仍使用本地原型数据，尚未迁移到 Supabase，不代表当前真实账号数据。")

if page == "🏠 首页":
    page_home(current_user_id, current_profile, auth_mode)
elif page == "✍️ 记录":
    page_record_hub(current_user_id)
elif page == "🗺️ 足迹":
    page_footprint_hub(current_user_id, auth_mode)
elif page == "🤝 发现":
    page_discover_hub(current_user_id, auth_mode)
elif page == "📰 动态":
    page_feed(current_user_id, auth_mode)
else:
    page_settings()

st.stop()

init_db()

users_df = query_df("SELECT id,nickname,avatar,city FROM users ORDER BY id")
user_labels = {
    f"{row['avatar']} {row['nickname']} · {row['city']}": int(row["id"])
    for _, row in users_df.iterrows()
}

with st.sidebar:
    st.markdown("# 🪐 共振")
    st.caption("生活记录 × 地点打卡 × 朋友匹配")
    selected_label = st.selectbox("当前演示用户", list(user_labels.keys()))
    current_user_id = user_labels[selected_label]
    st.divider()
    page = st.radio(
        "导航",
        ["首页", "记录生活", "地点打卡", "朋友匹配", "配置与隐私"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("MVP 原型 · 数据仅保存在本地")

if page == "首页":
    page_home(current_user_id)
elif page == "记录生活":
    page_log(current_user_id)
elif page == "地点打卡":
    page_checkin(current_user_id)
elif page == "朋友匹配":
    page_matches(current_user_id)
else:
    page_settings()
