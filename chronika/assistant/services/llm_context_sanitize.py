"""
Удаление полей из структур перед отправкой в промпты LLM (лишний шум / внешние идентификаторы).
Сессионный dialog_context в БД не трогаем — копия санитизируется только на границе вызова модели.
"""

from __future__ import annotations

from typing import Any

# Ключи выкидываются на любом уровне вложенности.
_LLM_DROP_KEYS = frozenset(
    {
        "google_event_id",
        "htmlLink",
        "organizer_email",
        # Заметки задачи в промпт не подставляем (объём и приватность)
        "notes",
    }
)


def sanitize_for_llm(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _LLM_DROP_KEYS:
                continue
            out[key] = sanitize_for_llm(item)
        return out
    if isinstance(value, list):
        return [sanitize_for_llm(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_llm(item) for item in value)
    return value
