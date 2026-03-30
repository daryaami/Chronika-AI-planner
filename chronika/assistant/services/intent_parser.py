import json
import logging
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils import timezone as django_timezone

from assistant.integrations.llm_client import LLMClientError, MistralLLMClient

logger = logging.getLogger(__name__)


@dataclass
class IntentDefinition:
    code: str
    description: str
    required_fields: list[str] = field(default_factory=list)


@dataclass
class ParsedIntent:
    """Одно намерение (один шаг)."""

    intent: str
    entity_type: str | None
    query: str | None
    fields: dict[str, Any]
    datetime: dict[str, Any]
    meta: dict[str, Any]
    filters: dict[str, Any]


@dataclass
class ParsedIntentResult:
    """Результат разбора: одно или несколько намерений в порядке упоминания в тексте."""

    items: list[ParsedIntent]
    raw_response: str | None = None


DEFAULT_INTENTS: list[IntentDefinition] = [
    IntentDefinition(
        code="create",
        description="Создать новую задачу или событие.",
        required_fields=["fields.title или query"],
    ),
    IntentDefinition(
        code="plan",
        description="Запланировать сущность на время/дату.",
        required_fields=["query"],
    ),
    IntentDefinition(
        code="update",
        description="Изменить поля существующей сущности.",
        required_fields=["query"],
    ),
    IntentDefinition(
        code="reschedule",
        description="Перенести существующую сущность на другое время/дату.",
        required_fields=["query"],
    ),
    IntentDefinition(
        code="delete",
        description="Удалить существующую сущность.",
        required_fields=["query"],
    ),
    IntentDefinition(
        code="get",
        description="Получить список/сводку сущностей по фильтрам.",
        required_fields=[],
    ),
    IntentDefinition(
        code="other",
        description="Прочие сообщения, не относящиеся к задачам/событиям.",
        required_fields=[],
    ),
]


class IntentParserService:
    """
    Service-level intent parser.

    Responsibilities:
    - build prompt from intent definitions
    - call LLM client
    - parse/normalize JSON response
    """

    def __init__(
        self,
        llm_client: MistralLLMClient | None = None,
        intents: list[IntentDefinition] | None = None,
    ):
        self.llm_client = llm_client or MistralLLMClient()
        self.intents = intents or DEFAULT_INTENTS

    def parse(self, user_text: str) -> ParsedIntentResult:
        messages = self._build_messages(user_text)
        try:
            raw_response = self.llm_client.chat_with_messages(
                messages=messages,
                temperature=0.0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
        except LLMClientError as exc:
            logger.warning("Intent parser failed to call LLM: %s", exc)
            return self._fallback_result(raw_response=None)

        parsed = self._safe_parse_json(raw_response)
        if parsed is None:
            return self._fallback_result(raw_response=raw_response)

        return self._normalize_root(parsed, raw_response=raw_response)

    @staticmethod
    def _now_context_for_prompt() -> str:
        """
        LLM has no real-time clock; without this, «завтра» cannot become a concrete date.
        Uses Django TIME_ZONE / USE_TZ (user-wide default until per-user TZ exists).
        """
        now = django_timezone.localtime(django_timezone.now())
        weekdays_ru = (
            "понедельник",
            "вторник",
            "среда",
            "четверг",
            "пятница",
            "суббота",
            "воскресенье",
        )
        wd = weekdays_ru[now.weekday()]
        d = now.date().isoformat()
        return (
            f"Ориентир по времени (сейчас для пользователя): дата {d}, {wd}, "
            f"часовой пояс {settings.TIME_ZONE}. "
            "По этим данным переводи «сегодня», «завтра», «послезавтра», дни недели в конкретные даты: "
            "в datetime (date, date_from, date_to, start_at, end_at) и при необходимости в fields.due_date "
            "используй ISO (YYYY-MM-DD или полный ISO 8601 для даты-времени).\n"
        )

    def _build_messages(self, user_text: str) -> list[dict[str, str]]:
        intents_schema = self._render_intents_schema()
        system_prompt = (
            "Ты Intent Parser для системы задач и календаря.\n"
            "Твоя задача — только структурировать запрос пользователя в JSON, без принятия решений.\n"
            "Верни строго JSON без markdown и без пояснений.\n"
            "Используй только интенты из списка ниже.\n"
            "Если определить значение нельзя, заполняй null, пустым объектом {} или unknown.\n"
            "Если пользователь говорит о существующей сущности, обязательно заполни query.\n"
            "entity_type может быть только: task, event, unknown или null (только для intent=other).\n"
            "Используй только разрешенные поля. Не добавляй ключи, которых нет в списках ниже.\n"
            "Поля fields для task: title, notes, priority, category_id, duration, due_date, completed.\n"
            "Поля fields для event: summary, description, start, end.\n"
            "Если entity_type=unknown, в fields можно использовать только общие поля: title, description, notes.\n"
            "Поля datetime: date, date_from, date_to, start_at, end_at, timezone, is_all_day.\n"
            "Поля meta: scope, source_text.\n"
            "Поля filters: date, date_from, date_to, priority, status, completed, category_id.\n"
            "Если в одной реплике несколько разных действий (например «создай задачу X и удали встречу Y»), "
            "верни JSON с ключом items — массив объектов, по одному на каждое действие, в порядке речи.\n"
            "Если действие одно, можно вернуть либо один объект как ниже, либо {\"items\": [ { ... один шаг ... } ]}.\n"
            f"{self._now_context_for_prompt()}"
            "Формат одного шага (intent_item):\n"
            "{\n"
            '  "intent": "create|plan|update|reschedule|delete|get|other",\n'
            '  "entity_type": "task|event|unknown|null",\n'
            '  "query": "строка или null",\n'
            '  "fields": {},\n'
            '  "datetime": {},\n'
            '  "meta": {},\n'
            '  "filters": {}\n'
            "}\n"
            "Формат нескольких шагов:\n"
            '{"items": [ intent_item, intent_item, ... ]}\n'
            f"Доступные интенты:\n{intents_schema}"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

    def _render_intents_schema(self) -> str:
        lines = []
        for intent in self.intents:
            required = ", ".join(intent.required_fields) if intent.required_fields else "нет"
            lines.append(
                f"- {intent.code}: {intent.description}; обязательные_поля=[{required}]"
            )
        return "\n".join(lines)

    @staticmethod
    def _safe_parse_json(raw_text: str) -> dict[str, Any] | None:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                return json.loads(raw_text[start : end + 1])
            except json.JSONDecodeError:
                return None

    def _normalize_root(self, payload: dict[str, Any], raw_response: str) -> ParsedIntentResult:
        items_raw = payload.get("items")
        if isinstance(items_raw, list) and len(items_raw) > 0:
            items: list[ParsedIntent] = []
            for entry in items_raw:
                if isinstance(entry, dict):
                    items.append(self._normalize_item_payload(entry))
            if not items:
                return self._fallback_result(raw_response=raw_response)
            return ParsedIntentResult(items=items, raw_response=raw_response)

        if isinstance(payload, dict) and self._looks_like_single_intent(payload):
            return ParsedIntentResult(
                items=[self._normalize_item_payload(payload)],
                raw_response=raw_response,
            )

        return self._fallback_result(raw_response=raw_response)

    @staticmethod
    def _looks_like_single_intent(payload: dict[str, Any]) -> bool:
        return any(
            k in payload
            for k in ("intent", "entity_type", "query", "fields", "datetime", "meta", "filters")
        )

    def _normalize_item_payload(self, payload: dict[str, Any]) -> ParsedIntent:
        allowed_intents = {item.code for item in self.intents}
        intent = str(payload.get("intent", "other"))
        if intent not in allowed_intents:
            intent = "other"

        entity_type = payload.get("entity_type", "unknown")
        if entity_type not in {"task", "event", "unknown", None}:
            entity_type = "unknown"
        if intent == "other":
            entity_type = None

        query = payload.get("query")
        if query is not None:
            query = str(query).strip() or None

        fields = payload.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}
        fields = self._normalize_fields_by_entity_type(fields, entity_type)

        datetime_payload = payload.get("datetime", {})
        if not isinstance(datetime_payload, dict):
            datetime_payload = {}
        datetime_payload = self._pick_allowed_keys(
            datetime_payload,
            {"date", "date_from", "date_to", "start_at", "end_at", "timezone", "is_all_day"},
        )

        meta = payload.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        meta = self._pick_allowed_keys(meta, {"scope", "source_text"})

        filters = payload.get("filters", {})
        if not isinstance(filters, dict):
            filters = {}
        filters = self._pick_allowed_keys(
            filters,
            {"date", "date_from", "date_to", "priority", "status", "completed", "category_id"},
        )

        return ParsedIntent(
            intent=intent,
            entity_type=entity_type,
            query=query,
            fields=fields,
            datetime=datetime_payload,
            meta=meta,
            filters=filters,
        )

    @staticmethod
    def _pick_allowed_keys(payload: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key in allowed_keys}

    def _normalize_fields_by_entity_type(
        self,
        fields: dict[str, Any],
        entity_type: str | None,
    ) -> dict[str, Any]:
        task_keys = {
            "title",
            "notes",
            "priority",
            "category_id",
            "duration",
            "due_date",
            "completed",
        }
        event_keys = {"summary", "description", "start", "end", "user_calendar_id"}
        common_unknown_keys = {"title", "description", "notes"}

        if entity_type == "task":
            allowed = task_keys
        elif entity_type == "event":
            allowed = event_keys
        elif entity_type == "unknown":
            allowed = common_unknown_keys
        else:
            allowed = set()

        return self._pick_allowed_keys(fields, allowed)

    def _fallback_result(self, raw_response: str | None) -> ParsedIntentResult:
        return ParsedIntentResult(
            items=[
                ParsedIntent(
                    intent="other",
                    entity_type=None,
                    query=None,
                    fields={},
                    datetime={},
                    meta={},
                    filters={},
                )
            ],
            raw_response=raw_response,
        )
