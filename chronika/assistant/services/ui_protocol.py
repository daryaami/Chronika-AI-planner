from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils.dateparse import parse_datetime

from assistant.domain.action_plan import action_plan_from_dict
from assistant.domain.context import structured_context_from_dict
from assistant.domain.dialog import DialogIntent, ReplyInterpretation
from assistant.fsm.machine import DialogSessionSnapshot
from assistant.fsm.states import DialogState

# Поля, которые UI может править в режиме подтверждения (остальное в `fields` только для отображения).
_EVENT_EDITABLE_FIELDS: tuple[str, ...] = ("summary", "start", "end")
_TASK_EDITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "due_date",
    "duration",
    "category_id",
    "priority",
)

# Не отдавать клиенту в blocks.entity.fields (внутреннее для планировщика / пайплайна).
_ENTITY_FIELDS_HIDDEN_FROM_CLIENT: frozenset[str] = frozenset({"time_constraints", "date"})


def _strip_internal_entity_fields_for_client(fields: dict[str, Any]) -> None:
    for k in _ENTITY_FIELDS_HIDDEN_FROM_CLIENT:
        fields.pop(k, None)


def _normalize_event_fields_for_ui(fields: dict[str, Any]) -> None:
    """Для события в UI всегда ключи start и end; значения из start_at/end_at подставляем и убираем дубли."""
    if "start" not in fields and fields.get("start_at") is not None:
        fields["start"] = fields["start_at"]
    if "end" not in fields and fields.get("end_at") is not None:
        fields["end"] = fields["end_at"]
    for k in ("start_at", "end_at"):
        fields.pop(k, None)
    if "start" not in fields:
        fields["start"] = None
    if "end" not in fields:
        fields["end"] = None


def _maybe_fill_event_end_from_duration(fields: dict[str, Any]) -> None:
    """Для события: при start + duration без end — выставить end в blocks (удобство UI)."""
    raw_dur = fields.get("duration")
    try:
        mins = int(raw_dur) if raw_dur is not None else 0
    except (TypeError, ValueError):
        return
    if mins < 1:
        return
    if fields.get("end") not in (None, ""):
        return
    start_raw = fields.get("start")
    if start_raw in (None, ""):
        return
    dt = parse_datetime(str(start_raw))
    if dt is None:
        return
    fields["end"] = (dt + timedelta(minutes=mins)).isoformat()


def _editable_fields_for_entity(entity_type: str, *, mode: str) -> list[str]:
    if mode != "editable":
        return []
    et = (entity_type or "").strip().lower()
    if et == "event":
        return list(_EVENT_EDITABLE_FIELDS)
    if et == "task":
        return list(_TASK_EDITABLE_FIELDS)
    return []


def build_ui_blocks(
    *,
    state: str,
    assistant_reply: str,
    plan: dict[str, Any] | None,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if (assistant_reply or "").strip():
        blocks.append({"type": "text", "text": assistant_reply.strip()})

    opts = context.get("disambiguation_options") or []
    if state == DialogState.DISAMBIGUATION.value and isinstance(opts, list) and opts:
        entities: list[dict[str, Any]] = []
        for o in opts:
            if not isinstance(o, dict):
                continue
            oid = o.get("object_id")
            if oid is None:
                continue
            et = str(o.get("entity_type") or "task")
            title = f"{et} #{oid}"
            row: dict[str, Any] = {
                "id": int(oid),
                "entity_type": et,
                "context_id": str(o.get("context_id") or f"pick_{o.get('index', 0)}"),
                "title": title,
            }
            entities.append(row)
        if entities:
            blocks.append({"type": "entity_selection", "entities": entities})

    elif plan and isinstance(plan.get("entities"), list) and plan["entities"]:
        mode = "editable" if state == DialogState.WAITING_CONFIRMATION.value else "readonly"
        entities = plan["entities"]
        actions = plan.get("actions") or []
        for i, ent in enumerate(entities):
            if not isinstance(ent, dict):
                continue
            data = actions[i].get("data") if i < len(actions) and isinstance(actions[i], dict) else {}
            if not isinstance(data, dict):
                data = {}
            fields: dict[str, Any] = {}
            if isinstance(data.get("fields"), dict):
                fields.update(data["fields"])
            dt = data.get("datetime") if isinstance(data.get("datetime"), dict) else {}
            if dt:
                for k, v in dt.items():
                    if v is not None and k not in fields:
                        fields[k] = v
            _strip_internal_entity_fields_for_client(fields)
            et = str(ent.get("type") or data.get("entity_type") or "task")
            if ent.get("title"):
                if et == "event" and "summary" not in fields:
                    fields["summary"] = ent["title"]
                elif et == "task" and "title" not in fields:
                    fields["title"] = ent["title"]
            if et == "event":
                _normalize_event_fields_for_ui(fields)
                _maybe_fill_event_end_from_duration(fields)
            editable = _editable_fields_for_entity(et, mode=mode)
            blocks.append(
                {
                    "type": "entity",
                    "entity_type": et,
                    "context_id": str(ent.get("context_id") or f"e{i}"),
                    "mode": mode,
                    "fields": fields,
                    "editable_fields": editable,
                }
            )

    slot_block = _time_slot_block_from_plan(plan)
    if slot_block:
        blocks.append(slot_block)

    return blocks


def _time_slot_block_from_plan(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan or not isinstance(plan.get("actions"), list):
        return None
    for action in plan["actions"]:
        if not isinstance(action, dict):
            continue
        data = action.get("data") if isinstance(action.get("data"), dict) else {}
        slots = data.get("time_slot_options") or data.get("slots")
        if isinstance(slots, list) and slots:
            return {
                "type": "time_slot_selection",
                "context_id": str(action.get("context_id") or "a0"),
                "slots": slots,
            }
    return None


def interpretation_from_ui_action(
    snapshot: DialogSessionSnapshot,
    action: dict[str, Any],
) -> ReplyInterpretation | None:
    if not isinstance(action, dict):
        return None
    atype = str(action.get("type") or "").strip().lower()
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

    if atype == "confirm":
        return ReplyInterpretation(dialog_intent=DialogIntent.CONFIRM)

    if atype == "cancel":
        return ReplyInterpretation(dialog_intent=DialogIntent.CANCEL)

    if atype == "entity_update":
        ctx = str(payload.get("context_id") or "").strip()
        fields = payload.get("fields")
        if not ctx or not isinstance(fields, dict):
            return None
        idx = _entity_index_by_context_id(snapshot, ctx)
        if idx is None:
            return None
        merge: dict[str, Any] = {"fields": fields}
        return ReplyInterpretation(
            dialog_intent=DialogIntent.MODIFY,
            step_patches=[{"index": idx, "merge": merge}],
        )

    if atype == "select_entity":
        ids = payload.get("context_ids")
        if not isinstance(ids, list) or not ids:
            return None
        target_ids = _resolve_disambig_selection(snapshot, [str(x) for x in ids])
        if not target_ids:
            return None
        return ReplyInterpretation(
            dialog_intent=DialogIntent.SELECT,
            target_ids=target_ids,
        )

    if atype == "select_time_slot":
        act_ctx = str(payload.get("context_id") or "").strip()
        slot = payload.get("slot")
        if not act_ctx or not isinstance(slot, dict):
            return None
        idx = _action_index_by_context_id(snapshot, act_ctx)
        if idx is None:
            return None
        merge_dt: dict[str, Any] = {}
        if slot.get("start") is not None:
            merge_dt["start_at"] = slot["start"]
        if slot.get("end") is not None:
            merge_dt["end_at"] = slot["end"]
        if not merge_dt:
            return None
        return ReplyInterpretation(
            dialog_intent=DialogIntent.MODIFY,
            step_patches=[
                {
                    "index": idx,
                    "merge": {
                        "datetime": merge_dt,
                        "fields": {},
                    },
                }
            ],
        )

    return None


def _entity_index_by_context_id(snapshot: DialogSessionSnapshot, context_id: str) -> int | None:
    if not snapshot.plan:
        return None
    for i, ent in enumerate(snapshot.plan.entities):
        if ent.context_id == context_id:
            return i
    return None


def _action_index_by_context_id(snapshot: DialogSessionSnapshot, context_id: str) -> int | None:
    if not snapshot.plan:
        return None
    for i, act in enumerate(snapshot.plan.actions):
        if act.context_id == context_id:
            return i
    return None


def _resolve_disambig_selection(
    snapshot: DialogSessionSnapshot,
    context_ids: list[str],
) -> list[int]:
    opts = snapshot.context.disambiguation_options
    if not opts:
        return []
    want = set(context_ids)
    out: list[int] = []
    for o in opts:
        if not isinstance(o, dict):
            continue
        cid = str(o.get("context_id") or "")
        if cid in want and o.get("object_id") is not None:
            out.append(int(o["object_id"]))
    return out


def snapshot_from_session_row(*, dialog_state: str, action_plan: Any, dialog_context: Any, last_ref: Any):
    try:
        st = DialogState(dialog_state)
    except ValueError:
        st = DialogState.IDLE
    last_id: int | None
    if last_ref is None or last_ref == "":
        last_id = None
    else:
        try:
            last_id = int(last_ref)
        except (TypeError, ValueError):
            last_id = None
    return DialogSessionSnapshot(
        state=st,
        plan=action_plan_from_dict(action_plan if isinstance(action_plan, dict) else None),
        context=structured_context_from_dict(dialog_context if isinstance(dialog_context, dict) else None),
        last_referenced_id=last_id,
    )
