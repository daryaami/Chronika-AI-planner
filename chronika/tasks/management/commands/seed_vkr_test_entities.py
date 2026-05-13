"""
Создание тестовых задач и событий по плану ВКР (diploma/test_and_evaluate_experiment.md).

Категории в БД: Personal / Work (как в миграции 0002_seed_default_categories).
В интерфейсе они могут отображаться как «Личное» / «Работа» — смысл тот же.

Запуск из каталога с manage.py:
  python manage.py seed_vkr_test_entities
  python manage.py seed_vkr_test_entities --email you@example.com
  python manage.py seed_vkr_test_entities --purge   # + удаление совпадающих событий в Google (если не --skip-google)
  python manage.py seed_vkr_test_entities --skip-google   # только БД, без Calendar API

События создаются в БД с пустым google_event_id и сразу выгружаются в Google Calendar
(синхронный вызов sync_event_to_google; нужны валидные Google-токены пользователя).

После команды для эмбеддингов событий нужен Celery worker (или подождать фоновую обработку).
Проверка эмбеддингов: python manage.py check_vkr_embeddings
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.enums import EmbeddingStatus, GoogleCalendarSyncStatus
from core.exceptions import CalendarWriteAccessDeniedError, EventNotFoundError
from events.models import Event, UserCalendar
from tasks.models import Category, Priority, Task

if TYPE_CHECKING:
    from users.models import CustomUser

DEFAULT_EMAIL = "darya.mitryashkina@dataacquisition.ru"

# Маркер тестовых событий: в description (для человека и фильтров); в Google — extendedProperties chronika__vkr-seed.
# Префикс google_event_id — только для старых сидов (ложный id); новые события получают реальный id от Google.
VKR_SEED_DESCRIPTION = "[vkr_seed]"
VKR_SEED_GOOGLE_ID_PREFIX = "vkr_seed_"

_SEED_EVENT_Q = Q(description__contains=VKR_SEED_DESCRIPTION) | Q(
    google_event_id__startswith=VKR_SEED_GOOGLE_ID_PREFIX
)

# Точные названия из diploma/test_and_evaluate_experiment.md §1.2
TASK_SEED: list[tuple[str, str]] = [
    ("подготовить конспект по матанализу", "Personal"),
    ("подготовить презентацию для заказчика", "Work"),
    ("написать курсовую", "Work"),
    ("купить лекарства", "Personal"),
    ("тренировка в зале", "Personal"),
    ("daily sync", "Work"),
    ("созвон с коллегами", "Work"),
    ("сдать отчёт по стажировке", "Work"),
    ("черновик отчёта заказчику", "Work"),
]

# (summary, day_kind, start_h, start_m, end_h, end_m) — даты относительно «сегодня» в текущей TZ Django
EVENT_SEED: list[tuple[str, str, int, int, int, int]] = [
    # summary, day_offset from today, start H,M, end H,M
    ("Командная встреча", "tomorrow", 14, 0, 15, 0),
    ("Спортзал вечером", "tomorrow", 18, 0, 19, 0),
    ("Учебный блок", "next_friday", 10, 0, 12, 0),
    ("Созвон", "next_wednesday", 11, 0, 12, 0),
    ("Созвон с командой", "next_wednesday", 16, 0, 17, 0),
    ("Встреча с руководителем", "next_monday", 10, 0, 11, 0),
    ("Встреча с заказчиком", "next_monday", 14, 0, 15, 0),
    ("Встреча 1:1 с ментором", "next_tuesday", 11, 0, 12, 0),
]


def _fix_next_weekday(anchor: date, target_weekday: int) -> date:
    """Дата target_weekday (0=пн) в ту же неделю, что anchor, или ближайшая такая дата не раньше anchor."""
    delta = (target_weekday - anchor.weekday()) % 7
    return anchor + timedelta(days=delta)


def _event_day(kind: str, today: date) -> date:
    if kind == "tomorrow":
        return today + timedelta(days=1)
    if kind == "next_monday":
        return _fix_next_weekday(today, 0)
    if kind == "next_tuesday":
        return _fix_next_weekday(today, 1)
    if kind == "next_wednesday":
        return _fix_next_weekday(today, 2)
    if kind == "next_friday":
        return _fix_next_weekday(today, 4)
    raise ValueError(kind)


def _combine(d: date, hour: int, minute: int, tz) -> datetime:
    naive = datetime.combine(d, dt_time(hour, minute))
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, tz)
    return naive


class Command(BaseCommand):
    help = "Создать тестовые задачи и события для прогона тестов ВКР (см. diploma/test_and_evaluate_experiment.md)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=DEFAULT_EMAIL,
            help=f"Email пользователя в БД (по умолчанию {DEFAULT_EMAIL}).",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help=(
                "Удалить предыдущие сущности этого скрипта: задачи с титулами из списка; "
                "события с меткой сида (description содержит [vkr_seed] или устаревший id vkr_seed_*); "
                "для событий с реальным google_event_id — попытка удалить и в Google Calendar."
            ),
        )
        parser.add_argument(
            "--skip-google",
            action="store_true",
            help="Не создавать и не удалять события в Google (только локальная БД).",
        )
        parser.add_argument(
            "--no-embeddings",
            action="store_true",
            help="Не ставить задачи и события в очередь на эмбеддинги (остаётся PENDING).",
        )

    def handle(self, *args, **options):
        email: str = options["email"]
        purge: bool = options["purge"]
        skip_google: bool = options["skip_google"]
        no_embeddings: bool = options["no_embeddings"]

        User = get_user_model()
        try:
            user: CustomUser = User.objects.get(email__iexact=email.strip())
        except User.DoesNotExist as exc:
            raise CommandError(
                f"Пользователь с email {email!r} не найден. "
                "Сначала войди в приложение через Google под этим аккаунтом."
            ) from exc

        cal = UserCalendar.objects.filter(user=user, primary=True).first()
        if cal is None:
            cal = UserCalendar.objects.filter(user=user).first()
        if cal is None:
            raise CommandError(
                f"У пользователя {email} нет календарей в БД. "
                "Нужна хотя бы одна синхронизация с Google после входа."
            )

        cat_map: dict[str, Category] = {}
        for name in ("Personal", "Work"):
            c = Category.objects.filter(name=name, user__isnull=True, is_default=True).first()
            if c is None:
                c = Category.objects.filter(name=name, user__isnull=True).first()
            if c is None:
                raise CommandError(
                    f"В БД нет категории {name!r} (дефолт из миграции). Выполни миграции: python manage.py migrate"
                )
            cat_map[name] = c

        today = timezone.localdate()
        tz = timezone.get_current_timezone()

        task_titles = [t[0] for t in TASK_SEED]

        if purge:
            from events.services import GoogleCalendarService

            ev_qs = (
                Event.objects.filter(user_calendar=cal)
                .filter(_SEED_EVENT_Q)
                .select_related("user_calendar")
            )
            if not skip_google:
                gcal = GoogleCalendarService()
                for ev in ev_qs:
                    gid = (ev.google_event_id or "").strip()
                    if not gid or gid.startswith(VKR_SEED_GOOGLE_ID_PREFIX):
                        continue
                    try:
                        gcal.delete_event(user, cal.google_calendar_id, gid)
                    except EventNotFoundError:
                        pass
                    except CalendarWriteAccessDeniedError as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  не удалено в Google (нет прав): event id={ev.id} — {e}"
                            )
                        )
                    except Exception as e:  # noqa: BLE001
                        self.stdout.write(
                            self.style.WARNING(f"  не удалено в Google: event id={ev.id} — {e}")
                        )
            deleted_e, _ = ev_qs.delete()
            deleted_t, _ = Task.objects.filter(user=user, title__in=task_titles).delete()
            self.stdout.write(
                self.style.WARNING(
                    f"Purge: удалено ORM-строк задач={deleted_t}, событий={deleted_e}"
                )
            )

        new_event_ids: list[int] = []

        with transaction.atomic():
            for title, cat_name in TASK_SEED:
                if Task.objects.filter(user=user, title=title).exists():
                    self.stdout.write(f"  задача уже есть, пропуск: {title!r}")
                    continue
                task = Task.objects.create(
                    user=user,
                    title=title,
                    priority=Priority.MEDIUM,
                    category=cat_map[cat_name],
                    calendar=cal,
                    completed=False,
                    embedding_status=EmbeddingStatus.PENDING,
                )
                self.stdout.write(self.style.SUCCESS(f"  задача: {title!r} ({cat_name})"))
                if not no_embeddings:
                    try:
                        from tasks.tasks import generate_task_embedding

                        generate_task_embedding.delay(task.id)
                    except Exception as e:  # noqa: BLE001
                        self.stdout.write(
                            self.style.WARNING(
                                f"  не удалось поставить embedding в очередь для task {task.id}: {e}"
                            )
                        )

            for summary, day_kind, sh, sm, eh, em in EVENT_SEED:
                day = _event_day(day_kind, today)
                start = _combine(day, sh, sm, tz)
                end = _combine(day, eh, em, tz)
                if Event.objects.filter(user_calendar=cal, summary=summary, start=start).filter(
                    _SEED_EVENT_Q
                ).exists():
                    self.stdout.write(f"  событие уже есть, пропуск: {summary!r} {start}")
                    continue
                ev = Event.objects.create(
                    user_calendar=cal,
                    google_event_id=None,
                    summary=summary,
                    description=VKR_SEED_DESCRIPTION,
                    start=start,
                    end=end,
                    embedding_status=EmbeddingStatus.PENDING,
                    google_sync_status=GoogleCalendarSyncStatus.PENDING,
                )
                new_event_ids.append(ev.id)
                self.stdout.write(self.style.SUCCESS(f"  событие (БД): {summary!r} {start.isoformat()}"))

        if not skip_google and new_event_ids:
            from events.tasks import sync_event_to_google

            for eid in new_event_ids:
                try:
                    ok = sync_event_to_google.apply(args=(eid,), throw=True).get(timeout=180)
                    if ok:
                        self.stdout.write(self.style.SUCCESS(f"  Google: синхронизировано event id={eid}"))
                    else:
                        self.stdout.write(
                            self.style.ERROR(f"  Google: sync_event_to_google вернул False для id={eid}")
                        )
                except Exception as e:  # noqa: BLE001
                    self.stdout.write(
                        self.style.ERROR(f"  Google: ошибка синхронизации event id={eid}: {e}")
                    )
        elif skip_google and new_event_ids:
            self.stdout.write(
                self.style.WARNING(
                    f"  --skip-google: {len(new_event_ids)} событий только в БД (google_sync_status=PENDING)."
                )
            )

        if not no_embeddings:
            try:
                from events.tasks import generate_event_embedding

                for eid in new_event_ids:
                    generate_event_embedding.delay(eid)
            except Exception as e:  # noqa: BLE001
                self.stdout.write(
                    self.style.WARNING(f"  не удалось поставить embedding в очередь для событий: {e}")
                )

        self.stdout.write(
            self.style.NOTICE(
                "\nГотово. Для эмбеддингов событий запусти worker: celery -A chronika worker -l info "
                "(или свой run-local.ps1)."
            )
        )
