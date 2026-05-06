from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from django.test import TestCase

from assistant.services.scheduler_service import SchedulerService


class SchedulerServiceTests(TestCase):
    def setUp(self):
        self.scheduler = SchedulerService()
        self.window_start = datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc)
        self.window_end = datetime(2026, 5, 11, 16, 0, tzinfo=timezone.utc)

    def _event(self, *, hour: int, embedding: list[float]):
        start = datetime(2026, 5, 11, hour, 0, tzinfo=timezone.utc)
        return SimpleNamespace(
            start=start,
            end=start + timedelta(hours=1),
            embedding=embedding,
        )

    def test_suggest_slots_prefers_hour_and_weekday_from_similar_history(self):
        slots = self.scheduler.suggest_slots_in_window(
            events=[],
            window_start=self.window_start,
            window_end=self.window_end,
            duration_minutes=60,
            step_minutes=60,
            limit=3,
            preference_context={
                "target_embedding": [1.0, 0.0],
                "history_events": [self._event(hour=11, embedding=[1.0, 0.0])],
                "preference_weight": 1.0,
                "sigma_hour": 0.75,
            },
        )

        self.assertEqual(slots[0]["start"], "2026-05-11T11:00:00+00:00")

    def test_suggest_slots_falls_back_to_intrinsic_when_no_preferences(self):
        slots = self.scheduler.suggest_slots_in_window(
            events=[],
            window_start=self.window_start,
            window_end=self.window_end,
            duration_minutes=60,
            step_minutes=60,
            limit=2,
            preference_context={"target_embedding": [], "history_events": []},
        )

        self.assertEqual(slots[0]["start"], "2026-05-11T08:00:00+00:00")

    def test_suggest_slots_penalizes_negative_similarity(self):
        slots = self.scheduler.suggest_slots_in_window(
            events=[],
            window_start=self.window_start,
            window_end=self.window_end,
            duration_minutes=60,
            step_minutes=60,
            limit=1,
            preference_context={
                "target_embedding": [1.0, 0.0],
                "history_events": [
                    self._event(hour=9, embedding=[-1.0, 0.0]),
                    self._event(hour=14, embedding=[1.0, 0.0]),
                ],
                "preference_weight": 1.0,
                "sigma_hour": 0.75,
            },
        )

        self.assertEqual(slots[0]["start"], "2026-05-11T14:00:00+00:00")
