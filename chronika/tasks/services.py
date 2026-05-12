from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser

from core.enums import EmbeddingStatus
from events.models import UserCalendar

from tasks.models import Task
from tasks.tasks import generate_task_embedding


class MissingPrimaryCalendarError(Exception):
    """REST-создание задачи без переданного календаря и без основного календаря пользователя."""


def build_task_create_kwargs(
    user: AbstractBaseUser, validated_data: dict[str, Any]
) -> dict[str, Any]:
    """
    Поля для ``create_task``: ``user``, календарь (из данных или основной календарь).
    Как для ``POST /api/tasks/``: только ``primary=True``, без fallback на selected/любой.
    """
    data = dict(validated_data)
    if "calendar" not in data or data["calendar"] is None:
        try:
            data["calendar"] = user.calendars.get(primary=True)
        except UserCalendar.DoesNotExist as exc:
            raise MissingPrimaryCalendarError from exc
    data["user"] = user
    return data


def enqueue_task_embedding(task: Task) -> None:
    task.embedding_status = EmbeddingStatus.PENDING
    task.save(update_fields=["embedding_status"])
    generate_task_embedding.delay(task.id)


def refresh_task_embedding_if_text_changed(
    task: Task, *, old_title: str, old_notes: str
) -> None:
    notes_after = task.notes or ""
    notes_before = old_notes or ""
    if task.title != old_title or notes_after != notes_before:
        enqueue_task_embedding(task)


def tasks_for_user_queryset(user: AbstractBaseUser):
    return Task.objects.filter(user=user)


def get_task_for_user(user: AbstractBaseUser, pk: int) -> Task | None:
    return tasks_for_user_queryset(user).filter(pk=pk).first()


def find_task_for_user_title_icontains(
    user: AbstractBaseUser, query: str
) -> Task | None:
    q = query.strip()
    if not q:
        return None
    return (
        tasks_for_user_queryset(user)
        .filter(title__icontains=q)
        .order_by("-updated")
        .first()
    )


def create_task(**fields: Any) -> Task:
    """
    Persist a task and enqueue embedding generation.
    Expects model-aligned keyword args (must include ``user`` and ``calendar``).
    """
    task = Task.objects.create(**fields)
    enqueue_task_embedding(task)
    return task


def update_task(task: Task, **updates: Any) -> Task:
    allowed = {
        "title",
        "duration",
        "completed",
        "notes",
        "due_date",
        "priority",
        "category",
        "calendar",
    }
    old_title = task.title
    old_notes = task.notes or ""
    for key, value in updates.items():
        if key not in allowed:
            continue
        setattr(task, key, value)
    task.save()
    refresh_task_embedding_if_text_changed(task, old_title=old_title, old_notes=old_notes)
    return task


def delete_task(task: Task) -> int:
    pk = task.id
    task.delete()
    return pk


def get_default_user_calendar(user: AbstractBaseUser) -> UserCalendar | None:
    return (
        UserCalendar.objects.filter(user=user, primary=True)
        .order_by("-updated_at")
        .first()
        or UserCalendar.objects.filter(user=user, selected=True)
        .order_by("-updated_at")
        .first()
        or UserCalendar.objects.filter(user=user).order_by("-updated_at").first()
    )
