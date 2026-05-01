from __future__ import annotations

from assistant.domain.action_plan import Action, ActionPlan, coerce_action_type
from assistant.domain.dialog import DialogIntent, ReplyInterpretation


class PlanMergeService:
    """
    Слияние ответа Reply Interpreter с текущим Action Plan (patch до confirm / execute).
    """

    def apply_reply(self, plan: ActionPlan, interpretation: ReplyInterpretation) -> ActionPlan:
        intent = interpretation.dialog_intent

        if intent in (DialogIntent.CANCEL, DialogIntent.REJECT):
            return ActionPlan(actions=[], entities=[])

        if intent == DialogIntent.NEW_REQUEST:
            return plan

        if intent == DialogIntent.SELECT and interpretation.target_ids:
            return self._apply_select(plan, interpretation.target_ids)

        if intent in (DialogIntent.MODIFY, DialogIntent.CONFIRM):
            out = plan
            if interpretation.step_patches:
                out = self._apply_step_patches(out, interpretation.step_patches)
            if interpretation.actions:
                out = self._append_patch_actions(out, interpretation.actions)
            return out

        return plan

    def _apply_step_patches(self, plan: ActionPlan, patches: list[dict]) -> ActionPlan:
        merge_keys = ("fields", "query", "datetime", "filters", "meta")
        new_actions: list[Action] = []
        for idx, action in enumerate(plan.actions):
            data = dict(action.data)
            for p in patches:
                if not isinstance(p, dict):
                    continue
                if int(p.get("index", -1)) != idx:
                    continue
                merge = p.get("merge")
                if not isinstance(merge, dict):
                    continue
                for key in merge_keys:
                    if key not in merge or merge[key] is None:
                        continue
                    delta = merge[key]
                    if not isinstance(delta, dict):
                        continue
                    base = dict(data.get(key) or {})
                    base.update(delta)
                    data[key] = base
            new_actions.append(
                Action(
                    context_id=action.context_id,
                    type=action.type,
                    target_id=action.target_id,
                    data=data,
                )
            )
        return ActionPlan(actions=new_actions, entities=list(plan.entities))

    def _apply_select(self, plan: ActionPlan, target_ids: list[int]) -> ActionPlan:
        out_actions: list[Action] = []
        tid_iter = iter(target_ids)
        for action in plan.actions:
            if action.target_id is None:
                try:
                    nid = next(tid_iter)
                except StopIteration:
                    out_actions.append(action)
                    continue
                out_actions.append(
                    Action(
                        context_id=action.context_id,
                        type=action.type,
                        target_id=nid,
                        data=dict(action.data),
                    )
                )
            else:
                out_actions.append(action)
        return ActionPlan(actions=out_actions, entities=list(plan.entities))

    def _append_patch_actions(self, plan: ActionPlan, patch: list[dict]) -> ActionPlan:
        new_actions = list(plan.actions)
        for raw in patch:
            if not isinstance(raw, dict):
                continue
            tid = raw.get("target_id")
            tid_int: int | None
            if tid is None:
                tid_int = None
            else:
                try:
                    tid_int = int(tid)
                except (TypeError, ValueError):
                    tid_int = None
            new_actions.append(
                Action(
                    context_id=str(raw.get("context_id") or f"a_patch_{len(new_actions)}"),
                    type=coerce_action_type(raw.get("type")),
                    target_id=tid_int,
                    data=dict(raw.get("data") or {}),
                )
            )
        return ActionPlan(actions=new_actions, entities=list(plan.entities))
