from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ActionType = Literal["create", "schedule", "update", "delete", "retrieve"]


@dataclass
class Entity:
    id: int
    context_id: str
    type: str
    title: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    context_id: str
    type: ActionType
    target_id: int | None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionPlan:
    actions: list[Action]
    entities: list[Entity] = field(default_factory=list)


def action_plan_to_dict(plan: ActionPlan) -> dict[str, Any]:
    return {
        "actions": [asdict(a) for a in plan.actions],
        "entities": [asdict(e) for e in plan.entities],
    }


def action_plan_from_dict(payload: dict[str, Any] | None) -> ActionPlan | None:
    if payload is None:
        return None
    actions_raw = payload.get("actions") or []
    entities_raw = payload.get("entities") or []
    if not isinstance(actions_raw, list) or not isinstance(entities_raw, list):
        return ActionPlan(actions=[], entities=[])

    actions: list[Action] = []
    for item in actions_raw:
        if not isinstance(item, dict):
            continue
        actions.append(
            Action(
                context_id=str(item.get("context_id") or ""),
                type=coerce_action_type(item.get("type")),
                target_id=_optional_int(item.get("target_id")),
                data=item.get("data") if isinstance(item.get("data"), dict) else {},
            )
        )

    entities: list[Entity] = []
    for item in entities_raw:
        if not isinstance(item, dict):
            continue
        entities.append(
            Entity(
                id=int(item.get("id") or 0),
                context_id=str(item.get("context_id") or ""),
                type=str(item.get("type") or "unknown"),
                title=str(item.get("title") or ""),
                meta=item.get("meta") if isinstance(item.get("meta"), dict) else {},
            )
        )

    return ActionPlan(actions=actions, entities=entities)


def _optional_int(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def coerce_action_type(raw: Any) -> ActionType:
    value = str(raw or "").strip().lower()
    allowed: set[ActionType] = {"create", "schedule", "update", "delete", "retrieve"}
    if value in allowed:
        return value  # type: ignore[return-value]
    return "retrieve"
