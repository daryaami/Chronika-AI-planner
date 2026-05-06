from __future__ import annotations

from datetime import datetime, timedelta, timezone as datetime_timezone
from typing import Any
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from assistant.integrations.semantic_search import SemanticSearchService
from core.enums import EmbeddingStatus
from events.models import Event, UserCalendar
from events.tasks import generate_event_embedding
from tasks.models import Priority, Task
from tasks.services import enqueue_task_embedding

from .scheduler_service import SchedulerService


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
        calendar = self._resolve_default_calendar()
        if not calendar:
            return self._err("calendar_not_found", "У пользователя нет основного календаря.", recoverable=True)
        task = Task.objects.create(
            user=self.user,
            calendar=calendar,
            title=str(payload.get("title") or "").strip(),
            duration=payload.get("duration") or 30,
            due_date=self._parse_dt(payload.get("due_date")),
            priority=self._normalize_priority(payload.get("priority")),
        )
        enqueue_task_embedding(task)
        return {"ok": True, "data": {"task": self._task_out(task)}}

    def _tool_update_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = self._resolve_task(payload)
        if not task:
            return self._err("task_not_found", "Task not found", recoverable=True)
        updates = dict(payload.get("updates") or {})
        should_refresh_embedding = any(key in updates for key in {"title", "notes"})
        for key in ("title", "duration", "completed", "notes"):
            if key in updates:
                setattr(task, key, updates[key])
        if "due_date" in updates:
            task.due_date = self._parse_dt(updates.get("due_date"))
        if "priority" in updates:
            task.priority = self._normalize_priority(updates.get("priority"))
        task.save()
        if should_refresh_embedding:
            enqueue_task_embedding(task)
        return {"ok": True, "data": {"task": self._task_out(task)}}

    def _tool_delete_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = self._resolve_task(payload)
        if not task:
            return self._err("task_not_found", "Task not found", recoverable=True)
        deleted_id = task.id
        task.delete()
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
        event = Event.objects.create(
            user_calendar=calendar,
            summary=str(payload.get("title") or payload.get("summary") or "").strip(),
            description=payload.get("description"),
            start=start,
            end=end,
            htmlLink=payload.get("htmlLink"),
            organizer_email=payload.get("organizer_email"),
            task_id=task_id,
            embedding_status=EmbeddingStatus.PENDING,
        )
        transaction.on_commit(lambda event_id=event.id: generate_event_embedding.delay(event_id))
        return {"ok": True, "data": {"event": self._event_out(event)}}

    def _tool_update_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = self._resolve_event(payload)
        if not event:
            return self._err("event_not_found", "Event not found", recoverable=True)
        updates = dict(payload.get("updates") or {})
        old_summary = event.summary
        old_description = event.description
        if "summary" in updates or "title" in updates:
            event.summary = updates.get("summary") or updates.get("title")
        if "description" in updates:
            event.description = updates.get("description")
        if "start" in updates:
            event.start = self._parse_dt(updates.get("start"))
        if "end" in updates:
            event.end = self._parse_dt(updates.get("end"))
        if "task_id" in updates:
            event.task_id = self._validated_task_id(updates.get("task_id"))
        if "htmlLink" in updates:
            event.htmlLink = updates.get("htmlLink")
        if "organizer_email" in updates:
            event.organizer_email = updates.get("organizer_email")
        text_fields_changed = event.summary != old_summary or event.description != old_description
        if text_fields_changed:
            event.embedding_status = EmbeddingStatus.PENDING
        event.save()
        if text_fields_changed:
            transaction.on_commit(lambda event_id=event.id: generate_event_embedding.delay(event_id))
        return {"ok": True, "data": {"event": self._event_out(event)}}

    def _tool_delete_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = self._resolve_event(payload)
        if not event:
            return self._err("event_not_found", "Event not found", recoverable=True)
        deleted_id = event.id
        event.delete()
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
        vec = []
        try:
            from assistant.integrations.embeddings_model import EmbeddingsModelProvider

            emb = EmbeddingsModelProvider.encode(query)
            vec = emb.tolist() if hasattr(emb, "tolist") else list(emb or [])
        except Exception:
            vec = []
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
            task = Task.objects.filter(user=self.user, id=task_id).first()
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
        if payload.get("task_id"):
            return Task.objects.filter(user=self.user, id=payload["task_id"]).first()
        query = str(payload.get("target_query") or "").strip()
        if query:
            return Task.objects.filter(user=self.user, title__icontains=query).order_by("-updated").first()
        return None

    def _resolve_event(self, payload: dict[str, Any]) -> Event | None:
        if payload.get("event_id"):
            return Event.objects.filter(user_calendar__user=self.user, id=payload["event_id"]).first()
        query = str(payload.get("target_query") or "").strip()
        if query:
            return Event.objects.filter(user_calendar__user=self.user, summary__icontains=query).order_by("-updated").first()
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
        val = str(value or Priority.MEDIUM).upper()
        return val if val in Priority.values else Priority.MEDIUM

    @staticmethod
    def _validated_task_id(raw_task_id: Any) -> int | None:
        try:
            parsed = int(raw_task_id)
        except (TypeError, ValueError):
            return None
        return parsed if Task.objects.filter(id=parsed).exists() else None

    def _resolve_default_calendar(self) -> UserCalendar | None:
        return (
            UserCalendar.objects.filter(user=self.user, primary=True).order_by("-updated_at").first()
            or UserCalendar.objects.filter(user=self.user, selected=True).order_by("-updated_at").first()
            or UserCalendar.objects.filter(user=self.user).order_by("-updated_at").first()
        )

    def _list_tasks_filtered(self, *, filters: dict[str, Any], limit: int) -> list[Task]:
        qs = Task.objects.filter(user=self.user)
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
