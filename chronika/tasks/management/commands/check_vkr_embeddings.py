"""
Проверка статуса эмбеддингов для тестовых задач (9 заголовков из сида) и событий сида:
description содержит [vkr_seed] или устаревший google_event_id с префиксом vkr_seed_.

Запуск (из каталога с manage.py):
  python manage.py check_vkr_embeddings
  python manage.py check_vkr_embeddings --email you@example.com
  python manage.py check_vkr_embeddings --strict   # код выхода 1, если не все COMPLETED
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from core.enums import EmbeddingStatus
from events.models import Event, UserCalendar
from tasks.management.commands.seed_vkr_test_entities import (
    TASK_SEED,
    VKR_SEED_DESCRIPTION,
    VKR_SEED_GOOGLE_ID_PREFIX,
)
from tasks.models import Task

DEFAULT_EMAIL = "darya.mitryashkina@dataacquisition.ru"


class Command(BaseCommand):
    help = "Показать embedding_status и вектор для тестовых задач и событий сида (метка [vkr_seed] в description или id vkr_seed_*)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=DEFAULT_EMAIL,
            help=f"Email пользователя (по умолчанию {DEFAULT_EMAIL}).",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Завершить с кодом 1, если есть не-COMPLETED или отсутствует вектор при COMPLETED.",
        )

    def handle(self, *args, **options):
        email: str = options["email"]
        strict: bool = options["strict"]

        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=email.strip())
        except User.DoesNotExist as exc:
            raise CommandError(f"Пользователь {email!r} не найден.") from exc

        cal = UserCalendar.objects.filter(user=user, primary=True).first()
        if cal is None:
            cal = UserCalendar.objects.filter(user=user).first()
        if cal is None:
            raise CommandError(f"У пользователя {email} нет календарей.")

        titles = [t[0] for t in TASK_SEED]
        tasks = list(
            Task.objects.filter(user=user, title__in=titles).order_by("id").only(
                "id", "title", "embedding_status", "embedding"
            )
        )
        events = list(
            Event.objects.filter(user_calendar=cal)
            .filter(
                Q(description__contains=VKR_SEED_DESCRIPTION)
                | Q(google_event_id__startswith=VKR_SEED_GOOGLE_ID_PREFIX)
            )
            .order_by("start")
            .only("id", "summary", "embedding_status", "embedding", "start", "description", "google_event_id")
        )

        self.stdout.write(self.style.NOTICE(f"Пользователь: {user.email}\n"))

        self.stdout.write("--- Задачи (тестовый набор) ---")
        self.stdout.write(f"{'id':>8}  {'status':<12}  {'vector':<6}  title")
        self.stdout.write("-" * 72)
        bad = False
        found_titles = {t.title for t in tasks}
        for t in tasks:
            has_vec = t.embedding is not None
            ok = t.embedding_status == EmbeddingStatus.COMPLETED and has_vec
            if not ok:
                bad = True
            vec_s = "yes" if has_vec else "no"
            line = f"{t.id:>8}  {t.embedding_status:<12}  {vec_s:<6}  {t.title}"
            if ok:
                self.stdout.write(line)
            else:
                self.stdout.write(self.style.WARNING(line))
        for title in titles:
            if title not in found_titles:
                self.stdout.write(self.style.ERROR(f"{'—':>8}  {'MISSING':<12}  {'—':<6}  {title}"))
                bad = True

        self.stdout.write("\n--- События сида (description содержит [vkr_seed] или id vkr_seed_*) ---")
        self.stdout.write(f"{'id':>8}  {'status':<12}  {'vector':<6}  summary")
        self.stdout.write("-" * 72)
        for e in events:
            has_vec = e.embedding is not None
            ok = e.embedding_status == EmbeddingStatus.COMPLETED and has_vec
            if not ok:
                bad = True
            vec_s = "yes" if has_vec else "no"
            summ = (e.summary or "")[:40]
            line = f"{e.id:>8}  {e.embedding_status:<12}  {vec_s:<6}  {summ}"
            if ok:
                self.stdout.write(line)
            else:
                self.stdout.write(self.style.WARNING(line))
        if not events:
            self.stdout.write(
                self.style.WARNING(
                    "Нет событий сида. Запусти: python manage.py seed_vkr_test_entities --purge "
                    "(события с меткой [vkr_seed] и выгрузкой в Google Calendar)."
                )
            )

        self.stdout.write("")
        if bad:
            self.stdout.write(
                self.style.WARNING(
                    "COMPLETED + непустой embedding — норма. PENDING — ждёт worker; "
                    "FAILED — смотри логи Celery / ошибки модели эмбеддингов."
                )
            )
            if strict:
                raise CommandError("Проверка --strict: не все эмбеддинги готовы.")
        else:
            self.stdout.write(self.style.SUCCESS("Все найденные строки: COMPLETED и вектор есть."))
