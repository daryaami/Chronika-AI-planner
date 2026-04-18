from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model

from assistant.domain.action_plan import action_plan_from_dict, action_plan_to_dict
from assistant.domain.context import structured_context_from_dict, structured_context_to_dict
from assistant.domain.dialog import ReplyInterpretation
from assistant.fsm.machine import DialogSessionSnapshot, FsmMachine
from assistant.fsm.states import DialogState
from assistant.services.intent_parser import IntentParserService


@dataclass
class ChatOrchestratorResult:
    message: str
    assistant_reply: str
    user_id: int
    intents: list[dict[str, Any]]
    state: str
    action_plan: dict[str, Any] | None
    context: dict[str, Any]
    last_referenced_id: int | None
    execution_artifact: dict[str, Any] | None


@dataclass
class DialogTurnResult:
    """Результат одного логического хода FSM (с учётом цепочки pending_followup)."""

    message: str
    user_id: int
    assistant_reply: str
    state: str
    plan: dict[str, Any] | None
    context: dict[str, Any]
    last_referenced_id: int | None
    execution_artifact: dict[str, Any] | None = None


class ChatOrchestratorService:
    """
    Оркестратор бизнес-логики ассистента.
    """

    def __init__(self, intent_parser: IntentParserService | None = None):
        self.intent_parser = intent_parser or IntentParserService()
        self.fsm = FsmMachine(intent_parser=self.intent_parser)

    def process_dialog_turn(
        self,
        user_id: int,
        message: str,
        *,
        session_state: str = DialogState.IDLE.value,
        plan_dict: dict[str, Any] | None = None,
        context_dict: dict[str, Any] | None = None,
        last_referenced_id: int | None = None,
        max_followups: int = 3,
        forced_interpretation: ReplyInterpretation | None = None,
    ) -> DialogTurnResult:
        """
        Точка входа stateful-диалога: FSM + Action Plan + структурированный контекст.

        При `pending_followup_message` (например new_request / new_intent_candidate) выполняется
        до `max_followups` последовательных проходов в том же вызове API.
        """
        User = get_user_model()
        user = User.objects.get(id=user_id)

        try:
            state = DialogState(session_state)
        except ValueError:
            state = DialogState.IDLE

        snapshot = DialogSessionSnapshot(
            state=state,
            plan=action_plan_from_dict(plan_dict),
            context=structured_context_from_dict(context_dict),
            last_referenced_id=last_referenced_id,
        )

        replies: list[str] = []
        artifact: dict[str, Any] | None = None
        follow = (message or "").strip()

        for turn_idx in range(max(1, max_followups)):
            fi = forced_interpretation if turn_idx == 0 else None
            turn = self.fsm.run_turn(
                user=user,
                user_message=follow,
                snapshot=snapshot,
                forced_interpretation=fi,
            )
            snapshot = turn.snapshot
            if turn.assistant_reply:
                replies.append(turn.assistant_reply.strip())
            if turn.execution_artifact is not None:
                artifact = turn.execution_artifact
            if not turn.pending_followup_message:
                break
            follow = turn.pending_followup_message.strip()

        assistant_reply = "\n\n".join(r for r in replies if r)

        return DialogTurnResult(
            message=message,
            user_id=user_id,
            assistant_reply=assistant_reply,
            state=snapshot.state.value,
            plan=action_plan_to_dict(snapshot.plan) if snapshot.plan else None,
            context=structured_context_to_dict(snapshot.context),
            last_referenced_id=snapshot.last_referenced_id,
            execution_artifact=artifact,
        )

    def process_message(
        self,
        user_id: int,
        message: str,
        *,
        session_state: str = DialogState.IDLE.value,
        plan_dict: dict[str, Any] | None = None,
        context_dict: dict[str, Any] | None = None,
        last_referenced_id: int | None = None,
    ) -> ChatOrchestratorResult:
        """
        HTTP-вход: полный путь FSM (как у `process_dialog_turn`), без дублирования
        старого парсера + отдельного semantic search.
        """
        turn = self.process_dialog_turn(
            user_id=user_id,
            message=message,
            session_state=session_state,
            plan_dict=plan_dict,
            context_dict=context_dict,
            last_referenced_id=last_referenced_id,
            forced_interpretation=None,
        )
        intents = self._intents_from_action_plan(turn.plan)
        return ChatOrchestratorResult(
            message=turn.message,
            assistant_reply=turn.assistant_reply,
            user_id=turn.user_id,
            intents=intents,
            state=turn.state,
            action_plan=turn.plan,
            context=turn.context,
            last_referenced_id=turn.last_referenced_id,
            execution_artifact=turn.execution_artifact,
        )

    @staticmethod
    def _intents_from_action_plan(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Совместимость с полем `intents`: шаги из `action.data` в плане."""
        if not plan:
            return []
        actions = plan.get("actions")
        if not isinstance(actions, list):
            return []
        out: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            data = action.get("data")
            if not isinstance(data, dict):
                data = {}
            item = dict(data)
            item["candidates"] = []
            out.append(item)
        return out
