from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Literal

from django.db.models import F, QuerySet
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from pgvector.django import CosineDistance

from core.enums import EmbeddingStatus
from events.models import Event
from tasks.models import Task

SearchScope = Literal["tasks", "events", "all"]


@dataclass(frozen=True)
class SemanticSearchCandidate:
    entity_type: Literal["task", "event"]
    object_id: int
    similarity: float
    payload: Task | Event


class SemanticSearchService:
    """
    Семантический поиск похожих задач/событий по косинусной близости эмбеддингов.
    """

    def find_candidates(
        self,
        *,
        user,
        embedding: list[float],
        similarity_threshold: float,
        scope: SearchScope = "all",
        limit: int = 10,
        include_completed_tasks: bool = False,
        include_past_events: bool = False,
        query: dict[str, Any] | None = None,
    ) -> list[SemanticSearchCandidate]:
        self._log(
            "find_candidates.start",
            scope=scope,
            user_id=getattr(user, "id", None),
            embedding_dim=len(embedding) if embedding is not None else 0,
            similarity_threshold=similarity_threshold,
            limit=limit,
            include_completed_tasks=include_completed_tasks,
            include_past_events=include_past_events,
            query_keys=sorted((query or {}).keys()),
        )
        if scope == "tasks":
            candidates = self.find_tasks(
                user=user,
                embedding=embedding,
                similarity_threshold=similarity_threshold,
                limit=limit,
                include_completed_tasks=include_completed_tasks,
                query=query,
            )
            self._log("find_candidates.done", scope=scope, candidates=len(candidates))
            return candidates
        if scope == "events":
            candidates = self.find_events(
                user=user,
                embedding=embedding,
                similarity_threshold=similarity_threshold,
                limit=limit,
                include_past_events=include_past_events,
                query=query,
            )
            self._log("find_candidates.done", scope=scope, candidates=len(candidates))
            return candidates
        if scope == "all":
            task_candidates = self.find_tasks(
                user=user,
                embedding=embedding,
                similarity_threshold=similarity_threshold,
                limit=limit,
                include_completed_tasks=include_completed_tasks,
                query=query,
            )
            event_candidates = self.find_events(
                user=user,
                embedding=embedding,
                similarity_threshold=similarity_threshold,
                limit=limit,
                include_past_events=include_past_events,
                query=query,
            )
            candidates = sorted(
                task_candidates + event_candidates,
                key=lambda item: item.similarity,
                reverse=True,
            )[:limit]
            self._log(
                "find_candidates.done",
                scope=scope,
                task_candidates=len(task_candidates),
                event_candidates=len(event_candidates),
                merged_candidates=len(candidates),
            )
            return candidates
        raise ValueError("Unsupported search scope. Use: tasks, events or all.")

    def find_tasks(
        self,
        *,
        user,
        embedding: list[float],
        similarity_threshold: float,
        limit: int = 10,
        include_completed_tasks: bool = False,
        query: dict[str, Any] | None = None,
    ) -> list[SemanticSearchCandidate]:
        self._log(
            "find_tasks.start",
            user_id=getattr(user, "id", None),
            similarity_threshold=similarity_threshold,
            limit=limit,
            include_completed_tasks=include_completed_tasks,
            query_keys=sorted((query or {}).keys()),
        )
        fetch_limit = max(limit, limit * 5)
        queryset = self._build_tasks_queryset(
            user=user,
            embedding=embedding,
            similarity_threshold=similarity_threshold,
            limit=fetch_limit,
            include_completed_tasks=include_completed_tasks,
            query=query,
        )
        candidates = [
            SemanticSearchCandidate(
                entity_type="task",
                object_id=task.id,
                similarity=self._distance_to_similarity(task.distance),
                payload=task,
            )
            for task in queryset
        ]
        candidates = self._rerank_candidates(candidates=candidates, query=query)[:limit]
        self._log("find_tasks.done", candidates=len(candidates))
        return candidates

    def find_events(
        self,
        *,
        user,
        embedding: list[float],
        similarity_threshold: float,
        limit: int = 10,
        include_past_events: bool = False,
        query: dict[str, Any] | None = None,
    ) -> list[SemanticSearchCandidate]:
        self._log(
            "find_events.start",
            user_id=getattr(user, "id", None),
            similarity_threshold=similarity_threshold,
            limit=limit,
            include_past_events=include_past_events,
            query_keys=sorted((query or {}).keys()),
        )
        fetch_limit = max(limit, limit * 5)
        queryset = self._build_events_queryset(
            user=user,
            embedding=embedding,
            similarity_threshold=similarity_threshold,
            limit=fetch_limit,
            include_past_events=include_past_events,
            query=query,
        )
        candidates = [
            SemanticSearchCandidate(
                entity_type="event",
                object_id=event.id,
                similarity=self._distance_to_similarity(event.distance),
                payload=event,
            )
            for event in queryset
        ]
        candidates = self._rerank_candidates(candidates=candidates, query=query)[:limit]
        self._log("find_events.done", candidates=len(candidates))
        return candidates

    def _build_tasks_queryset(
        self,
        *,
        user,
        embedding: list[float],
        similarity_threshold: float,
        limit: int,
        include_completed_tasks: bool,
        query: dict[str, Any] | None,
    ) -> QuerySet[Task]:
        distance_threshold = self._similarity_to_distance(similarity_threshold)
        queryset = (
            Task.objects.filter(
                user=user,
                embedding__isnull=False,
                embedding_status=EmbeddingStatus.COMPLETED,
            )
        )
        if not include_completed_tasks:
            queryset = queryset.filter(completed=False)
        queryset = self._apply_task_query_filters(queryset, query=query)
        return queryset.annotate(distance=CosineDistance("embedding", embedding)).filter(
            distance__lte=distance_threshold
        ).order_by("distance", F("updated").desc(nulls_last=True))[:limit]

    def _build_events_queryset(
        self,
        *,
        user,
        embedding: list[float],
        similarity_threshold: float,
        limit: int,
        include_past_events: bool,
        query: dict[str, Any] | None,
    ) -> QuerySet[Event]:
        distance_threshold = self._similarity_to_distance(similarity_threshold)
        queryset = (
            Event.objects.filter(
                user_calendar__user=user,
                embedding__isnull=False,
                embedding_status=EmbeddingStatus.COMPLETED,
            )
            .select_related("user_calendar", "task")
        )
        if not include_past_events:
            now = timezone.now()
            cutoff = now - timedelta(days=2)
            queryset = queryset.filter(end__gte=cutoff)
        queryset = self._apply_event_query_filters(queryset, query=query)
        return queryset.annotate(distance=CosineDistance("embedding", embedding)).filter(
            distance__lte=distance_threshold
        ).order_by("distance", F("updated").desc(nulls_last=True))[:limit]

    @staticmethod
    def _similarity_to_distance(similarity_threshold: float) -> float:
        normalized = max(0.0, min(1.0, float(similarity_threshold)))
        return 1.0 - normalized

    @staticmethod
    def _distance_to_similarity(distance: Any) -> float:
        if distance is None:
            return 0.0
        return max(0.0, 1.0 - float(distance))

    def _rerank_candidates(
        self,
        *,
        candidates: list[SemanticSearchCandidate],
        query: dict[str, Any] | None,
    ) -> list[SemanticSearchCandidate]:
        if not query:
            return sorted(candidates, key=lambda item: item.similarity, reverse=True)

        has_strict_identifier = bool(
            self._normalize_text(query.get("title")) or self._normalize_text(query.get("summary"))
        )

        ranked = sorted(
            candidates,
            key=lambda item: self._candidate_sort_key(item, query, has_strict_identifier),
            reverse=True,
        )
        return ranked

    def _candidate_sort_key(
        self,
        candidate: SemanticSearchCandidate,
        query: dict[str, Any],
        has_strict_identifier: bool,
    ) -> tuple[float, float]:
        query_dt = self._extract_query_datetime(query)
        if query_dt is not None:
            # Если пользователь указал конкретную дату, дата становится
            # главным сигналом ранжирования, а семантика — вторым.
            date_score = self._candidate_date_score(candidate, query_dt)
            return (date_score, candidate.similarity)

        priority_score = self._query_priority_score(candidate, query)
        # Если есть явный идентификатор (title/summary), семантика остается главным
        # критерием: сначала сортируем по similarity, а приоритеты применяем только
        # внутри одинаково близких кандидатов.
        if has_strict_identifier:
            return (candidate.similarity, priority_score)

        # Если строгого идентификатора нет, оставляем мягкий contextual boost.
        semantic_bucket = round(candidate.similarity, 2)
        return (semantic_bucket, priority_score)

    def _candidate_date_score(self, candidate: SemanticSearchCandidate, query_dt) -> float:
        payload = candidate.payload
        if candidate.entity_type == "task":
            candidate_dt = getattr(payload, "due_date", None)
        else:
            candidate_dt = getattr(payload, "start", None) or getattr(payload, "end", None)
        return self._datetime_proximity_score(query_dt, candidate_dt)

    def _query_priority_score(self, candidate: SemanticSearchCandidate, query: dict[str, Any]) -> float:
        score = 0.0
        payload = candidate.payload

        title_query = self._normalize_text(query.get("title"))
        summary_query = self._normalize_text(query.get("summary"))
        description_query = self._normalize_text(query.get("description"))
        notes_query = self._normalize_text(query.get("notes"))

        if candidate.entity_type == "task":
            score += self._text_match_score(title_query, self._normalize_text(getattr(payload, "title", None)))
            score += self._text_match_score(notes_query, self._normalize_text(getattr(payload, "notes", None)))
            task_dt = getattr(payload, "due_date", None)
            query_dt = self._extract_query_datetime(query)
            score += self._datetime_proximity_score(query_dt, task_dt)
        else:
            score += self._text_match_score(summary_query, self._normalize_text(getattr(payload, "summary", None)))
            score += self._text_match_score(description_query, self._normalize_text(getattr(payload, "description", None)))
            event_dt = getattr(payload, "start", None) or getattr(payload, "end", None)
            query_dt = self._extract_query_datetime(query)
            score += self._datetime_proximity_score(query_dt, event_dt)

        return score

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    @staticmethod
    def _text_match_score(query_text: str, target_text: str) -> float:
        if not query_text or not target_text:
            return 0.0
        if query_text == target_text:
            return 0.8
        if query_text in target_text:
            return 0.5
        return 0.0

    def _extract_query_datetime(self, query: dict[str, Any]):
        raw = (
            query.get("due_date")
            or query.get("start")
            or query.get("end")
            or query.get("date")
        )
        if not raw:
            return None
        parsed_dt = parse_datetime(str(raw))
        if parsed_dt:
            if timezone.is_naive(parsed_dt):
                return timezone.make_aware(parsed_dt)
            return parsed_dt
        parsed_d = parse_date(str(raw))
        if parsed_d:
            return timezone.make_aware(datetime.combine(parsed_d, time.min))
        return None

    @staticmethod
    def _datetime_proximity_score(query_dt, candidate_dt) -> float:
        if not query_dt or not candidate_dt:
            return 0.0
        if timezone.is_naive(candidate_dt):
            candidate_dt = timezone.make_aware(candidate_dt)
        diff = abs((candidate_dt - query_dt).total_seconds())
        day_seconds = 86400.0
        if diff <= day_seconds:
            return 1.0
        if diff <= 2 * day_seconds:
            return 0.8
        if diff <= 3 * day_seconds:
            return 0.5
        if diff <= 7 * day_seconds:
            return 0.2
        return 0.0

    def _apply_task_query_filters(self, queryset: QuerySet[Task], query: dict[str, Any] | None) -> QuerySet[Task]:
        if not query:
            return queryset

        if "priority" in query and query.get("priority") is not None:
            queryset = queryset.filter(priority=str(query["priority"]).strip())
        if "completed" in query and query.get("completed") is not None:
            parsed_completed = self._to_bool(query["completed"])
            if parsed_completed is not None:
                queryset = queryset.filter(completed=parsed_completed)
        if "category_id" in query and query.get("category_id") is not None:
            queryset = queryset.filter(category_id=query["category_id"])

        query_dt = self._extract_query_datetime(query)
        if query_dt is not None:
            day_start = query_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            queryset = queryset.filter(due_date__gte=day_start, due_date__lt=day_end)

        return queryset

    def _apply_event_query_filters(self, queryset: QuerySet[Event], query: dict[str, Any] | None) -> QuerySet[Event]:
        if not query:
            return queryset

        if "google_event_id" in query and query.get("google_event_id"):
            queryset = queryset.filter(google_event_id=str(query["google_event_id"]).strip())
        if "google_calendar_id" in query and query.get("google_calendar_id"):
            queryset = queryset.filter(
                user_calendar__google_calendar_id=str(query["google_calendar_id"]).strip()
            )

        query_dt = self._extract_query_datetime(query)
        if query_dt is not None:
            day_start = query_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            queryset = queryset.filter(start__lt=day_end, end__gte=day_start)

        return queryset

    @staticmethod
    def _log(event: str, **kwargs: Any) -> None:
        details = " ".join(f"{key}={value}" for key, value in kwargs.items())
        print(f"[SemanticSearch] {event} {details}".rstrip())

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
