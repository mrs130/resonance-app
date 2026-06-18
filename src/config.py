from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    publishable_key: str

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.publishable_key)


def get_supabase_config(environ: Mapping[str, str] | None = None) -> SupabaseConfig:
    source = environ if environ is not None else os.environ
    return SupabaseConfig(
        url=source.get("SUPABASE_URL", "").strip(),
        publishable_key=source.get("SUPABASE_PUBLISHABLE_KEY", "").strip(),
    )


def is_supabase_enabled(environ: Mapping[str, str] | None = None) -> bool:
    return get_supabase_config(environ).enabled
