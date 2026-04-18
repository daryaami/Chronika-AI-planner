# Минимальная data-модель в assistant
# AssistantSession — одна активная сессия диалога на пользователя (состояние FSM в Postgres)
# AssistantMessage(session, role, content, metadata_json, created_at)
# PromptTemplate / прочее — см. комментарии в истории файла

import uuid

from django.conf import settings
from django.db import models

from assistant.fsm.states import DialogState

User = settings.AUTH_USER_MODEL


class AssistantSession(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="assistant_dialog_session",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    dialog_state = models.CharField(
        max_length=64,
        default=DialogState.IDLE.value,
        help_text="Состояние FSM (idle, waiting_confirmation, …).",
    )
    action_plan = models.JSONField(
        null=True,
        blank=True,
        help_text="Текущий план действий (сериализация ActionPlan).",
    )
    dialog_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Структурированный контекст (disambiguation_options, last_interaction, …).",
    )
    last_referenced_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Последний выбранный object_id (задача/событие).",
    )

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"AssistantSession {self.id} user={self.user_id} state={self.dialog_state}"


class AssistantMessage(models.Model):
    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    session = models.ForeignKey(AssistantSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=255)
    content = models.TextField()
    metadata_json = models.JSONField(default=dict, blank=True)
    blocks = models.JSONField(default=list, blank=True, help_text="UI-блоки ответа ассистента (протокол чата).")
    fsm_state = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AssistantMessage {self.id} session={self.session_id}"


class PromptTemplate(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=255)
    system_prompt = models.TextField()
    config_json = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} {self.version}"
