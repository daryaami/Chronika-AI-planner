from django.db import models
from django.utils.translation import gettext_lazy as _


class EmbeddingStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    COMPLETED = "COMPLETED", _("Completed")
    FAILED = "FAILED", _("Failed")


class GoogleCalendarSyncStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending Google sync")
    SYNCED = "SYNCED", _("Synced with Google")
    FAILED = "FAILED", _("Google sync failed")
