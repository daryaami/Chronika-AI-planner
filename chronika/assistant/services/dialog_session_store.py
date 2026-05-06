from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from typing import Any

from django.db import transaction
from django.utils import timezone

from assistant.integrations.llm_client import MistralLLMClient
from assistant.models import AssistantMessage, AssistantSession

from .orchestrator import Orchestrator
from .pending_store import PendingStore
from .tool_router import ToolRouter


@dataclass
class OrchestratorApiResult:
    state: str
    status: str
    user_message: str
    results: list[dict[str, Any]]
    pending_action: dict[str, Any] | None
    presentables: dict[str, Any]


def _get_or_create_session(user) -> AssistantSession:
    session, _ = AssistantSession.objects.get_or_create(user=user)
    return session


def _build_blocks(result: OrchestratorApiResult) -> list[dict[str, Any]]:
    blocks = [{"type": "text", "text": result.user_message}]
    for item in list(result.presentables.get("entities") or []):
        fields = item.get("data") if isinstance(item.get("data"), dict) else {}
        if not fields:
            continue
        entity_type = str(item.get("entity_type") or "")
        entity_id = item.get("id")
        if not entity_type or entity_id is None:
            continue
        blocks.append(
            {
                "type": "entity",
                "entity_type": entity_type,
                "context_id": f"e:{entity_type}:{entity_id}",
                "mode": "readonly",
                "fields": fields,
                "editable_fields": [],
            }
        )
    for deletion in list(result.presentables.get("deletions") or []):
        if not isinstance(deletion, dict):
            continue
        entity_id = deletion.get("id")
        entity_type = deletion.get("entity_type")
        if entity_id is None or not entity_type:
            continue
        blocks.append(
            {
                "type": "deleted_entity",
                "entity_type": entity_type,
                "id": entity_id,
                "context_id": f"e:{entity_type}:{entity_id}",
            }
        )
    if result.pending_action and result.pending_action.get("disambiguation_candidates"):
        entities = []
        for candidate in list(result.pending_action.get("disambiguation_candidates") or []):
            if not isinstance(candidate, dict):
                continue
            entity_type = str(candidate.get("entity_type") or "")
            entity_id = candidate.get("id")
            payload = candidate.get("data") if isinstance(candidate.get("data"), dict) else {}
            if not entity_type or entity_id is None:
                continue
            entities.append(
                {
                    "id": entity_id,
                    "entity_type": entity_type,
                    "context_id": f"e:{entity_type}:{entity_id}",
                    "title": payload.get("title") or payload.get("summary"),
                    "start": payload.get("start"),
                    "end": payload.get("end"),
                }
            )
        if entities:
            blocks.append({"type": "entity_selection", "entities": entities})
    elif (
        result.pending_action
        and result.pending_action.get("slot_candidates")
        and str(result.pending_action.get("status") or "") == "needs_disambiguation"
    ):
        blocks.append(
            {
                "type": "time_slot_selection",
                "context_id": result.pending_action.get("id"),
                "slots": [
                    {"start": slot.get("start"), "end": slot.get("end")}
                    for slot in list(result.pending_action.get("slot_candidates") or [])
                    if isinstance(slot, dict)
                ],
            }
        )
    if result.pending_action:
        blocks.append({"type": "pending_action", "pending_action": result.pending_action})
    return blocks


def _build_orchestrator(user) -> Orchestrator:
    pending_store = PendingStore()
    session = AssistantSession.objects.filter(user=user).first()
    if session and session.dialog_state in {"awaiting_confirmation", "needs_disambiguation"}:
        for msg in session.messages.filter(role="assistant").order_by("-created_at")[:20]:
            pending = (msg.metadata_json or {}).get("pending_action")
            if not isinstance(pending, dict):
                continue
            pending_status = str(pending.get("status") or "")
            if pending_status not in {"awaiting_confirmation", "needs_disambiguation"}:
                continue
            expires_at_raw = pending.get("expires_at")
            if not isinstance(expires_at_raw, str):
                continue
            try:
                expires_at = datetime.fromisoformat(expires_at_raw)
            except ValueError:
                continue
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at, timezone=datetime_timezone.utc)
            if expires_at <= timezone.now():
                continue
            pending_store.create(
                action_type=str(pending.get("type") or "pending"),
                payload=dict(pending.get("payload") or {}),
                status=pending_status,
                slot_candidates=list(pending.get("slot_candidates") or []),
                disambiguation_candidates=list(pending.get("disambiguation_candidates") or []),
                meta=dict(pending.get("meta") or {}),
            )
            break
    return Orchestrator(
        llm_client=MistralLLMClient(),
        tool_router=ToolRouter(user=user),
        pending_store=pending_store,
    )


def _extract_last_entity(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(list(results or [])):
        if not isinstance(item, dict):
            continue
        if item.get("status") != "executed":
            continue
        data = item.get("data") or {}
        if not isinstance(data, dict):
            continue
        task = data.get("task")
        if isinstance(task, dict) and task.get("id") is not None:
            return {
                "kind": "task",
                "id": task.get("id"),
                "title": task.get("title"),
                "duration": task.get("duration"),
                "due_date": task.get("due_date"),
            }
        event = data.get("event")
        if isinstance(event, dict) and event.get("id") is not None:
            return {
                "kind": "event",
                "id": event.get("id"),
                "title": event.get("title") or event.get("summary"),
                "start": event.get("start"),
                "end": event.get("end"),
            }
    return None


def _build_presentables(
    results: list[dict[str, Any]],
    pending_action: dict[str, Any] | None,
) -> dict[str, Any]:
    entities: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []
    deletions: list[dict[str, Any]] = []
    seen_entities: set[tuple[str, Any]] = set()
    seen_slots: set[tuple[Any, Any]] = set()
    seen_deletions: set[tuple[str, Any]] = set()
    for item in list(results or []):
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        # Do not expose raw search candidates in generic responses.
        # Ambiguity choices are rendered via pending_action.disambiguation_candidates
        # and finalized entity cards are rendered from task/event mutation results below.
        for slot in list(data.get("slots") or []):
            if not isinstance(slot, dict):
                continue
            key = (slot.get("start"), slot.get("end"))
            if key in seen_slots:
                continue
            seen_slots.add(key)
            slots.append(dict(slot))
        task = data.get("task")
        if isinstance(task, dict) and task.get("id") is not None:
            key = ("task", task.get("id"))
            if key not in seen_entities:
                seen_entities.add(key)
                entities.append({"entity_type": "task", "id": task.get("id"), "data": task})
        event = data.get("event")
        if isinstance(event, dict) and event.get("id") is not None:
            key = ("event", event.get("id"))
            if key not in seen_entities:
                seen_entities.add(key)
                entities.append({"entity_type": "event", "id": event.get("id"), "data": event})
        deleted_id = data.get("deleted_id")
        if deleted_id is not None:
            deleted_type = ""
            tool_name = str(item.get("tool_name") or "")
            if tool_name in {"delete_task"}:
                deleted_type = "task"
            elif tool_name in {"delete_event"}:
                deleted_type = "event"
            elif tool_name == "confirm_action":
                resolved_payload = item.get("resolved_payload")
                if isinstance(resolved_payload, dict):
                    nested_tool_name = str(
                        (resolved_payload.get("tool_name") or "")
                    )
                    if nested_tool_name == "delete_task":
                        deleted_type = "task"
                    elif nested_tool_name == "delete_event":
                        deleted_type = "event"
                if not deleted_type:
                    deleted_type = str(data.get("entity_type") or "")
            if deleted_type:
                deletion_key = (deleted_type, deleted_id)
                if deletion_key not in seen_deletions:
                    seen_deletions.add(deletion_key)
                    deletions.append({"entity_type": deleted_type, "id": deleted_id})

    if isinstance(pending_action, dict):
        for slot in list(pending_action.get("slot_candidates") or []):
            if not isinstance(slot, dict):
                continue
            key = (slot.get("start"), slot.get("end"))
            if key in seen_slots:
                continue
            seen_slots.add(key)
            slots.append(dict(slot))
        for candidate in list(pending_action.get("disambiguation_candidates") or []):
            if not isinstance(candidate, dict):
                continue
            entity_type = str(candidate.get("entity_type") or "")
            entity_id = candidate.get("id")
            data_payload = candidate.get("data")
            if not entity_type or entity_id is None or not isinstance(data_payload, dict):
                continue
            key = (entity_type, entity_id)
            if key in seen_entities:
                continue
            seen_entities.add(key)
            entities.append({"entity_type": entity_type, "id": entity_id, "data": data_payload})

    return {"entities": entities, "slots": slots, "deletions": deletions}


def _public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    sanitized = dict(metadata)
    sanitized.pop("results", None)
    return sanitized


def _normalize_ui_action(action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    action_type = str(action.get("type") or "").strip()
    payload = dict(action.get("payload") or {})
    if action_type == "confirm":
        return "confirm_action", payload
    if action_type == "cancel":
        return "cancel_action", payload
    if action_type == "select_time_slot":
        context_id = str(payload.get("context_id") or "")
        slot = payload.get("slot") if isinstance(payload.get("slot"), dict) else {}
        return "modify_action", {"pending_id": context_id, "changes": {"slot": slot}}
    if action_type == "select_entity":
        context_ids = payload.get("context_ids")
        selected = context_ids[0] if isinstance(context_ids, list) and context_ids else payload.get("context_id")
        return "modify_action", {"changes": {"selected_context_id": selected}}
    if action_type == "entity_update":
        context_id = payload.get("context_id")
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        return "modify_action", {"changes": {"context_id": context_id, "fields": fields}}
    return action_type, payload


@transaction.atomic
def run_assistant_turn_with_persisted_state(user, message: str, client_message_id: str | None = None):
    session = _get_or_create_session(user)
    AssistantMessage.objects.create(
        session=session,
        role="user",
        content=str(message),
        metadata_json={"client_message_id": client_message_id} if client_message_id else {},
        blocks=[{"type": "text", "text": str(message)}],
        fsm_state=session.dialog_state,
    )
    orchestrator = _build_orchestrator(user)
    dialog_context = dict(session.dialog_context or {})
    dialog_context["user_tz"] = getattr(user, "time_zone", None) or "UTC"
    out = orchestrator.handle_message(str(message), dialog_context=dialog_context)
    api_result = OrchestratorApiResult(
        state=out["state"],
        status=out["status"],
        user_message=out["user_message"],
        results=out["results"],
        pending_action=out.get("pending_action"),
        presentables=_build_presentables(out["results"], out.get("pending_action")),
    )
    orchestrator_context = dict(out.get("dialog_context") or {})
    orchestrator_meta = dict(out.get("meta") or {})
    blocks = _build_blocks(api_result)
    assistant_msg = AssistantMessage.objects.create(
        session=session,
        role="assistant",
        content=api_result.user_message,
        metadata_json={
            "results": api_result.results,
            "presentables": api_result.presentables,
            "pending_action": api_result.pending_action,
            "meta": orchestrator_meta,
        },
        blocks=blocks,
        fsm_state=api_result.state,
    )
    updated_context = dict(session.dialog_context or {})
    updated_context.update(orchestrator_context)
    updated_context["user_tz"] = getattr(user, "time_zone", None) or "UTC"
    last_entity = _extract_last_entity(api_result.results)
    if last_entity:
        updated_context["last_entity"] = last_entity
        updated_context["last_referenced_id"] = last_entity.get("id")
    session.dialog_state = api_result.state
    session.dialog_context = updated_context
    session.last_referenced_id = updated_context.get("last_referenced_id")
    session.save(update_fields=["dialog_state", "dialog_context", "last_referenced_id", "updated_at"])
    return api_result, str(assistant_msg.public_id), blocks


def run_assistant_ui_action(user, body: dict[str, Any]):
    action = body.get("action") if isinstance(body, dict) else {}
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    action_type, payload = _normalize_ui_action(action)
    if action_type not in {"confirm_action", "cancel_action", "modify_action"}:
        raise ValueError("Unsupported action.type")
    session = _get_or_create_session(user)
    orchestrator = _build_orchestrator(user)
    out = orchestrator.handle_ui_action(action_type=action_type, payload=payload)
    api_result = OrchestratorApiResult(
        state=out["state"],
        status=out["status"],
        user_message=out["user_message"],
        results=out["results"],
        pending_action=out.get("pending_action"),
        presentables=_build_presentables(out["results"], out.get("pending_action")),
    )
    orchestrator_context = dict(out.get("dialog_context") or {})
    orchestrator_meta = dict(out.get("meta") or {})
    blocks = _build_blocks(api_result)
    assistant_msg = AssistantMessage.objects.create(
        session=session,
        role="assistant",
        content=api_result.user_message,
        metadata_json={
            "results": api_result.results,
            "presentables": api_result.presentables,
            "pending_action": api_result.pending_action,
            "ui_action": action,
            "meta": orchestrator_meta,
        },
        blocks=blocks,
        fsm_state=api_result.state,
    )
    updated_context = dict(session.dialog_context or {})
    updated_context.update(orchestrator_context)
    updated_context["user_tz"] = getattr(user, "time_zone", None) or "UTC"
    last_entity = _extract_last_entity(api_result.results)
    if last_entity:
        updated_context["last_entity"] = last_entity
        updated_context["last_referenced_id"] = last_entity.get("id")
    session.dialog_state = api_result.state
    session.dialog_context = updated_context
    session.last_referenced_id = updated_context.get("last_referenced_id")
    session.save(update_fields=["dialog_state", "dialog_context", "last_referenced_id", "updated_at"])
    return api_result, str(assistant_msg.public_id), blocks


def get_session_history_payload(user):
    session = AssistantSession.objects.filter(user=user).first()
    if not session:
        return {"session_id": None, "state": "idle", "messages": []}
    msgs = session.messages.order_by("created_at")
    out = []
    for m in msgs:
        out.append(
            {
                "message_id": str(m.public_id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "blocks": m.blocks or [{"type": "text", "text": m.content}],
                "state": m.fsm_state or None,
                "metadata": _public_metadata(m.metadata_json or {}),
            }
        )
    return {"session_id": session.id, "state": session.dialog_state, "messages": out}


@transaction.atomic
def clear_user_assistant_session(user):
    session = AssistantSession.objects.filter(user=user).first()
    if not session:
        return {"cleared": True, "messages_deleted": 0}
    deleted = session.messages.all().delete()[0]
    session.dialog_state = "idle"
    session.action_plan = None
    session.dialog_context = {}
    session.last_referenced_id = None
    session.save(update_fields=["dialog_state", "action_plan", "dialog_context", "last_referenced_id", "updated_at"])
    return {"cleared": True, "messages_deleted": deleted}
