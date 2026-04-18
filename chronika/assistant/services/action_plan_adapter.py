from __future__ import annotations

from assistant.domain.action_plan import Action, ActionPlan, ActionType, Entity
from assistant.services.intent_parser import ParsedIntent

_ACTION_TYPES: frozenset[str] = frozenset({"create", "schedule", "update", "delete", "retrieve"})


def parsed_intents_to_action_plan(items: list[ParsedIntent]) -> ActionPlan:
    entities: list[Entity] = []
    actions: list[Action] = []
    for idx, item in enumerate(items):
        if item.action == "other":
            continue

        eid = f"e{idx}"
        aid = f"a{idx}"
        title = ""
        fields = item.fields if isinstance(item.fields, dict) else {}
        if fields.get("title"):
            title = str(fields["title"])
        elif fields.get("summary"):
            title = str(fields["summary"])

        meta: dict = {}
        if item.datetime:
            meta["datetime"] = item.datetime
        if item.filters:
            meta["filters"] = item.filters

        entities.append(
            Entity(
                id=0,
                context_id=eid,
                type=str(item.entity_type or "unknown"),
                title=title,
                meta=meta,
            )
        )

        action_type: ActionType = item.action if item.action in _ACTION_TYPES else "retrieve"

        actions.append(
            Action(
                context_id=aid,
                type=action_type,
                target_id=None,
                data={
                    "action": item.action,
                    "entity_type": item.entity_type,
                    "query": item.query,
                    "fields": dict(fields),
                    "datetime": dict(item.datetime) if item.datetime else {},
                    "meta": dict(item.meta) if item.meta else {},
                    "filters": dict(item.filters) if item.filters else {},
                },
            )
        )

    return ActionPlan(actions=actions, entities=entities)
