from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class LastInteraction:
    last_entities: list[dict[str, Any]] = field(default_factory=list)
    last_actions: list[dict[str, Any]] = field(default_factory=list)
    last_target_ids: list[int] = field(default_factory=list)
    previous_values: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredContext:
    last_interaction: LastInteraction = field(default_factory=LastInteraction)
    disambiguation_options: list[dict[str, Any]] = field(default_factory=list)


def structured_context_from_dict(payload: dict[str, Any] | None) -> StructuredContext:
    if payload is None:
        return StructuredContext()
    li = payload.get("last_interaction") or {}
    if not isinstance(li, dict):
        li = {}
    last = LastInteraction(
        last_entities=list(li.get("last_entities") or []),
        last_actions=list(li.get("last_actions") or []),
        last_target_ids=_coerce_int_list(li.get("last_target_ids")),
        previous_values=li.get("previous_values") if isinstance(li.get("previous_values"), dict) else {},
    )
    options = payload.get("disambiguation_options") or []
    if not isinstance(options, list):
        options = []
    return StructuredContext(last_interaction=last, disambiguation_options=list(options))


def _coerce_int_list(raw: Any) -> list[int]:
    out: list[int] = []
    for x in raw or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def structured_context_to_dict(ctx: StructuredContext) -> dict[str, Any]:
    return {
        "last_interaction": {
            f.name: getattr(ctx.last_interaction, f.name)
            for f in fields(LastInteraction)
        },
        "disambiguation_options": list(ctx.disambiguation_options),
    }
