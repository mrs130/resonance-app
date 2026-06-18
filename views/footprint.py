from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

from src.footprint_service import (
    CATEGORY_OPTIONS,
    category_distribution,
    city_options,
    delete_checkin,
    export_csv,
    export_json,
    footprint_stats,
    heatmap_rows,
    list_footprints,
    monthly_stats,
    place_atlas,
    tag_options,
    update_checkin,
    valid_map_footprints,
)
from src.geo_utils import category_color, map_center
from ui.footprint_components import bar_chart, empty_state, footprint_card, heatmap_chart, metric_row, render_tags


def _date_range_defaults() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=90), today


def _render_filter_panel(conn: Any, user_id: int) -> dict[str, Any]:
    start_default, end_default = _date_range_defaults()
    st.markdown("#### 筛选")
    cols = st.columns([1, 1, 1, 1])
    start = cols[0].date_input("开始日期", value=st.session_state.get("footprint_start", start_default))
    end = cols[1].date_input("结束日期", value=st.session_state.get("footprint_end", end_default))
    city = cols[2].selectbox("城市", city_options(conn, user_id), key="footprint_city")
    category = cols[3].selectbox("类型", ["全部"] + CATEGORY_OPTIONS, key="footprint_category")
    rows_for_tags = list_footprints(conn, user_id=user_id, start_date=start, end_date=end, city=city, category=category)
    cols2 = st.columns([2, 1, 1])
    tag = cols2[0].selectbox("标签", tag_options(rows_for_tags), format_func=lambda x: "全部" if not x else f"#{x}", key="footprint_tag")
    only_notes = cols2[1].toggle("只看有备注", value=st.session_state.get("footprint_only_notes", False))
    if cols2[2].button("重置筛选", width="stretch"):
        for key in ["footprint_city", "footprint_category", "footprint_tag", "footprint_only_notes"]:
            st.session_state.pop(key, None)
        st.rerun()
    st.session_state["footprint_start"] = start
    st.session_state["footprint_end"] = end
    st.session_state["footprint_only_notes"] = only_notes
    return {"start_date": start, "end_date": end, "city": city, "category": category, "tag": tag, "only_with_notes": only_notes}


def _render_map(rows: list[dict[str, Any]], selected_id: int | None) -> None:
    points = valid_map_footprints(rows)
    if not points:
        empty_state("没有可显示的地图点位", "当前筛选结果没有有效经纬度，地图会在有地点后自动出现。")
        return
    center_lat, center_lon = map_center(points)
    df = pd.DataFrame(points)
    df["color"] = df["category"].map(lambda value: category_color(value))
    df["radius"] = df["id"].map(lambda value: 170 if int(value) == int(selected_id or -1) else 95)
    df["tooltip"] = df.apply(lambda row: f"{row['poi_name']} · {row['activity']}", axis=1)
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[longitude, latitude]",
        get_radius="radius",
        get_fill_color="[239, 68, 68, 210]",
        pickable=True,
        auto_highlight=True,
    )
    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=11, pitch=0),
            layers=[layer],
            tooltip={"text": "{tooltip}"},
        ),
        use_container_width=True,
    )


def _selected_item(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    ids = [int(row["id"]) for row in rows]
    current = st.session_state.get("selected_checkin_id")
    if current not in ids:
        st.session_state["selected_checkin_id"] = ids[0]
    labels = {f"{row['poi_name']} · {row['visited_at'] or row['created_at']}": int(row["id"]) for row in rows}
    selected_label = st.selectbox("当前足迹", list(labels.keys()), key="selected_checkin_label")
    selected_id = labels[selected_label]
    st.session_state["selected_checkin_id"] = selected_id
    return next((row for row in rows if int(row["id"]) == selected_id), rows[0])


def _render_detail(conn: Any, user_id: int, item: dict[str, Any]) -> None:
    st.markdown("#### 足迹详情")
    footprint_card(item, selected=True)
    if item.get("notes"):
        st.write(item["notes"])

    with st.expander("编辑这条足迹"):
        with st.form(f"edit_checkin_{item['id']}"):
            activity = st.text_input("活动", value=str(item.get("activity") or ""))
            privacy = st.selectbox("可见范围", ["公开", "仅用于匹配", "私密"], index=0 if item.get("privacy") == "公开" else 1)
            mood = st.text_input("心情", value=str(item.get("mood") or ""))
            notes = st.text_area("备注", value=str(item.get("notes") or ""), height=100)
            tags = st.text_input("标签", value=", ".join(item.get("tags_list") or []), help="最多保存 8 个，用逗号分隔")
            saved = st.form_submit_button("保存修改", type="primary")
        if saved:
            ok = update_checkin(
                conn,
                checkin_id=int(item["id"]),
                user_id=user_id,
                activity=activity,
                privacy=privacy,
                mood=mood,
                notes=notes,
                tags=[part.strip() for part in tags.split(",")],
            )
            conn.commit()
            if ok:
                st.success("足迹已更新。")
                st.rerun()
            st.error("没有权限修改这条足迹。")

    with st.expander("删除这条足迹"):
        confirm = st.checkbox("确认删除，仅删除当前用户自己的这条足迹", key=f"delete_confirm_{item['id']}")
        if st.button("删除足迹", type="secondary", disabled=not confirm):
            ok = delete_checkin(conn, checkin_id=int(item["id"]), user_id=user_id)
            conn.commit()
            if ok:
                st.success("足迹已删除。")
                st.session_state.pop("selected_checkin_id", None)
                st.rerun()
            st.error("没有权限删除这条足迹。")


def _timeline_tab(conn: Any, user_id: int, rows: list[dict[str, Any]]) -> None:
    metric_row(footprint_stats(rows))
    left, right = st.columns([1.4, 1])
    with left:
        _render_map(rows, st.session_state.get("selected_checkin_id"))
    with right:
        item = _selected_item(rows)
        if item:
            _render_detail(conn, user_id, item)
    st.divider()
    st.markdown("#### 时间轴")
    if not rows:
        empty_state("当前没有足迹", "放宽筛选条件，或者去“记录”里新增一次地点打卡。")
    for row in rows:
        footprint_card(row, selected=int(row["id"]) == int(st.session_state.get("selected_checkin_id") or -1))
        if st.button("查看", key=f"select_fp_{row['id']}"):
            st.session_state["selected_checkin_id"] = int(row["id"])
            st.rerun()


def _atlas_tab(rows: list[dict[str, Any]]) -> None:
    atlas = place_atlas(rows)
    if not atlas:
        empty_state("地点图鉴还没点亮", "每次打卡都会让一个地点卡片更完整。")
        return
    query = st.text_input("搜索地点", placeholder="输入地点、城市、标签")
    if query.strip():
        key = query.strip().lower()
        atlas = [
            item for item in atlas
            if key in " ".join([str(item.get("name")), str(item.get("city")), " ".join(item.get("tags") or [])]).lower()
        ]
    cols = st.columns(3)
    for idx, item in enumerate(atlas):
        with cols[idx % 3]:
            st.markdown(
                f"""
                <div class="card">
                    <b>{item['name']}</b>
                    <div class="activity-meta">{item.get('city') or '城市未知'} · {item['category']}</div>
                    <div class="match-score">{item['visit_count']}</div>
                    <span class="muted">最近到访：{item['last_visited_at']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_tags(item.get("tags") or [])


def _stats_tab(rows: list[dict[str, Any]]) -> None:
    stats = footprint_stats(rows)
    metric_row(stats)
    st.markdown(
        f"""
        <div class="card">
            这段时间一共记录了 <b>{stats['visits']}</b> 次足迹，点亮 <b>{stats['unique_places']}</b> 个地点，
            最常出现的类型是 <b>{stats['favorite_category']}</b>。复访率为 <b>{int(stats['revisit_rate'] * 100)}%</b>，
            说明这个版本已经能展示“常去地点”和“生活节奏”的雏形。
        </div>
        """,
        unsafe_allow_html=True,
    )
    heatmap_chart(heatmap_rows(rows))
    c1, c2 = st.columns(2)
    with c1:
        bar_chart(monthly_stats(rows), "month", "count", "月份")
    with c2:
        bar_chart(category_distribution(rows), "category", "count", "类型")


def render_footprint_page(conn: Any, user_id: int, *, auth_mode: str = "demo") -> None:
    st.title("我的足迹")
    st.caption("把地点打卡变成地图、时间轴、地点图鉴和生活统计。")
    if auth_mode == "supabase":
        st.info("当前足迹仍是本地原型数据，尚未迁移到 Supabase；不会把演示地点写入真实账号。")
    filters = _render_filter_panel(conn, user_id)
    rows = list_footprints(conn, user_id=user_id, **filters)
    tabs = st.tabs(["地图时间轴", "地点图鉴", "生活统计", "导出"])
    with tabs[0]:
        _timeline_tab(conn, user_id, rows)
    with tabs[1]:
        _atlas_tab(rows)
    with tabs[2]:
        _stats_tab(rows)
    with tabs[3]:
        st.download_button("下载 CSV", data=export_csv(rows), file_name="resonance-footprints.csv", mime="text/csv")
        st.download_button("下载 JSON", data=export_json(rows), file_name="resonance-footprints.json", mime="application/json")
