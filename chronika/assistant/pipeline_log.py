"""
Пошаговое логирование цепочки ассистента в файл (logger assistant.pipeline в LOGGING).

Не логируйте секреты: в сообщениях — только префиксы / длины по необходимости.
"""

from __future__ import annotations

import json
import logging
import traceback
import uuid
from contextvars import ContextVar
from dataclasses import asdict
from typing import Any

from assistant.domain.dialog import ReplyInterpretation

_logger = logging.getLogger("assistant.pipeline")

_ctx: ContextVar[dict[str, Any]] = ContextVar("assistant_pipeline_ctx", default={})

# Верхняя граница размера одного блока в trace/pretty (символов).
_TRACE_MAX = 400_000


def bind_context(**kwargs: Any) -> None:
    cur = dict(_ctx.get())
    for k, v in kwargs.items():
        if v is not None:
            cur[k] = v
    _ctx.set(cur)


def clear_context() -> None:
    _ctx.set({})


def new_request_id() -> str:
    return str(uuid.uuid4())[:8]


def _safe_json(obj: Any, max_len: int = 14_000) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…[truncated]"


def _ctx_line() -> str:
    c = _ctx.get()
    if not c:
        return ""
    parts = []
    if rid := c.get("request_id"):
        parts.append(f"req={rid}")
    if uid := c.get("user_id"):
        parts.append(f"user={uid}")
    if ep := c.get("endpoint"):
        parts.append(f"ep={ep}")
    return ("  [контекст] " + " ".join(parts)) if parts else ""


def event(phase: str, *, caller: str, callee: str | None = None, **data: Any) -> None:
    """Компактная одна строка (ошибки валидации и редкие метки)."""
    parts = [f"phase={phase}", f"from={caller}"]
    if callee:
        parts.append(f"to={callee}")
    for k in sorted(data.keys()):
        v = data[k]
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            parts.append(f"{k}={_safe_json(v)}")
        else:
            parts.append(f"{k}={v}")
    prefix = _ctx_line()
    if prefix:
        parts.insert(0, prefix.strip())
    _logger.info(" | ".join(parts))


def pretty_data(obj: Any, *, max_len: int = _TRACE_MAX) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        s = str(obj)
    if len(s) > max_len:
        return s[:max_len] + "\n… [обрезано]"
    return s


def pretty_json_text(raw: str | None, *, max_len: int = _TRACE_MAX) -> str:
    if raw is None or not str(raw).strip():
        return "(нет текста ответа)"
    text = str(raw).strip()
    try:
        s = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        s = text
    if len(s) > max_len:
        return s[:max_len] + "\n… [обрезано]"
    return s


def interpretation_to_dict(interp: ReplyInterpretation) -> dict[str, Any]:
    return {
        "dialog_intent": interp.dialog_intent.value,
        "actions": interp.actions,
        "target_ids": interp.target_ids,
        "new_intent_candidate": (
            {"raw": interp.new_intent_candidate.raw} if interp.new_intent_candidate else None
        ),
        "step_patches": interp.step_patches,
    }


def trace(title: str, **sections: str) -> None:
    """
    Читаемый многострочный блок: заголовок и именованные секции (уже отформатированные строки).
    """
    lines: list[str] = [
        "",
        f"──────── {title} ────────",
    ]
    ctx = _ctx_line()
    if ctx:
        lines.append(ctx)
    for name, body in sections.items():
        if body is None or str(body).strip() == "":
            continue
        lines.append(f"  ▸ {name}")
        for line in str(body).rstrip().splitlines():
            lines.append(f"     {line}")
        lines.append("")
    lines.append(f"──────── конец: {title} ────────")
    _logger.info("\n".join(lines))


def log_exception(phase: str, caller: str, exc: BaseException) -> None:
    _logger.error(
        "%sphase=%s from=%s error=%s\n%s",
        _ctx_line() + "\n" if _ctx_line() else "",
        phase,
        caller,
        exc,
        traceback.format_exc(),
    )
