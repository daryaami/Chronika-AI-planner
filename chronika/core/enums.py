from django.db import models
from django.utils.translation import gettext_lazy as _


class EmbeddingStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    COMPLETED = "COMPLETED", _("Completed")
    FAILED = "FAILED", _("Failed")
