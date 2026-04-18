from unittest import mock

from django.test import TestCase

from assistant.integrations.llm_client import LLMClientError
from assistant.services import intent_parser as intent_parser_module
from assistant.services.intent_parser import IntentParserService, ParsedIntentResult


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

    def test_parse_fallback_to_other_when_llm_call_fails(self):
        fake = FakeLLMClient(should_raise=True)
        parser = IntentParserService(llm_client=fake)

        with mock.patch.object(intent_parser_module.logger, "warning"):
            result = parser.parse("Что-то непонятное")

        self.assertEqual(len(result.items), 1)
        r0 = result.items[0]
        self.assertEqual(r0.action, "other")
        self.assertIsNone(r0.entity_type)
        self.assertIsNone(r0.query)
        self.assertEqual(r0.fields, {})
        self.assertEqual(r0.datetime, {})
        self.assertEqual(r0.meta, {})
        self.assertEqual(r0.filters, {})

    def test_parse_fallback_to_other_when_json_is_invalid(self):
        fake = FakeLLMClient(response="не json")
        parser = IntentParserService(llm_client=fake)

        result = parser.parse("Удали что-нибудь")

        self.assertEqual(result.items[0].action, "other")
        self.assertIsNone(result.items[0].entity_type)
        self.assertEqual(result.raw_response, "не json")

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
