
from rest_framework import serializers

from assistant.services.chat_orchestrator import ChatOrchestratorResult
from assistant.services.semantic_search import SemanticSearchCandidate


class SemanticCandidatePayloadSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_null=True)
    due_date = serializers.DateTimeField(required=False, allow_null=True)
    summary = serializers.CharField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_null=True)
    start = serializers.DateTimeField(required=False, allow_null=True)
    end = serializers.DateTimeField(required=False, allow_null=True)


class SemanticSearchCandidateSerializer(serializers.Serializer):
    entity_type = serializers.CharField()
    object_id = serializers.IntegerField()
    similarity = serializers.FloatField()
    payload = serializers.SerializerMethodField()

    def get_payload(self, obj: SemanticSearchCandidate):
        payload = obj.payload
        if obj.entity_type == "task":
            return {
                "title": getattr(payload, "title", None),
                "notes": getattr(payload, "notes", None),
                "due_date": getattr(payload, "due_date", None),
            }
        return {
            "summary": getattr(payload, "summary", None),
            "description": getattr(payload, "description", None),
            "start": getattr(payload, "start", None),
            "end": getattr(payload, "end", None),
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["similarity"] = round(float(data["similarity"]), 6)
        return data


class AssistantIntentResultSerializer(serializers.Serializer):
    item_index = serializers.IntegerField()
    step = serializers.DictField(child=serializers.JSONField(), allow_empty=True)
    candidates = SemanticSearchCandidateSerializer(many=True)


class AssistantOrchestratorResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    assistant_reply = serializers.CharField(allow_blank=True)
    user_id = serializers.IntegerField()
    intents = AssistantIntentResultSerializer(many=True)
    state = serializers.CharField()
    action_plan = serializers.JSONField(allow_null=True)
    context = serializers.JSONField()
    last_referenced_id = serializers.IntegerField(allow_null=True)
    execution_artifact = serializers.JSONField(allow_null=True)

    @classmethod
    def from_result(cls, result: ChatOrchestratorResult) -> dict:
        intent_items = result.intents or []
        intents_payload = []
        for index, intent_item in enumerate(intent_items):
            step = {k: v for k, v in intent_item.items() if k != "candidates"}
            intents_payload.append(
                {
                    "item_index": index,
                    "step": step,
                    "candidates": intent_item.get("candidates", []),
                }
            )

        payload = {
            "message": result.message,
            "assistant_reply": result.assistant_reply,
            "user_id": result.user_id,
            "intents": intents_payload,
            "state": result.state,
            "action_plan": result.action_plan,
            "context": result.context,
            "last_referenced_id": result.last_referenced_id,
            "execution_artifact": result.execution_artifact,
        }
        return cls(payload).data
