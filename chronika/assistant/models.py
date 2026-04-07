# Минимальная data-модель в assistant
# AssistantSession(user, title, created_at, updated_at)
# AssistantMessage(session, role, content, metadata_json, created_at)
# IntentDefinition(code, schema_json, active)
# IntentExecution(message, intent_code, slots_json, confidence, status)
# PromptTemplate(name, version, system_prompt, config_json, active)
# PromptRunTrace(message, template_version, prompt_hash, tokens_in, tokens_out, latency_ms)
# RetrievalCache(user, query_hash, topk_json, expires_at) (опционально, если cache в БД нужен)


from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

class AssistantSession(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assistant_sessions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Assistant Session {self.id} for {self.user.username}"

class AssistantMessage(models.Model):
    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(AssistantSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=255)
    content = models.TextField()
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Assistant Message {self.id} for {self.session.id}"

class PromptTemplate(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=255)
    system_prompt = models.TextField()
    config_json = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Prompt Template {self.name} {self.version}"