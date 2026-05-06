"""
Live Mistral integration tests for current orchestration path.
Not run by default (cost + flakiness).

  set RUN_LLM_INTEGRATION=1
  set MISTRAL_API_KEY=...   (or load via .env as usual)
  py -m pytest chronika/assistant/tests/integration/test_llm_integration.py
"""

import json
import os
import unittest

from django.conf import settings
from django.test import TestCase

from assistant.integrations.llm_client import MistralLLMClient
from assistant.prompts.tool_schemas import get_orchestrator_tool_schemas


@unittest.skipUnless(
    os.environ.get("RUN_LLM_INTEGRATION") == "1" and bool(getattr(settings, "MISTRAL_API_KEY", None)),
    "Set RUN_LLM_INTEGRATION=1 and MISTRAL_API_KEY to run live LLM tests",
)
class MistralLiveIntegrationTests(TestCase):
    def setUp(self):
        self.client = MistralLLMClient()

    def test_chat_text_returns_non_empty_reply(self):
        reply = self.client.chat_text(
            system_prompt="Отвечай кратко на русском языке.",
            user_prompt="Скажи одним словом привет.",
            fallback="fallback",
            temperature=0.0,
        )
        print("\n--- chat_text reply ---\n", reply, sep="")
        self.assertIsInstance(reply, str)
        self.assertTrue(reply.strip())

    def test_chat_with_tools_returns_valid_shape(self):
        result = self.client.chat_with_tools(
            messages=[
                {"role": "system", "content": "Ты ассистент-планировщик. Используй tools при необходимости."},
                {"role": "user", "content": "Покажи мои задачи на сегодня"},
            ],
            tools=get_orchestrator_tool_schemas(),
            fallback={"content": "", "tool_calls": []},
            temperature=0.0,
        )
        print("\n--- chat_with_tools result ---\n", json.dumps(result, ensure_ascii=False, indent=2), sep="")
        self.assertIn("content", result)
        self.assertIn("tool_calls", result)
        self.assertIsInstance(result["tool_calls"], list)
        for call in result["tool_calls"]:
            self.assertIn("function", call)
            self.assertIsInstance(call["function"].get("name"), str)
            self.assertIsInstance(call["function"].get("arguments"), str)
