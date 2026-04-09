from dataclasses import asdict, dataclass
from typing import Any

from assistant.services.intent_parser import IntentParserService


@dataclass
class ChatOrchestratorResult:
    message: str
    assistant_reply: str
    user_id: int
    intent_parser: dict[str, Any]


class ChatOrchestratorService:
    """
    Оркестратор бизнес-логики ассистента.
    """

    def __init__(self, intent_parser: IntentParserService | None = None):
        self.intent_parser = intent_parser or IntentParserService()

    def process_message(self, user_id: int, message: str) -> ChatOrchestratorResult:
        parsed_intent_payload = self._parse_intent_payload(message)

        # Пока заглушка для ответа ассистента: здесь будет развиваться
        # основная бизнес-логика (действия по интентам, reply builder и т.д.).
        return ChatOrchestratorResult(
            message=message,
            assistant_reply="",
            user_id=user_id,
            intent_parser=parsed_intent_payload,
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
