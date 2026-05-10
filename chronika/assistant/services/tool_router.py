from __future__ import annotations

from datetime import datetime, timedelta, timezone as datetime_timezone
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from assistant.integrations.semantic_search import SemanticSearchService
from events.models import Event, UserCalendar
from events.services import EventWriteService, add_event_extended_properties
from tasks.models import Priority, Task
from tasks.services import (
    create_task,
    delete_task,
    find_task_for_user_title_icontains,
    get_default_user_calendar,
    get_task_for_user,
    tasks_for_user_queryset,
    update_task,
)

from .scheduler_service import SchedulerService

# Строгий семантический отбор для разрешения target у мутаций (update/delete).
TARGET_RESOLUTION_SEMANTIC_THRESHOLD = 0.7
TARGET_RESOLUTION_MAX_CANDIDATES = 3


class ToolRouter:
    def __init__(self, *, user):
        self.user = user
        self.user_tz = self._resolve_user_tz()
        self.scheduler = SchedulerService()
        self.semantic_search = SemanticSearchService()

    def execute(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            fn = getattr(self, f"_tool_{tool_name}", None)
            if fn is None:
                return self._err("unknown_tool", f"Unknown tool: {tool_name}", recoverable=False)
            return fn(payload)
        except Exception as exc:
            return self._err("tool_execution_failed", str(exc), recoverable=True)

    def _tool_create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        calendar = get_default_user_calendar(self.user)
        if not calendar:
            return self._err("calendar_not_found", "У пользователя нет основного календаря.", recoverable=True)
        task = create_task(
            user=self.user,
            calendar=calendar,
            title=str(payload.get("title") or "").strip(),
            duration=payload.get("duration") or 30,
            due_date=self._parse_dt(payload.get("due_date")),
            priority=self._normalize_priority(payload.get("priority")),
        )
        return {"ok": True, "data": {"task": self._task_out(task)}}

    def _tool_update_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = self._resolve_task(payload)
        if not task:
            return self._err("task_not_found", "Task not found", recoverable=True)
        updates = dict(payload.get("updates") or {})
        kwargs: dict[str, Any] = {}
        for key in ("title", "duration", "completed", "notes"):
            if key in updates:
                kwargs[key] = updates[key]
        if "due_date" in updates:
            kwargs["due_date"] = self._parse_dt(updates.get("due_date"))
        if "priority" in updates:
            kwargs["priority"] = self._normalize_priority(updates.get("priority"))
        task = update_task(task, **kwargs)
        return {"ok": True, "data": {"task": self._task_out(task)}}

    def _tool_delete_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = self._resolve_task(payload)
        if not task:
            return self._err("task_not_found", "Task not found", recoverable=True)
        deleted_id = delete_task(task)
        return {"ok": True, "data": {"deleted_id": deleted_id}}

    def _tool_create_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        calendar = self._resolve_default_calendar()
        if not calendar:
            return self._err("calendar_not_found", "У пользователя нет основного календаря.", recoverable=True)
        start = self._require_dt(payload.get("start"), "start")
        end = self._parse_dt(payload.get("end"))
        if not end:
            end = start + timedelta(minutes=int(payload.get("duration_minutes") or 60))
        task_id = self._validated_task_id(payload.get("task_id"))
        summary = str(payload.get("title") or payload.get("summary") or "").strip()
        event_data = {
            "summary": summary,
            "description": payload.get("description"),
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        try:
            local_event = EventWriteService().create_calendar_event(
                user=self.user,
                user_calendar=calendar,
                event_data=event_data,
                task_id=task_id,
                enqueue_embedding=True,
            )
        except Exception as exc:
            return self._err("tool_execution_failed", str(exc), recoverable=True)
        return {"ok": True, "data": {"event": self._event_out(local_event)}}

    def _tool_update_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = self._resolve_event(payload)
        if not event:
            return self._err("event_not_found", "Event not found", recoverable=True)
        updates = dict(payload.get("updates") or {})
        patch_data = self._event_updates_to_google_patch(updates)
        try:
            EventWriteService().update_calendar_event(
                user=self.user,
                user_calendar=event.user_calendar,
                event=event,
                patch_data=patch_data,
            )
        except Exception as exc:
            return self._err("tool_execution_failed", str(exc), recoverable=True)
        event.refresh_from_db()
        return {"ok": True, "data": {"event": self._event_out(event)}}

    def _tool_delete_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = self._resolve_event(payload)
        if not event:
            return self._err("event_not_found", "Event not found", recoverable=True)
        deleted_id = event.id
        user_calendar = event.user_calendar
        try:
            EventWriteService().delete_calendar_event(
                user=self.user,
                user_calendar=user_calendar,
                event=event,
            )
        except Exception as exc:
            return self._err("tool_execution_failed", str(exc), recoverable=True)
        return {"ok": True, "data": {"deleted_id": deleted_id}}

    def _tool_move_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload["updates"] = {"start": payload.get("start"), "end": payload.get("end")}
        return self._tool_update_event(payload)

    def _tool_get_calendar(self, payload: dict[str, Any]) -> dict[str, Any]:
        date_from = self._parse_dt(payload.get("date_from"))
        date_to = self._parse_dt(payload.get("date_to"))
        qs = Event.objects.filter(user_calendar__user=self.user)
        if date_from:
            qs = qs.filter(end__gte=date_from)
        if date_to:
            qs = qs.filter(start__lte=date_to)
        return {"ok": True, "data": {"events": [self._event_out(ev) for ev in qs[:100]]}}

    def _tool_search_entities(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        entity_type = str(payload.get("entity_type") or "all").strip().lower()
        filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
        limit = 10
        similarity_threshold = 0.65
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, Any]] = set()

        def _append_item(entry: dict[str, Any]) -> None:
            key = (str(entry.get("entity_type") or ""), entry.get("id"))
            if key in seen:
                return
            seen.add(key)
            items.append(entry)

        # List mode: no semantic query provided, return filtered entities directly.
        if not query:
            if entity_type in {"task", "all"}:
                for task in self._list_tasks_filtered(filters=filters, limit=limit):
                    _append_item({"id": task.id, "entity_type": "task", "data": self._task_out(task)})
            if entity_type in {"event", "all"}:
                for ev in self._list_events_filtered(filters=filters, limit=limit):
                    _append_item({"id": ev.id, "entity_type": "event", "data": self._event_out(ev)})
            return {"ok": True, "data": {"items": items, "total": len(items)}}

        # Primary path: semantic search (query is treated as intent text, not strict title substring).
        include_completed_tasks = self._to_bool(filters.get("completed")) is True
        include_past_events = bool(filters.get("date_from"))
        vec = self._encode_query_embedding(query)
        if vec:
            scope = "tasks" if entity_type == "task" else "events" if entity_type == "event" else "all"
            for c in self.semantic_search.find_candidates(
                user=self.user,
                embedding=vec,
                similarity_threshold=similarity_threshold,
                scope=scope,
                limit=limit,
                include_completed_tasks=include_completed_tasks,
                include_past_events=include_past_events,
                query=self._build_semantic_query(query=query, filters=filters),
            ):
                if c.entity_type == "task":
                    _append_item({"id": c.object_id, "entity_type": "task", "data": self._task_out(c.payload)})
                else:
                    _append_item({"id": c.object_id, "entity_type": "event", "data": self._event_out(c.payload)})

        return {"ok": True, "data": {"items": items, "total": len(items)}}

    def candidate_items_for_target_resolution(
        self,
        *,
        query: str,
        entity_type: str,
        similarity_threshold: float | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Кандидаты для подстановки task_id/event_id: высокий порог сходства, не более ``limit``.
        Формат элементов как у ``search_entities`` (id, entity_type, data).
        При пустой семантике — узкий лексический fallback (задача: одна по подстроке заголовка;
        событие: до ``limit`` по подстроке summary).
        """
        threshold = (
            float(similarity_threshold)
            if similarity_threshold is not None
            else TARGET_RESOLUTION_SEMANTIC_THRESHOLD
        )
        max_n = int(limit if limit is not None else TARGET_RESOLUTION_MAX_CANDIDATES)
        q = str(query or "").strip()
        if not q:
            return []
        sq = self._build_semantic_query(query=q, filters={})
        vec = self._encode_query_embedding(q)
        items: list[dict[str, Any]] = []
        et = str(entity_type or "").strip().lower()
        if vec:
            if et == "task":
                for c in self.semantic_search.find_tasks(
                    user=self.user,
                    embedding=vec,
                    similarity_threshold=threshold,
                    limit=max_n,
                    include_completed_tasks=True,
                    query=sq,
                ):
                    if isinstance(c.payload, Task):
                        items.append(
                            {
                                "id": c.object_id,
                                "entity_type": "task",
                                "data": self._task_out(c.payload),
                            }
                        )
            elif et == "event":
                for c in self.semantic_search.find_events(
                    user=self.user,
                    embedding=vec,
                    similarity_threshold=threshold,
                    limit=max_n,
                    include_past_events=True,
                    query=sq,
                ):
                    if isinstance(c.payload, Event):
                        items.append(
                            {
                                "id": c.object_id,
                                "entity_type": "event",
                                "data": self._event_out(c.payload),
                            }
                        )
        if items:
            return items[:max_n]
        if et == "task":
            task = find_task_for_user_title_icontains(self.user, q)
            if task:
                return [
                    {"id": task.id, "entity_type": "task", "data": self._task_out(task)}
                ]
            return []
        if et == "event":
            matches = list(
                Event.objects.filter(
                    user_calendar__user=self.user, summary__icontains=q
                ).order_by("-updated")[:max_n]
            )
            return [
                {"id": ev.id, "entity_type": "event", "data": self._event_out(ev)}
                for ev in matches
            ]
        return []

    def _tool_find_slots(self, payload: dict[str, Any]) -> dict[str, Any]:
        start = self._require_dt(payload.get("window_start"), "window_start")
        end = self._require_dt(payload.get("window_end"), "window_end")
        duration = int(payload.get("duration_minutes") or 60)
        events = list(
            Event.objects.filter(
                user_calendar__user=self.user,
            ).filter(Q(start__lt=end) & Q(end__gt=start))
        )
        preference_context = self._build_preference_context(payload)
        slots = self.scheduler.suggest_slots_in_window(
            events=events,
            window_start=start,
            window_end=end,
            duration_minutes=duration,
            limit=int(payload.get("limit") or 5),
            preference_context=preference_context,
        )
        return {"ok": True, "data": {"slots": slots}}

    def _build_preference_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        planning_context = dict(payload.get("planning_context") or {})
        target_embedding = self._resolve_planning_embedding(planning_context)
        history_events = list(
            Event.objects.filter(
                user_calendar__user=self.user,
                start__isnull=False,
                embedding__isnull=False,
            ).order_by("-start")[:500]
        )
        return {
            "target_embedding": target_embedding,
            "history_events": history_events,
        }

    def _resolve_planning_embedding(self, planning_context: dict[str, Any]) -> list[float]:
        task_id = self._validated_task_id(planning_context.get("task_id"))
        if task_id:
            task = get_task_for_user(self.user, task_id)
            if task and task.embedding is not None:
                return task.embedding.tolist() if hasattr(task.embedding, "tolist") else list(task.embedding)

        title = str(planning_context.get("title") or "").strip()
        if not title:
            return []
        try:
            from assistant.integrations.embeddings_model import EmbeddingsModelProvider

            embedding = EmbeddingsModelProvider.encode(title)
            if hasattr(embedding, "tolist"):
                return embedding.tolist()
            return list(embedding or [])
        except Exception:
            return []

    def _resolve_task(self, payload: dict[str, Any]) -> Task | None:
        tid = payload.get("task_id")
        if tid is not None:
            try:
                return get_task_for_user(self.user, int(tid))
            except (TypeError, ValueError):
                return None
        query = str(payload.get("target_query") or "").strip()
        if not query:
            return None
        items = self.candidate_items_for_target_resolution(
            query=query, entity_type="task"
        )
        if len(items) != 1:
            return None
        pk = items[0].get("id")
        try:
            return get_task_for_user(self.user, int(pk))
        except (TypeError, ValueError):
            return None

    def _event_updates_to_google_patch(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Поля для Google Calendar patch из словаря обновлений ассистента."""
        patch: dict[str, Any] = {}
        if "summary" in updates or "title" in updates:
            patch["summary"] = (updates.get("summary") or updates.get("title") or "").strip()
        if "description" in updates:
            patch["description"] = updates.get("description")
        if "start" in updates:
            dt = self._parse_dt(updates.get("start"))
            if dt:
                patch["start"] = {"dateTime": dt.isoformat()}
        if "end" in updates:
            dt = self._parse_dt(updates.get("end"))
            if dt:
                patch["end"] = {"dateTime": dt.isoformat()}
        if "task_id" in updates:
            tid = self._validated_task_id(updates.get("task_id"))
            add_event_extended_properties(patch, tid)
        return patch

    def _resolve_event(self, payload: dict[str, Any]) -> Event | None:
        if payload.get("event_id"):
            return Event.objects.filter(user_calendar__user=self.user, id=payload["event_id"]).first()
        query = str(payload.get("target_query") or "").strip()
        if not query:
            return None
        items = self.candidate_items_for_target_resolution(
            query=query, entity_type="event"
        )
        if len(items) != 1:
            return None
        pk = items[0].get("id")
        try:
            return Event.objects.filter(
                user_calendar__user=self.user, id=int(pk)
            ).first()
        except (TypeError, ValueError):
            return None

    def _task_out(self, task: Task) -> dict[str, Any]:
        return {
            "id": task.id,
            "title": task.title,
            "due_date": self._to_user_iso(task.due_date),
            "duration": task.duration,
            "priority": task.priority,
            "completed": task.completed,
        }

    def _event_out(self, ev: Event) -> dict[str, Any]:
        return {
            "id": ev.id,
            "summary": ev.summary,
            "title": ev.summary,
            "description": ev.description,
            "start": self._to_user_iso(ev.start),
            "end": self._to_user_iso(ev.end),
            "task_id": ev.task_id,
        }

    def _parse_dt(self, raw):
        if not raw:
            return None
        if isinstance(raw, datetime):
            dt = raw
        else:
            dt = datetime.fromisoformat(str(raw))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone=self.user_tz)
        return dt.astimezone(datetime_timezone.utc)

    def _require_dt(self, raw, field: str):
        dt = self._parse_dt(raw)
        if not dt:
            raise ValueError(f"{field} is required")
        return dt

    def _normalize_priority(self, value) -> str:
        if value is None:
            return Priority.NONE
        if isinstance(value, str) and not value.strip():
            return Priority.NONE
        val = str(value).strip().upper()
        return val if val in Priority.values else Priority.NONE

    @staticmethod
    def _validated_task_id(raw_task_id: Any) -> int | None:
        try:
            parsed = int(raw_task_id)
        except (TypeError, ValueError):
            return None
        return parsed if Task.objects.filter(id=parsed).exists() else None

    def _resolve_default_calendar(self) -> UserCalendar | None:
        return get_default_user_calendar(self.user)

    def _list_tasks_filtered(self, *, filters: dict[str, Any], limit: int) -> list[Task]:
        qs = tasks_for_user_queryset(self.user)
        completed = self._to_bool(filters.get("completed"))
        if completed is None:
            qs = qs.filter(completed=False)
        else:
            qs = qs.filter(completed=completed)
        if filters.get("priority"):
            qs = qs.filter(priority=str(filters.get("priority")).upper())
        date_from = self._parse_dt(filters.get("date_from"))
        date_to = self._parse_dt(filters.get("date_to"))
        if date_from:
            qs = qs.filter(due_date__gte=date_from)
        if date_to:
            qs = qs.filter(due_date__lte=date_to)
        return list(qs.order_by("-updated")[:limit])

    def _list_events_filtered(self, *, filters: dict[str, Any], limit: int) -> list[Event]:
        qs = Event.objects.filter(user_calendar__user=self.user)
        date_from = self._parse_dt(filters.get("date_from"))
        date_to = self._parse_dt(filters.get("date_to"))
        if date_from:
            qs = qs.filter(end__gte=date_from)
        if date_to:
            qs = qs.filter(start__lte=date_to)
        return list(qs.order_by("-updated")[:limit])

    @staticmethod
    def _encode_query_embedding(text: str) -> list[float]:
        q = str(text or "").strip()
        if not q:
            return []
        try:
            from assistant.integrations.embeddings_model import EmbeddingsModelProvider

            emb = EmbeddingsModelProvider.encode(q)
            return emb.tolist() if hasattr(emb, "tolist") else list(emb or [])
        except Exception:
            return []

    @staticmethod
    def _build_semantic_query(*, query: str, filters: dict[str, Any]) -> dict[str, Any]:
        semantic_query: dict[str, Any] = {"title": query, "summary": query}
        mapped_values = {
            "start": filters.get("date_from"),
            "due_date": filters.get("date_from"),
            "end": filters.get("date_to"),
            "priority": filters.get("priority"),
            "completed": filters.get("completed"),
        }
        for key, value in mapped_values.items():
            if value is not None:
                semantic_query[key] = value
        return semantic_query

    @staticmethod
    def _to_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
        return None

    def _err(self, code: str, message: str, *, recoverable: bool) -> dict[str, Any]:
        return {"ok": False, "error": {"code": code, "message": message, "recoverable": recoverable}}

    def _to_user_iso(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        dt = value if timezone.is_aware(value) else timezone.make_aware(value, timezone=datetime_timezone.utc)
        return dt.astimezone(self.user_tz).isoformat()

    def _resolve_user_tz(self):
        raw_tz = str(getattr(self.user, "time_zone", "") or "UTC")
        try:
            return ZoneInfo(raw_tz)
        except Exception:
            return ZoneInfo("UTC")
