from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping


AUTH_SESSION_KEYS = (
    "user_id",
    "user_email",
    "access_token",
    "refresh_token",
    "auth_mode",
    "profile",
    "profile_save_mode",
    "onboarding_profile_fallback",
)


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    message: str
    user: Any | None = None
    session: Any | None = None


def validate_registration_input(
    nickname: str,
    email: str,
    password: str,
    confirm_password: str,
) -> list[str]:
    errors: list[str] = []
    if not nickname.strip():
        errors.append("昵称不能为空。")
    if not email.strip():
        errors.append("邮箱不能为空。")
    if len(password) < 8:
        errors.append("密码至少需要 8 位。")
    if password != confirm_password:
        errors.append("两次输入的密码不一致。")
    return errors


def validate_login_input(email: str, password: str) -> list[str]:
    errors: list[str] = []
    if not email.strip():
        errors.append("邮箱不能为空。")
    if not password:
        errors.append("密码不能为空。")
    return errors


def translate_supabase_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "invalid login credentials" in text or "invalid credentials" in text:
        return "邮箱或密码不正确。"
    if "email not confirmed" in text:
        return "邮箱尚未完成验证，请先检查邮件。"
    if "already registered" in text or "user already registered" in text:
        return "这个邮箱已经注册，请直接登录。"
    if "password" in text and ("weak" in text or "short" in text):
        return "密码强度不足，请使用至少 8 位密码。"
    if "rate limit" in text or "too many" in text:
        return "请求过于频繁，请稍后再试。"
    return "认证服务暂时不可用，请稍后再试。"


def sign_up_with_password(client: Any, nickname: str, email: str, password: str) -> AuthResult:
    try:
        response = client.auth.sign_up(
            {
                "email": email.strip(),
                "password": password,
                "options": {"data": {"nickname": nickname.strip()}},
            }
        )
        return AuthResult(ok=True, message="注册成功。", user=response.user, session=response.session)
    except Exception as exc:
        return AuthResult(ok=False, message=translate_supabase_error(exc))


def sign_in_with_password(client: Any, email: str, password: str) -> AuthResult:
    try:
        response = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
        return AuthResult(ok=True, message="登录成功。", user=response.user, session=response.session)
    except Exception as exc:
        return AuthResult(ok=False, message=translate_supabase_error(exc))


def save_auth_session(state: MutableMapping[str, Any], result: AuthResult) -> None:
    user = result.user
    session = result.session
    state["user_id"] = getattr(user, "id", "")
    state["user_email"] = getattr(user, "email", "")
    state["access_token"] = getattr(session, "access_token", "")
    state["refresh_token"] = getattr(session, "refresh_token", "")
    state["auth_mode"] = "supabase"


def clear_auth_session(state: MutableMapping[str, Any]) -> None:
    for key in AUTH_SESSION_KEYS:
        state.pop(key, None)


def sign_out(client: Any, state: MutableMapping[str, Any]) -> None:
    try:
        if client:
            client.auth.sign_out()
    except Exception:
        pass
    clear_auth_session(state)


def is_logged_in(state: MutableMapping[str, Any]) -> bool:
    return bool(
        state.get("auth_mode") == "supabase"
        and state.get("user_id")
        and state.get("access_token")
        and state.get("refresh_token")
    )


def can_enter_main_app(state: MutableMapping[str, Any], profile: dict[str, Any] | None) -> bool:
    if not is_logged_in(state):
        return False
    return bool(profile and profile.get("onboarding_completed"))
