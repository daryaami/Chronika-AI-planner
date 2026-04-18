import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils import timezone as django_timezone

from assistant.integrations.llm_client import LLMClientError, MistralLLMClient

logger = logging.getLogger(__name__)

def normalize_action_code(raw: str | None) -> str:
    """Только нормализация строки: допустимые коды — ровно Action.type из схемы (без синонимов)."""
    return str(raw or "").strip().lower()


@dataclass
class ActionDefinition:
    """Описание одного допустимого значения поля action (тип шага = Action.type в Action Plan)."""
    code: str
    description: str
    required_fields: list[str] = field(default_factory=list)


@dataclass
class ParsedIntent:
    """Один шаг: тип действия совпадает с Action.type в Action Plan (поле action)."""
    action: str
    entity_type: str | None
    query: dict[str, Any] | None
    fields: dict[str, Any]
    datetime: dict[str, Any]
    meta: dict[str, Any]
    filters: dict[str, Any]


@dataclass
class ParsedIntentResult:
    """Результат разбора: шаги (action) в порядке упоминания в тексте."""

    items: list[ParsedIntent]
    raw_response: str | None = None


DEFAULT_ACTIONS: list[ActionDefinition] = [
    ActionDefinition(
        code="create",
        description="Создать новую задачу или событие.",
        required_fields=["fields.title или query"],
    ),
    ActionDefinition(
        code="schedule",
        description="Назначить время существующей задаче/событию или перенести время.",
        required_fields=["query (если объект уже существует)"],
    ),
    ActionDefinition(
        code="update",
        description="Изменить поля существующей сущности.",
        required_fields=["query"],
    ),
    ActionDefinition(
        code="delete",
        description="Удалить существующую сущность.",
        required_fields=["query"],
    ),
    ActionDefinition(
        code="retrieve",
        description="Найти, показать список или сводку задач/событий по фильтрам.",
        required_fields=[],
    ),
    ActionDefinition(
        code="other",
        description="Прочие сообщения, не относящиеся к задачам/событиям.",
        required_fields=[],
    ),
]


class IntentParserService:
    """
    Парсер первого уровня: шаги с полем action, совпадающим с Action.type в Action Plan
    (create | schedule | update | delete | retrieve | other).
    """

    def __init__(
        self,
        llm_client: MistralLLMClient | None = None,
        actions: list[ActionDefinition] | None = None,
        *,
        intents: list[ActionDefinition] | None = None,
    ):
        self.llm_client = llm_client or MistralLLMClient()
        self._action_definitions = actions or intents or DEFAULT_ACTIONS

    def parse(self, user_text: str) -> ParsedIntentResult:
        messages = self._build_messages(user_text)
        max_tokens = self._resolve_max_tokens(user_text)
        input_len = len((user_text or "").strip())
        print(
            f"[IntentParser] start parse: input_len={input_len}, "
            f"max_tokens={max_tokens}, messages={len(messages)}"
        )

        try:
            started_at = time.perf_counter()
            raw_response = self.llm_client.chat_with_messages(
                messages=messages,
                temperature=0.0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            print(
                f"[IntentParser] primary inference done: elapsed_ms={elapsed_ms}, "
                f"response_len={len(raw_response)}"
            )
        except LLMClientError as exc:
            print(f"[IntentParser] primary inference error: {exc}")
            logger.warning("Intent parser failed to call LLM: %s", exc)
            return self._fallback_result(raw_response=None)

        parsed = self._safe_parse_json(raw_response)
        if parsed is None:
            # Retry once with a larger budget: multi-step requests can produce
            # longer JSON and may be truncated on first attempt.
            retry_tokens = min(max_tokens * 2, 1200)
            print(
                "[IntentParser] primary response JSON parse failed; "
                f"retrying with retry_tokens={retry_tokens}"
            )
            try:
                retry_started_at = time.perf_counter()
                raw_response_retry = self.llm_client.chat_with_messages(
                    messages=messages,
                    temperature=0.0,
                    max_tokens=retry_tokens,
                    response_format={"type": "json_object"},
                )
                retry_elapsed_ms = int((time.perf_counter() - retry_started_at) * 1000)
                print(
                    f"[IntentParser] retry inference done: elapsed_ms={retry_elapsed_ms}, "
                    f"response_len={len(raw_response_retry)}"
                )
            except LLMClientError as exc:
                print(f"[IntentParser] retry inference error: {exc}")
                logger.warning("Intent parser retry failed to call LLM: %s", exc)
                return self._fallback_result(raw_response=raw_response)

            parsed_retry = self._safe_parse_json(raw_response_retry)
            if parsed_retry is None:
                print("[IntentParser] retry JSON parse failed; fallback=intent_other")
                return self._fallback_result(raw_response=raw_response_retry)
            result = self._normalize_root(parsed_retry, raw_response=raw_response_retry)
            print(
                f"[IntentParser] retry parse success: items_count={len(result.items)}, "
                f"raw_response_len={len(raw_response_retry)}"
            )
            return result

        result = self._normalize_root(parsed, raw_response=raw_response)
        print(
            f"[IntentParser] primary parse success: items_count={len(result.items)}, "
            f"raw_response_len={len(raw_response)}"
        )
        return result

    @staticmethod
    def _resolve_max_tokens(user_text: str) -> int:
        """
        Dynamic budget for response tokens:
        - short inputs get a smaller cap (faster/cheaper),
        - long inputs still get enough space for structured JSON.
        """
        text = (user_text or "").strip()
        char_count = len(text)

        # Rough heuristic: ~4 chars per token + baseline for JSON structure.
        estimated_tokens = 120 + (char_count // 4)
        return max(200, min(estimated_tokens, 700))

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
        actions_schema = self._render_actions_schema()
        system_prompt = (
            "Ты Intent Parser для системы задач и календаря.\n"
            "Твоя задача — только структурировать запрос пользователя в JSON, без принятия решений.\n"
            "Верни строго один JSON-объект без markdown, без комментариев и без текста вокруг.\n"
            "Каждый шаг имеет поле action — это то же значение, что поле type у Action в Action Plan.\n"
            "Допустимы только такие строки для action (ровно в нижнем регистре): "
            "create, schedule, update, delete, retrieve, other.\n"
            "В каждом шаге обязателен ключ action (не используй другие имена для типа шага).\n"
            "Если определить значение нельзя, заполняй null, пустым объектом {} или unknown.\n"
            "Если пользователь говорит о существующей сущности, обязательно заполни query.\n"
            "query содержит признаки для поиска существующей сущности.\n"
            "Разрешенные поля query: title, summary, description, notes, due_date, start, end, "
            "priority, completed.\n"
            "entity_type может быть только: task, event, unknown или null (только для action=other).\n"
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
            "Формат одного шага (step_item):\n"
            "{\n"
            '  "action": "create|schedule|update|delete|retrieve|other",\n'
            '  "entity_type": "task|event|unknown|null",\n'
            '  "query": {},\n'
            '  "fields": {},\n'
            '  "datetime": {},\n'
            '  "meta": {},\n'
            '  "filters": {}\n'
            "}\n"
            "Формат нескольких шагов:\n"
            '{"items": [ step_item, step_item, ... ]}\n'
            f"Доступные значения action:\n{actions_schema}"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

    def _render_actions_schema(self) -> str:
        lines = []
        for definition in self._action_definitions:
            required = ", ".join(definition.required_fields) if definition.required_fields else "нет"
            lines.append(
                f"- {definition.code}: {definition.description}; обязательные_поля=[{required}]"
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
            for k in ("action", "entity_type", "query", "fields", "datetime", "meta", "filters")
        )

    def _normalize_item_payload(self, payload: dict[str, Any]) -> ParsedIntent:
        allowed_codes = {item.code for item in self._action_definitions}
        raw_step = payload.get("action")
        action = normalize_action_code(str(raw_step if raw_step is not None else "other"))
        if action not in allowed_codes:
            action = "other"

        entity_type = payload.get("entity_type", "unknown")
        if entity_type not in {"task", "event", "unknown", None}:
            entity_type = "unknown"
        if action == "other":
            entity_type = None

        query = payload.get("query")
        if not isinstance(query, dict):
            query = {}
        query = self._normalize_query_by_entity_type(query, entity_type)
        if not query:
            query = None

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
            action=action,
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

    def _normalize_query_by_entity_type(
        self,
        query: dict[str, Any],
        entity_type: str | None,
    ) -> dict[str, Any]:
        common_keys = {"title", "summary", "description", "notes"}
        task_keys = common_keys | {"due_date", "priority", "category_id", "completed"}
        event_keys = common_keys | {"start", "end", "google_event_id", "google_calendar_id"}
        unknown_keys = common_keys | {"due_date", "start", "end", "priority"}

        if entity_type == "task":
            allowed = task_keys
        elif entity_type == "event":
            allowed = event_keys
        elif entity_type == "unknown":
            allowed = unknown_keys
        else:
            allowed = set()

        return self._pick_allowed_keys(query, allowed)

    def _fallback_result(self, raw_response: str | None) -> ParsedIntentResult:
        return ParsedIntentResult(
            items=[
                ParsedIntent(
                    action="other",
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


# Старые имена (импорт из внешнего кода / ноутбуков)
IntentDefinition = ActionDefinition
DEFAULT_INTENTS = DEFAULT_ACTIONS


# Старые имена (импорт из внешнего кода / ноутбуков)
IntentDefinition = ActionDefinition
DEFAULT_INTENTS = DEFAULT_ACTIONS
