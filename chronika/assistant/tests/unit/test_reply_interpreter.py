from django.test import TestCase

from assistant.domain.action_plan import Action, ActionPlan
from assistant.domain.dialog import DialogIntent, ReplyInterpretation
from assistant.fsm.states import DialogState
from assistant.integrations.llm_client import LLMClientError
from assistant.services.plan_merge import PlanMergeService
from assistant.services.reply_interpreter import ReplyInterpreterInput, ReplyInterpreterService


class FakeLLM:
    def __init__(self, response: str):
        self.response = response

    def chat_with_messages(self, **kwargs):
        return self.response


class ReplyInterpreterHeuristicTests(TestCase):
    def test_disambiguation_select_by_number(self):
        svc = ReplyInterpreterService(llm_client=FakeLLM("{}"))
        payload = ReplyInterpreterInput(
            state=DialogState.DISAMBIGUATION.value,
            current_plan={"actions": [], "entities": []},
            entities_in_context=[],
            disambiguation_options=[
                {"index": 0, "object_id": 10, "entity_type": "task"},
                {"index": 1, "object_id": 20, "entity_type": "task"},
            ],
            last_referenced_id=None,
            user_message="2",
        )
        r = svc.interpret(payload)
        self.assertEqual(r.dialog_intent, DialogIntent.SELECT)
        self.assertEqual(r.target_ids, [20])

    def test_waiting_confirmation_confirm(self):
        svc = ReplyInterpreterService(llm_client=FakeLLM("{}"))
        payload = ReplyInterpreterInput(
            state=DialogState.WAITING_CONFIRMATION.value,
            current_plan={"actions": [], "entities": []},
            entities_in_context=[],
            disambiguation_options=[],
            last_referenced_id=None,
            user_message="да",
        )
        r = svc.interpret(payload)
        self.assertEqual(r.dialog_intent, DialogIntent.CONFIRM)

    def test_single_word_ok_horosho_confirm(self):
        svc = ReplyInterpreterService(llm_client=FakeLLM("{}"))
        bases = ("да", "ок", "хорошо", "Да", "ОК")
        punct_suffixes = ("", ".", "!", "?", "…", ".!!")
        for base in bases:
            for suf in punct_suffixes:
                word = base + suf
                with self.subTest(word=word):
                    payload = ReplyInterpreterInput(
                        state=DialogState.WAITING_CONFIRMATION.value,
                        current_plan={"actions": [], "entities": []},
                        entities_in_context=[],
                        disambiguation_options=[],
                        last_referenced_id=None,
                        user_message=word,
                    )
                    r = svc.interpret(payload)
                    self.assertEqual(r.dialog_intent, DialogIntent.CONFIRM)

    def test_confirm_word_phrase_not_heuristic(self):
        svc = ReplyInterpreterService(llm_client=FakeLLM('{"dialog_intent":"unclear"}'))
        payload = ReplyInterpreterInput(
            state=DialogState.WAITING_CONFIRMATION.value,
            current_plan={"actions": [], "entities": []},
            entities_in_context=[],
            disambiguation_options=[],
            last_referenced_id=None,
            user_message="подтверждаю",
        )
        r = svc.interpret(payload)
        self.assertNotEqual(r.dialog_intent, DialogIntent.CONFIRM)

    def test_yes_with_weekday_correction_not_heuristic_confirm(self):
        """«Да, запланируй на вторник…» — уточнение, не мгновенный CONFIRM."""
        svc = ReplyInterpreterService(llm_client=FakeLLM('{"dialog_intent":"unclear"}'))
        payload = ReplyInterpreterInput(
            state=DialogState.WAITING_CONFIRMATION.value,
            current_plan={"actions": [], "entities": []},
            entities_in_context=[],
            disambiguation_options=[],
            last_referenced_id=None,
            user_message="Да, запланируй на вторник а не понедельник",
        )
        r = svc.interpret(payload)
        self.assertNotEqual(r.dialog_intent, DialogIntent.CONFIRM)

    def test_confirm_with_qualifier_goes_to_llm(self):
        llm = FakeLLM(
            '{"dialog_intent":"modify","target_ids":[],"actions":[],"step_patches":['
            '{"index":0,"merge":{"datetime":{"date":"2026-04-20"}}}],"new_intent_raw":null}'
        )
        svc = ReplyInterpreterService(llm_client=llm)
        payload = ReplyInterpreterInput(
            state=DialogState.WAITING_CONFIRMATION.value,
            current_plan={"actions": [{"context_id": "a0", "type": "create", "target_id": None, "data": {}}]},
            entities_in_context=[],
            disambiguation_options=[],
            last_referenced_id=None,
            user_message="да, но перенеси на послезавтра",
        )
        r = svc.interpret(payload)
        self.assertEqual(r.dialog_intent, DialogIntent.MODIFY)
        self.assertEqual(len(r.step_patches), 1)

    def test_llm_failure_unclear(self):
        class BoomLLM:
            def chat_with_messages(self, **kwargs):
                raise LLMClientError("x")

        svc = ReplyInterpreterService(llm_client=BoomLLM())
        payload = ReplyInterpreterInput(
            state=DialogState.WAITING_CLARIFICATION.value,
            current_plan={"actions": [], "entities": []},
            entities_in_context=[],
            disambiguation_options=[],
            last_referenced_id=None,
            user_message="про молоко",
        )
        r = svc.interpret(payload)
        self.assertEqual(r.dialog_intent, DialogIntent.UNCLEAR)


class PlanMergeStepPatchesTests(TestCase):
    def test_merge_fields_into_step(self):
        plan = ActionPlan(
            actions=[
                Action(
                    context_id="a0",
                    type="create",
                    target_id=None,
                    data={
                        "action": "create",
                        "entity_type": "task",
                        "fields": {"title": "X"},
                        "query": None,
                        "datetime": {},
                        "meta": {},
                        "filters": {},
                    },
                )
            ],
            entities=[],
        )
        interp = ReplyInterpretation(
            dialog_intent=DialogIntent.MODIFY,
            step_patches=[{"index": 0, "merge": {"fields": {"notes": "n"}}}],
        )
        merged = PlanMergeService().apply_reply(plan, interp)
        self.assertEqual(merged.actions[0].data["fields"]["title"], "X")
        self.assertEqual(merged.actions[0].data["fields"]["notes"], "n")
