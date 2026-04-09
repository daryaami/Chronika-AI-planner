from dataclasses import asdict, dataclass
from typing import Any
from assistant.services.semantic_search import SemanticSearchCandidate
from django.contrib.auth import get_user_model

from assistant.services.intent_parser import IntentParserService
from assistant.services.semantic_search import SemanticSearchService
from assistant.integrations.embeddings_model import EmbeddingsModelProvider


@dataclass
class ChatOrchestratorResult:
    message: str
    assistant_reply: str
    user_id: int
    intent_parser: dict[str, Any]
    candidates: list[SemanticSearchCandidate] | None
    candidates_by_intent: list[list[SemanticSearchCandidate]] | None

class ChatOrchestratorService:
    """
    Оркестратор бизнес-логики ассистента.
    """

    def __init__(self, intent_parser: IntentParserService | None = None):
        self.intent_parser = intent_parser or IntentParserService()
        self.semantic_search = SemanticSearchService()

    def process_message(self, user_id: int, message: str) -> ChatOrchestratorResult:
        parsed_intent_payload = self._parse_intent_payload(message)
        candidates: list[SemanticSearchCandidate] = []
        candidates_by_intent: list[list[SemanticSearchCandidate]] = []

        parsed_items = parsed_intent_payload.get("items", [])
        user = None
        if parsed_items:
            User = get_user_model()
            user = User.objects.get(id=user_id)

        for item in parsed_items:
            query_text = self._build_query_text_for_embedding(item.get("query"))
            if not query_text or user is None:
                candidates_by_intent.append([])
                continue

            embedding = EmbeddingsModelProvider.encode(query_text)
            if embedding is None or len(embedding) == 0:
                candidates_by_intent.append([])
                continue

            scope = self._resolve_scope_by_entity_type(item.get("entity_type"))
            intent_candidates = self.semantic_search.find_candidates(
                user=user,
                embedding=embedding,
                similarity_threshold=0.7,
                limit=3,
                scope=scope,
            )
            candidates_by_intent.append(intent_candidates)
            candidates.extend(intent_candidates)

        # Пока заглушка для ответа ассистента: здесь будет развиваться
        # основная бизнес-логика (действия по интентам, reply builder и т.д.).
        return ChatOrchestratorResult(
            message=message,
            assistant_reply="",
            user_id=user_id,
            intent_parser=parsed_intent_payload,
            candidates=candidates,
            candidates_by_intent=candidates_by_intent,
        )
    

    def _parse_intent_payload(self, message: str) -> dict[str, Any]:
        try:
            parsed_intent_result = self.intent_parser.parse(message)
            return {
                "items": [asdict(item) for item in parsed_intent_result.items],
            }
        except Exception as exc:
            # Не роняем ассистента, если parser/LLM временно недоступны.
            return {
                "items": [],
                "error": str(exc),
            }

    @staticmethod
    def _build_query_text_for_embedding(query: Any) -> str | None:
        if not isinstance(query, dict):
            return None

        preferred_order = (
            "title",
            "summary",
            "description",
            "notes",
        )
        parts: list[str] = []
        for key in preferred_order:
            value = query.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                parts.append(text)

        if not parts:
            return None
        return " ".join(parts)

    @staticmethod
    def _resolve_scope_by_entity_type(entity_type: Any) -> str:
        if entity_type == "task":
            return "tasks"
        if entity_type == "event":
            return "events"
        return "all"
