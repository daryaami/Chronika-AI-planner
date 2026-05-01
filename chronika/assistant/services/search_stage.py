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

    @staticmethod
    def _candidate_display_label(c: SemanticSearchCandidate) -> str:
        """Человекочитаемая подпись варианта для assistant_hint в disambiguation."""
        payload = c.payload
        if c.entity_type == "event":
            title = (getattr(payload, "summary", None) or "").strip() or f"event #{c.object_id}"
            st = getattr(payload, "start", None)
            en = getattr(payload, "end", None)
            if st and en:
                return f"{title} ({st.isoformat()} — {en.isoformat()})"
            if st:
                return f"{title} (с {st.isoformat()})"
            return title
        title = (getattr(payload, "title", None) or "").strip() or f"task #{c.object_id}"
        due = getattr(payload, "due_date", None)
        if due:
            return f"{title} (due {due.isoformat()})"
        return title

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
                0.8 if action_code in {"plan", "reschedule"} and entity_type != "event" else 0.7
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
                one = candidates[0]
                cid = one.object_id
                enriched_data = self._enrich_action_data_from_candidate(
                    action.data,
                    one,
                    action_code=action_code,
                )
                working.actions[idx] = Action(
                    context_id=action.context_id,
                    type=action.type,
                    target_id=cid,
                    data=enriched_data,
                )
                self._enrich_entity_preview(working.entities, idx, one)
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
                titles.append(self._candidate_display_label(c))
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
    def _enrich_action_data_from_candidate(
        action_data: dict[str, Any],
        c: SemanticSearchCandidate,
        *,
        action_code: str,
    ) -> dict[str, Any]:
        """
        Добавляет в шаг человекочитаемые поля найденного объекта для UI/подтверждения.
        Не перетирает уже заданные пользователем поля.
        """
        data = dict(action_data) if isinstance(action_data, dict) else {}
        fields = dict(data.get("fields") or {})
        dt = dict(data.get("datetime") or {})
        payload = c.payload

        if c.entity_type == "event":
            summary = (getattr(payload, "summary", None) or "").strip()
            if summary and fields.get("summary") in (None, ""):
                fields["summary"] = summary
            start = getattr(payload, "start", None)
            end = getattr(payload, "end", None)
            # Для delete не подмешиваем слоты в шаг (иначе UI выглядит как «редактирование времени»).
            if action_code in {"plan", "reschedule", "update", "retrieve"}:
                if dt.get("start_at") in (None, "") and start is not None:
                    dt["start_at"] = start.isoformat()
                if dt.get("end_at") in (None, "") and end is not None:
                    dt["end_at"] = end.isoformat()
        elif c.entity_type == "task":
            title = (getattr(payload, "title", None) or "").strip()
            if title and fields.get("title") in (None, ""):
                fields["title"] = title
            priority = getattr(payload, "priority", None)
            if priority is not None and fields.get("priority") in (None, ""):
                fields["priority"] = priority
            category_id = getattr(payload, "category_id", None)
            if category_id is not None and fields.get("category_id") in (None, ""):
                fields["category_id"] = category_id
            due = getattr(payload, "due_date", None)
            if dt.get("date") in (None, "") and due is not None:
                dt["date"] = due.isoformat()

        data["fields"] = fields
        data["datetime"] = dt
        return data

    @staticmethod
    def _enrich_entity_preview(entities: list[Any], idx: int, c: SemanticSearchCandidate) -> None:
        """Обновляет title/meta сущности в Action Plan для корректного отображения в UI."""
        if idx >= len(entities) or not isinstance(entities[idx], dict):
            return
        ent = dict(entities[idx])
        payload = c.payload
        if c.entity_type == "event":
            summary = (getattr(payload, "summary", None) or "").strip()
            if summary:
                ent["title"] = summary
            st = getattr(payload, "start", None)
            en = getattr(payload, "end", None)
            meta = dict(ent.get("meta") or {})
            dt_meta = dict(meta.get("datetime") or {})
            if st is not None:
                dt_meta["start_at"] = st.isoformat()
            if en is not None:
                dt_meta["end_at"] = en.isoformat()
            if dt_meta:
                meta["datetime"] = dt_meta
                ent["meta"] = meta
        elif c.entity_type == "task":
            title = (getattr(payload, "title", None) or "").strip()
            if title:
                ent["title"] = title
        entities[idx] = ent

    @staticmethod
    def _needs_resolution(action: Action) -> bool:
        if action.target_id is not None:
            return False
        code = _step_action_code(action)
        return code in {"plan", "reschedule", "update", "delete", "retrieve"}


def _step_action_code(action: Action) -> str:
    return normalize_action_code(str(action.data.get("action") or ""))


def _resolve_search_scope(*, action_code: str, entity_type: Any) -> str:
    if action_code in {"reschedule", "plan"}:
        if entity_type == "event":
            return "events"
        if entity_type == "task":
            return "tasks"
        return "all"
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
