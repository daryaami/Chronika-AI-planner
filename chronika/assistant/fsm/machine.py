from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from assistant.domain.action_plan import ActionPlan, action_plan_to_dict
from assistant.domain.context import StructuredContext
from assistant.domain.dialog import DialogIntent, ReplyInterpretation
from assistant.fsm.states import DialogState
from assistant.pipeline_log import interpretation_to_dict, pretty_data, pretty_json_text, trace
from assistant.services.action_plan_adapter import parsed_intents_to_action_plan
from assistant.services.intent_parser import IntentParserService
from assistant.services.plan_executor import PlanExecutorService
from assistant.services.plan_merge import PlanMergeService
from assistant.services.reply_interpreter import ReplyInterpreterInput, ReplyInterpreterService
from assistant.services.scheduler_service import SchedulerService
from assistant.services.search_stage import SearchStageService


@dataclass
class DialogSessionSnapshot:
    state: DialogState
    plan: ActionPlan | None
    context: StructuredContext
    last_referenced_id: int | None = None


@dataclass(frozen=True)
class FsmTurnResult:
    snapshot: DialogSessionSnapshot
    assistant_reply: str
    pending_followup_message: str | None = None
    execution_artifact: dict | None = None


class FsmMachine:
    """
    Управляющий слой: idle → Intent Parser + Search stage; иначе Reply Interpreter + merge/execute.
    Исключение: не-idle, но план без шагов — снова idle и Intent Parser (реплика как новая команда).
    """

    def __init__(
        self,
        intent_parser: IntentParserService | None = None,
        reply_interpreter: ReplyInterpreterService | None = None,
        plan_merge: PlanMergeService | None = None,
        search_stage: SearchStageService | None = None,
        executor: PlanExecutorService | None = None,
        scheduler: SchedulerService | None = None,
    ):
        self.intent_parser = intent_parser or IntentParserService()
        self.reply_interpreter = reply_interpreter or ReplyInterpreterService()
        self.plan_merge = plan_merge or PlanMergeService()
        self.search_stage = search_stage or SearchStageService()
        self.executor = executor or PlanExecutorService()
        self.scheduler = scheduler or SchedulerService()

    def run_turn(
        self,
        *,
        user,
        user_message: str,
        snapshot: DialogSessionSnapshot,
        forced_interpretation: ReplyInterpretation | None = None,
    ) -> FsmTurnResult:
        if snapshot.state == DialogState.IDLE:
            out = self._handle_idle(user=user, user_message=user_message, snapshot=snapshot)
        else:
            out = self._handle_dialog(
                user=user,
                user_message=user_message,
                snapshot=snapshot,
                forced_interpretation=forced_interpretation,
            )
        return out

    def _handle_idle(self, *, user, user_message: str, snapshot: DialogSessionSnapshot) -> FsmTurnResult:
        parsed = self.intent_parser.parse(user_message)
        plan = parsed_intents_to_action_plan(parsed.items)
        plan_after_adapter = action_plan_to_dict(plan)
        search = self.search_stage.resolve_targets_in_plan(user=user, plan=plan)
        sched_plan = search.plan
        sched_hint: str | None = None
        if search.next_state == DialogState.WAITING_CONFIRMATION:
            sched_plan, sched_hint = self.scheduler.apply_to_plan(user, search.plan)
        plan_after_search = action_plan_to_dict(sched_plan)
        trace(
            "FSM (IDLE): ответ IntentParser → нормализация → Action Plan",
            сырой_json_от_llm=pretty_json_text(parsed.raw_response),
            нормализованные_intents=pretty_data([asdict(x) for x in parsed.items]),
            action_plan_после_адаптера=pretty_data(plan_after_adapter),
            action_plan_после_search_stage=pretty_data(plan_after_search),
            следующее_состояние_fsm=search.next_state.value,
            подсказка_ассистента=pretty_data({"text": search.assistant_hint or ""}),
            подсказка_планировщика=pretty_data({"text": sched_hint or ""}),
        )

        ctx = snapshot.context
        if search.next_state == DialogState.DISAMBIGUATION:
            ctx = replace(ctx, disambiguation_options=list(search.disambiguation_options))
        else:
            ctx = replace(ctx, disambiguation_options=[])

        new_snapshot = DialogSessionSnapshot(
            state=search.next_state,
            plan=sched_plan,
            context=self._sync_last_interaction(ctx, sched_plan),
            last_referenced_id=self._primary_target_id(sched_plan) or snapshot.last_referenced_id,
        )

        reply_parts = [search.assistant_hint or ""]
        if sched_hint:
            reply_parts.append(sched_hint)
        assistant_reply = " ".join(p for p in reply_parts if p).strip()

        return FsmTurnResult(
            snapshot=new_snapshot,
            assistant_reply=assistant_reply,
        )

    def _handle_dialog(
        self,
        *,
        user,
        user_message: str,
        snapshot: DialogSessionSnapshot,
        forced_interpretation: ReplyInterpretation | None = None,
    ) -> FsmTurnResult:
        if snapshot.plan is None:
            idle_snap = replace(snapshot, state=DialogState.IDLE, plan=None)
            return self._handle_idle(user=user, user_message=user_message, snapshot=idle_snap)

        plan = snapshot.plan
        # Пустой план при waiting_clarification и т.п. (часто после «не удалось сформировать план»):
        # шагов нечего уточнять через Reply Interpreter — следующая реплика = новая команда с нуля.
        if forced_interpretation is None and not plan.actions:
            idle_snap = replace(
                snapshot,
                state=DialogState.IDLE,
                plan=None,
                context=replace(snapshot.context, disambiguation_options=[]),
            )
            trace(
                "FSM (диалог): в плане нет шагов — idle и Intent Parser (как новое сообщение)",
                предыдущее_состояние=snapshot.state.value,
            )
            return self._handle_idle(user=user, user_message=user_message, snapshot=idle_snap)

        if forced_interpretation is not None:
            interpretation = forced_interpretation
            trace(
                "FSM (диалог): интерпретация с UI (без LLM Reply Interpreter)",
                интерпретация=pretty_data(interpretation_to_dict(interpretation)),
            )
        else:
            interpretation = self.reply_interpreter.interpret(
                ReplyInterpreterInput(
                    state=snapshot.state.value,
                    current_plan=action_plan_to_dict(plan),
                    entities_in_context=[asdict(e) for e in plan.entities],
                    disambiguation_options=list(snapshot.context.disambiguation_options),
                    last_referenced_id=snapshot.last_referenced_id,
                    user_message=user_message,
                )
            )

        if interpretation.dialog_intent == DialogIntent.CANCEL:
            return FsmTurnResult(
                snapshot=self._clear_session(snapshot),
                assistant_reply="Сценарий отменён.",
            )

        if interpretation.dialog_intent == DialogIntent.REJECT:
            return FsmTurnResult(
                snapshot=self._clear_session(snapshot),
                assistant_reply="Хорошо, не выполняю.",
            )

        if interpretation.dialog_intent == DialogIntent.NEW_REQUEST:
            follow = (
                interpretation.new_intent_candidate.raw.strip()
                if interpretation.new_intent_candidate
                else ""
            )
            if not follow:
                follow = user_message.strip()
            cleared = self._clear_session(snapshot)
            return FsmTurnResult(
                snapshot=cleared,
                assistant_reply="",
                pending_followup_message=follow or None,
            )

        if (
            interpretation.dialog_intent == DialogIntent.SELECT
            and snapshot.state == DialogState.DISAMBIGUATION
            and interpretation.target_ids
        ):
            merged = self.plan_merge.apply_reply(plan, interpretation)
            trace(
                "FSM: Action Plan после merge (ветка SELECT / disambiguation)",
                action_plan=pretty_data(action_plan_to_dict(merged)),
            )
            sched_merged, sched_hint = self.scheduler.apply_to_plan(user, merged)
            trace(
                "FSM: Action Plan после Scheduler (SELECT)",
                action_plan=pretty_data(action_plan_to_dict(sched_merged)),
                подсказка_планировщика=pretty_data({"text": sched_hint or ""}),
            )
            ctx = replace(snapshot.context, disambiguation_options=[])
            new_snapshot = DialogSessionSnapshot(
                state=DialogState.WAITING_CONFIRMATION,
                plan=sched_merged,
                context=self._sync_last_interaction(ctx, sched_merged),
                last_referenced_id=interpretation.target_ids[0],
            )
            reply_parts = ["Выбор зафиксирован. Подтвердите выполнение."]
            if sched_hint:
                reply_parts.append(sched_hint)
            return FsmTurnResult(
                snapshot=new_snapshot,
                assistant_reply=" ".join(reply_parts).strip(),
            )

        if interpretation.dialog_intent == DialogIntent.CONFIRM:
            merged = self.plan_merge.apply_reply(plan, interpretation)
            trace(
                "FSM: Action Plan после merge (ветка CONFIRM, перед выполнением)",
                action_plan=pretty_data(action_plan_to_dict(merged)),
            )
            artifact = self.executor.execute(user_id=user.id, plan=merged)
            trace(
                "FSM: результат PlanExecutor.execute",
                execution_artifact=pretty_data(artifact),
            )
            ctx = self._sync_last_interaction(
                replace(snapshot.context, disambiguation_options=[]),
                merged,
            )
            pending = (
                interpretation.new_intent_candidate.raw
                if interpretation.new_intent_candidate
                else None
            )
            cleared = DialogSessionSnapshot(
                state=DialogState.IDLE,
                plan=None,
                context=ctx,
                last_referenced_id=snapshot.last_referenced_id,
            )
            return FsmTurnResult(
                snapshot=cleared,
                assistant_reply="Готово.",
                pending_followup_message=(pending.strip() if pending else None),
                execution_artifact=artifact,
            )

        if interpretation.dialog_intent == DialogIntent.MODIFY and (
            interpretation.actions or interpretation.step_patches
        ):
            merged = self.plan_merge.apply_reply(plan, interpretation)
            trace(
                "FSM: Action Plan после merge (ветка MODIFY)",
                action_plan=pretty_data(action_plan_to_dict(merged)),
            )
            sched_merged, sched_hint = self.scheduler.apply_to_plan(user, merged)
            trace(
                "FSM: Action Plan после Scheduler (MODIFY)",
                action_plan=pretty_data(action_plan_to_dict(sched_merged)),
                подсказка_планировщика=pretty_data({"text": sched_hint or ""}),
            )
            new_snapshot = DialogSessionSnapshot(
                state=DialogState.WAITING_CONFIRMATION,
                plan=sched_merged,
                context=self._sync_last_interaction(snapshot.context, sched_merged),
                last_referenced_id=snapshot.last_referenced_id,
            )
            reply_parts = ["План обновлён. Подтвердите выполнение."]
            if sched_hint:
                reply_parts.append(sched_hint)
            return FsmTurnResult(
                snapshot=new_snapshot,
                assistant_reply=" ".join(reply_parts).strip(),
            )

        return FsmTurnResult(
            snapshot=snapshot,
            assistant_reply="Нужно уточнение: переформулируйте или ответьте на вопрос выше.",
        )

    @staticmethod
    def _primary_target_id(plan: ActionPlan | None) -> int | None:
        if not plan:
            return None
        for action in plan.actions:
            if action.target_id is not None:
                return int(action.target_id)
        return None

    @staticmethod
    def _sync_last_interaction(ctx: StructuredContext, plan: ActionPlan | None) -> StructuredContext:
        if not plan:
            return ctx
        li = ctx.last_interaction
        li.last_entities = [asdict(e) for e in plan.entities]
        li.last_actions = [asdict(a) for a in plan.actions]
        li.last_target_ids = [int(a.target_id) for a in plan.actions if a.target_id is not None]
        return ctx

    @staticmethod
    def _clear_session(snapshot: DialogSessionSnapshot) -> DialogSessionSnapshot:
        ctx = replace(snapshot.context, disambiguation_options=[])
        return DialogSessionSnapshot(
            state=DialogState.IDLE,
            plan=None,
            context=ctx,
            last_referenced_id=snapshot.last_referenced_id,
        )
