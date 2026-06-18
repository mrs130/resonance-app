from __future__ import annotations

from types import SimpleNamespace

from src.auth_service import (
    can_enter_main_app,
    clear_auth_session,
    is_logged_in,
    sign_out,
    validate_registration_input,
)
from src.config import is_supabase_enabled
from src.supabase_client import create_supabase_client


def authenticated_state() -> dict[str, str]:
    return {
        "user_id": "user-1",
        "user_email": "alice@example.com",
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "auth_mode": "supabase",
    }


def test_registration_password_must_be_at_least_8_chars() -> None:
    errors = validate_registration_input("Alice", "alice@example.com", "1234567", "1234567")

    assert "密码至少需要 8 位。" in errors


def test_registration_password_confirmation_must_match() -> None:
    errors = validate_registration_input("Alice", "alice@example.com", "12345678", "abcdefgh")

    assert "两次输入的密码不一致。" in errors


def test_missing_supabase_config_disables_supabase_mode() -> None:
    env = {"SUPABASE_URL": "", "SUPABASE_PUBLISHABLE_KEY": ""}

    assert is_supabase_enabled(env) is False
    missing_state = create_supabase_client(config=SimpleNamespace(enabled=False))
    assert missing_state.enabled is False
    assert "演示模式" in missing_state.message


def test_unauthenticated_user_cannot_enter_main_app() -> None:
    assert is_logged_in({}) is False
    assert can_enter_main_app({}, {"onboarding_completed": True}) is False


def test_incomplete_onboarding_cannot_enter_main_app() -> None:
    state = authenticated_state()
    profile = {"onboarding_completed": False}

    assert is_logged_in(state) is True
    assert can_enter_main_app(state, profile) is False


def test_completed_onboarding_can_enter_main_app() -> None:
    state = authenticated_state()
    profile = {"onboarding_completed": True}

    assert can_enter_main_app(state, profile) is True


def test_logout_clears_auth_session_and_calls_supabase() -> None:
    calls: list[str] = []
    client = SimpleNamespace(auth=SimpleNamespace(sign_out=lambda: calls.append("sign_out")))
    state = authenticated_state()
    state["profile"] = {"nickname": "Alice"}

    sign_out(client, state)

    assert calls == ["sign_out"]
    assert state == {}


def test_clear_auth_session_keeps_unrelated_state() -> None:
    state = authenticated_state()
    state["page"] = "首页"

    clear_auth_session(state)

    assert state == {"page": "首页"}
