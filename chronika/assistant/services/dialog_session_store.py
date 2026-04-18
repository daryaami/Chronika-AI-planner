from __future__ import annotations

import uuid
from typing import Any

from django.db import IntegrityError, transaction

from assistant.fsm.states import DialogState
from assistant.models import AssistantMessage, AssistantSession
from assistant.services.chat_orchestrator import (
    ChatOrchestratorResult,
    ChatOrchestratorService,
    DialogTurnResult,
)
from assistant.services.ui_protocol import (
    build_ui_blocks,
    interpretation_from_ui_action,
    snapshot_from_session_row,
)


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


def _turn_to_chat_result(turn: DialogTurnResult, *, message: str, user_id: int) -> ChatOrchestratorResult:
    return ChatOrchestratorResult(
        message=message,
        assistant_reply=turn.assistant_reply,
        user_id=user_id,
        intents=ChatOrchestratorService._intents_from_action_plan(turn.plan),
        state=turn.state,
        action_plan=turn.plan,
        context=turn.context,
        last_referenced_id=turn.last_referenced_id,
        execution_artifact=turn.execution_artifact,
    )


def _persist_assistant_message(
    session: AssistantSession,
    *,
    assistant_reply: str,
    state: str,
    blocks: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> AssistantMessage:
    return AssistantMessage.objects.create(
        session=session,
        role="assistant",
        content=assistant_reply or "",
        metadata_json=metadata if isinstance(metadata, dict) else {},
        blocks=blocks,
        fsm_state=state,
    )


def run_assistant_turn_with_persisted_state(
    user,
    message: str,
    *,
    client_message_id: str | None = None,
) -> tuple[ChatOrchestratorResult, str, list[dict[str, Any]]]:
    orchestrator = ChatOrchestratorService()

    with transaction.atomic():
        session = get_or_create_dialog_session_for_update(user)
        if client_message_id:
            try:
                mid = uuid.UUID(str(client_message_id))
            except (ValueError, TypeError) as exc:
                raise ValueError("invalid client_context.message_id") from exc
            if not AssistantMessage.objects.filter(
                session=session, public_id=mid, role="assistant"
            ).exists():
                raise ValueError("unknown client_context.message_id")

        AssistantMessage.objects.create(
            session=session,
            role="user",
            content=str(message),
            metadata_json={},
            blocks=[],
            fsm_state="",
        )

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
        blocks = build_ui_blocks(
            state=result.state,
            assistant_reply=result.assistant_reply,
            plan=result.action_plan,
            context=result.context,
        )
        am = _persist_assistant_message(
            session,
            assistant_reply=result.assistant_reply,
            state=result.state,
            blocks=blocks,
            metadata={"user_message": message},
        )
    return result, str(am.public_id), blocks


def run_assistant_ui_action(
    user,
    body: dict[str, Any],
) -> tuple[ChatOrchestratorResult, str, list[dict[str, Any]]]:
    message_id = body.get("message_id")
    cc = body.get("client_context") if isinstance(body.get("client_context"), dict) else {}
    if not message_id and isinstance(cc, dict) and cc.get("message_id"):
        message_id = cc.get("message_id")
    if not message_id:
        raise ValueError("message_id is required")

    action = body.get("action")
    if not isinstance(action, dict):
        raise ValueError("action must be an object")

    orchestrator = ChatOrchestratorService()

    with transaction.atomic():
        session = get_or_create_dialog_session_for_update(user)
        try:
            mid = uuid.UUID(str(message_id))
        except (ValueError, TypeError):
            raise ValueError("invalid message_id") from None
        if not AssistantMessage.objects.filter(
            session=session, public_id=mid, role="assistant"
        ).exists():
            raise ValueError("unknown message_id")

        snapshot = snapshot_from_session_row(
            dialog_state=session.dialog_state,
            action_plan=session.action_plan,
            dialog_context=session.dialog_context,
            last_ref=session.last_referenced_id,
        )
        interpretation = interpretation_from_ui_action(snapshot, action)
        if interpretation is None:
            raise ValueError("unsupported or invalid action")

        if session.dialog_state == DialogState.IDLE.value:
            raise ValueError("no active dialog step for this action")

        turn = orchestrator.process_dialog_turn(
            user_id=user.id,
            message="",
            session_state=session.dialog_state,
            plan_dict=session.action_plan,
            context_dict=session.dialog_context,
            last_referenced_id=session.last_referenced_id,
            forced_interpretation=interpretation,
        )
        apply_turn_to_session(
            session,
            state=turn.state,
            action_plan=turn.plan,
            context=turn.context,
            last_referenced_id=turn.last_referenced_id,
        )
        result = _turn_to_chat_result(turn, message="", user_id=user.id)
        blocks = build_ui_blocks(
            state=result.state,
            assistant_reply=result.assistant_reply,
            plan=result.action_plan,
            context=result.context,
        )
        am = _persist_assistant_message(
            session,
            assistant_reply=result.assistant_reply,
            state=result.state,
            blocks=blocks,
            metadata={"ui_action": action},
        )

    return result, str(am.public_id), blocks
