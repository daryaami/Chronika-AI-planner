"""
Планировщик: проверка точного слота по календарю и подбор вариантов по time_constraints
и due_date (в fields / datetime): конец слота не позже caps — дата → конец локального дня.

Окна «время суток» и календарные даты трактуются в TZ пользователя (CustomUser.time_zone),
с запасным вариантом — TIME_ZONE из настроек Django.

Пока: занятость только из Event. Без точного времени — один случайный слот из кандидатов (все кандидаты в лог).
Если указано точное время, но не влезает / занято — до MAX_SLOT_OPTIONS вариантов в time_slot_selection.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime as datetime_cls, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from assistant.domain.action_plan import Action, ActionPlan
from assistant.pipeline_log import pretty_data, trace
from assistant.services.calendar_availability import (
    get_event_busy_intervals,
    iter_free_intervals,
    merge_busy_intervals,
)

SLOT_STEP_MINUTES = 15
MIN_DURATION_MINUTES = 15
MAX_SLOT_OPTIONS = 5
DEFAULT_HORIZON_DAYS = 14
_MAX_CANDIDATES_SCAN = 400
_LOG_CANDIDATES_CAP = 120

# Ключи из fields, которые должны участвовать в планировании, если в datetime их нет
# (как в build_ui_blocks: часть полей живёт только в fields).
_SCHEDULE_KEYS_FROM_FIELDS: tuple[str, ...] = (
    "date",
    "date_from",
    "date_to",
    "time_constraints",
    "start_at",
    "end_at",
)


def _schedule_view(fields: dict[str, Any], dt: dict[str, Any]) -> dict[str, Any]:
    out = dict(dt) if isinstance(dt, dict) else {}
    if not isinstance(fields, dict):
        return out
    for k in _SCHEDULE_KEYS_FROM_FIELDS:
        if fields.get(k) is None:
            continue
        if out.get(k) is None:
            out[k] = fields[k]
    return out


def _user_tz(user: Any) -> tzinfo:
    """IANA TZ из профиля; иначе активная TZ Django (settings.TIME_ZONE)."""
    raw = getattr(user, "time_zone", None) if user is not None else None
    if isinstance(raw, str) and raw.strip():
        try:
            return ZoneInfo(raw.strip())
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return timezone.get_current_timezone()


def _to_user_local_date(moment: datetime_cls, user_tz: tzinfo) -> date:
    return moment.astimezone(user_tz).date()


def _iso_slot_bounds(a: datetime_cls, b: datetime_cls, user_tz: tzinfo) -> dict[str, str]:
    """Границы слота в TZ пользователя — те же инстанты, что и в UTC, но читаемые как локальные часы."""
    return {
        "start": a.astimezone(user_tz).isoformat(),
        "end": b.astimezone(user_tz).isoformat(),
    }


def _log_slot_candidates(
    candidates: list[tuple[datetime_cls, datetime_cls]],
    user_tz: tzinfo,
    *,
    title_suffix: str = "",
) -> None:
    if not candidates:
        trace(
            f"Scheduler: кандидаты слотов{title_suffix}".strip(),
            результат="подходящих интервалов не найдено",
        )
        return
    shown = candidates[:_LOG_CANDIDATES_CAP]
    rows = [_iso_slot_bounds(a, b, user_tz) for a, b in shown]
    trace(
        f"Scheduler: кандидаты слотов{title_suffix}".strip(),
        всего_кандидатов=str(len(candidates)),
        в_логе_строк=str(len(shown)),
        локальное_время_пользователя=pretty_data(rows),
    )


def _parse_iso_dt(val: Any, user_tz: tzinfo) -> datetime_cls | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    dt = parse_datetime(s)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, user_tz)
    return dt


def _parse_date_only(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime_cls):
        return val.date()
    if isinstance(val, date):
        return val
    return parse_date(str(val).strip())


def _parse_hhmm(val: Any, user_tz: tzinfo) -> time | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if "T" in s:
        dt = parse_datetime(s)
        if dt is None:
            return None
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, user_tz)
        return dt.astimezone(user_tz).time()
    parts = s.split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return time(h, m)
    except (ValueError, IndexError):
        return None


def _combine(wall_date: date, wall_time: time, user_tz: tzinfo) -> datetime_cls:
    """Календарная дата + локальное время суток в TZ пользователя."""
    dt = datetime_cls.combine(wall_date, wall_time)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, user_tz)
    return dt


def _duration_minutes(fields: dict[str, Any], dt: dict[str, Any]) -> int:
    for src in (fields, dt):
        if not isinstance(src, dict):
            continue
        raw = src.get("duration")
        if raw is not None:
            try:
                n = int(float(raw))
                if n >= MIN_DURATION_MINUTES:
                    return n
            except (TypeError, ValueError):
                pass
    return 30


def _due_datetime_cap(fields: dict[str, Any], dt: dict[str, Any], user_tz: tzinfo) -> datetime_cls | None:
    raw = None
    if isinstance(fields, dict) and fields.get("due_date") is not None:
        raw = fields.get("due_date")
    if raw is None and isinstance(dt, dict) and dt.get("due_date") is not None:
        raw = dt.get("due_date")
    if raw is None:
        return None
    if isinstance(raw, datetime_cls):
        dt_p = raw
        if timezone.is_naive(dt_p):
            dt_p = timezone.make_aware(dt_p, user_tz)
        return dt_p
    if isinstance(raw, date):
        return _combine(raw, time(23, 59, 59), user_tz)
    s = str(raw).strip()
    if not s:
        return None
    if "T" in s:
        parsed = _parse_iso_dt(raw, user_tz)
        return parsed
    d_only = _parse_date_only(raw)
    if d_only:
        return _combine(d_only, time(23, 59, 59), user_tz)
    parsed = _parse_iso_dt(raw, user_tz)
    return parsed


def _dates_for_search(dt: dict[str, Any]) -> list[date]:
    out: list[date] = []
    if not isinstance(dt, dict):
        return []
    if dt.get("date"):
        d = _parse_date_only(dt["date"])
        if d:
            out.append(d)
    df = _parse_date_only(dt.get("date_from"))
    dto = _parse_date_only(dt.get("date_to"))
    if df and dto:
        cur = df
        while cur <= dto:
            out.append(cur)
            cur += timedelta(days=1)
    elif df:
        out.append(df)
    elif dto:
        out.append(dto)
    return sorted(set(out))


def _constraint_times(tc: dict[str, Any], user_tz: tzinfo) -> tuple[time, time]:
    st = _parse_hhmm(tc.get("start"), user_tz) if isinstance(tc, dict) else None
    en = _parse_hhmm(tc.get("end"), user_tz) if isinstance(tc, dict) else None
    return st or time(0, 0), en or time(23, 59, 59)


def _interval_free_of_busy(
    seg_start: datetime_cls,
    seg_end: datetime_cls,
    merged_busy: list[tuple[datetime_cls, datetime_cls]],
) -> bool:
    for bs, be in merged_busy:
        if seg_start < be and seg_end > bs:
            return False
    return True


def _slot_respects_due_end(seg_end: datetime_cls, due_cap: datetime_cls | None) -> bool:
    return due_cap is None or seg_end <= due_cap


@dataclass
class _ScheduleOutcome:
    action: Action
    hint: str | None = None


class SchedulerService:
    """
    1) Точный start_at/end_at: проверка по Event и due_date; при конфликте — укорочение длительности
       с шагом SLOT_STEP_MINUTES.
    2) Без точного start_at — поиск слотов; все кандидаты в лог, один выбирается случайно → в план.
    3) Точное время не удалось сохранить (календарь / due) — до MAX_SLOT_OPTIONS вариантов
       в time_slot_selection для ручного выбора.
    """

    def apply_to_plan(self, user, plan: ActionPlan) -> tuple[ActionPlan, str | None]:
        hints: list[str] = []
        new_actions: list[Action] = []
        for action in plan.actions:
            out = self._process_action(user, action)
            new_actions.append(out.action)
            if out.hint:
                hints.append(out.hint)
        hint = " ".join(hints).strip() or None
        return ActionPlan(actions=new_actions, entities=list(plan.entities)), hint

    def _process_action(self, user, action: Action) -> _ScheduleOutcome:
        data = dict(action.data) if isinstance(action.data, dict) else {}
        code = str(data.get("action") or "").strip().lower()
        et = data.get("entity_type")
        et_s = str(et).lower() if et is not None else ""
        if et_s not in ("event", "task"):
            return _ScheduleOutcome(action)
        if code not in ("create", "schedule"):
            return _ScheduleOutcome(action)

        fields = dict(data.get("fields") or {})
        dt = dict(data.get("datetime") or {})
        sched = _schedule_view(fields, dt)
        duration = _duration_minutes(fields, sched)
        tc = (
            sched.get("time_constraints")
            if isinstance(sched.get("time_constraints"), dict)
            else None
        )
        user_tz = _user_tz(user)
        due_cap = _due_datetime_cap(fields, sched, user_tz)

        now = timezone.now()
        horizon_end = now + timedelta(days=DEFAULT_HORIZON_DAYS)
        busy = get_event_busy_intervals(
            user,
            horizon_start=now,
            horizon_end=horizon_end,
            naive_tz=user_tz,
        )
        merged = merge_busy_intervals(busy)

        start_at = _parse_iso_dt(sched.get("start_at"), user_tz)
        end_at = _parse_iso_dt(sched.get("end_at"), user_tz)

        if start_at is not None:
            if due_cap is not None and start_at > due_cap:
                options = self._offer_slot_options(
                    sched, tc, duration, merged, now, horizon_end, due_cap, user_tz,
                    log_suffix=" (start после due_date)",
                )
                if options:
                    return self._with_options(
                        action,
                        data,
                        options,
                        hint="Начало позже due_date — выберите другой слот в пределах срока.",
                    )
                return _ScheduleOutcome(
                    self._clone_action(action, data),
                    hint="Не удалось подобрать слот до срока due_date.",
                )
            if end_at is None:
                end_at = start_at + timedelta(minutes=duration)
            if _interval_free_of_busy(start_at, end_at, merged) and _slot_respects_due_end(
                end_at, due_cap
            ):
                new_dt = dict(dt)
                new_dt["start_at"] = start_at.isoformat()
                new_dt["end_at"] = end_at.isoformat()
                data["datetime"] = new_dt
                data.pop("time_slot_options", None)
                return _ScheduleOutcome(self._clone_action(action, data))

            orig_end = end_at
            blocked_by_busy = not _interval_free_of_busy(start_at, orig_end, merged)
            blocked_by_due = not _slot_respects_due_end(orig_end, due_cap)
            req_mins = max(int((end_at - start_at).total_seconds() // 60), MIN_DURATION_MINUTES)
            for mins in range(req_mins, MIN_DURATION_MINUTES - 1, -SLOT_STEP_MINUTES):
                ne = start_at + timedelta(minutes=mins)
                if _interval_free_of_busy(start_at, ne, merged) and _slot_respects_due_end(
                    ne, due_cap
                ):
                    new_dt = dict(dt)
                    new_dt["start_at"] = start_at.isoformat()
                    new_dt["end_at"] = ne.isoformat()
                    fields = dict(fields)
                    fields["duration"] = mins
                    data["fields"] = fields
                    data["datetime"] = new_dt
                    data.pop("time_slot_options", None)
                    hint_parts: list[str] = []
                    if mins < req_mins:
                        if blocked_by_busy:
                            hint_parts.append(
                                "В календаре мешают другие события — длительность уменьшена, чтобы влезть."
                            )
                        if blocked_by_due:
                            hint_parts.append(
                                "Длительность уменьшена, чтобы окончание уложилось в due_date."
                            )
                    return _ScheduleOutcome(
                        self._clone_action(action, data),
                        hint=" ".join(hint_parts).strip() or None,
                    )

            options = self._offer_slot_options(
                sched, tc, duration, merged, now, horizon_end, due_cap, user_tz,
                log_suffix=" (точное время занято / не влезает)",
            )
            if options:
                return self._with_options(
                    action,
                    data,
                    options,
                    hint="Указанное время занято или не подходит — выберите другой слот.",
                )
            return _ScheduleOutcome(
                self._clone_action(action, data),
                hint="Не удалось найти свободное окно в календаре в рамках ограничений по времени.",
            )

        chosen = self._suggest_slots(
            sched, tc, duration, merged, now, horizon_end, due_cap, user_tz,
            log_suffix="",
        )
        if chosen:
            return self._apply_chosen_slot(action, data, dt, fields, chosen, hint=None)
        data.pop("time_slot_options", None)
        return _ScheduleOutcome(
            self._clone_action(action, data),
            hint="Не удалось найти свободное окно в календаре в рамках ограничений по времени.",
        )

    def _apply_chosen_slot(
        self,
        action: Action,
        data: dict[str, Any],
        dt: dict[str, Any],
        fields: dict[str, Any],
        chosen: dict[str, str],
        *,
        hint: str | None,
    ) -> _ScheduleOutcome:
        """Записывает выбранный слот в план (UTC ISO в datetime); убирает time_slot_options."""
        new_dt = dict(dt)
        new_dt["start_at"] = chosen["start"]
        new_dt["end_at"] = chosen["end"]
        data = dict(data)
        data["datetime"] = new_dt
        data.pop("time_slot_options", None)
        fields = dict(fields)
        try:
            sa = parse_datetime(str(chosen["start"]))
            se = parse_datetime(str(chosen["end"]))
            if sa is not None and se is not None:
                fields["duration"] = max(
                    MIN_DURATION_MINUTES,
                    int((se - sa).total_seconds() // 60),
                )
        except (TypeError, ValueError):
            pass
        data["fields"] = fields
        return _ScheduleOutcome(self._clone_action(action, data), hint=hint)

    def _with_options(
        self,
        action: Action,
        data: dict[str, Any],
        options: list[dict[str, str]],
        hint: str | None = None,
    ) -> _ScheduleOutcome:
        data = dict(data)
        data["time_slot_options"] = options
        return _ScheduleOutcome(self._clone_action(action, data), hint=hint)

    @staticmethod
    def _clone_action(action: Action, data: dict[str, Any]) -> Action:
        return Action(
            context_id=action.context_id,
            type=action.type,
            target_id=action.target_id,
            data=data,
        )

    def _collect_slot_candidates(
        self,
        dt: dict[str, Any],
        tc: dict[str, Any] | None,
        duration_minutes: int,
        merged_busy: list[tuple[datetime_cls, datetime_cls]],
        horizon_start: datetime_cls,
        horizon_end: datetime_cls,
        due_cap: datetime_cls | None,
        user_tz: tzinfo,
    ) -> list[tuple[datetime_cls, datetime_cls]]:
        schedule_now = timezone.now()
        days = _dates_for_search(dt)
        if not days:
            d0 = _to_user_local_date(schedule_now, user_tz)
            last_day = d0 + timedelta(days=DEFAULT_HORIZON_DAYS - 1)
            if due_cap is not None:
                last_day = min(last_day, _to_user_local_date(due_cap, user_tz))
            if last_day < d0:
                return []
            days = [d0 + timedelta(days=i) for i in range((last_day - d0).days + 1)]
        elif due_cap is not None:
            dlim = _to_user_local_date(due_cap, user_tz)
            days = [d for d in days if d <= dlim]
            if not days:
                return []

        st_t, en_t = _constraint_times(tc or {}, user_tz)
        typ = str((tc or {}).get("type") or "").lower()
        deadline_cap: datetime_cls | None = None
        if typ == "deadline" and tc:
            deadline_cap = _parse_iso_dt(tc.get("end"), user_tz)
            if deadline_cap is None:
                d_anchor = days[0] if days else _to_user_local_date(schedule_now, user_tz)
                et = _parse_hhmm(tc.get("end"), user_tz)
                if et:
                    deadline_cap = _combine(d_anchor, et, user_tz)

        hard_cap: datetime_cls | None = None
        for c in (deadline_cap, due_cap):
            if c is None:
                continue
            hard_cap = c if hard_cap is None else min(hard_cap, c)

        candidates: list[tuple[datetime_cls, datetime_cls]] = []
        need_td = timedelta(minutes=duration_minutes)
        step_td = timedelta(minutes=SLOT_STEP_MINUTES)

        for day in days:
            day_win_start = _combine(day, st_t, user_tz)
            day_win_end = _combine(day, en_t, user_tz)
            if day_win_end <= day_win_start:
                continue
            win_a = max(day_win_start, schedule_now, horizon_start)
            win_b = min(day_win_end, horizon_end)
            if hard_cap is not None:
                win_b = min(win_b, hard_cap)
            if win_b <= win_a:
                continue

            free_parts = iter_free_intervals(
                merged_busy, win_a, win_b, min_gap_minutes=SLOT_STEP_MINUTES
            )
            for fa, fb in free_parts:
                cur = fa
                while cur + need_td <= fb:
                    candidates.append((cur, cur + need_td))
                    cur += step_td
                    if len(candidates) >= _MAX_CANDIDATES_SCAN:
                        break
                if len(candidates) >= _MAX_CANDIDATES_SCAN:
                    break
            if len(candidates) >= _MAX_CANDIDATES_SCAN:
                break

        now_cut = timezone.now()
        return [(a, b) for a, b in candidates if a >= now_cut]

    def _suggest_slots(
        self,
        dt: dict[str, Any],
        tc: dict[str, Any] | None,
        duration_minutes: int,
        merged_busy: list[tuple[datetime_cls, datetime_cls]],
        horizon_start: datetime_cls,
        horizon_end: datetime_cls,
        due_cap: datetime_cls | None,
        user_tz: tzinfo,
        *,
        log_suffix: str = "",
    ) -> dict[str, str] | None:
        """Без точного времени: лог всех кандидатов, один случайный слот (UTC ISO в план)."""
        candidates = self._collect_slot_candidates(
            dt, tc, duration_minutes, merged_busy, horizon_start, horizon_end, due_cap, user_tz
        )
        _log_slot_candidates(candidates, user_tz, title_suffix=log_suffix)
        if not candidates:
            return None
        a, b = random.choice(candidates)
        chosen = {"start": a.isoformat(), "end": b.isoformat()}
        trace(
            f"Scheduler: выбран слот{log_suffix}".strip(),
            utc_iso=pretty_data(chosen),
            локально_пользователь=pretty_data([_iso_slot_bounds(a, b, user_tz)]),
        )
        return chosen

    def _offer_slot_options(
        self,
        dt: dict[str, Any],
        tc: dict[str, Any] | None,
        duration_minutes: int,
        merged_busy: list[tuple[datetime_cls, datetime_cls]],
        horizon_start: datetime_cls,
        horizon_end: datetime_cls,
        due_cap: datetime_cls | None,
        user_tz: tzinfo,
        *,
        log_suffix: str = "",
    ) -> list[dict[str, str]] | None:
        """Конфликт точного времени: лог всех кандидатов, до MAX_SLOT_OPTIONS вариантов для UI."""
        candidates = self._collect_slot_candidates(
            dt, tc, duration_minutes, merged_busy, horizon_start, horizon_end, due_cap, user_tz
        )
        _log_slot_candidates(candidates, user_tz, title_suffix=log_suffix)
        if not candidates:
            return None
        k = min(MAX_SLOT_OPTIONS, len(candidates))
        picked = random.sample(candidates, k=k)
        picked.sort(key=lambda x: x[0])
        return [_iso_slot_bounds(a, b, user_tz) for a, b in picked]
