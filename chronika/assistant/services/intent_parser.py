import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils import timezone as django_timezone

from assistant.integrations.llm_client import LLMClientError, MistralLLMClient
from assistant.pipeline_log import log_exception, pretty_data, trace
from core.exceptions import AssistantLLMParseError

logger = logging.getLogger(__name__)

# Если при create LLM не вернул duration — одно значение по умолчанию (без подбора по ключевым словам).
DEFAULT_CREATE_DURATION_MINUTES = 30


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
        trace(
            "IntentParser: что уходит в LLM (текст пользователя и полные сообщения)",
            пользовательский_текст=pretty_data({"text": user_text}),
            сообщения_для_llm=pretty_data(messages),
            max_tokens=str(max_tokens),
        )

        started_at = time.perf_counter()
        raw_response = self._llm_chat_with_retry(messages, max_tokens, label="primary")
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        print(
            f"[IntentParser] primary inference done: elapsed_ms={elapsed_ms}, "
            f"response_len={len(raw_response)}"
        )
        parsed = self._safe_parse_json(raw_response)
        if parsed is None:
            retry_tokens = min(max_tokens * 2, 1200)
            print(
                "[IntentParser] primary response JSON parse failed; "
                f"retrying inference with retry_tokens={retry_tokens}"
            )
            retry_started_at = time.perf_counter()
            raw_response = self._llm_chat_with_retry(messages, retry_tokens, label="retry_parse")
            retry_elapsed_ms = int((time.perf_counter() - retry_started_at) * 1000)
            print(
                f"[IntentParser] retry inference done: elapsed_ms={retry_elapsed_ms}, "
                f"response_len={len(raw_response)}"
            )
            parsed = self._safe_parse_json(raw_response)
            if parsed is None:
                print("[IntentParser] retry JSON parse failed; raising AssistantLLMParseError")
                logger.warning("Intent parser: JSON parse failed after LLM retry")
                err = AssistantLLMParseError()
                log_exception("intent.parse", "IntentParserService.parse", err)
                raise err

        result = self._normalize_root(parsed, raw_response=raw_response)
        print(
            f"[IntentParser] parse success: items_count={len(result.items)}, "
            f"raw_response_len={len(raw_response)}"
        )
        return result

    def _llm_chat_with_retry(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        *,
        label: str,
    ) -> str:
        for attempt in range(2):
            try:
                return self.llm_client.chat_with_messages(
                    messages=messages,
                    temperature=0.0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            except LLMClientError as exc:
                print(f"[IntentParser] {label} LLM error (attempt {attempt + 1}): {exc}")
                logger.warning("Intent parser LLM call failed (%s, attempt %s): %s", label, attempt + 1, exc)
                if attempt == 1:
                    log_exception("intent.parse.llm", "IntentParserService._llm_chat_with_retry", exc)
                    raise AssistantLLMParseError() from exc

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
            f"Ориентир времени для пользователя: сегодня {d} ({wd}), часовой пояс {settings.TIME_ZONE}. "
            "Переводи «сегодня», «завтра», «послезавтра», названия дней недели в конкретную календарную дату: "
            "поле datetime.date (или date_from/date_to для диапазона дней). "
            "Не подставляй вымышленные часы минуты, если пользователь их не назвал явно (например «в 15:30», «с 18 до 20»).\n"
        )

    def _build_messages(self, user_text: str) -> list[dict[str, str]]:
        actions_schema = self._render_actions_schema()
        system_prompt = (
            "Ты Intent Parser для приложения с задачами и календарём. Задача — только структурировать реплику "
            "пользователя в JSON. Не выполняй действия, не комментируй, не оборачивай ответ в markdown — "
            "только один JSON-объект.\n\n"
            "Корень ответа: либо один объект-шаг, либо {\"items\": [шаг1, шаг2, …]} если в одной фразе несколько "
            "разных действий (порядок шагов = порядок в речи).\n\n"
            "Каждый шаг — объект с ключами: action, entity_type, query, fields, datetime, meta, filters. "
            "Обязателен только action; остальное при отсутствии данных — null или пустой объект {}.\n\n"
            "action (строго нижний регистр) — тип шага, совпадает с Action.type в плане: "
            "create | schedule | update | delete | retrieve | other.\n"
            "entity_type: task | event | unknown | null. Для action=other укажи entity_type: null.\n\n"
            "create: новая сущность — как правило query: null, всё содержимое в fields и datetime.\n"
            "schedule | update | delete | retrieve: если речь о существующем объекте — заполни query так, "
            "чтобы по нему можно было найти задачу или событие.\n\n"
            "query — признаки для поиска уже существующей задачи или события (актуально для schedule, update, delete, "
            "retrieve). Если пользователь ссылается на существующий объект — заполни query конкретно.\n"
            "Разрешённые ключи query: title, summary, description, notes, due_date, start, end, priority, completed.\n\n"
            "fields — данные для создания или правки сущности.\n"
            "- task: title, notes, priority, category_id, duration, due_date, completed.\n"
            "- event: summary, description, duration, user_calendar_id. "
            "Не клади в fields ключи start/end — только в datetime (см. ниже).\n"
            "- при entity_type=unknown в fields допускаются только: title, description, notes.\n\n"
            "datetime — календарь и время шага.\n"
            "- Один день: date (YYYY-MM-DD).\n"
            "- Диапазон календарных дней без конкретных часов («с понедельника по среду», «с 1 по 5 апреля», «эта неделя» как несколько дней): "
            "datetime.date_from и datetime.date_to (оба YYYY-MM-DD). Это основной способ спарсить именно **диапазон дат**; "
            "time_constraints тогда не обязателен, если отдельно не нужно окно времени суток.\n"
            "- Точный слот (только если пользователь назвал конкретное время или интервал часов): "
            "start_at, end_at — ISO 8601 с часовым поясом или Z.\n"
            "- Если время неточное («утром», «днём», «вечером», «на понедельник вечером», «на выходных», "
            "«до конца недели» и т.п.) — НЕ выбирай конкретный слот. "
            "Вместо start_at/end_at и вместо выдуманных часов в fields используй объект datetime.time_constraints:\n"
            '  {"type":"exact|interval|window|range|deadline","start":"...","end":"...","preferences":{"flexible":true}}\n'
            "Смысл type:\n"
            "- exact — пользователь дал конкретное время; тогда обязательны start_at/end_at (или пара start/end в смысле слота), "
            "time_constraints можно не задавать.\n"
            "- window — окно в течение одного календарного дня; start/end внутри time_constraints — только границы из таблицы "
            "ниже (для «вечером» на date=2026-04-20: type=window, start=17:00, end=22:00 в локальном дне date).\n"
            "- interval | range — диапазон по **времени суток или таймлайну** (часы/минуты в start/end constraints или в связке с date); "
            "не путай с диапазоном **календарных дней** — для дней используй date_from/date_to.\n"
            "- deadline — «к среде», «не позже пятницы», «сдать к концу дня»: граница во времени без выбора слота планировщиком. "
            "Обычно достаточно datetime.date или пары date + time_constraints с type=deadline и end как конец допустимого интервала "
            "(дата или ISO конца дня в локальной зоне); не придумывай start_at/end_at как конкретную встречу, если пользователь их не назвал.\n"
            "Нормализация частей суток (локальное время пользователя, границы для time_constraints.start/end как время суток):\n"
            "| утро | 06:00–11:00 |\n| день | 11:00–17:00 |\n| вечер | 17:00–22:00 |\n"
            "«Выходные» — date_from/date_to на ближайшие сб–вс или пара шагов; «до конца недели» — date_to = воскресенье той же недели.\n"
            "Принцип: при неточной формулировке LLM задаёт ограничения (time_constraints + date), планировщик позже выберет слот — "
            "не заполняй start_at/end_at вымышленными значениями.\n"
            "duration (целые минуты) — в fields.duration для task/event; дублировать в datetime.duration можно.\n"
            "timezone, is_all_day — по необходимости.\n"
            "meta: scope, source_text.\n"
            "filters: date, date_from, date_to, priority, status, completed, category_id.\n\n"
            "Не добавляй ключи вне списков для соответствующего блока (query / fields / datetime / meta / filters).\n"
            "Обязательно для action=create при entity_type task или event: всегда укажи fields.duration — целые минуты "
            "(оценка блока времени / выполнения). Если в реплике нет явной длительности — разумная оценка по смыслу, не ниже 15. "
            "Если заданы точные start_at и end_at, duration не противоречь интервалу.\n\n"
            f"{self._now_context_for_prompt()}"
            "Пример одного шага (структура, значения вымышленные):\n"
            '{"action":"create","entity_type":"task","query":null,'
            '"fields":{"title":"…","duration":30},"datetime":{"date":"2026-04-20"},"meta":{},"filters":{}}\n'
            "Пример create event «вечером в понедельник» (без выдуманного ISO-слота):\n"
            '{"action":"create","entity_type":"event","query":null,'
            '"fields":{"summary":"Встреча с коллегами","duration":120},'
            '"datetime":{"date":"2026-04-20","time_constraints":{"type":"window","start":"17:00","end":"22:00",'
            '"preferences":{"flexible":true}}},"meta":{},"filters":{}}\n'
            "Пример задачи на диапазон дат (без часов):\n"
            '{"action":"create","entity_type":"task","query":null,'
            '"fields":{"title":"Подготовить отчёт","duration":120},'
            '"datetime":{"date_from":"2026-04-20","date_to":"2026-04-22"},"meta":{},"filters":{}}\n'
            "Пример двух шагов в одной реплике:\n"
            '{"items":['
            '{"action":"create","entity_type":"task","query":null,"fields":{"title":"…"},"datetime":{},'
            '"meta":{},"filters":{}},'
            '{"action":"delete","entity_type":"event","query":{"summary":"…"},"fields":{},'
            '"datetime":{},"meta":{},"filters":{}}'
            "]}\n\n"
            f"Пояснения по кодам action:\n{actions_schema}"
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

        raw_fields = payload.get("fields", {})
        if not isinstance(raw_fields, dict):
            raw_fields = {}

        datetime_payload = payload.get("datetime", {})
        if not isinstance(datetime_payload, dict):
            datetime_payload = {}
        datetime_payload = self._sanitize_datetime_payload(datetime_payload)

        if entity_type == "event":
            self._migrate_event_start_end_fields_to_datetime(raw_fields, datetime_payload)

        fields = self._normalize_fields_by_entity_type(raw_fields, entity_type)

        self._resolve_vague_time_vs_exact_slot(datetime_payload)
        if "duration" in datetime_payload:
            dv = datetime_payload.pop("duration")
            if fields.get("duration") in (None, ""):
                fields["duration"] = dv
        self._coerce_duration_field(fields)
        self._default_duration_create(
            action=action,
            entity_type=entity_type,
            fields=fields,
            datetime_payload=datetime_payload,
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

    def _sanitize_datetime_payload(self, datetime_payload: dict[str, Any]) -> dict[str, Any]:
        d = dict(datetime_payload)
        if "start" in d and d.get("start_at") in (None, ""):
            d["start_at"] = d.pop("start", None)
        if "end" in d and d.get("end_at") in (None, ""):
            d["end_at"] = d.pop("end", None)
        allowed = {
            "date",
            "date_from",
            "date_to",
            "start_at",
            "end_at",
            "timezone",
            "is_all_day",
            "duration",
            "time_constraints",
        }
        dt = self._pick_allowed_keys(d, allowed)
        tc_raw = dt.get("time_constraints")
        tc = self._normalize_time_constraints_value(tc_raw)
        if tc:
            dt["time_constraints"] = tc
        else:
            dt.pop("time_constraints", None)
        return dt

    @staticmethod
    def _normalize_time_constraints_value(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        allowed_inner = frozenset({"type", "start", "end", "preferences"})
        out: dict[str, Any] = {k: v for k, v in raw.items() if k in allowed_inner}
        if "type" in out:
            t = str(out["type"]).strip().lower()
            if t in ("exact", "interval", "window", "range", "deadline"):
                out["type"] = t
            else:
                out.pop("type", None)
        pref = out.get("preferences")
        if pref is not None and not isinstance(pref, dict):
            out.pop("preferences", None)
        elif isinstance(pref, dict):
            out["preferences"] = {k: pref[k] for k in ("flexible",) if k in pref}
        return out or None

    @staticmethod
    def _migrate_event_start_end_fields_to_datetime(
        raw_fields: dict[str, Any],
        datetime_payload: dict[str, Any],
    ) -> None:
        for src, dst in (("start", "start_at"), ("end", "end_at")):
            v = raw_fields.get(src)
            if v in (None, ""):
                continue
            if datetime_payload.get(dst) in (None, ""):
                datetime_payload[dst] = v
                raw_fields.pop(src, None)

    @staticmethod
    def _resolve_vague_time_vs_exact_slot(datetime_payload: dict[str, Any]) -> None:
        tc = datetime_payload.get("time_constraints")
        if not isinstance(tc, dict):
            return
        t = str(tc.get("type") or "").strip().lower()
        if t in ("window", "interval", "range"):
            datetime_payload.pop("start_at", None)
            datetime_payload.pop("end_at", None)
        elif t == "deadline":
            # «Не позже» — граница может быть в end_at или в time_constraints.end; start_at без явного времени не нужен.
            datetime_payload.pop("start_at", None)

    @staticmethod
    def _coerce_duration_field(fields: dict[str, Any]) -> None:
        raw = fields.get("duration")
        if raw is None or raw == "":
            return
        try:
            n = int(float(raw))
            if n < 1:
                fields.pop("duration", None)
            else:
                fields["duration"] = n
        except (TypeError, ValueError):
            fields.pop("duration", None)

    @staticmethod
    def _default_duration_create(
        *,
        action: str,
        entity_type: str | None,
        fields: dict[str, Any],
        datetime_payload: dict[str, Any],
    ) -> None:
        if action != "create" or entity_type not in ("task", "event"):
            return
        if fields.get("duration") is not None:
            return
        if entity_type == "event":
            if datetime_payload.get("end_at") not in (None, ""):
                return
        fields["duration"] = DEFAULT_CREATE_DURATION_MINUTES

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
        event_keys = {"summary", "description", "duration", "user_calendar_id"}
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
