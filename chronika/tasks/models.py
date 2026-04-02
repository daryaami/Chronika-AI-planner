from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from pgvector.django import VectorField
from core.enums import EmbeddingStatus

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
    calendar = models.ForeignKey('events.UserCalendar', on_delete=models.CASCADE, related_name='tasks')
    completed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    notes = models.TextField(null=True, blank=True)
    embedding = VectorField(dimensions=1024, null=True, blank=True)
    embedding_status = models.CharField(max_length=10, choices=EmbeddingStatus.choices, default=EmbeddingStatus.PENDING)

    class Meta:
        ordering = ['-due_date', '-created']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title