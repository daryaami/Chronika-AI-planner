import unittest
from unittest.mock import MagicMock

from assistant.domain.action_plan import ActionPlan
from assistant.domain.context import StructuredContext
from assistant.fsm.machine import DialogSessionSnapshot, FsmMachine
from assistant.fsm.states import DialogState
from assistant.services.intent_parser import ParsedIntentResult


class FsmEmptyPlanRoutesIdleTest(unittest.TestCase):
    def test_empty_plan_skips_reply_interpreter_uses_intent_parser(self):
        intent = MagicMock()
        intent.parse.return_value = ParsedIntentResult(items=[], raw_response="[]")
        reply = MagicMock()

        fsm = FsmMachine(intent_parser=intent, reply_interpreter=reply)
        user = MagicMock()
        user.id = 1

        snap = DialogSessionSnapshot(
            state=DialogState.WAITING_CLARIFICATION,
            plan=ActionPlan(actions=[], entities=[]),
            context=StructuredContext(),
        )
        fsm.run_turn(user=user, user_message="Перенеси обед на попозже", snapshot=snap)
        intent.parse.assert_called_once_with("Перенеси обед на попозже")
        reply.interpret.assert_not_called()
