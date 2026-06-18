from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import SupabaseConfig, get_supabase_config


@dataclass(frozen=True)
class SupabaseClientState:
    client: Any | None
    enabled: bool
    message: str


def create_supabase_client(config: SupabaseConfig | None = None) -> SupabaseClientState:
    cfg = config or get_supabase_config()
    if not cfg.enabled:
        return SupabaseClientState(
            client=None,
            enabled=False,
            message="Supabase 配置缺失，已进入演示模式。",
        )

    try:
        from supabase import create_client
    except ImportError:
        return SupabaseClientState(
            client=None,
            enabled=False,
            message="未安装 supabase 依赖，已进入演示模式。",
        )

    try:
        client = create_client(cfg.url, cfg.publishable_key)
    except Exception:
        return SupabaseClientState(
            client=None,
            enabled=False,
            message="Supabase 客户端初始化失败，已进入演示模式。",
        )

    return SupabaseClientState(client=client, enabled=True, message="Supabase 已启用。")


def restore_supabase_session(client: Any, access_token: str | None, refresh_token: str | None) -> bool:
    if not client or not access_token or not refresh_token:
        return False
    try:
        client.auth.set_session(access_token, refresh_token)
        return True
    except Exception:
        return False
