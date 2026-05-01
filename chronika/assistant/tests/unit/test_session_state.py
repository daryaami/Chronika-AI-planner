from django.test import TestCase

from assistant.services.intent_parser import ParsedIntent, ParsedIntentResult
from assistant.services.session_state import (
    AssistantExecutionState,
    SessionStateStore,
    advance_to_next_pending_item,
    build_prompt_context_summary,
    clear_disambiguation,
    clear_pending_confirmation,
    default_execution_state,
    mark_item_status,
    merge_parser_result_into_state,
    record_last_completed,
    reset_scenario,
    resolve_active_entity,
    set_disambiguation_candidates,
    set_pending_confirmation,
    set_step,
    suggested_parse_mode,
)


class SessionStatePureFunctionsTests(TestCase):
    def test_default_state_roundtrip_dict(self):
        s = default_execution_state()
        d = s.to_dict()
        s2 = AssistantExecutionState.from_dict(d)
        self.assertEqual(s2.step, "idle")
        self.assertEqual(s2.version, s.version)
        self.assertEqual(s2.turn_id, s.turn_id)
        self.assertEqual(len(s2.intent_plan.items), 0)

    def test_from_dict_empty_and_invalid(self):
        self.assertEqual(AssistantExecutionState.from_dict(None).step, "idle")
        self.assertEqual(AssistantExecutionState.from_dict({}).step, "idle")

    def test_merge_parser_result(self):
        s = default_execution_state()
        result = ParsedIntentResult(
            items=[
                ParsedIntent(
                    intent="reschedule",
                    entity_type="event",
                    query="встреча с клиентом",
                    fields={},
                    datetime={"date": "2026-04-04"},
                    meta={},
                    filters={},
                )
            ]
        )
        merge_parser_result_into_state(s, result, clear_transient=True)
        self.assertEqual(len(s.intent_plan.items), 1)
        self.assertEqual(s.intent_plan.items[0].intent, "reschedule")
        self.assertEqual(s.intent_plan.items[0].query, "встреча с клиентом")
        self.assertEqual(s.intent_plan.active_item_index, 0)

    def test_reset_scenario(self):
        s = default_execution_state()
        merge_parser_result_into_state(
            s,
            ParsedIntentResult(
                items=[
                    ParsedIntent(
                        intent="get",
                        entity_type="task",
                        query=None,
                        fields={},
                        datetime={},
                        meta={},
                        filters={"date": "2026-04-04"},
                    )
                ]
            ),
        )
        set_step(s, "disambiguating")
        set_disambiguation_candidates(s, [{"id": "1", "title": "A"}])
        reset_scenario(s)
        self.assertEqual(s.step, "idle")
        self.assertEqual(s.intent_plan.items, [])
        self.assertEqual(s.disambiguation.candidates, [])

    def test_disambiguation_and_resolve(self):
        s = default_execution_state()
        merge_parser_result_into_state(
            s,
            ParsedIntentResult(
                items=[
                    ParsedIntent(
                        intent="delete",
                        entity_type="event",
                        query="стендап",
                        fields={},
                        datetime={},
                        meta={},
                        filters={},
                    )
                ]
            ),
        )
        set_disambiguation_candidates(s, [{"id": "e1", "title": "стендап", "datetime": "2026-04-01T10:00:00"}])
        resolve_active_entity(s, "e1", resolution_meta={"picked_index": 1})
        self.assertEqual(active_entity_id(s), "e1")
        clear_disambiguation(s)
        self.assertEqual(s.disambiguation.candidates, [])

    def test_mark_items_and_advance(self):
        s = default_execution_state()
        merge_parser_result_into_state(
            s,
            ParsedIntentResult(
                items=[
                    ParsedIntent(
                        intent="create",
                        entity_type="task",
                        query=None,
                        fields={"title": "a"},
                        datetime={},
                        meta={},
                        filters={},
                    ),
                    ParsedIntent(
                        intent="delete",
                        entity_type="event",
                        query="b",
                        fields={},
                        datetime={},
                        meta={},
                        filters={},
                    ),
                ]
            ),
        )
        mark_item_status(s, 0, "done")
        advance_to_next_pending_item(s)
        self.assertEqual(s.intent_plan.active_item_index, 1)

    def test_pending_confirmation(self):
        s = default_execution_state()
        set_pending_confirmation(s, "bulk_delete", {"count": 3}, idempotency_key="k1")
        self.assertEqual(s.step, "confirming")
        self.assertEqual(s.pending_confirmation.action, "bulk_delete")
        clear_pending_confirmation(s)
        self.assertIsNone(s.pending_confirmation)

    def test_record_last_completed(self):
        s = default_execution_state()
        record_last_completed(s, "create_task", entity_id="t1")
        self.assertEqual(s.last_completed_action.action, "create_task")
        self.assertEqual(s.last_completed_action.entity_id, "t1")

    def test_build_prompt_context_contains_step_and_candidates(self):
        s = default_execution_state()
        set_step(s, "disambiguating")
        merge_parser_result_into_state(
            s,
            ParsedIntentResult(
                items=[
                    ParsedIntent(
                        intent="reschedule",
                        entity_type="event",
                        query="x",
                        fields={},
                        datetime={},
                        meta={},
                        filters={},
                    )
                ],
            ),
            clear_transient=False,
        )
        set_disambiguation_candidates(
            s,
            [{"title": "С клиентом", "datetime": "2026-03-27T14:00:00"}],
        )
        text = build_prompt_context_summary(s)
        self.assertIn("disambiguating", text)
        self.assertIn("С клиентом", text)

    def test_suggested_parse_mode(self):
        idle = default_execution_state()
        self.assertEqual(suggested_parse_mode(idle), "full")
        set_step(idle, "collecting")
        self.assertEqual(suggested_parse_mode(idle), "continuation")


def active_entity_id(state):
    from assistant.services.session_state import active_item

    it = active_item(state)
    return it.entity_id if it else None


class SessionStateStoreTests(TestCase):
    def test_load_save_roundtrip(self):
        from assistant.models import AssistantSession
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create(email="a@b.c", name="A")

        session = AssistantSession.objects.create(user=user)
        state = default_execution_state()
        set_step(state, "collecting")
        SessionStateStore.save(session, state)

        session.refresh_from_db()
        loaded = SessionStateStore.load(session)
        self.assertEqual(loaded.step, "collecting")
        self.assertEqual(loaded.turn_id, state.turn_id)
