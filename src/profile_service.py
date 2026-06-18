from __future__ import annotations

from typing import Any


PROFILE_FIELDS = ("id", "nickname", "city", "bio", "social_goal", "onboarding_completed", "created_at", "updated_at")
ONBOARDING_FIELDS = ("nickname", "city", "bio", "social_goal")


def normalize_profile(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    return {field: data.get(field) for field in PROFILE_FIELDS}


def fetch_current_profile(client: Any, user_id: str) -> dict[str, Any] | None:
    if not user_id:
        return None
    try:
        response = (
            client.table("profiles")
            .select(",".join(PROFILE_FIELDS))
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception as exc:
        text = str(exc)
        if "PGRST116" in text or "0 rows" in text or "JSON object requested" in text:
            return None
        raise
    return normalize_profile(response.data)


def update_onboarding_profile(
    client: Any,
    user_id: str,
    *,
    nickname: str,
    city: str,
    bio: str,
    social_goal: str,
) -> dict[str, Any] | None:
    if not user_id:
        raise ValueError("缺少当前用户。")

    payload = {
        "nickname": nickname.strip(),
        "city": city.strip(),
        "bio": bio.strip(),
        "social_goal": social_goal.strip(),
        "onboarding_completed": True,
    }
    response = (
        client.table("profiles")
        .update(payload)
        .eq("id", user_id)
        .select(",".join(PROFILE_FIELDS))
        .execute()
    )
    data = response.data
    if isinstance(data, list) and data:
        return normalize_profile(data[0])
    if isinstance(data, dict):
        return normalize_profile(data)

    response = (
        client.table("profiles")
        .upsert({"id": user_id, **payload})
        .select(",".join(PROFILE_FIELDS))
        .execute()
    )
    data = response.data
    if isinstance(data, list) and data:
        return normalize_profile(data[0])
    if isinstance(data, dict):
        return normalize_profile(data)
    return None
