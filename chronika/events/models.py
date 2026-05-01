from django.db import models
from django.conf import settings
from django.db.models import Q, UniqueConstraint
from pgvector.django import VectorField
from core.enums import EmbeddingStatus

User = settings.AUTH_USER_MODEL

class UserCalendar(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="calendars"
    )
    google_calendar_id = models.CharField(
        max_length=255,
        help_text="Идентификатор календаря из Google.",
    )
    summary = models.CharField(
        max_length=255,
        help_text="Название календаря, как отображается у пользователя."
    )
    description = models.TextField(
        blank=True, 
        null=True,
        help_text="Описание календаря, если доступно."
    )
    owner = models.BooleanField(
        blank=True,
        default=True,
        help_text='Является ли пользователь владельцем календаря.'
    )
    background_color = models.CharField(
        max_length=7, 
        blank=True, 
        null=True,
        help_text="Цвет календаря в формате HEX (например, #ff0000)."
    )
    selected = models.BooleanField(
        default=True,
        help_text="Флаг, указывающий выбран ли календарь для отображения."
    )
    time_zone = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        help_text="Часовой пояс календаря."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    primary = models.BooleanField(default=False, help_text="Флаг, указывающий является ли основным календарем.")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "google_calendar_id"],
                name="unique_user_calendar_id_when_owner_true"
            )
        ]

    def __str__(self):
        return f"{self.summary} ({self.google_calendar_id})"


class Event(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_calendar = models.ForeignKey(UserCalendar, on_delete=models.CASCADE, related_name='events')
    google_event_id = models.CharField(max_length=256, null=True, blank=True, help_text="ID события в Google Calendar")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    summary = models.CharField(max_length=256, null=True, blank=True, help_text="Название события")
    description = models.TextField(null=True, blank=True, help_text="Описание события")
    start = models.DateTimeField(null=True, blank=True, help_text="Дата начала события")
    end = models.DateTimeField(null=True, blank=True, help_text="Дата окончания события")
    htmlLink = models.URLField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="Ссылка на событие в Google Calendar",
    )
    organizer_email = models.EmailField(null=True, blank=True, help_text="Email организатора")
    embedding = VectorField(dimensions=1024, null=True, blank=True)
    embedding_status = models.CharField(
        max_length=10,
        choices=EmbeddingStatus.choices,
        default=EmbeddingStatus.PENDING,
    )

    task = models.ForeignKey(
        'tasks.Task',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events"
    )
    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user_calendar", "google_event_id"],
                name="unique_event_id_when_user_calendar_id_is_not_null"
            )
        ]
        ordering = ['start']

    def __str__(self):
        return self.summary