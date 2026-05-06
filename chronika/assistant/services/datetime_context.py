from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


class DateTimeContext:
    def now_iso(self, user_tz: str) -> str:
        return datetime.now(self._tz(user_tz)).isoformat()

    def normalize_iso(self, raw: str, user_tz: str) -> str:
        dt = datetime.fromisoformat(str(raw))
        tz = self._tz(user_tz)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)
        return dt.isoformat()

    def normalize_action(self, payload: dict[str, Any], *, user_tz: str) -> dict[str, Any]:
        return self._normalize_nested(payload, user_tz=user_tz)

    def _normalize_nested(self, value: Any, *, user_tz: str):
        if isinstance(value, dict):
            return {k: self._normalize_nested(v, user_tz=user_tz) for k, v in value.items()}
        if isinstance(value, list):
            return [self._normalize_nested(item, user_tz=user_tz) for item in value]
        if isinstance(value, datetime):
            return self.normalize_iso(value.isoformat(), user_tz=user_tz)
        if isinstance(value, str):
            try:
                return self.normalize_iso(value, user_tz=user_tz)
            except ValueError:
                return value
        return value

    def _tz(self, user_tz: str):
        try:
            return ZoneInfo(user_tz)
        except Exception:
            return ZoneInfo("UTC")
