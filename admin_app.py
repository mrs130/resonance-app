from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.demo_social_service import ensure_friend_request_schema, update_friend_request_status


load_dotenv()

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "data" / "resonance.db"

st.set_page_config(
    page_title="Resonance Admin",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"] {background:#f7fafc;color:#102033;}
    .block-container {padding-top:1.2rem;max-width:1240px;}
    [data-testid="stSidebar"] {background:#111827;}
    [data-testid="stSidebar"] * {color:#f9fafb;}
    .admin-hero {
        padding:22px 24px;
        border:1px solid #dbeafe;
        border-radius:10px;
        background:linear-gradient(135deg,#eff6ff,#ecfdf5);
        box-shadow:0 10px 28px rgba(15,23,42,.06);
        margin-bottom:16px;
    }
    .admin-card {
        border:1px solid #e5e7eb;
        border-radius:8px;
        background:#fff;
        padding:14px 16px;
        margin-bottom:12px;
        box-shadow:0 5px 18px rgba(15,23,42,.05);
    }
    .muted {color:#64748b;font-size:.9rem;}
    div[data-testid="stMetric"] {
        background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    ensure_friend_request_schema(conn)
    conn.commit()
    return conn


def query_df(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def has_demo_tables() -> bool:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users','life_logs','checkins')"
        ).fetchall()
        return len(rows) == 3
    finally:
        conn.close()


def metric_value(sql: str) -> int:
    df = query_df(sql)
    if df.empty:
        return 0
    return int(df.iloc[0, 0])


def render_friend_request_admin() -> None:
    st.subheader("好友申请审核")
    requests_df = query_df(
        """
        SELECT fr.id, rq.nickname AS requester, rc.nickname AS receiver,
               fr.message, fr.status, fr.created_at, fr.updated_at,
               fr.receiver_id
        FROM friend_requests fr
        JOIN users rq ON rq.id = fr.requester_id
        JOIN users rc ON rc.id = fr.receiver_id
        ORDER BY fr.updated_at DESC
        """
    )
    if requests_df.empty:
        st.info("暂无好友申请。")
        return

    status_filter = st.segmented_control(
        "状态",
        ["全部", "pending", "accepted", "rejected", "cancelled"],
        default="全部",
    )
    visible = requests_df if status_filter == "全部" else requests_df[requests_df["status"] == status_filter]
    st.dataframe(visible, hide_index=True, width="stretch")

    pending = requests_df[requests_df["status"] == "pending"]
    if pending.empty:
        return

    st.markdown("#### 快速处理 pending 申请")
    for _, row in pending.iterrows():
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(f"**{row['requester']} → {row['receiver']}**")
                st.write(row["message"] or "无留言")
                st.caption(f"创建：{row['created_at']}")
            with right:
                if st.button("通过", key=f"admin_accept_{row['id']}", width="stretch"):
                    conn = get_conn()
                    try:
                        ok, message = update_friend_request_status(
                            conn,
                            int(row["id"]),
                            int(row["receiver_id"]),
                            "accepted",
                        )
                    finally:
                        conn.close()
                    st.success(message) if ok else st.error(message)
                    st.rerun()
                if st.button("拒绝", key=f"admin_reject_{row['id']}", width="stretch"):
                    conn = get_conn()
                    try:
                        ok, message = update_friend_request_status(
                            conn,
                            int(row["id"]),
                            int(row["receiver_id"]),
                            "rejected",
                        )
                    finally:
                        conn.close()
                    st.success(message) if ok else st.error(message)
                    st.rerun()


def render_content_admin() -> None:
    st.subheader("内容与地点")
    tab_logs, tab_checkins = st.tabs(["生活记录", "地点打卡"])
    with tab_logs:
        logs = query_df(
            """
            SELECT l.id, u.nickname, u.city, l.content, l.privacy, l.mood,
                   l.social_intent, l.created_at
            FROM life_logs l
            JOIN users u ON u.id = l.user_id
            ORDER BY l.created_at DESC
            """
        )
        st.dataframe(logs, hide_index=True, width="stretch")
    with tab_checkins:
        checkins = query_df(
            """
            SELECT c.id, u.nickname, u.city, c.poi_name, c.poi_type, c.activity,
                   c.privacy, c.verified, c.created_at
            FROM checkins c
            JOIN users u ON u.id = c.user_id
            ORDER BY c.created_at DESC
            """
        )
        st.dataframe(checkins, hide_index=True, width="stretch")


def render_user_admin() -> None:
    st.subheader("用户画像")
    users = query_df(
        """
        SELECT u.id, u.nickname, u.city, u.social_goal,
               COUNT(DISTINCT l.id) AS life_logs,
               COUNT(DISTINCT c.id) AS checkins
        FROM users u
        LEFT JOIN life_logs l ON l.user_id = u.id
        LEFT JOIN checkins c ON c.user_id = u.id
        GROUP BY u.id
        ORDER BY u.id
        """
    )
    st.dataframe(users, hide_index=True, width="stretch")


def render_system_admin() -> None:
    st.subheader("系统状态")
    st.markdown(
        f"""
        <div class="admin-card">
            <b>数据库</b><br>
            <span class="muted">{DB_PATH}</span>
        </div>
        <div class="admin-card">
            <b>说明</b><br>
            <span class="muted">后台站点只管理本地 SQLite 原型数据；Supabase 登录/profile 不在这里修改。</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.markdown("# Resonance Admin")
    page = st.radio("导航", ["总览", "用户", "内容", "好友申请", "系统"], label_visibility="collapsed")
    st.caption("本地原型后台 · 交作业展示")

st.markdown(
    """
    <div class="admin-hero">
        <h1 style="margin:0 0 6px 0">Resonance 后台</h1>
        <p class="muted" style="margin:0">查看演示用户、动态内容、地点打卡和好友申请状态。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not has_demo_tables():
    st.error("还没有初始化演示数据库。请先运行用户端网站 app.py。")
    st.stop()

if page == "总览":
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("用户", metric_value("SELECT COUNT(*) FROM users"))
    c2.metric("生活记录", metric_value("SELECT COUNT(*) FROM life_logs"))
    c3.metric("地点打卡", metric_value("SELECT COUNT(*) FROM checkins"))
    c4.metric("待处理申请", metric_value("SELECT COUNT(*) FROM friend_requests WHERE status='pending'"))

    left, right = st.columns([1, 1])
    with left:
        st.subheader("最近动态")
        recent = query_df(
            """
            SELECT u.nickname, l.content, l.privacy, l.created_at
            FROM life_logs l
            JOIN users u ON u.id = l.user_id
            ORDER BY l.created_at DESC
            LIMIT 8
            """
        )
        st.dataframe(recent, hide_index=True, width="stretch")
    with right:
        st.subheader("最近地点")
        recent_places = query_df(
            """
            SELECT u.nickname, c.poi_name, c.activity, c.created_at
            FROM checkins c
            JOIN users u ON u.id = c.user_id
            ORDER BY c.created_at DESC
            LIMIT 8
            """
        )
        st.dataframe(recent_places, hide_index=True, width="stretch")
elif page == "用户":
    render_user_admin()
elif page == "内容":
    render_content_admin()
elif page == "好友申请":
    render_friend_request_admin()
else:
    render_system_admin()
