
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
    intent = serializers.DictField(child=serializers.JSONField(), allow_empty=True)
    candidates = SemanticSearchCandidateSerializer(many=True)


class AssistantOrchestratorResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    assistant_reply = serializers.CharField(allow_blank=True)
    user_id = serializers.IntegerField()
    candidates = SemanticSearchCandidateSerializer(many=True)
    intents = AssistantIntentResultSerializer(many=True)

    @classmethod
    def from_result(cls, result: ChatOrchestratorResult) -> dict:
        intent_items = (result.intent_parser or {}).get("items", [])
        candidates_by_intent = result.candidates_by_intent or []
        intents_payload = []
        for index, intent_item in enumerate(intent_items):
            intent_candidates = candidates_by_intent[index] if index < len(candidates_by_intent) else []
            intents_payload.append(
                {
                    "item_index": index,
                    "intent": intent_item,
                    "candidates": intent_candidates,
                }
            )

        payload = {
            "message": result.message,
            "assistant_reply": result.assistant_reply,
            "user_id": result.user_id,
            "candidates": result.candidates or [],
            "intents": intents_payload,
        }
        return cls(payload).data
