from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from assistant.domain.action_plan import Action, ActionPlan
from assistant.fsm.states import DialogState
from assistant.integrations.embeddings_model import EmbeddingsModelProvider
from assistant.services.intent_parser import normalize_action_code
from assistant.services.semantic_search import SemanticSearchCandidate, SemanticSearchService


@dataclass(frozen=True)
class SearchStageResult:
    plan: ActionPlan
    next_state: DialogState
    assistant_hint: str
    disambiguation_options: tuple[dict[str, Any], ...] = ()


class SearchStageService:
    """
    Разрешение target_id для действий с query (только вне Reply Interpreter).
    """

    def __init__(self, semantic_search: SemanticSearchService | None = None):
        self.semantic_search = semantic_search or SemanticSearchService()

    @staticmethod
    def _disambiguation_option(entity_ctx: str, i: int, c: SemanticSearchCandidate) -> dict[str, Any]:
        """Поля для UI: имя и (для события) время начала/конца — из ORM-объекта кандидата."""
        payload = c.payload
        row: dict[str, Any] = {
            "index": i,
            "entity_type": c.entity_type,
            "object_id": c.object_id,
            "similarity": c.similarity,
            "context_id": f"{entity_ctx}_c{i}",
        }
        if c.entity_type == "event":
            title = (getattr(payload, "summary", None) or "").strip()
            row["title"] = title or f"event #{c.object_id}"
            st = getattr(payload, "start", None)
            en = getattr(payload, "end", None)
            row["start"] = st.isoformat() if st else None
            row["end"] = en.isoformat() if en else None
        else:
            title = (getattr(payload, "title", None) or "").strip()
            row["title"] = title or f"task #{c.object_id}"
            due = getattr(payload, "due_date", None)
            row["due_date"] = due.isoformat() if due else None
        return row

    def resolve_targets_in_plan(self, *, user, plan: ActionPlan) -> SearchStageResult:
        if not plan.actions:
            return SearchStageResult(
                plan=plan,
                next_state=DialogState.WAITING_CLARIFICATION,
                assistant_hint="Не удалось сформировать план действий.",
            )

        working = ActionPlan(
            actions=[self._copy_action(a) for a in plan.actions],
            entities=list(plan.entities),
        )

        for idx, action in enumerate(working.actions):
            if not self._needs_resolution(action):
                continue

            query = action.data.get("query")
            if not isinstance(query, dict) or len(query) == 0:
                return SearchStageResult(
                    plan=working,
                    next_state=DialogState.WAITING_CLARIFICATION,
                    assistant_hint="Нужно уточнение: по какой именно задаче или событию?",
                )

            action_code = _step_action_code(action)
            embedding_text = _text_for_embedding(query=query)
            if not embedding_text:
                return SearchStageResult(
                    plan=working,
                    next_state=DialogState.WAITING_CLARIFICATION,
                    assistant_hint="Недостаточно данных для поиска объекта.",
                )

            embedding_vector = EmbeddingsModelProvider.encode(embedding_text)
            if embedding_vector is None or len(embedding_vector) == 0:
                return SearchStageResult(
                    plan=working,
                    next_state=DialogState.WAITING_CLARIFICATION,
                    assistant_hint="Поиск временно недоступен.",
                )

            entity_type = action.data.get("entity_type")
            scope = _resolve_search_scope(
                action_code=action_code,
                entity_type=entity_type,
            )
            threshold = (
                0.8 if action_code == "schedule" and entity_type != "event" else 0.7
            )
            candidates = self.semantic_search.find_candidates(
                user=user,
                embedding=embedding_vector,
                similarity_threshold=threshold,
                limit=3,
                scope=scope,
                query=query,
            )

            if len(candidates) == 0:
                return SearchStageResult(
                    plan=working,
                    next_state=DialogState.WAITING_CLARIFICATION,
                    assistant_hint="Не нашла подходящий объект. Уточните название или детали.",
                )
            if len(candidates) == 1:
                cid = candidates[0].object_id
                working.actions[idx] = Action(
                    context_id=action.context_id,
                    type=action.type,
                    target_id=cid,
                    data=dict(action.data),
                )
                continue

            entity_ctx = (
                working.entities[idx].context_id
                if idx < len(working.entities)
                else f"e{idx}"
            )
            options_list: list[dict[str, Any]] = []
            titles: list[str] = []
            for i, c in enumerate(candidates):
                opt = SearchStageService._disambiguation_option(entity_ctx, i, c)
                options_list.append(opt)
                titles.append(str(opt.get("title") or f"{c.entity_type} #{c.object_id}"))
            options = tuple(options_list)

            hint = "Несколько совпадений: " + "; ".join(
                f"{i + 1}) {titles[i]}" for i in range(len(titles))
            )
            return SearchStageResult(
                plan=working,
                next_state=DialogState.DISAMBIGUATION,
                assistant_hint=hint,
                disambiguation_options=options,
            )

        return SearchStageResult(
            plan=working,
            next_state=DialogState.WAITING_CONFIRMATION,
            assistant_hint="Подтвердите, пожалуйста, или скорректируйте детали.",
        )

    @staticmethod
    def _copy_action(action: Action) -> Action:
        return Action(
            context_id=action.context_id,
            type=action.type,
            target_id=action.target_id,
            data=dict(action.data),
        )

    @staticmethod
    def _needs_resolution(action: Action) -> bool:
        if action.target_id is not None:
            return False
        code = _step_action_code(action)
        return code in {"schedule", "update", "delete", "retrieve"}


def _step_action_code(action: Action) -> str:
    return normalize_action_code(str(action.data.get("action") or ""))


def _resolve_search_scope(*, action_code: str, entity_type: Any) -> str:
    if action_code == "schedule":
        if entity_type == "event":
            return "events"
        return "tasks"
    if entity_type == "task":
        return "tasks"
    if entity_type == "event":
        return "events"
    return "all"


def _text_for_embedding(*, query: dict[str, Any] | None) -> str:
    if not query:
        return ""
    parts: list[str] = []
    for key in ("title", "summary", "description", "notes"):
        value = query.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            parts.append(text)
    return " ".join(parts)
