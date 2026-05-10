from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .datetime_context import DateTimeContext
from .pending_store import PendingStore
from .tool_router import ToolRouter


class OrchestrationPolicy:
    def __init__(self, *, pending_store: PendingStore, tool_router: ToolRouter, datetime_context: DateTimeContext):
        self.pending_store = pending_store
        self.tool_router = tool_router
        self.datetime_context = datetime_context

    @staticmethod
    def is_mutation_tool(tool_name: str) -> bool:
        return tool_name in {
            "create_task",
            "update_task",
            "delete_task",
            "create_event",
            "update_event",
            "delete_event",
            "move_event",
        }

    def needs_confirmation(self, tool_name: str, *, total_mutations: int) -> bool:
        if tool_name in {"create_task", "update_task"}:
            return False
        if total_mutations >= 2 and self.is_mutation_tool(tool_name):
            return True
        return tool_name in {"delete_task", "delete_event"}

    def normalize_tool_payload(self, tool_name: str, payload: dict[str, Any], *, user_tz: str) -> dict[str, Any]:
        data = dict(payload or {})
        if tool_name == "create_task":
            if not data.get("title"):
                return {"ok": False, "message": "create_task requires title"}
            if data.get("duration") is None:
                data["duration"] = 30
            return {"ok": True, "tool_name": tool_name, "payload": data}

        if tool_name == "create_event":
            title = data.get("title") or data.get("summary")
            start = data.get("start")
            end = data.get("end")
            if not title or not start:
                return {"ok": False, "message": "create_event requires title and start"}
            if end is None:
                duration = int(data.get("duration_minutes") or 60)
                start_dt = datetime.fromisoformat(str(start))
                data["end"] = (start_dt + timedelta(minutes=max(15, duration))).isoformat()
            data["summary"] = title
            data.pop("title", None)
            data.pop("duration_minutes", None)
            return {"ok": True, "tool_name": tool_name, "payload": self.datetime_context.normalize_action(data, user_tz=user_tz)}

        if tool_name in {"update_task", "update_event"}:
            updates = dict(data.get("updates") or {})
            if not updates:
                updates = {k: v for k, v in data.items() if k not in {"task_id", "event_id", "target_query", "updates"}}
            if tool_name == "update_event" and "title" in updates and "summary" not in updates:
                updates["summary"] = updates.pop("title")
            normalized_updates = self.datetime_context.normalize_action(updates, user_tz=user_tz)
            base = {
                "target_query": data.get("target_query"),
                "updates": normalized_updates,
            }
            if tool_name == "update_task":
                base["task_id"] = data.get("task_id")
            else:
                base["event_id"] = data.get("event_id")
            return {"ok": True, "tool_name": tool_name, "payload": base}

        if tool_name == "move_event":
            updates = dict(data.get("updates") or {})
            if data.get("start") is not None:
                updates["start"] = data.get("start")
            if data.get("end") is not None:
                updates["end"] = data.get("end")
            return {
                "ok": True,
                "tool_name": "update_event",
                "payload": {
                    "event_id": data.get("event_id"),
                    "target_query": data.get("target_query"),
                    "updates": self.datetime_context.normalize_action(updates, user_tz=user_tz),
                },
            }

        if tool_name in {"delete_task", "delete_event", "find_slots", "search_entities", "get_calendar", "confirm_action", "cancel_action", "modify_action"}:
            return {"ok": True, "tool_name": tool_name, "payload": self.datetime_context.normalize_action(data, user_tz=user_tz)}

        return {"ok": False, "message": f"Unsupported tool: {tool_name}"}

    def resolve_target_for_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],
        *,
        user_text: str,
    ) -> dict[str, Any]:
        target_field = None
        entity_type = None
        if tool_name in {"update_task", "delete_task"}:
            target_field, entity_type = "task_id", "task"
        elif tool_name in {"update_event", "delete_event"}:
            target_field, entity_type = "event_id", "event"
        if not target_field:
            return {"status": "ok"}
        if str(payload.get(target_field) or "").strip():
            return {"status": "ok"}
        query = str(payload.get("target_query") or user_text).strip()
        if not query:
            return {"status": "failed", "message": "target query is missing"}
        items = self.tool_router.candidate_items_for_target_resolution(
            query=query,
            entity_type=entity_type,
        )
        if not items:
            return {"status": "failed", "message": f"{entity_type} not found"}
        if len(items) == 1:
            payload[target_field] = items[0]["id"]
            return {"status": "ok"}
        return {"status": "needs_disambiguation", "candidates": list(items)}
