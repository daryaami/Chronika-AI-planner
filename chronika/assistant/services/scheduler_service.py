from __future__ import annotations

import os
from datetime import datetime, timedelta
import math
import random
from typing import Any

from events.models import Event


class SchedulerService:
    @staticmethod
    def _normalize_embedding(raw: Any) -> list[float]:
        if raw is None:
            return []
        if hasattr(raw, "tolist"):
            raw = raw.tolist()
        if not isinstance(raw, (list, tuple)):
            return []
        normalized: list[float] = []
        for value in raw:
            try:
                normalized.append(float(value))
            except (TypeError, ValueError):
                return []
        return normalized

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _gaussian(distance: float, sigma: float) -> float:
        sigma = max(1e-6, float(sigma))
        return math.exp(-0.5 * ((float(distance) / sigma) ** 2))

    @staticmethod
    def _hour_distance(hour_a: float, hour_b: float) -> float:
        # Keep hour preference cyclic, so 23:00 and 00:00 stay close.
        diff = abs(float(hour_a) - float(hour_b))
        return min(diff, 24.0 - diff)

    @staticmethod
    def _weekday_distance(day_a: int, day_b: int) -> int:
        diff = abs(int(day_a) - int(day_b))
        return min(diff, 7 - diff)

    def _continuous_preference_score(
        self,
        *,
        slot_start: datetime,
        target_embedding: list[float],
        history_events: list[Event],
        sigma_hour: float,
        sigma_weekday: float,
        recency_half_life_days: float | None = None,
    ) -> float:
        if not target_embedding or not history_events:
            return 0.0

        slot_hour = slot_start.hour + (slot_start.minute / 60.0)
        slot_weekday = slot_start.weekday()
        score = 0.0

        for ev in history_events:
            if not ev.start or ev.embedding is None:
                continue
            event_embedding = self._normalize_embedding(ev.embedding)
            if not event_embedding:
                continue
            sim = self._cosine_similarity(target_embedding, event_embedding)
            if sim == 0.0:
                continue

            event_hour = ev.start.hour + (ev.start.minute / 60.0)
            hour_score = self._gaussian(
                self._hour_distance(slot_hour, event_hour),
                sigma_hour,
            )
            weekday_score = self._gaussian(
                self._weekday_distance(slot_weekday, ev.start.weekday()),
                sigma_weekday,
            )
            recency_weight = 1.0
            if recency_half_life_days and recency_half_life_days > 0:
                age_days = max(
                    0.0,
                    (slot_start - ev.start).total_seconds() / 86400.0,
                )
                recency_weight = 0.5 ** (age_days / recency_half_life_days)
            score += sim * hour_score * weekday_score * recency_weight
        return score

    @staticmethod
    def _normalize_scores(values: list[float]) -> list[float]:
        if not values:
            return []
        low = min(values)
        high = max(values)
        if high - low <= 1e-9:
            return [0.5 for _ in values]
        return [(value - low) / (high - low) for value in values]

    @staticmethod
    def _intrinsic_slot_score(slot_start: datetime, window_start: datetime, window_end: datetime) -> float:
        # Normalize to [0, 1]: earlier slots in the requested window score higher.
        total_window_seconds = max(1.0, float((window_end - window_start).total_seconds()))
        offset_seconds = max(0.0, float((slot_start - window_start).total_seconds()))
        normalized = 1.0 - (offset_seconds / total_window_seconds)
        return round(max(0.0, min(1.0, normalized)), 6)

    @staticmethod
    def _align_to_step(dt: datetime, *, step_minutes: int) -> datetime:
        step_seconds = max(1, int(step_minutes)) * 60
        aligned = dt.replace(second=0, microsecond=0)
        seconds_since_hour = aligned.minute * 60
        remainder = seconds_since_hour % step_seconds
        if remainder == 0:
            return aligned
        return aligned + timedelta(seconds=step_seconds - remainder)

    def suggest_slots_in_window(
        self,
        *,
        events: list[Event],
        window_start: datetime,
        window_end: datetime,
        duration_minutes: int,
        limit: int = 5,
        step_minutes: int = 15,
        preference_context: dict[str, Any] | None = None,
    ) -> list[dict]:
        if duration_minutes <= 0:
            return []
        duration = timedelta(minutes=int(duration_minutes))
        step = timedelta(minutes=max(1, int(step_minutes)))
        pointer = self._align_to_step(window_start, step_minutes=step_minutes)
        candidate_slots: list[tuple[datetime, datetime, float, float]] = []

        preference_context = preference_context or {}
        target_embedding = self._normalize_embedding(preference_context.get("target_embedding"))
        history_events = list(preference_context.get("history_events") or [])
        sigma_hour = float(preference_context.get("sigma_hour") or 2.0)
        sigma_weekday = float(preference_context.get("sigma_weekday") or 1.0)
        recency_half_life_days = preference_context.get("recency_half_life_days")
        preference_weight = float(preference_context.get("preference_weight") or 0.8)
        preference_weight = max(0.0, min(1.0, preference_weight))
        intrinsic_weight = 1.0 - preference_weight

        simulate_scores = os.getenv("APP_AGENT_SIMULATE_SLOT_SCORES", "").strip().lower() == "true"
        while pointer + duration <= window_end:
            cand_end = pointer + duration
            blocked = False
            for ev in events:
                if not ev.start or not ev.end:
                    continue
                if ev.start < cand_end and ev.end > pointer:
                    blocked = True
                    break
            if not blocked:
                intrinsic_score = (
                    round(random.random(), 6)
                    if simulate_scores
                    else self._intrinsic_slot_score(pointer, window_start, window_end)
                )
                preference_score = self._continuous_preference_score(
                    slot_start=pointer,
                    target_embedding=target_embedding,
                    history_events=history_events,
                    sigma_hour=sigma_hour,
                    sigma_weekday=sigma_weekday,
                    recency_half_life_days=recency_half_life_days,
                )
                candidate_slots.append((pointer, cand_end, intrinsic_score, preference_score))
            pointer += step

        if not candidate_slots:
            return []

        raw_preference_scores = [item[3] for item in candidate_slots]
        normalized_preference_scores = self._normalize_scores(raw_preference_scores)
        scored: list[tuple[datetime, datetime, float]] = []
        for idx, (start, end, intrinsic_score, _pref_raw) in enumerate(candidate_slots):
            if target_embedding and history_events:
                final_score = (
                    intrinsic_weight * intrinsic_score
                    + preference_weight * normalized_preference_scores[idx]
                )
            else:
                final_score = intrinsic_score
            scored.append((start, end, round(final_score, 6)))

        scored.sort(key=lambda item: item[2], reverse=True)
        top = scored[: max(1, int(limit))]
        return [
            {"index": idx, "start": start.isoformat(), "end": end.isoformat(), "score": score}
            for idx, (start, end, score) in enumerate(top)
        ]
