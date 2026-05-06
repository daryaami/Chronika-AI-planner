from __future__ import annotations

import os
from datetime import datetime, timedelta
import random

from events.models import Event


class SchedulerService:
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
    ) -> list[dict]:
        if duration_minutes <= 0:
            return []
        duration = timedelta(minutes=int(duration_minutes))
        step = timedelta(minutes=max(1, int(step_minutes)))
        pointer = self._align_to_step(window_start, step_minutes=step_minutes)
        scored: list[tuple[datetime, datetime, float]] = []
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
                simulate_scores = os.getenv("APP_AGENT_SIMULATE_SLOT_SCORES", "").strip().lower() == "true"
                score = (
                    round(random.random(), 6)
                    if simulate_scores
                    else self._intrinsic_slot_score(pointer, window_start, window_end)
                )
                scored.append((pointer, cand_end, score))
            pointer += step
        scored.sort(key=lambda item: item[2], reverse=True)
        top = scored[: max(1, int(limit))]
        return [
            {"index": idx, "start": start.isoformat(), "end": end.isoformat(), "score": score}
            for idx, (start, end, score) in enumerate(top)
        ]
