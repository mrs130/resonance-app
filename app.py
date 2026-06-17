
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

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
    .block-container {padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1180px;}
    [data-testid="stSidebar"] {background: #0f172a;}
    [data-testid="stSidebar"] * {color: #f8fafc;}
    .hero {
        padding: 26px 30px;
        border: 1px solid #dbeafe;
        border-radius: 22px;
        background: linear-gradient(135deg, #eff6ff 0%, #f5f3ff 55%, #fff7ed 100%);
        margin-bottom: 18px;
    }
    .hero h1 {font-size: 2.1rem; margin: 0 0 6px 0;}
    .hero p {font-size: 1.02rem; color: #475569; margin: 0;}
    .card {
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 18px;
        background: white;
        box-shadow: 0 5px 20px rgba(15, 23, 42, 0.04);
        margin-bottom: 12px;
    }
    .tag {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        background: #eef2ff;
        color: #4338ca;
        font-size: 0.82rem;
        margin: 2px 5px 2px 0;
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
        letter-spacing: -0.04em;
    }
    .muted {color: #64748b;}
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
    count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count == 0:
        seed_demo_data(conn)
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


# --------------------------- Pages ---------------------------

def page_home(user_id: int) -> None:
    user = get_user(user_id)
    features = collect_user_features(user_id)
    logs_count = int(query_df("SELECT COUNT(*) AS n FROM life_logs WHERE user_id=?", (user_id,)).iloc[0]["n"])
    check_count = int(query_df("SELECT COUNT(*) AS n FROM checkins WHERE user_id=?", (user_id,)).iloc[0]["n"])
    matches = calculate_matches(user_id)

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


# --------------------------- Main ---------------------------

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
