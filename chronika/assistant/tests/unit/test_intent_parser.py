from unittest import mock

from django.test import TestCase

from assistant.integrations.llm_client import LLMClientError
from assistant.services import intent_parser as intent_parser_module
from assistant.services.intent_parser import IntentParserService, ParsedIntentResult
from core.exceptions import AssistantLLMParseError


class FakeLLMClient:
    def __init__(self, response: str | None = None, should_raise: bool = False):
        self.response = response or "{}"
        self.should_raise = should_raise
        self.last_messages = None
        self.last_response_format = None

    def chat_with_messages(self, messages, temperature, max_tokens, response_format=None):
        self.last_messages = messages
        self.last_response_format = response_format
        if self.should_raise:
            raise LLMClientError("boom")
        return self.response


class IntentParserServiceTests(TestCase):
    def test_parse_returns_structured_payload_for_valid_json(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"task","query":null,'
                '"fields":{"title":"купить продукты"},'
                '"datetime":{"date":"2026-03-28"},"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)

        result = parser.parse("Создай задачу купить продукты на завтра")

        self.assertIsInstance(result, ParsedIntentResult)
        self.assertEqual(len(result.items), 1)
        r0 = result.items[0]
        self.assertEqual(r0.action, "create")
        self.assertEqual(r0.entity_type, "task")
        self.assertIsNone(r0.query)
        self.assertEqual(r0.fields.get("title"), "купить продукты")
        self.assertEqual(r0.datetime.get("date"), "2026-03-28")
        self.assertEqual(r0.meta, {})
        self.assertEqual(r0.filters, {})

    def test_parse_unknown_action_code_becomes_other(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"find","entity_type":"task","query":null,'
                '"fields":{},"datetime":{},"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)

        result = parser.parse("Найди мои задачи")

        self.assertEqual(result.items[0].action, "other")

    def test_parse_json_without_action_key_yields_other(self):
        fake = FakeLLMClient(
            response=(
                '{"intent":"schedule","entity_type":"task","query":{"title":"полить цветы"},'
                '"fields":{},"datetime":{},"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)

        result = parser.parse("Запланируй задачу полить цветы")

        self.assertEqual(result.items[0].action, "other")
        self.assertIsNone(result.items[0].entity_type)

    def test_parse_raises_after_llm_call_fails_twice(self):
        fake = FakeLLMClient(should_raise=True)
        parser = IntentParserService(llm_client=fake)

        with mock.patch.object(intent_parser_module.logger, "warning"):
            with self.assertRaises(AssistantLLMParseError):
                parser.parse("Что-то непонятное")

    def test_parse_raises_when_json_invalid_after_retry_inference(self):
        fake = FakeLLMClient(response="не json")
        parser = IntentParserService(llm_client=fake)

        with self.assertRaises(AssistantLLMParseError):
            parser.parse("Удали что-нибудь")

    def test_parse_extracts_json_from_noisy_response(self):
        fake = FakeLLMClient(
            response=(
                "Ответ:\n"
                '{"action":"delete","entity_type":"unknown","query":{"title":"купить продукты"},'
                '"fields":{},"datetime":{},"meta":{"scope":"single"},"filters":{}}'
                "\nСпасибо"
            )
        )
        parser = IntentParserService(llm_client=fake)

        result = parser.parse("Удали задачу купить продукты")

        self.assertEqual(result.items[0].action, "delete")
        self.assertEqual(result.items[0].query, {"title": "купить продукты"})
        self.assertEqual(result.items[0].meta.get("scope"), "single")

    def test_parse_normalizes_invalid_action_and_entity_type(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"unsupported_intent","entity_type":"meeting","query":"встреча",'
                '"fields":"bad","datetime":"bad","meta":"bad","filters":"bad"}'
            )
        )
        parser = IntentParserService(llm_client=fake)

        result = parser.parse("Сделай что-то со встречей")

        self.assertEqual(result.items[0].action, "other")
        self.assertIsNone(result.items[0].entity_type)
        self.assertEqual(result.items[0].fields, {})
        self.assertEqual(result.items[0].datetime, {})
        self.assertEqual(result.items[0].meta, {})
        self.assertEqual(result.items[0].filters, {})

    def test_parser_asks_for_json_object_response_format(self):
        fake = FakeLLMClient(
            response='{"action":"other","entity_type":null,"query":null,"fields":{},"datetime":{},"meta":{},"filters":{}}'
        )
        parser = IntentParserService(llm_client=fake)

        parser.parse("Привет")

        self.assertEqual(fake.last_response_format, {"type": "json_object"})

    def test_parse_multiple_items_returns_ordered_list(self):
        fake = FakeLLMClient(
            response=(
                '{"items":['
                '{"action":"create","entity_type":"task","query":null,'
                '"fields":{"title":"купить молоко"},"datetime":{},"meta":{},"filters":{}},'
                '{"action":"delete","entity_type":"event","query":{"summary":"встреча с клиентом"},'
                '"fields":{},"datetime":{},"meta":{},"filters":{}}'
                "]}"
            )
        )
        parser = IntentParserService(llm_client=fake)

        result = parser.parse("Создай задачу купить молоко и удали встречу с клиентом")

        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.items[0].action, "create")
        self.assertEqual(result.items[0].fields.get("title"), "купить молоко")
        self.assertEqual(result.items[1].action, "delete")
        self.assertEqual(result.items[1].query, {"summary": "встреча с клиентом"})

    def test_parse_normalizes_query_dict_and_drops_unknown_keys(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"update","entity_type":"task",'
                '"query":{"title":"купить молоко","priority":"HIGH","foo":"bar"},'
                '"fields":{"priority":"LOW"},"datetime":{},"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)

        result = parser.parse("Обнови приоритет задачи купить молоко")

        self.assertEqual(
            result.items[0].query,
            {"title": "купить молоко", "priority": "HIGH"},
        )

    def test_no_duration_when_event_has_end(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"event","query":null,'
                '"fields":{"summary":"X"},'
                '"datetime":{"start_at":"2026-04-20T10:00:00","end_at":"2026-04-20T11:00:00"},'
                '"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)
        result = parser.parse("событие")
        self.assertIsNone(result.items[0].fields.get("duration"))

    def test_default_duration_when_create_task_omits_it(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"task","query":null,'
                '"fields":{"title":"Полить цветы"},'
                '"datetime":{},"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)
        result = parser.parse("Создай задачу полить цветы")
        self.assertEqual(result.items[0].fields.get("duration"), 30)

    def test_default_duration_when_create_task_has_date_only(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"task","query":null,'
                '"fields":{"title":"Полить цветы"},'
                '"datetime":{"date":"2026-04-20"},"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)
        result = parser.parse("На понедельник поставь задачу полить цветы")
        self.assertEqual(result.items[0].fields.get("duration"), 30)

    def test_default_duration_when_create_event_omits_it(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"event","query":null,'
                '"fields":{"summary":"Созвон"},'
                '"datetime":{"start_at":"2026-04-20T10:00:00"},'
                '"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)
        result = parser.parse("созвон в 10")
        self.assertEqual(result.items[0].fields.get("duration"), 30)

    def test_duration_in_datetime_moved_to_fields(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"event","query":null,'
                '"fields":{"summary":"X"},'
                '"datetime":{"start_at":"2026-04-20T10:00:00","duration":45},"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)
        result = parser.parse("событие")
        self.assertEqual(result.items[0].fields.get("duration"), 45)
        self.assertNotIn("duration", result.items[0].datetime)

    def test_time_constraints_window_drops_conflicting_start_at(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"event","query":null,'
                '"fields":{"summary":"Встреча","duration":60},'
                '"datetime":{"date":"2026-04-20","start_at":"2026-04-20T18:00:00Z","end_at":"2026-04-20T20:00:00Z",'
                '"time_constraints":{"type":"window","start":"17:00","end":"22:00","preferences":{"flexible":true}}},'
                '"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)
        result = parser.parse("вечером встреча")
        dt = result.items[0].datetime
        self.assertNotIn("start_at", dt)
        self.assertNotIn("end_at", dt)
        self.assertEqual(dt.get("date"), "2026-04-20")
        tc = dt.get("time_constraints")
        self.assertIsInstance(tc, dict)
        self.assertEqual(tc.get("type"), "window")

    def test_time_constraints_deadline_drops_start_at_only(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"task","query":null,'
                '"fields":{"title":"Отчёт","duration":60},'
                '"datetime":{"date":"2026-04-25","start_at":"2026-04-25T09:00:00Z","end_at":"2026-04-25T18:00:00Z",'
                '"time_constraints":{"type":"deadline","end":"2026-04-25T18:00:00","preferences":{"flexible":true}}},'
                '"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)
        result = parser.parse("отчёт к пятнице вечером")
        dt = result.items[0].datetime
        self.assertNotIn("start_at", dt)
        self.assertEqual(dt.get("end_at"), "2026-04-25T18:00:00Z")
        self.assertEqual(dt.get("time_constraints", {}).get("type"), "deadline")

    def test_legacy_start_in_fields_moved_to_datetime(self):
        fake = FakeLLMClient(
            response=(
                '{"action":"create","entity_type":"event","query":null,'
                '"fields":{"summary":"X","start":"2026-04-20T10:00:00"},'
                '"datetime":{},"meta":{},"filters":{}}'
            )
        )
        parser = IntentParserService(llm_client=fake)
        result = parser.parse("событие")
        self.assertEqual(result.items[0].datetime.get("start_at"), "2026-04-20T10:00:00")
        self.assertIsNone(result.items[0].fields.get("start"))
