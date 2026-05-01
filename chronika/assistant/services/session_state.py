"""
Слой работы с execution state ассистента (рабочая память сценария).

State хранится в AssistantSession.execution_state (JSON).
Структура согласована с ParsedIntent / ParsedIntentResult из intent_parser.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any, Literal

from django.utils import timezone

from assistant.services.intent_parser import ParsedIntent, ParsedIntentResult

Step = Literal["idle", "collecting", "disambiguating", "confirming", "executing"]
ItemStatus = Literal["pending", "blocked", "done", "failed"]
ParseMode = Literal["full", "continuation", "none"]

STATE_VERSION = 1


@dataclass
class IntentPlanItem:
    ordinal: int
    intent: str
    entity_type: str | None
    query: str | None
    entity_id: str | None
    fields: dict[str, Any]
    datetime: dict[str, Any]
    filters: dict[str, Any]
    meta: dict[str, Any]
    status: ItemStatus = "pending"
    block_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntentPlanItem:
        known = {f.name for f in fields(cls)}
        kwargs = {k: data[k] for k in known if k in data}
        return cls(**kwargs)


@dataclass
class IntentPlan:
    items: list[IntentPlanItem] = field(default_factory=list)
    active_item_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "active_item_index": self.active_item_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> IntentPlan:
        if not data:
            return cls()
        items_raw = data.get("items") or []
        items = [IntentPlanItem.from_dict(x) for x in items_raw if isinstance(x, dict)]
        idx = int(data.get("active_item_index", 0))
        return cls(items=items, active_item_index=max(0, min(idx, len(items) - 1)) if items else 0)


@dataclass
class DisambiguationState:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    resolution: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"candidates": copy.deepcopy(self.candidates), "resolution": self.resolution}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DisambiguationState:
        if not data:
            return cls()
        cand = data.get("candidates")
        if not isinstance(cand, list):
            cand = []
        res = data.get("resolution")
        if res is not None and not isinstance(res, dict):
            res = None
        return cls(candidates=copy.deepcopy(cand), resolution=res)


@dataclass
class PendingConfirmation:
    action: str
    payload_summary: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "payload_summary": copy.deepcopy(self.payload_summary),
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingConfirmation:
        return cls(
            action=str(data.get("action", "")),
            payload_summary=dict(data.get("payload_summary") or {}),
            idempotency_key=data.get("idempotency_key"),
        )


@dataclass
class LastCompletedAction:
    action: str
    entity_id: str | None = None
    at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "entity_id": self.entity_id, "at": self.at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LastCompletedAction:
        return cls(
            action=str(data.get("action", "")),
            entity_id=data.get("entity_id"),
            at=str(data.get("at", "")),
        )


@dataclass
class AssistantExecutionState:
    version: int = STATE_VERSION
    step: Step = "idle"
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent_plan: IntentPlan = field(default_factory=IntentPlan)
    disambiguation: DisambiguationState = field(default_factory=DisambiguationState)
    pending_confirmation: PendingConfirmation | None = None
    last_completed_action: LastCompletedAction | None = None
    updated_at: str | None = None

    def touch(self) -> None:
        self.updated_at = timezone.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "step": self.step,
            "turn_id": self.turn_id,
            "intent_plan": self.intent_plan.to_dict(),
            "disambiguation": self.disambiguation.to_dict(),
            "pending_confirmation": self.pending_confirmation.to_dict()
            if self.pending_confirmation
            else None,
            "last_completed_action": self.last_completed_action.to_dict()
            if self.last_completed_action
            else None,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AssistantExecutionState:
        if not data or not isinstance(data, dict):
            return default_execution_state()
        step = data.get("step", "idle")
        if step not in ("idle", "collecting", "disambiguating", "confirming", "executing"):
            step = "idle"
        pc_raw = data.get("pending_confirmation")
        pending = PendingConfirmation.from_dict(pc_raw) if isinstance(pc_raw, dict) else None
        if pending and not pending.action:
            pending = None
        lc_raw = data.get("last_completed_action")
        last = LastCompletedAction.from_dict(lc_raw) if isinstance(lc_raw, dict) else None
        if last and not last.action:
            last = None
        tid = data.get("turn_id") or str(uuid.uuid4())
        return cls(
            version=int(data.get("version", STATE_VERSION)),
            step=step,
            turn_id=str(tid),
            intent_plan=IntentPlan.from_dict(data.get("intent_plan")),
            disambiguation=DisambiguationState.from_dict(data.get("disambiguation")),
            pending_confirmation=pending,
            last_completed_action=last,
            updated_at=data.get("updated_at"),
        )


def default_execution_state() -> AssistantExecutionState:
    s = AssistantExecutionState()
    s.touch()
    return s


def intent_plan_item_from_parsed(parsed: ParsedIntent, ordinal: int) -> IntentPlanItem:
    return IntentPlanItem(
        ordinal=ordinal,
        intent=parsed.intent,
        entity_type=parsed.entity_type,
        query=parsed.query,
        entity_id=None,
        fields=dict(parsed.fields),
        datetime=dict(parsed.datetime),
        filters=dict(parsed.filters),
        meta=dict(parsed.meta),
        status="pending",
        block_reason=None,
    )


def suggested_parse_mode(state: AssistantExecutionState) -> ParseMode:
    if state.step == "idle" and not state.intent_plan.items:
        return "full"
    if state.step == "idle":
        return "full"
    return "continuation"


def merge_parser_result_into_state(
    state: AssistantExecutionState,
    result: ParsedIntentResult,
    *,
    clear_transient: bool = True,
) -> AssistantExecutionState:
    """
    Заменяет intent_plan результатом парсера. Опционально сбрасывает disambiguation и подтверждение.
    Поле step не меняет — выставляет оркестратор.
    """
    items = [intent_plan_item_from_parsed(p, i) for i, p in enumerate(result.items)]
    state.intent_plan = IntentPlan(items=items, active_item_index=0)
    if clear_transient:
        state.disambiguation = DisambiguationState()
        state.pending_confirmation = None
    state.touch()
    return state


def reset_scenario(state: AssistantExecutionState) -> AssistantExecutionState:
    state.step = "idle"
    state.intent_plan = IntentPlan()
    state.disambiguation = DisambiguationState()
    state.pending_confirmation = None
    state.turn_id = str(uuid.uuid4())
    state.touch()
    return state


def start_new_turn(state: AssistantExecutionState) -> AssistantExecutionState:
    state.turn_id = str(uuid.uuid4())
    state.touch()
    return state


def active_item(state: AssistantExecutionState) -> IntentPlanItem | None:
    plan = state.intent_plan
    if not plan.items:
        return None
    idx = plan.active_item_index
    if idx < 0 or idx >= len(plan.items):
        return None
    return plan.items[idx]


def set_step(state: AssistantExecutionState, step: Step) -> AssistantExecutionState:
    state.step = step
    state.touch()
    return state


def set_active_item_index(state: AssistantExecutionState, index: int) -> AssistantExecutionState:
    plan = state.intent_plan
    if not plan.items:
        return state
    state.intent_plan.active_item_index = max(0, min(index, len(plan.items) - 1))
    state.touch()
    return state


def set_disambiguation_candidates(
    state: AssistantExecutionState,
    candidates: list[dict[str, Any]],
) -> AssistantExecutionState:
    state.disambiguation = DisambiguationState(candidates=copy.deepcopy(candidates), resolution=None)
    state.touch()
    return state


def resolve_active_entity(
    state: AssistantExecutionState,
    entity_id: str,
    *,
    resolution_meta: dict[str, Any] | None = None,
) -> AssistantExecutionState:
    item = active_item(state)
    if item:
        item.entity_id = entity_id
    if resolution_meta is not None:
        state.disambiguation.resolution = copy.deepcopy(resolution_meta)
    state.touch()
    return state


def clear_disambiguation(state: AssistantExecutionState) -> AssistantExecutionState:
    state.disambiguation = DisambiguationState()
    state.touch()
    return state


def set_pending_confirmation(
    state: AssistantExecutionState,
    action: str,
    payload_summary: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> AssistantExecutionState:
    state.pending_confirmation = PendingConfirmation(
        action=action,
        payload_summary=copy.deepcopy(payload_summary or {}),
        idempotency_key=idempotency_key,
    )
    state.step = "confirming"
    state.touch()
    return state


def clear_pending_confirmation(state: AssistantExecutionState) -> AssistantExecutionState:
    state.pending_confirmation = None
    state.touch()
    return state


def mark_item_status(
    state: AssistantExecutionState,
    ordinal: int,
    status: ItemStatus,
    block_reason: str | None = None,
) -> AssistantExecutionState:
    for it in state.intent_plan.items:
        if it.ordinal == ordinal:
            it.status = status
            it.block_reason = block_reason
            break
    state.touch()
    return state


def advance_to_next_pending_item(state: AssistantExecutionState) -> AssistantExecutionState:
    plan = state.intent_plan
    for i, it in enumerate(plan.items):
        if it.status == "pending":
            plan.active_item_index = i
            state.touch()
            return state
    state.touch()
    return state


def record_last_completed(
    state: AssistantExecutionState,
    action: str,
    entity_id: str | None = None,
) -> AssistantExecutionState:
    state.last_completed_action = LastCompletedAction(
        action=action,
        entity_id=entity_id,
        at=timezone.now().isoformat(),
    )
    state.touch()
    return state


def build_prompt_context_summary(state: AssistantExecutionState) -> str:
    """
    Краткая выжимка для промпта LLM (на русском). Не включает сырые UUID без подписи.
    """
    lines: list[str] = []
    lines.append("Текущий контекст сценария (данные системы, не выдумывай):")
    lines.append(f"- step: {state.step}")
    lines.append(f"- turn_id: {state.turn_id}")

    item = active_item(state)
    if item:
        lines.append(
            f"- активный шаг плана: intent={item.intent}, entity_type={item.entity_type}, "
            f"query={item.query!r}, entity_id={item.entity_id!r}, status={item.status}"
        )
        if item.fields:
            lines.append(f"- fields: {item.fields}")
        if item.datetime:
            lines.append(f"- datetime: {item.datetime}")
        if item.filters:
            lines.append(f"- filters: {item.filters}")
        if item.block_reason:
            lines.append(f"- block_reason: {item.block_reason}")
    elif state.intent_plan.items:
        lines.append(f"- в плане {len(state.intent_plan.items)} шаг(ов), активный индекс: {state.intent_plan.active_item_index}")

    if state.disambiguation.candidates:
        lines.append("- кандидаты для выбора (пользователь видит нумерованный список):")
        for i, c in enumerate(state.disambiguation.candidates, start=1):
            label = c.get("title") or c.get("summary") or c.get("label") or str(c.get("id", i))
            extra = c.get("datetime") or c.get("start") or c.get("due_date")
            if extra:
                lines.append(f"  {i}) {label} — {extra}")
            else:
                lines.append(f"  {i}) {label}")

    if state.pending_confirmation:
        lines.append(
            f"- ожидается подтверждение действия: {state.pending_confirmation.action}; "
            f"кратко: {state.pending_confirmation.payload_summary}"
        )

    if state.last_completed_action and state.last_completed_action.action:
        lines.append(
            f"- последнее завершённое действие: {state.last_completed_action.action} "
            f"(entity_id={state.last_completed_action.entity_id!r})"
        )

    return "\n".join(lines)


class SessionStateStore:
    """Загрузка и сохранение execution state в AssistantSession."""

    @staticmethod
    def load(session) -> AssistantExecutionState:
        from assistant.models import AssistantSession

        if not isinstance(session, AssistantSession):
            raise TypeError("Expected AssistantSession")
        raw = getattr(session, "execution_state", None)
        if raw is None or raw == {}:
            return default_execution_state()
        if not isinstance(raw, dict):
            return default_execution_state()
        return AssistantExecutionState.from_dict(raw)

    @staticmethod
    def save(session, state: AssistantExecutionState) -> None:
        from assistant.models import AssistantSession

        if not isinstance(session, AssistantSession):
            raise TypeError("Expected AssistantSession")
        state.touch()
        session.execution_state = state.to_dict()
        session.save(update_fields=["execution_state"])
