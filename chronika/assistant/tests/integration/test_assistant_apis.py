from unittest.mock import patch
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from assistant.models import AssistantMessage
from assistant.models import AssistantSession
from events.models import Event
from events.models import UserCalendar
from users.models import CustomUser


class AssistantApiTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="assistant-api@example.com",
            name="Assistant API User",
            password="password123",
            google_id="assistant-api-google-id",
        )
        self.client.force_authenticate(self.user)
        UserCalendar.objects.get_or_create(
            user=self.user,
            google_calendar_id=f"assistant-api-{self.user.id}",
            defaults={
                "summary": "Assistant Calendar",
                "selected": True,
                "primary": True,
            },
        )

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_api_returns_protocol_payload(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {"content": "", "tool_calls": []}
        llm.chat_text.return_value = "Готово."

        response = self.client.post(
            reverse("assistant_message"),
            {"message": "Создай задачу купить хлеб"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message_id", response.data)
        self.assertIn("state", response.data)
        self.assertIn("blocks", response.data)
        self.assertNotIn("presentables", response.data)
        self.assertEqual(response.data["state"], "success")
        self.assertTrue(any(block.get("type") == "text" for block in response.data["blocks"]))

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_action_api_processes_pending_without_llm_roundtrip(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "find_slots",
                        "arguments": (
                            "{\"window_start\": \"2026-05-07T10:00:00+03:00\", "
                            "\"window_end\": \"2026-05-07T14:00:00+03:00\", "
                            "\"duration_minutes\": 60}"
                        ),
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Нужно подтверждение действия."

        first = self.client.post(reverse("assistant_message"), {"message": "Подбери слот на завтра"}, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        with patch("assistant.services.dialog_session_store.MistralLLMClient") as action_llm_cls:
            action_llm = action_llm_cls.return_value
            action_llm.chat_with_tools.side_effect = AssertionError("UI action should not call chat_with_tools")
            action_llm.chat_text.side_effect = AssertionError("UI action should not call chat_text")

            response = self.client.post(
                reverse("assistant_action"),
                {
                    "message_id": first.data["message_id"],
                    "action": {"type": "cancel", "payload": {}},
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        self.assertNotIn("presentables", response.data)
        self.assertTrue(any(block.get("type") == "text" for block in response.data["blocks"]))

    def test_history_api_returns_session_messages(self):
        AssistantSession.objects.get_or_create(user=self.user)
        response = self.client.get(reverse("assistant_history"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("messages", response.data)

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_history_api_hides_internal_results_from_metadata(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "search_entities",
                        "arguments": '{"query":"мои задачи","entity_type":"task"}',
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Список задач."

        self.client.post(reverse("assistant_message"), {"message": "Покажи мои задачи"}, format="json")
        history = self.client.get(reverse("assistant_history"))

        self.assertEqual(history.status_code, status.HTTP_200_OK)
        assistant_messages = [m for m in history.data["messages"] if m.get("role") == "assistant"]
        self.assertGreaterEqual(len(assistant_messages), 1)
        metadata = assistant_messages[-1].get("metadata") or {}
        self.assertNotIn("results", metadata)

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_persists_meta_trace_in_assistant_message(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {"content": "", "tool_calls": []}
        llm.chat_text.return_value = "Готово."

        response = self.client.post(
            reverse("assistant_message"),
            {"message": "Проверь состояние"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assistant_message = AssistantMessage.objects.filter(session__user=self.user, role="assistant").latest("created_at")
        metadata = assistant_message.metadata_json or {}
        meta = metadata.get("meta") or {}
        self.assertIn("fsm_state", meta)
        self.assertIn("fsm_trace", meta)
        self.assertIn("prompt_versions", meta)
        self.assertIsInstance(meta["fsm_trace"], list)
        self.assertGreaterEqual(len(meta["fsm_trace"]), 1)
        self.assertIsInstance(meta["prompt_versions"], dict)
        self.assertGreaterEqual(len(meta["prompt_versions"]), 1)

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_updates_last_entity_in_session_context(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "create_task",
                        "arguments": '{"title":"Купить молоко","duration":"PT30M"}',
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Создала задачу."
        tool_execute.return_value = {
            "ok": True,
            "data": {
                "task": {
                    "id": 777,
                    "title": "Купить молоко",
                    "duration": "PT30M",
                    "due_date": None,
                }
            },
        }

        response = self.client.post(
            reverse("assistant_message"),
            {"message": "Создай задачу купить молоко"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session = AssistantSession.objects.get(user=self.user)
        context = session.dialog_context or {}
        self.assertIn("last_entity", context)
        self.assertEqual(context["last_entity"]["kind"], "task")
        self.assertEqual(context["last_entity"]["id"], 777)
        self.assertEqual(session.last_referenced_id, 777)

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_updates_turn_context_across_messages(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {"content": "", "tool_calls": []}
        llm.chat_text.return_value = "Ок."

        first_text = "Первая реплика"
        second_text = "Вторая реплика"
        first = self.client.post(reverse("assistant_message"), {"message": first_text}, format="json")
        second = self.client.post(reverse("assistant_message"), {"message": second_text}, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        session = AssistantSession.objects.get(user=self.user)
        context = session.dialog_context or {}
        self.assertEqual(context.get("last_user_text"), second_text)
        self.assertEqual(context.get("previous_user_text"), first_text)
        self.assertEqual(
            context.get("conversation_history"),
            [
                {"role": "user", "content": first_text},
                {"role": "assistant", "content": "Ок."},
                {"role": "user", "content": second_text},
                {"role": "assistant", "content": "Ок."},
            ],
        )

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_persists_resolved_entities_context_from_search_results(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "search_entities",
                        "arguments": '{"query":"обед","entity_type":"event"}',
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Нашла обед."
        tool_execute.return_value = {
            "ok": True,
            "data": {
                "items": [
                    {
                        "id": 1101,
                        "entity_type": "event",
                        "data": {
                            "id": 1101,
                            "summary": "🍱 Обед",
                            "title": "🍱 Обед",
                            "start": "2026-05-07T13:00:00+03:00",
                            "end": "2026-05-07T14:00:00+03:00",
                        },
                    }
                ],
                "total": 1,
            },
        }

        response = self.client.post(reverse("assistant_message"), {"message": "Найди обед"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        session = AssistantSession.objects.get(user=self.user)
        context = session.dialog_context or {}
        resolved = context.get("resolved_entities_context") or {}
        events_ctx = resolved.get("event") or []
        self.assertGreaterEqual(len(events_ctx), 1)
        self.assertEqual(events_ctx[0]["id"], 1101)

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_passes_full_conversation_history_to_llm(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {"content": "", "tool_calls": []}
        llm.chat_text.return_value = "Поняла."

        self.client.post(reverse("assistant_message"), {"message": "Первая реплика"}, format="json")
        self.client.post(reverse("assistant_message"), {"message": "Вторая реплика"}, format="json")

        chat_with_tools_calls = llm.chat_with_tools.call_args_list
        self.assertGreaterEqual(len(chat_with_tools_calls), 2)
        second_tools_messages = chat_with_tools_calls[1].kwargs["messages"]
        self.assertIn("conversation_history", second_tools_messages[1]["content"])
        self.assertIn('"content": "Первая реплика"', second_tools_messages[1]["content"])
        self.assertIn('"content": "Поняла."', second_tools_messages[1]["content"])

        chat_text_calls = llm.chat_text.call_args_list
        self.assertGreaterEqual(len(chat_text_calls), 2)
        second_user_prompt = chat_text_calls[1].kwargs["user_prompt"]
        self.assertIn("conversation_history", second_user_prompt)
        self.assertIn('"content": "Первая реплика"', second_user_prompt)
        self.assertIn('"content": "Поняла."', second_user_prompt)

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_passes_resolved_entities_context_to_llm(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {"content": "", "tool_calls": []}
        llm.chat_text.return_value = "Ок."

        session, _ = AssistantSession.objects.get_or_create(user=self.user)
        session.dialog_context = {
            "resolved_entities_context": {
                "event": [
                    {
                        "id": 1101,
                        "entity_type": "event",
                        "data": {
                            "id": 1101,
                            "summary": "🍱 Обед",
                            "title": "🍱 Обед",
                            "start": "2026-05-07T13:00:00+03:00",
                            "end": "2026-05-07T14:00:00+03:00",
                        },
                    }
                ],
                "task": [],
            }
        }
        session.save(update_fields=["dialog_context", "updated_at"])

        response = self.client.post(reverse("assistant_message"), {"message": "Перенеси его на 14"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        messages = llm.chat_with_tools.call_args.kwargs["messages"]
        llm_input_payload = messages[1]["content"]
        self.assertIn("resolved_entities_context", llm_input_payload)
        self.assertIn('"id": 1101', llm_input_payload)

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_action_plan_find_slot_then_create_short_followup(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {"content": "", "tool_calls": []}
        llm.chat_text.return_value = "Выберите слот."
        tool_execute.return_value = {
            "ok": True,
            "data": {
                "slots": [
                    {
                        "start": "2026-05-08T10:00:00+03:00",
                        "end": "2026-05-08T11:00:00+03:00",
                        "score": 0.91,
                    }
                ]
            },
        }

        session, _ = AssistantSession.objects.get_or_create(user=self.user)
        session.dialog_context = {
            "action_plan": {
                "status": "active",
                "window_start": "2026-05-08T09:00:00+03:00",
                "window_end": "2026-05-08T18:00:00+03:00",
                "steps": [
                    {
                        "id": "s1",
                        "type": "find_slot_then_create",
                        "title": "Встреча с дизайнером",
                        "duration_minutes": 60,
                        "status": "pending",
                    }
                ],
            }
        }
        session.save(update_fields=["dialog_context", "updated_at"])

        response = self.client.post(reverse("assistant_message"), {"message": "Давай"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "waiting_confirmation")
        self.assertFalse(any(block.get("type") == "time_slot_selection" for block in response.data["blocks"]))
        tool_execute.assert_any_call(
            "find_slots",
            {
                "window_start": "2026-05-08T06:00:00+00:00",
                "window_end": "2026-05-08T15:00:00+00:00",
                "duration_minutes": 60,
                "planning_context": {"action": "create_event", "title": "Встреча с дизайнером"},
            },
        )

    def test_pending_restore_respects_expires_at(self):
        session, _ = AssistantSession.objects.get_or_create(user=self.user)
        session.dialog_state = "awaiting_confirmation"
        session.save(update_fields=["dialog_state", "updated_at"])

        AssistantMessage.objects.create(
            session=session,
            role="assistant",
            content="pending expired",
            metadata_json={
                "pending_action": {
                    "id": "p_expired",
                    "status": "awaiting_confirmation",
                    "type": "delete_task",
                    "payload": {"tool_name": "delete_task", "tool_payload": {"task_id": 1}},
                    "expires_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
                    "slot_candidates": [],
                    "disambiguation_candidates": [],
                    "meta": {},
                }
            },
            blocks=[{"type": "text", "text": "pending expired"}],
            fsm_state="awaiting_confirmation",
        )

        expired_response = self.client.post(
            reverse("assistant_action"),
            {"action": {"type": "cancel", "payload": {}}},
            format="json",
        )
        self.assertEqual(expired_response.status_code, status.HTTP_200_OK)
        self.assertEqual(expired_response.data["state"], "failed")
        session.refresh_from_db()
        session.dialog_state = "awaiting_confirmation"
        session.save(update_fields=["dialog_state", "updated_at"])

        AssistantMessage.objects.create(
            session=session,
            role="assistant",
            content="pending active",
            metadata_json={
                "pending_action": {
                    "id": "p_active",
                    "status": "awaiting_confirmation",
                    "type": "delete_task",
                    "payload": {"tool_name": "delete_task", "tool_payload": {"task_id": 1}},
                    "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat(),
                    "slot_candidates": [],
                    "disambiguation_candidates": [],
                    "meta": {},
                }
            },
            blocks=[{"type": "text", "text": "pending active"}],
            fsm_state="awaiting_confirmation",
        )

        active_response = self.client.post(
            reverse("assistant_action"),
            {"action": {"type": "cancel", "payload": {}}},
            format="json",
        )
        self.assertEqual(active_response.status_code, status.HTTP_200_OK)
        self.assertEqual(active_response.data["state"], "success")

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_does_not_followup_repeat_search_entities(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "search_entities",
                        "arguments": '{"query":"мои задачи","entity_type":"task"}',
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Список задач пуст."
        tool_execute.return_value = {"ok": True, "data": {"items": [], "total": 0}}

        response = self.client.post(reverse("assistant_message"), {"message": "Покажи мои задачи"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        self.assertEqual(tool_execute.call_count, 1)
        assistant_message = AssistantMessage.objects.filter(session__user=self.user, role="assistant").latest("created_at")
        saved_results = (assistant_message.metadata_json or {}).get("results") or []
        self.assertEqual(len(saved_results), 1)
        first = saved_results[0]
        self.assertEqual(first.get("tool_name"), "search_entities")

    @patch("tasks.services.enqueue_task_embedding")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_create_task_enqueues_embedding_job(self, llm_cls, enqueue_embedding):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "create_task",
                        "arguments": '{"title":"Полить цветы","duration":30}',
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Задача создана."

        response = self.client.post(reverse("assistant_message"), {"message": "Добавь задачу полить цветы"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        self.assertEqual(enqueue_embedding.call_count, 1)

    @patch("assistant.services.tool_router.transaction.on_commit")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_create_event_enqueues_embedding_job(self, llm_cls, on_commit_mock):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "create_event",
                        "arguments": (
                            '{"title":"Встреча по книге",'
                            '"start":"2026-05-09T10:00:00+03:00",'
                            '"duration_minutes":60}'
                        ),
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Событие создано."

        response = self.client.post(reverse("assistant_message"), {"message": "Создай событие на завтра в 10"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        self.assertEqual(on_commit_mock.call_count, 1)

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_create_event_persists_event_in_db(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "create_event",
                        "arguments": (
                            '{"title":"Встреча по книге",'
                            '"start":"2026-05-09T10:00:00+03:00",'
                            '"duration_minutes":60,'
                            '"description":"Обсудить главы 1-3"}'
                        ),
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Событие создано."

        response = self.client.post(
            reverse("assistant_message"),
            {"message": "Создай событие на завтра в 10"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")

        created = Event.objects.filter(
            user_calendar__user=self.user,
            summary="Встреча по книге",
        ).latest("id")
        self.assertEqual(created.description, "Обсудить главы 1-3")
        self.assertIsNotNone(created.start)
        self.assertIsNotNone(created.end)

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    def test_action_entity_update_executes_update_by_context_id(self, tool_execute):
        tool_execute.return_value = {"ok": True, "data": {"task": {"id": 42, "title": "Обновлено"}}}

        response = self.client.post(
            reverse("assistant_action"),
            {
                "action": {
                    "type": "entity_update",
                    "payload": {
                        "context_id": "e:task:42",
                        "fields": {"title": "Обновлено"},
                    },
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        tool_execute.assert_called_with("update_task", {"task_id": 42, "updates": {"title": "Обновлено"}})

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    def test_action_select_entity_resolves_pending_disambiguation(self, tool_execute):
        tool_execute.return_value = {"ok": True, "data": {"task": {"id": 42, "title": "Полить цветы"}}}
        session, _ = AssistantSession.objects.get_or_create(user=self.user)
        session.dialog_state = "needs_disambiguation"
        session.save(update_fields=["dialog_state", "updated_at"])
        AssistantMessage.objects.create(
            session=session,
            role="assistant",
            content="Выбери задачу",
            metadata_json={
                "pending_action": {
                    "id": "p_disamb_1",
                    "status": "needs_disambiguation",
                    "type": "update_task",
                    "payload": {"tool_name": "update_task", "tool_payload": {"updates": {"title": "Полить цветы"}}},
                    "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat(),
                    "slot_candidates": [],
                    "disambiguation_candidates": [
                        {"id": 42, "entity_type": "task", "data": {"title": "Полить цветы"}},
                        {"id": 43, "entity_type": "task", "data": {"title": "Полить цветы дома"}},
                    ],
                    "meta": {},
                }
            },
            blocks=[{"type": "entity_selection", "entities": []}],
            fsm_state="needs_disambiguation",
        )

        response = self.client.post(
            reverse("assistant_action"),
            {
                "action": {
                    "type": "select_entity",
                    "payload": {"context_ids": ["e:task:42"]},
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        tool_execute.assert_called_with("update_task", {"updates": {"title": "Полить цветы"}, "task_id": 42})

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_api_maps_waiting_confirmation_state(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "delete_task",
                        "arguments": '{"task_id": 1}',
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Подтвердите удаление."

        response = self.client.post(reverse("assistant_message"), {"message": "Удали задачу 1"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "waiting_confirmation")

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_api_does_not_render_raw_search_candidates(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "search_entities",
                        "arguments": '{"query":"цветы","entity_type":"task"}',
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Нашла задачу."
        tool_execute.return_value = {
            "ok": True,
            "data": {
                "items": [
                    {
                        "id": 42,
                        "entity_type": "task",
                        "data": {"id": 42, "title": "Полить цветы", "due_date": None, "duration": 30},
                    }
                ],
                "total": 1,
            },
        }

        response = self.client.post(reverse("assistant_message"), {"message": "Найди задачу про цветы"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entity_blocks = [b for b in response.data["blocks"] if b.get("type") == "entity"]
        self.assertEqual(entity_blocks, [])

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_message_hides_search_candidates_when_mutation_executed(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "search_entities",
                        "arguments": '{"query":"ужин","entity_type":"event"}',
                    },
                },
                {
                    "id": "2",
                    "function": {
                        "name": "update_event",
                        "arguments": (
                            '{"event_id":101,'
                            '"updates":{"summary":"Обед","start":"2026-05-09T14:00:00+03:00","end":"2026-05-09T15:00:00+03:00"}}'
                        ),
                    },
                },
            ],
        }
        llm.chat_text.return_value = "Событие перенесено."

        def _execute(tool_name, payload):
            if tool_name == "search_entities":
                return {
                    "ok": True,
                    "data": {
                        "items": [
                            {
                                "id": 201,
                                "entity_type": "event",
                                "data": {"id": 201, "summary": "Ужин", "start": "2026-05-09T19:00:00+03:00", "end": "2026-05-09T20:00:00+03:00"},
                            },
                            {
                                "id": 202,
                                "entity_type": "event",
                                "data": {"id": 202, "summary": "Ужин", "start": "2026-05-10T19:00:00+03:00", "end": "2026-05-10T20:00:00+03:00"},
                            },
                        ],
                        "total": 2,
                    },
                }
            if tool_name == "update_event":
                return {
                    "ok": True,
                    "data": {
                        "event": {
                            "id": 101,
                            "summary": "Обед",
                            "title": "Обед",
                            "start": "2026-05-09T14:00:00+03:00",
                            "end": "2026-05-09T15:00:00+03:00",
                        }
                    },
                }
            return {"ok": False, "error": {"code": "unexpected_tool", "message": tool_name, "recoverable": False}}

        tool_execute.side_effect = _execute

        response = self.client.post(reverse("assistant_message"), {"message": "Перенеси обед на 14"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entity_blocks = [b for b in response.data["blocks"] if b.get("type") == "entity"]
        self.assertEqual(len(entity_blocks), 1)
        self.assertEqual(entity_blocks[0]["entity_type"], "event")
        self.assertEqual(entity_blocks[0]["context_id"], "e:event:101")

    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_action_api_accepts_confirm_alias(self, llm_cls):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "find_slots",
                        "arguments": (
                            "{\"window_start\": \"2026-05-07T10:00:00+03:00\", "
                            "\"window_end\": \"2026-05-07T14:00:00+03:00\", "
                            "\"duration_minutes\": 60}"
                        ),
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Выберите слот."

        first = self.client.post(reverse("assistant_message"), {"message": "Подбери слот на завтра"}, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        response = self.client.post(
            reverse("assistant_action"),
            {
                "message_id": first.data["message_id"],
                "action": {"type": "confirm", "payload": {}},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("blocks", response.data)

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_confirm_action_returns_entity_and_deleted_entity_id_blocks(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "delete_task",
                        "arguments": '{"task_id": 42}',
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Подтвердите удаление."

        def _execute(tool_name, payload):
            if tool_name == "delete_task":
                return {"ok": True, "data": {"deleted_id": 42}}
            return {"ok": True, "data": {"task": {"id": 7, "title": "stub"}}}

        tool_execute.side_effect = _execute

        first = self.client.post(reverse("assistant_message"), {"message": "Удали задачу 42"}, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["state"], "waiting_confirmation")

        response = self.client.post(
            reverse("assistant_action"),
            {
                "message_id": first.data["message_id"],
                "action": {"type": "confirm", "payload": {}},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        deleted_blocks = [b for b in response.data["blocks"] if b.get("type") == "deleted_entity"]
        self.assertEqual(len(deleted_blocks), 1)
        self.assertEqual(deleted_blocks[0]["entity_type"], "task")
        self.assertEqual(deleted_blocks[0]["id"], 42)

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_confirm_action_hides_search_candidates_and_shows_updated_event_only(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.side_effect = [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "function": {
                            "name": "search_entities",
                            "arguments": '{"query":"обед","entity_type":"event"}',
                        },
                    },
                    {
                        "id": "2",
                        "function": {
                            "name": "delete_event",
                            "arguments": '{"event_id": 501}',
                        },
                    },
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "3",
                        "function": {
                            "name": "confirm_action",
                            "arguments": "{}",
                        },
                    }
                ],
            },
        ]
        llm.chat_text.return_value = "Обед перенесен."

        def _execute(tool_name, payload):
            if tool_name == "search_entities":
                return {
                    "ok": True,
                    "data": {
                        "items": [
                            {
                                "id": 700,
                                "entity_type": "event",
                                "data": {"id": 700, "summary": "Ужин", "start": "2026-05-08T19:00:00+03:00", "end": "2026-05-08T20:00:00+03:00"},
                            },
                            {
                                "id": 701,
                                "entity_type": "event",
                                "data": {"id": 701, "summary": "Обед", "start": "2026-05-08T13:00:00+03:00", "end": "2026-05-08T14:00:00+03:00"},
                            },
                        ],
                        "total": 2,
                    },
                }
            if tool_name == "delete_event":
                return {
                    "ok": True,
                    "data": {
                        "deleted_id": payload.get("event_id"),
                        "entity_type": "event",
                    },
                }
            return {"ok": False, "error": {"code": "unexpected_tool", "message": tool_name, "recoverable": False}}

        tool_execute.side_effect = _execute

        first = self.client.post(reverse("assistant_message"), {"message": "Удали обед"}, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["state"], "waiting_confirmation")

        second = self.client.post(reverse("assistant_message"), {"message": "Да"}, format="json")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        entity_blocks = [b for b in second.data["blocks"] if b.get("type") == "entity"]
        self.assertEqual(entity_blocks, [])
        deleted_blocks = [b for b in second.data["blocks"] if b.get("type") == "deleted_entity"]
        self.assertEqual(len(deleted_blocks), 1)
        self.assertEqual(deleted_blocks[0]["entity_type"], "event")
        self.assertEqual(deleted_blocks[0]["id"], 501)

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_confirm_single_slot_creates_event_in_selected_window(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "find_slots",
                        "arguments": (
                            '{"window_start":"2026-05-09T12:00:00+03:00",'
                            '"window_end":"2026-05-09T19:00:00+03:00",'
                            '"duration_minutes":180,'
                            '"planning_context":{"action":"create_event","title":"Тренировка"}}'
                        ),
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Подходит слот с 14:00 до 17:00?"

        def _execute(tool_name, payload):
            if tool_name == "find_slots":
                return {
                    "ok": True,
                    "data": {
                        "slots": [
                            {
                                "start": "2026-05-09T14:00:00+03:00",
                                "end": "2026-05-09T17:00:00+03:00",
                                "score": 0.92,
                            }
                        ]
                    },
                }
            if tool_name == "create_event":
                return {
                    "ok": True,
                    "data": {
                        "event": {
                            "id": 501,
                            "title": payload.get("title"),
                            "summary": payload.get("title"),
                            "start": payload.get("start"),
                            "end": payload.get("end"),
                        }
                    },
                }
            return {"ok": False, "error": {"code": "unexpected_tool", "message": tool_name, "recoverable": False}}

        tool_execute.side_effect = _execute

        first = self.client.post(
            reverse("assistant_message"),
            {"message": "Поставь тренировку после обеда и до танцев, длиной 3 часа"},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["state"], "waiting_confirmation")

        response = self.client.post(
            reverse("assistant_action"),
            {"message_id": first.data["message_id"], "action": {"type": "confirm", "payload": {}}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "success")
        tool_execute.assert_any_call(
            "create_event",
            {
                "title": "Тренировка",
                "start": "2026-05-09T14:00:00+03:00",
                "end": "2026-05-09T17:00:00+03:00",
            },
        )

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_find_slots_retries_with_expanded_window_when_initial_empty(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "find_slots",
                        "arguments": (
                            '{"window_start":"2026-05-10T14:00:00+03:00",'
                            '"window_end":"2026-05-10T17:00:00+03:00",'
                            '"duration_minutes":60,'
                            '"planning_context":{"action":"create_event","title":"Тренировка"}}'
                        ),
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Подобрала окно."

        def _execute(tool_name, payload):
            if tool_name != "find_slots":
                return {"ok": False, "error": {"code": "unexpected_tool", "message": tool_name, "recoverable": False}}
            if payload.get("window_start") == "2026-05-10T11:00:00+00:00":
                return {"ok": True, "data": {"slots": []}}
            return {
                "ok": True,
                "data": {
                    "slots": [
                        {
                            "start": "2026-05-10T13:00:00+03:00",
                            "end": "2026-05-10T14:00:00+03:00",
                            "score": 0.8,
                        }
                    ]
                },
            }

        tool_execute.side_effect = _execute

        response = self.client.post(
            reverse("assistant_message"),
            {"message": "Поставь тренировку после обеда до танцев"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "waiting_confirmation")
        find_slots_calls = [call for call in tool_execute.call_args_list if call.args and call.args[0] == "find_slots"]
        self.assertEqual(len(find_slots_calls), 2)

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_chat_text_receives_humanized_local_time_without_offset(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "find_slots",
                        "arguments": (
                            '{"window_start":"2026-05-09T14:00:00+03:00",'
                            '"window_end":"2026-05-09T17:00:00+03:00",'
                            '"duration_minutes":60,'
                            '"planning_context":{"action":"create_event","title":"Тренировка"}}'
                        ),
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Подобрала варианты."
        tool_execute.return_value = {
            "ok": True,
            "data": {
                "slots": [
                    {
                        "start": "2026-05-09T11:00:00+00:00",
                        "end": "2026-05-09T12:00:00+00:00",
                        "score": 1.0,
                    }
                ]
            },
        }

        response = self.client.post(
            reverse("assistant_message"),
            {"message": "Поставь тренировку в субботу после обеда и до танцев"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "waiting_confirmation")
        chat_kwargs = llm.chat_text.call_args.kwargs
        self.assertIn('"results_local_time"', chat_kwargs["user_prompt"])
        self.assertIn('"start": "2026-05-09 11:00"', chat_kwargs["user_prompt"])
        self.assertIn('"end": "2026-05-09 12:00"', chat_kwargs["user_prompt"])

    @patch("assistant.services.orchestrator.ToolRouter.execute")
    @patch("assistant.services.dialog_session_store.MistralLLMClient")
    def test_single_slot_goes_directly_to_waiting_confirmation(self, llm_cls, tool_execute):
        llm = llm_cls.return_value
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "find_slots",
                        "arguments": (
                            '{"window_start":"2026-05-09T14:00:00+03:00",'
                            '"window_end":"2026-05-09T17:00:00+03:00",'
                            '"duration_minutes":180,'
                            '"planning_context":{"action":"create_event","title":"Тренировка"}}'
                        ),
                    },
                }
            ],
        }
        llm.chat_text.return_value = "Найден один слот. Создать событие?"
        tool_execute.return_value = {
            "ok": True,
            "data": {
                "slots": [
                    {
                        "start": "2026-05-09T11:00:00+00:00",
                        "end": "2026-05-09T14:00:00+00:00",
                        "score": 1.0,
                    }
                ]
            },
        }

        response = self.client.post(
            reverse("assistant_message"),
            {"message": "Поставь в субботу тренировку после обеда и до танцев трехчасовую"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], "waiting_confirmation")
        self.assertFalse(any(block.get("type") == "time_slot_selection" for block in response.data["blocks"]))

