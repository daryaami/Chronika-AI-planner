from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from django.db.models import F, QuerySet
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
    ) -> list[SemanticSearchCandidate]:
        self._log(
            "find_candidates.start",
            scope=scope,
            user_id=getattr(user, "id", None),
            embedding_dim=len(embedding) if embedding is not None else 0,
            similarity_threshold=similarity_threshold,
            limit=limit,
        )
        if scope == "tasks":
            candidates = self.find_tasks(
                user=user,
                embedding=embedding,
                similarity_threshold=similarity_threshold,
                limit=limit,
            )
            self._log("find_candidates.done", scope=scope, candidates=len(candidates))
            return candidates
        if scope == "events":
            candidates = self.find_events(
                user=user,
                embedding=embedding,
                similarity_threshold=similarity_threshold,
                limit=limit,
            )
            self._log("find_candidates.done", scope=scope, candidates=len(candidates))
            return candidates
        if scope == "all":
            task_candidates = self.find_tasks(
                user=user,
                embedding=embedding,
                similarity_threshold=similarity_threshold,
                limit=limit,
            )
            event_candidates = self.find_events(
                user=user,
                embedding=embedding,
                similarity_threshold=similarity_threshold,
                limit=limit,
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
    ) -> list[SemanticSearchCandidate]:
        self._log(
            "find_tasks.start",
            user_id=getattr(user, "id", None),
            similarity_threshold=similarity_threshold,
            limit=limit,
        )
        queryset = self._build_tasks_queryset(
            user=user,
            embedding=embedding,
            similarity_threshold=similarity_threshold,
            limit=limit,
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
        self._log("find_tasks.done", candidates=len(candidates))
        return candidates

    def find_events(
        self,
        *,
        user,
        embedding: list[float],
        similarity_threshold: float,
        limit: int = 10,
    ) -> list[SemanticSearchCandidate]:
        self._log(
            "find_events.start",
            user_id=getattr(user, "id", None),
            similarity_threshold=similarity_threshold,
            limit=limit,
        )
        queryset = self._build_events_queryset(
            user=user,
            embedding=embedding,
            similarity_threshold=similarity_threshold,
            limit=limit,
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
        self._log("find_events.done", candidates=len(candidates))
        return candidates

    def _build_tasks_queryset(
        self,
        *,
        user,
        embedding: list[float],
        similarity_threshold: float,
        limit: int,
    ) -> QuerySet[Task]:
        distance_threshold = self._similarity_to_distance(similarity_threshold)
        return (
            Task.objects.filter(
                user=user,
                embedding__isnull=False,
                embedding_status=EmbeddingStatus.COMPLETED,
            )
            .annotate(distance=CosineDistance("embedding", embedding))
            .filter(distance__lte=distance_threshold)
            .order_by("distance", F("updated").desc(nulls_last=True))
        )[:limit]

    def _build_events_queryset(
        self,
        *,
        user,
        embedding: list[float],
        similarity_threshold: float,
        limit: int,
    ) -> QuerySet[Event]:
        distance_threshold = self._similarity_to_distance(similarity_threshold)
        return (
            Event.objects.filter(
                user_calendar__user=user,
                embedding__isnull=False,
                embedding_status=EmbeddingStatus.COMPLETED,
            )
            .select_related("user_calendar", "task")
            .annotate(distance=CosineDistance("embedding", embedding))
            .filter(distance__lte=distance_threshold)
            .order_by("distance", F("updated").desc(nulls_last=True))
        )[:limit]

    @staticmethod
    def _similarity_to_distance(similarity_threshold: float) -> float:
        normalized = max(0.0, min(1.0, float(similarity_threshold)))
        return 1.0 - normalized

    @staticmethod
    def _distance_to_similarity(distance: Any) -> float:
        if distance is None:
            return 0.0
        return max(0.0, 1.0 - float(distance))

    @staticmethod
    def _log(event: str, **kwargs: Any) -> None:
        details = " ".join(f"{key}={value}" for key, value in kwargs.items())
        print(f"[SemanticSearch] {event} {details}".rstrip())
