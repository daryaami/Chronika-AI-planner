"""
Live Mistral calls. Not run by default (cost + flakiness).

  set RUN_LLM_INTEGRATION=1
  set MISTRAL_API_KEY=...   (or load via .env as usual)

  py manage.py test assistant.test_integration_llm
  Чтобы прогнать живой вызов:
    $env:RUN_LLM_INTEGRATION="1"
    # MISTRAL_API_KEY уже должен быть в .env / окружении
    py manage.py test assistant.test_integration_llm
"""

import json
import os
import unittest
from dataclasses import asdict

from django.conf import settings
from django.test import TestCase

from assistant.services.intent_parser import IntentParserService, ParsedIntentResult


def _print_live_parse(user_text: str, result: ParsedIntentResult) -> None:
    print("\n--- Запрос пользователя ---\n", user_text, sep="")
    print("\n--- Сырой ответ модели ---\n", result.raw_response or "(нет: сработал fallback)", sep="")
    print(
        "\n--- Нормализованный результат (items) ---\n",
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        sep="",
    )


@unittest.skipUnless(
    os.environ.get("RUN_LLM_INTEGRATION") == "1" and bool(getattr(settings, "MISTRAL_API_KEY", None)),
    "Set RUN_LLM_INTEGRATION=1 and MISTRAL_API_KEY to run live LLM tests",
)
class MistralLiveIntentParserTests(TestCase):
    def test_parse_create_task_russian(self):
        user_text = "Создай задачу купить хлеб на завтра"
        parser = IntentParserService()
        result = parser.parse(user_text)

        _print_live_parse(user_text, result)

        self.assertGreaterEqual(len(result.items), 1)
        self.assertEqual(result.items[0].intent, "create")
        self.assertEqual(result.items[0].entity_type, "task")
        blob = json.dumps(asdict(result), ensure_ascii=False).lower()
        self.assertIn("хлеб", blob)

    def test_parse_reschedule_meeting_next_monday_noon(self):
        user_text = (
            "Перенеси встречу с коллегами на следующий понедельник на 12 часов"
        )
        parser = IntentParserService()
        result = parser.parse(user_text)

        _print_live_parse(user_text, result)

        self.assertGreaterEqual(len(result.items), 1)
        self.assertEqual(result.items[0].intent, "reschedule")
        self.assertEqual(result.items[0].entity_type, "event")
        blob = json.dumps(asdict(result), ensure_ascii=False).lower()
        self.assertIn("коллег", blob)
        self.assertIn("12", blob)

    def test_parse_multiple_intents_nails_appointment_and_bread_task(self):
        user_text = (
            "Завтра у меня в час запись на ноготочки, еще нужно добавить задачу купить хлеб завтра."
        )
        parser = IntentParserService()
        result = parser.parse(user_text)

        _print_live_parse(user_text, result)

        self.assertGreaterEqual(
            len(result.items),
            2,
            "Ожидалось минимум два намерения (запись и задача).",
        )
        blob = json.dumps(asdict(result), ensure_ascii=False).lower()
        self.assertIn("хлеб", blob)
        self.assertTrue(
            any(x in blob for x in ("ногот", "маник", "запис")),
            "В разборе должны отразиться запись или ноготочки.",
        )
