from __future__ import annotations

from django.db import IntegrityError, transaction

from assistant.fsm.states import DialogState
from assistant.models import AssistantSession
from assistant.services.chat_orchestrator import ChatOrchestratorResult, ChatOrchestratorService


def get_or_create_dialog_session_for_update(user) -> AssistantSession:
    """
    Одна активная сессия диалога на пользователя; строка блокируется на время транзакции.
    """
    session = AssistantSession.objects.select_for_update().filter(user=user).first()
    if session is not None:
        return session
    sid = transaction.savepoint()
    try:
        return AssistantSession.objects.create(
            user=user,
            dialog_state=DialogState.IDLE.value,
            action_plan=None,
            dialog_context={},
            last_referenced_id=None,
        )
    except IntegrityError:
        transaction.savepoint_rollback(sid)
        return AssistantSession.objects.select_for_update().get(user=user)


def apply_turn_to_session(
    session: AssistantSession,
    *,
    state: str,
    action_plan: dict | None,
    context: dict,
    last_referenced_id: int | None,
) -> None:
    session.dialog_state = state
    session.action_plan = action_plan
    session.dialog_context = context if isinstance(context, dict) else {}
    session.last_referenced_id = last_referenced_id
    session.save(
        update_fields=[
            "dialog_state",
            "action_plan",
            "dialog_context",
            "last_referenced_id",
            "updated_at",
        ]
    )


def run_assistant_turn_with_persisted_state(user, message: str) -> ChatOrchestratorResult:
    orchestrator = ChatOrchestratorService()

    with transaction.atomic():
        session = get_or_create_dialog_session_for_update(user)
        result = orchestrator.process_message(
            user_id=user.id,
            message=message,
            session_state=session.dialog_state,
            plan_dict=session.action_plan,
            context_dict=session.dialog_context,
            last_referenced_id=session.last_referenced_id,
        )
        apply_turn_to_session(
            session,
            state=result.state,
            action_plan=result.action_plan,
            context=result.context,
            last_referenced_id=result.last_referenced_id,
        )

    return result
