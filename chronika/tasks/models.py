from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from zoneinfo import ZoneInfo

from events.models import UserCalendar

User = settings.AUTH_USER_MODEL

DEFAULT_DURATION = 30

class Priority(models.TextChoices):
    NONE = 'NONE', _('None')
    LOW = 'LOW', _('Low')
    MEDIUM = 'MEDIUM', _('Medium')
    HIGH = 'HIGH', _('High')
    CRITICAL = 'CRITICAL', _('Critical')

class Category(models.Model):
    name = models.CharField(max_length=100)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='categories',
        null=True,
        blank=True
    )
    color = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return self.name
    
class Task(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='tasks')
    # TODO: поменять due date на просто дату
    due_date = models.DateTimeField(null=True, blank=True)
    duration = models.SmallIntegerField(null=True, blank=True, default=DEFAULT_DURATION)
    calendar = models.ForeignKey(UserCalendar, on_delete=models.CASCADE, related_name='tasks')
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-due_date', '-created_at']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class TimeLog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    google_event_id = models.CharField(max_length=256, null=True, blank=True, help_text="ID события в Google Calendar")

    def __str__(self):
        return f"{self.task.title}: {self.start_time} - {self.end_time}"
