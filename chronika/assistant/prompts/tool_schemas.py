from __future__ import annotations

from typing import Any, Dict, List


def get_orchestrator_tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "Create a task. If user does not specify duration, infer a sensible duration in minutes. If user states a due day or deadline, set due_date as timezone-aware ISO 8601 using the request runtime_context.now_iso and runtime_context.user_tz (do not guess the calendar date). Omit due_date only when no day/deadline was stated.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "duration": {"type": ["integer", "null"]},
                        "due_date": {"type": ["string", "null"]},
                        "category": {"type": ["string", "null"]},
                        "priority": {"type": ["string", "null"]},
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_task",
                "description": "Update task fields (duration minutes, due_date, title, priority, …). Use when the user changes how long a task takes or other task attributes — not modify_action. If conversation_context.last_entity.kind is task, use its id as task_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": ["string", "null"]},
                        "target_query": {"type": ["string", "null"]},
                        "updates": {"type": "object"},
                    },
                    "required": ["updates"],
                },
            },
        },
        {"type": "function", "function": {"name": "delete_task", "description": "Delete task by id or query.", "parameters": {"type": "object", "properties": {"task_id": {"type": ["string", "null"]}, "target_query": {"type": ["string", "null"]}}}}},
        {
            "type": "function",
            "function": {
                "name": "create_event",
                "description": "Create event. Call only after availability check for target interval (typically via get_calendar); if interval is busy, use find_slots instead of immediate creation. If user does not specify duration/end, infer a sensible duration and provide either end or duration_minutes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": ["string", "null"]},
                        "duration_minutes": {"type": ["integer", "null"]},
                        "task_id": {"type": ["string", "null"]},
                    },
                    "required": ["title", "start"],
                    "anyOf": [
                        {"required": ["end"]},
                        {"required": ["duration_minutes"]},
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_event",
                "description": "Update event by id or query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": ["string", "null"]},
                        "target_query": {"type": ["string", "null"]},
                        "updates": {"type": "object"},
                    },
                    "required": ["updates"],
                },
            },
        },
        {"type": "function", "function": {"name": "delete_event", "description": "Delete event by id or query.", "parameters": {"type": "object", "properties": {"event_id": {"type": ["string", "null"]}, "target_query": {"type": ["string", "null"]}}}}},
        {"type": "function", "function": {"name": "move_event", "description": "Move event by id or query.", "parameters": {"type": "object", "properties": {"event_id": {"type": ["string", "null"]}, "target_query": {"type": ["string", "null"]}, "start": {"type": ["string", "null"]}, "end": {"type": ["string", "null"]}, "updates": {"type": ["object", "null"]}}}}},
        {
            "type": "function",
            "function": {
                "name": "search_entities",
                "description": (
                    "Semantic search for listing or resolving tasks/events. "
                    "Pass query when you want semantic retrieval by title/description. "
                    "Pass filters when you need strict constraints (date range / priority / completed). "
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": ["string", "null"],
                            "description": "Intent text for semantic search.",
                        },
                        "entity_type": {
                            "type": ["string", "null"],
                            "enum": ["task", "event", "all", None],
                            "description": "Scope for semantic search results.",
                        },
                        "filters": {
                            "type": ["object", "null"],
                            "description": "Optional strict filters applied on top of semantic retrieval.",
                            "properties": {
                                "date_from": {"type": ["string", "null"], "description": "From date/datetime (YYYY-MM-DD or ISO)." },
                                "date_to": {"type": ["string", "null"], "description": "To date/datetime (YYYY-MM-DD or ISO)." },
                                "priority": {"type": ["string", "null"], "description": "Task priority filter."},
                                "completed": {"type": ["boolean", "string", "null"], "description": "Task completion filter."},
                            },
                        },
                    },
                },
            },
        },
        {"type": "function", "function": {"name": "get_calendar", "description": "Get calendar events in range. Use for availability/occupancy questions.", "parameters": {"type": "object", "properties": {"date_from": {"type": ["string", "null"]}, "date_to": {"type": ["string", "null"]}}}}},
        {
            "type": "function",
            "function": {
                "name": "find_slots",
                "description": "Find free slots for scheduling/rescheduling a specific event, not for generic availability checks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "window_start": {"type": "string"},
                        "window_end": {"type": "string"},
                        "duration_minutes": {"type": "integer"},
                        "limit": {"type": ["integer", "null"]},
                        "planning_context": {
                            "type": ["object", "null"],
                            "properties": {
                                "action": {"type": ["string", "null"]},
                                "title": {"type": ["string", "null"]},
                                "task_id": {"type": ["string", "null"]},
                            },
                            "required": ["action", "title"],
                        },
                    },
                    "required": ["window_start", "window_end", "duration_minutes"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "confirm_action",
                "description": "Confirm current pending action. Use only when pending_context is active. When there are multiple active pending items, pass pending_id explicitly, otherwise the first pending item or all items with same type will be confirmed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pending_id": {"type": ["string", "null"]},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_action",
                "description": "Cancel current pending action. Use only when pending_context is active. Prefer pending_ids for batch cancel, then pending_id for single cancel; otherwise the first pending item will be canceled.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pending_ids": {"type": ["array", "null"], "items": {"type": "string"}},
                        "pending_id": {"type": ["string", "null"]},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "modify_action",
                "description": "Adjust the active pending workflow only (e.g. slot_index). Use only when pending_context is active. Never use for task duration or task field edits — use update_task (e.g. updates.duration in minutes). When there are multiple active pending items, pass pending_id explicitly.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pending_id": {"type": ["string", "null"]},
                        "changes": {"type": "object"},
                    },
                    "required": ["changes"],
                },
            },
        },
    ]
