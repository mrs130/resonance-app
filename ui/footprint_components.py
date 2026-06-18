from __future__ import annotations

from typing import Any, Iterable

import altair as alt
import pandas as pd
import streamlit as st

from src.geo_utils import category_color


def metric_row(stats: dict[str, Any]) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("打卡次数", stats["visits"])
    c2.metric("去过地点", stats["unique_places"])
    c3.metric("再次到访", stats["revisits"])
    c4.metric("活跃城市", stats["active_cities"])
    c5.metric("复访率", f"{int(stats['revisit_rate'] * 100)}%")


def render_tags(tags: Iterable[str]) -> None:
    html = "".join(f'<span class="tag">#{tag}</span>' for tag in tags)
    if html:
        st.markdown(html, unsafe_allow_html=True)


def footprint_card(item: dict[str, Any], *, selected: bool = False) -> None:
    border = "#ef4444" if selected else "#e5e7eb"
    color = category_color(item.get("category"))
    st.markdown(
        f"""
        <div class="activity-card" style="border-color:{border};">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
                <div>
                    <b>{item.get('poi_name')}</b>
                    <div class="activity-meta">{item.get('activity')} · {item.get('visited_at') or item.get('created_at')}</div>
                    <div class="activity-meta">{item.get('place_city') or '城市未知'} · {item.get('privacy')} · {item.get('mood') or '未记录心情'}</div>
                </div>
                <span class="status-pill" style="background:{color}22;color:{color};">{item.get('category')}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_tags(item.get("tags_list") or [])


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="card">
            <h3 style="margin-top:0">{title}</h3>
            <p class="muted">{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def heatmap_chart(rows: list[dict[str, Any]]) -> None:
    if not rows:
        empty_state("还没有热力图数据", "先完成几次地点打卡，这里会显示按日期聚合的活跃度。")
        return
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["weekday"] = df["date"].dt.day_name()
    chart = (
        alt.Chart(df)
        .mark_rect(cornerRadius=3)
        .encode(
            x=alt.X("week:O", title="周"),
            y=alt.Y("weekday:N", title="", sort=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]),
            color=alt.Color("count:Q", title="次数", scale=alt.Scale(scheme="tealblues")),
            tooltip=["date:T", "count:Q"],
        )
        .properties(height=220)
    )
    st.altair_chart(chart, use_container_width=True)


def bar_chart(rows: list[dict[str, Any]], x: str, y: str, title: str) -> None:
    if not rows:
        empty_state("暂无统计数据", "当前筛选条件下没有可统计的足迹。")
        return
    chart = (
        alt.Chart(pd.DataFrame(rows))
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(x=alt.X(f"{x}:N", title=title), y=alt.Y(f"{y}:Q", title="次数"), tooltip=[x, y])
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)
