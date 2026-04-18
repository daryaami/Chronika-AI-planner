"""
Занятость календаря пользователя по событиям из БД (модель Event).

Задачи (Task) с due_date пока не учитываются как блокирующие интервалы — см. TODO в Scheduler.

Наивные start/end событий приводятся к aware через naive_tz (профиль пользователя), чтобы совпадать
с интерпретацией окон планировщика.
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from typing import Any

from django.utils import timezone


def merge_busy_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    cleaned = [(a, b) for a, b in intervals if a < b]
    if not cleaned:
        return []
    cleaned.sort(key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = [cleaned[0]]
    for a, b in cleaned[1:]:
        la, lb = merged[-1]
        if a <= lb:
            merged[-1] = (la, max(lb, b))
        else:
            merged.append((a, b))
    return merged


def iter_free_intervals(
    merged_busy: list[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
    *,
    min_gap_minutes: int = 15,
) -> list[tuple[datetime, datetime]]:
    """Свободные интервалы внутри [window_start, window_end], исключая занятость."""
    if window_end <= window_start:
        return []
    min_td = timedelta(minutes=min_gap_minutes)
    # Обрезаем занятость до окна
    clipped: list[tuple[datetime, datetime]] = []
    for bs, be in merged_busy:
        cs = max(bs, window_start)
        ce = min(be, window_end)
        if cs < ce:
            clipped.append((cs, ce))
    merged = merge_busy_intervals(clipped)
    free: list[tuple[datetime, datetime]] = []
    cur = window_start
    for bs, be in merged:
        if bs > cur:
            seg_end = min(bs, window_end)
            if seg_end - cur >= min_td:
                free.append((cur, seg_end))
        cur = max(cur, be)
    if cur < window_end and window_end - cur >= min_td:
        free.append((cur, window_end))
    return free


def get_event_busy_intervals(
    user: Any,
    *,
    horizon_start: datetime,
    horizon_end: datetime,
    naive_tz: tzinfo | None = None,
) -> list[tuple[datetime, datetime]]:
    """
    Интервалы [start, end) событий пользователя, пересекающие горизонт.
    Только записи с обоими полями start и end.

    naive_tz: для наивных start/end в БД — в какой TZ трактовать «стеночные» даты
    (должна совпадать с TZ планировщика, обычно профиль пользователя). Иначе — TIME_ZONE Django.
    """
    from events.models import Event

    tz_for_naive = naive_tz or timezone.get_current_timezone()

    qs = (
        Event.objects.filter(
            user_calendar__user_id=getattr(user, "id", None),
            start__isnull=False,
            end__isnull=False,
            end__gt=horizon_start,
            start__lt=horizon_end,
        )
        .order_by("start")
        .only("start", "end")
    )
    out: list[tuple[datetime, datetime]] = []
    for ev in qs:
        a, b = ev.start, ev.end
        if a is None or b is None or a >= b:
            continue
        if timezone.is_naive(a):
            a = timezone.make_aware(a, tz_for_naive)
        if timezone.is_naive(b):
            b = timezone.make_aware(b, tz_for_naive)
        out.append((a, b))
    return merge_busy_intervals(out)
