from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from typing import Any

from assistant.prompts.orchestrator_prompts import get_prompt_template
from assistant.prompts.tool_schemas import get_orchestrator_tool_schemas

from .llm_context_sanitize import sanitize_for_llm
from .pending_store import PendingStore
from .datetime_context import DateTimeContext
from .orchestration_policy import OrchestrationPolicy
from .tool_router import ToolRouter


class Orchestrator:
    _READ_ONLY_TOOLS = {"search_entities", "get_calendar", "find_slots"}
    _FOLLOWUP_ELIGIBLE_TOOLS = {"search_entities", "get_calendar", "find_slots"}
    _MAX_TOOL_FOLLOWUP_STEPS = 3
    _FSM_RECEIVE_INPUT = "RECEIVE_INPUT"
    _FSM_PLAN_TOOL_CALLS = "PLAN_TOOL_CALLS"
    _FSM_EXECUTE_TOOLS = "EXECUTE_TOOLS"
    _FSM_COMPOSE_REPLY = "COMPOSE_REPLY"
    _FSM_DONE = "DONE"
    _FSM_FAILED = "FAILED"

    def __init__(self, *, llm_client, tool_router: ToolRouter, pending_store: PendingStore):
        self.llm = llm_client
        self.tool_router = tool_router
        self.pending_store = pending_store
        self.time_parser = DateTimeContext()
        self.policy = OrchestrationPolicy(
            pending_store=pending_store,
            tool_router=tool_router,
            datetime_context=self.time_parser,
        )
        self.orchestrator_prompt = get_prompt_template("orchestrator_fc")
        self.user_reply_prompt = get_prompt_template("user_reply_system")

    def handle_message(self, user_text: str, *, dialog_context: dict[str, Any] | None = None) -> dict[str, Any]:
        fsm_state = self._FSM_RECEIVE_INPUT
        fsm_trace = [fsm_state]
        pending = self.pending_store.active_items()
        pending_context = [item.to_dict() for item in pending]
        dialog_context_data = dict(dialog_context or {})
        self._remember_turn_context(dialog_context_data, user_text)
        self._append_history_entry(dialog_context_data, role="user", content=user_text)
        conversation_history = list(dialog_context_data.get("conversation_history") or [])
        user_tz = str(dialog_context_data.get("user_tz") or "UTC")
        runtime_context = {
            "user_tz": user_tz,
            "now_iso": self.time_parser.now_iso(user_tz),
        }
        fsm_state = self._FSM_PLAN_TOOL_CALLS
        fsm_trace.append(fsm_state)
        llm_response = self.llm.chat_with_tools(
            messages=[
                {"role": "system", "content": self.orchestrator_prompt.content},
                {
                    "role": "user",
                    "content": json.dumps(
                        sanitize_for_llm(
                            {
                                "user_text": user_text,
                                "pending_context": copy.deepcopy(pending_context),
                                "dialog_context": copy.deepcopy(dialog_context_data),
                                "conversation_history": copy.deepcopy(conversation_history),
                                "runtime_context": runtime_context,
                            }
                        ),
                        ensure_ascii=False,
                    ),
                },
            ],
            tools=get_orchestrator_tool_schemas(),
            fallback={"content": "", "tool_calls": []},
            temperature=0.1,
        )
        planner_messages: list[str] = []
        first_planner_content = str(llm_response.get("content") or "").strip()
        if first_planner_content:
            planner_messages.append(first_planner_content)
        calls = self._parse_tool_calls(llm_response)
        action_plan_calls = self._build_action_plan_followup_calls(
            dialog_context=dialog_context_data,
            user_text=user_text,
            has_active_pending=bool(pending_context),
        )
        if action_plan_calls:
            calls = action_plan_calls
        results: list[dict[str, Any]] = []
        created_pending = None
        followup_step = 0
        seen_call_fingerprints: set[str] = set()
        fsm_state = self._FSM_EXECUTE_TOOLS
        fsm_trace.append(fsm_state)
        while calls:
            fingerprint = self._calls_fingerprint(calls)
            if fingerprint in seen_call_fingerprints:
                break
            seen_call_fingerprints.add(fingerprint)
            exec_out = self._execute_calls(
                calls=calls,
                user_text=user_text,
                user_tz=user_tz,
                dialog_context=dialog_context_data,
            )
            results.extend(exec_out["results"])
            created_pending = exec_out["created_pending"] or created_pending
            if not self._should_attempt_followup(
                calls=calls,
                exec_out=exec_out,
                followup_step=followup_step,
            ):
                break
            followup_step += 1
            next_llm = self.llm.chat_with_tools(
                messages=[
                    {"role": "system", "content": self.orchestrator_prompt.content},
                    {
                        "role": "user",
                        "content": json.dumps(
                            sanitize_for_llm(
                                {
                                    "user_text": user_text,
                                    "dialog_context": copy.deepcopy(dialog_context_data),
                                    "conversation_history": copy.deepcopy(conversation_history),
                                    "runtime_context": runtime_context,
                                    "iteration": followup_step,
                                    "previous_results": copy.deepcopy(results),
                                }
                            ),
                            ensure_ascii=False,
                        ),
                    },
                ],
                tools=get_orchestrator_tool_schemas(),
                fallback={"content": "", "tool_calls": []},
                temperature=0.1,
            )
            next_planner_content = str(next_llm.get("content") or "").strip()
            if next_planner_content:
                planner_messages.append(next_planner_content)
            calls = self._parse_tool_calls(next_llm)
        self._sync_action_plan_state(dialog_context=dialog_context_data, results=results)
        self._remember_resolution_entities(dialog_context=dialog_context_data, results=results)
        status = "success"
        if any(item.get("status") == "failed" for item in results):
            status = "failed"
        elif created_pending and created_pending.status == "needs_disambiguation":
            status = "needs_disambiguation"
        elif created_pending:
            status = "awaiting_confirmation"
        fsm_state = self._FSM_COMPOSE_REPLY
        fsm_trace.append(fsm_state)
        fallback = self._fallback_reply(status, created_pending)
        pending_action_dict = created_pending.to_dict() if created_pending else None
        llm_results = sanitize_for_llm(
            self.time_parser.normalize_action(copy.deepcopy(results), user_tz=user_tz)
        )
        llm_pending_action = sanitize_for_llm(
            self.time_parser.normalize_action(copy.deepcopy(pending_action_dict), user_tz=user_tz)
        )
        llm_conversation_context = sanitize_for_llm(
            self.time_parser.normalize_action(
                {
                    "last_entity": dialog_context_data.get("last_entity"),
                    "previous_user_text": dialog_context_data.get("previous_user_text"),
                    "last_user_text": dialog_context_data.get("last_user_text"),
                },
                user_tz=user_tz,
            )
        )
        llm_results_local_time = self._local_time_view(llm_results)
        llm_pending_action_local_time = self._local_time_view(llm_pending_action)
        llm_conversation_context_local_time = self._local_time_view(llm_conversation_context)
        user_message = self.llm.chat_text(
            system_prompt=self.user_reply_prompt.content,
            user_prompt=json.dumps(
                sanitize_for_llm(
                    {
                        "user_text": user_text,
                        "conversation_history": copy.deepcopy(conversation_history),
                        "status": status,
                        "results": llm_results,
                        "results_local_time": llm_results_local_time,
                        "pending_action": llm_pending_action,
                        "pending_action_local_time": llm_pending_action_local_time,
                        "planner_handoff_message": self._planner_handoff_message(planner_messages),
                        "orchestration_summary": self._build_orchestration_summary(
                            status=status,
                            results=llm_results,
                            pending_action=llm_pending_action,
                            fsm_trace=fsm_trace,
                        ),
                        "conversation_context": llm_conversation_context,
                        "conversation_context_local_time": llm_conversation_context_local_time,
                        "runtime_context": runtime_context,
                    }
                ),
                ensure_ascii=False,
            ),
            fallback=fallback,
            temperature=0.1,
        )
        self._append_history_entry(dialog_context_data, role="assistant", content=user_message or fallback)
        return {
            "state": status,
            "status": status,
            "results": results,
            "pending_action": created_pending.to_dict() if created_pending else None,
            "user_message": user_message or fallback,
            "dialog_context": dialog_context_data,
            "meta": self._response_meta(
                fsm_state=self._FSM_DONE if status != "failed" else self._FSM_FAILED,
                fsm_trace=fsm_trace + [self._FSM_DONE if status != "failed" else self._FSM_FAILED],
            ),
        }

    def _execute_calls(
        self,
        *,
        calls: list[dict[str, Any]],
        user_text: str,
        user_tz: str,
        dialog_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        created_pending = None
        any_failed = False
        any_pending = False
        executed_tools: list[str] = []
        mutation_calls = [call for call in calls if self.policy.is_mutation_tool(str(call.get("name") or ""))]
        batch_find_slots: list[dict[str, Any]] = []

        for idx, call in enumerate(calls):
            tool_name = call["name"]
            args = call["arguments"]
            if tool_name in {"confirm_action", "cancel_action", "modify_action"}:
                control_result = self._handle_pending_control(tool_name, args)
                results.append(
                    {
                        "action_id": f"a_{idx+1}",
                        "tool_name": tool_name,
                        "resolved_payload": dict(args or {}),
                        **control_result,
                    }
                )
                if control_result.get("status") == "pending":
                    any_pending = True
                    pending_items = self.pending_store.active_items()
                    created_pending = pending_items[-1] if pending_items else created_pending
                if control_result.get("status") == "failed":
                    any_failed = True
                continue

            normalized = self.policy.normalize_tool_payload(tool_name, args, user_tz=user_tz)
            if not normalized.get("ok"):
                any_failed = True
                results.append(
                    {
                        "action_id": f"a_{idx+1}",
                        "tool_name": tool_name,
                        "status": "failed",
                        "data": None,
                        "error": {"code": "invalid_payload", "message": normalized.get("message"), "recoverable": True},
                    }
                )
                continue

            effective_tool = str(normalized.get("tool_name") or tool_name)
            effective_payload = dict(normalized.get("payload") or {})
            resolved = self.policy.resolve_target_for_tool(
                effective_tool,
                effective_payload,
                user_text=user_text,
            )
            if resolved.get("status") == "failed":
                any_failed = True
                results.append(
                    {
                        "action_id": f"a_{idx+1}",
                        "tool_name": effective_tool,
                        "resolved_payload": effective_payload,
                        "status": "failed",
                        "data": None,
                        "error": {"code": "target_resolution_failed", "message": resolved.get("message"), "recoverable": True},
                    }
                )
                continue
            if resolved.get("status") == "needs_disambiguation":
                any_pending = True
                created_pending = self.pending_store.create(
                    effective_tool,
                    {"tool_name": effective_tool, "tool_payload": effective_payload},
                    status="needs_disambiguation",
                    disambiguation_candidates=list(resolved.get("candidates") or []),
                )
                results.append(
                    {
                        "action_id": f"a_{idx+1}",
                        "tool_name": effective_tool,
                        "resolved_payload": effective_payload,
                        "status": "needs_disambiguation",
                        "data": {"candidates": resolved.get("candidates"), "pending_action_id": created_pending.id},
                        "error": None,
                    }
                )
                continue

            if self.policy.needs_confirmation(effective_tool, total_mutations=len(mutation_calls)):
                any_pending = True
                created_pending = self.pending_store.create(
                    effective_tool,
                    {"tool_name": effective_tool, "tool_payload": effective_payload},
                    status="awaiting_confirmation",
                )
                results.append(
                    {
                        "action_id": f"a_{idx+1}",
                        "tool_name": effective_tool,
                        "resolved_payload": effective_payload,
                        "status": "pending",
                        "data": {"pending_action_id": created_pending.id},
                        "error": None,
                    }
                )
                continue

            out = self.tool_router.execute(effective_tool, effective_payload)
            if not out.get("ok"):
                any_failed = True
                results.append(
                    {
                        "action_id": f"a_{idx+1}",
                        "tool_name": effective_tool,
                        "resolved_payload": effective_payload,
                        "status": "failed",
                        "data": None,
                        "error": out.get("error"),
                    }
                )
                continue

            executed_tools.append(effective_tool)
            data = out.get("data") or {}
            if isinstance(data, dict):
                data = {**data, "mutation_tool": effective_tool}
            if effective_tool == "find_slots" and not list(data.get("slots") or []):
                retried = self._retry_find_slots_with_expanded_window(effective_payload)
                if retried is not None:
                    data = retried
            if effective_tool == "find_slots" and data.get("slots"):
                batch_find_slots.append(
                    {
                        "action_id": f"a_{idx+1}",
                        "payload": effective_payload,
                        "slots": list(data.get("slots") or []),
                    }
                )
                results.append(
                    {
                        "action_id": f"a_{idx+1}",
                        "tool_name": effective_tool,
                        "resolved_payload": effective_payload,
                        "status": "executed",
                        "data": {"slots": data.get("slots"), "batched": True},
                        "error": None,
                    }
                )
                continue

            results.append(
                {
                    "action_id": f"a_{idx+1}",
                    "tool_name": effective_tool,
                    "resolved_payload": effective_payload,
                    "status": "executed",
                    "data": data,
                    "error": None,
                }
            )

        if batch_find_slots:
            merged_slots = self._merge_slots(batch_find_slots)
            if merged_slots:
                any_pending = True
                pending_status = "needs_disambiguation"
                pending_meta: dict[str, Any] = {}
                result_status = "needs_disambiguation"
                if len(merged_slots) == 1:
                    pending_status = "awaiting_confirmation"
                    pending_meta = {"selected_slot_index": 0}
                    result_status = "pending"
                created_pending = self.pending_store.create(
                    "select_slot",
                    {"tool_name": "find_slots", "tool_payload": batch_find_slots[0]["payload"]},
                    status=pending_status,
                    slot_candidates=merged_slots,
                    meta=pending_meta,
                )
                results.append(
                    {
                        "action_id": "a_slots_merged",
                        "tool_name": "find_slots",
                        "resolved_payload": batch_find_slots[0]["payload"],
                        "status": result_status,
                        "data": {"slots": merged_slots, "pending_action_id": created_pending.id, "merged": True},
                        "error": None,
                    }
                )

        return {
            "results": results,
            "created_pending": created_pending,
            "any_failed": any_failed,
            "any_pending": any_pending,
            "executed_tools": executed_tools,
        }

    def _retry_find_slots_with_expanded_window(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        window_start_raw = payload.get("window_start")
        window_end_raw = payload.get("window_end")
        if not window_start_raw or not window_end_raw:
            return None
        try:
            window_start = datetime.fromisoformat(str(window_start_raw))
            window_end = datetime.fromisoformat(str(window_end_raw))
        except ValueError:
            return None
        if window_end <= window_start:
            return None
        expanded_payload = dict(payload)
        expanded_payload["window_start"] = (window_start - timedelta(hours=2)).isoformat()
        expanded_payload["window_end"] = (window_end + timedelta(hours=2)).isoformat()
        out = self.tool_router.execute("find_slots", expanded_payload)
        if not out.get("ok"):
            return None
        data = dict(out.get("data") or {})
        if not list(data.get("slots") or []):
            return None
        data["retried_with_expanded_window"] = True
        data["expanded_window_start"] = expanded_payload["window_start"]
        data["expanded_window_end"] = expanded_payload["window_end"]
        return data

    def _merge_slots(self, batch_find_slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best_by_key: dict[str, dict[str, Any]] = {}
        for chunk in batch_find_slots:
            for slot in chunk["slots"]:
                key = f"{slot.get('start')}|{slot.get('end')}"
                prev = best_by_key.get(key)
                if prev is None or float(slot.get("score") or -10**9) > float(prev.get("score") or -10**9):
                    best_by_key[key] = dict(slot)
        merged = sorted(best_by_key.values(), key=lambda s: float(s.get("score") or -10**9), reverse=True)
        for idx, item in enumerate(merged):
            item["index"] = idx
        return merged[:8]

    def _should_attempt_followup(self, *, calls: list[dict[str, Any]], exec_out: dict[str, Any], followup_step: int) -> bool:
        if followup_step >= self._MAX_TOOL_FOLLOWUP_STEPS:
            return False
        if exec_out["any_failed"] or exec_out["any_pending"]:
            return False
        if not calls:
            return False
        has_non_readonly = any(str(call.get("name") or "").strip() not in self._READ_ONLY_TOOLS for call in calls)
        if has_non_readonly:
            return False
        return any(tool in self._FOLLOWUP_ELIGIBLE_TOOLS for tool in exec_out["executed_tools"])

    @staticmethod
    def _calls_fingerprint(calls: list[dict[str, Any]]) -> str:
        normalized: list[dict[str, Any]] = []
        for call in calls:
            normalized.append(
                {
                    "name": str(call.get("name") or "").strip(),
                    "arguments": call.get("arguments") or {},
                }
            )
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)

    def _build_action_plan_followup_calls(
        self,
        *,
        dialog_context: dict[str, Any],
        user_text: str,
        has_active_pending: bool,
    ) -> list[dict[str, Any]]:
        if has_active_pending:
            return []
        normalized = str(user_text or "").strip().lower()
        if not normalized or len(normalized.split()) > 4:
            return []
        plan = dialog_context.get("action_plan")
        if not isinstance(plan, dict) or plan.get("status") not in {"active", "in_progress"}:
            return []
        steps = plan.get("steps")
        if not isinstance(steps, list):
            return []
        next_step = next(
            (step for step in steps if isinstance(step, dict) and step.get("status") in {"pending", "in_progress"}),
            None,
        )
        if not isinstance(next_step, dict) or str(next_step.get("type") or "") != "find_slot_then_create":
            return []
        window_start = plan.get("window_start")
        window_end = plan.get("window_end")
        title = next_step.get("title")
        duration_minutes = next_step.get("duration_minutes")
        if not window_start or not window_end or not title or duration_minutes is None:
            return []
        next_step["status"] = "in_progress"
        plan["status"] = "in_progress"
        dialog_context["action_plan"] = plan
        return [
            {
                "id": f"ap_{next_step.get('id') or 'step'}",
                "name": "find_slots",
                "arguments": {
                    "window_start": window_start,
                    "window_end": window_end,
                    "duration_minutes": int(duration_minutes),
                    "planning_context": {"action": "create_event", "title": str(title)},
                },
            }
        ]

    def _sync_action_plan_state(self, *, dialog_context: dict[str, Any], results: list[dict[str, Any]]) -> None:
        if not results:
            return
        plan = dialog_context.get("action_plan")
        if not isinstance(plan, dict):
            return
        steps = plan.get("steps")
        if not isinstance(steps, list):
            return
        for item in results:
            if item.get("tool_name") == "find_slots" and item.get("status") in {"pending", "needs_disambiguation"}:
                title = (((item.get("data") or {}).get("planning_context") or {}).get("title"))
                if not title:
                    title = (((item.get("resolved_payload") or {}).get("planning_context") or {}).get("title"))
                for step in steps:
                    if isinstance(step, dict) and step.get("title") == title and step.get("status") in {"pending", "in_progress"}:
                        step["status"] = "awaiting_confirmation"
            if item.get("tool_name") == "confirm_action" and item.get("status") == "executed":
                data = item.get("data") or {}
                event = data.get("event") if isinstance(data, dict) else None
                title = event.get("title") if isinstance(event, dict) else None
                if title:
                    for step in steps:
                        if isinstance(step, dict) and step.get("title") == title:
                            step["status"] = "completed"
        if steps and all(isinstance(step, dict) and step.get("status") == "completed" for step in steps):
            plan["status"] = "completed"
        dialog_context["action_plan"] = plan

    @staticmethod
    def _remember_turn_context(dialog_context: dict[str, Any], user_text: str) -> None:
        prev = str(dialog_context.get("last_user_text") or "").strip()
        if prev:
            dialog_context["previous_user_text"] = prev
        normalized = str(user_text or "").strip()
        if normalized:
            dialog_context["last_user_text"] = normalized

    @staticmethod
    def _append_history_entry(dialog_context: dict[str, Any], *, role: str, content: str) -> None:
        normalized_role = str(role or "").strip().lower()
        normalized_content = str(content or "").strip()
        if normalized_role not in {"user", "assistant"} or not normalized_content:
            return
        existing = dialog_context.get("conversation_history")
        history = list(existing) if isinstance(existing, list) else []
        history.append({"role": normalized_role, "content": normalized_content})
        dialog_context["conversation_history"] = history

    @staticmethod
    def _remember_resolution_entities(dialog_context: dict[str, Any], results: list[dict[str, Any]]) -> None:
        existing = dialog_context.get("resolved_entities_context")
        context = (
            {
                "event": list(existing.get("event") or []),
                "task": list(existing.get("task") or []),
            }
            if isinstance(existing, dict)
            else {"event": [], "task": []}
        )

        def _push(candidate: dict[str, Any]) -> None:
            entity_type = str(candidate.get("entity_type") or "")
            if entity_type not in {"event", "task"}:
                return
            entity_id = candidate.get("id")
            if entity_id is None:
                return
            packed = {
                "id": entity_id,
                "entity_type": entity_type,
                "data": dict(candidate.get("data") or {}),
            }
            previous = [item for item in context[entity_type] if item.get("id") != entity_id]
            context[entity_type] = ([packed] + previous)[:10]

        for result in list(results or []):
            if not isinstance(result, dict):
                continue
            data = result.get("data")
            if not isinstance(data, dict):
                continue
            for item in list(data.get("items") or []):
                if isinstance(item, dict):
                    _push(item)
            for item in list(data.get("candidates") or []):
                if isinstance(item, dict):
                    _push(item)

        dialog_context["resolved_entities_context"] = context

    def _response_meta(self, *, fsm_state: str, fsm_trace: list[str]) -> dict[str, Any]:
        return {
            "fsm_state": fsm_state,
            "fsm_trace": list(fsm_trace),
            "prompt_versions": {
                self.orchestrator_prompt.key: self.orchestrator_prompt.qualified_version,
                self.user_reply_prompt.key: self.user_reply_prompt.qualified_version,
            },
        }

    def _parse_tool_calls(self, llm_response: dict[str, Any]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for item in llm_response.get("tool_calls") or []:
            fn = item.get("function") if isinstance(item, dict) else None
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            raw_arguments = fn.get("arguments")
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(raw_arguments, str):
                raw_arguments = "{}"
            try:
                args = json.loads(raw_arguments)
            except json.JSONDecodeError:
                args = {}
            calls.append({"name": name.strip(), "arguments": args if isinstance(args, dict) else {}})
        return calls

    def _handle_pending_control(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        active = self.pending_store.active_items()
        pending_id = str(args.get("pending_id") or "")
        current = self.pending_store.get(pending_id) if pending_id else (active[-1] if active else None)
        if tool_name == "modify_action":
            changes = dict(args.get("changes") or {})
            # Entity update can be executed directly by context_id even without active pending action.
            direct_entity_update = self._handle_direct_entity_update(changes)
            if direct_entity_update is not None:
                return direct_entity_update
        if not current:
            return {
                "status": "failed",
                "data": None,
                "error": {"code": "pending_not_found", "message": "Нет активного pending action", "recoverable": True},
            }
        if tool_name == "cancel_action":
            self.pending_store.transition(current.id, "cancelled")
            return {"status": "executed", "data": {"cancelled_pending_id": current.id}, "error": None}
        if tool_name == "modify_action":
            changes = dict(args.get("changes") or {})
            if current.status == "needs_disambiguation" and "selected_context_id" in changes:
                selected = self._resolve_selected_candidate(current, changes.get("selected_context_id"))
                if not selected:
                    return {
                        "status": "failed",
                        "data": None,
                        "error": {
                            "code": "selected_entity_not_found",
                            "message": "Выбранная сущность не найдена среди кандидатов.",
                            "recoverable": True,
                        },
                    }
                payload = current.payload or {}
                tool_name_to_run = str(payload.get("tool_name") or "")
                tool_payload = dict(payload.get("tool_payload") or {})
                entity_type = str(selected.get("entity_type") or "")
                entity_id = selected.get("id")
                if tool_name_to_run in {"update_task", "delete_task"}:
                    if entity_type != "task":
                        return {
                            "status": "failed",
                            "data": None,
                            "error": {
                                "code": "selected_entity_type_mismatch",
                                "message": "Выбрана сущность другого типа.",
                                "recoverable": True,
                            },
                        }
                    tool_payload["task_id"] = entity_id
                elif tool_name_to_run in {"update_event", "delete_event", "move_event"}:
                    if entity_type != "event":
                        return {
                            "status": "failed",
                            "data": None,
                            "error": {
                                "code": "selected_entity_type_mismatch",
                                "message": "Выбрана сущность другого типа.",
                                "recoverable": True,
                            },
                        }
                    tool_payload["event_id"] = entity_id
                payload["tool_payload"] = tool_payload
                current.payload = payload
                if self.policy.needs_confirmation(tool_name_to_run, total_mutations=1):
                    self.pending_store.transition(current.id, "awaiting_confirmation")
                    return {"status": "pending", "data": {"pending_action_id": current.id}, "error": None}
                self.pending_store.transition(current.id, "executed")
                result = self.tool_router.execute(tool_name_to_run, tool_payload)
                if result.get("ok"):
                    return {
                        "status": "executed",
                        "data": self._enrich_control_data(
                            tool_name=tool_name_to_run,
                            data=result.get("data"),
                        ),
                        "error": None,
                    }
                return {"status": "failed", "data": None, "error": result.get("error")}
            if current.type == "select_slot" and "slot_index" in changes:
                idx = int(changes["slot_index"])
                current.meta["selected_slot_index"] = idx
                self.pending_store.transition(current.id, "awaiting_confirmation")
                return {"status": "pending", "data": {"pending_action_id": current.id}, "error": None}
            if current.type == "select_slot" and "slot" in changes and isinstance(changes.get("slot"), dict):
                selected_slot = changes.get("slot") or {}
                selected_idx = None
                for idx, candidate in enumerate(list(current.slot_candidates or [])):
                    if not isinstance(candidate, dict):
                        continue
                    if candidate.get("start") == selected_slot.get("start") and candidate.get("end") == selected_slot.get("end"):
                        selected_idx = idx
                        break
                if selected_idx is not None:
                    current.meta["selected_slot_index"] = selected_idx
                    self.pending_store.transition(current.id, "awaiting_confirmation")
                    return {"status": "pending", "data": {"pending_action_id": current.id}, "error": None}
            return {"status": "pending", "data": {"pending_action_id": current.id}, "error": None}
        if tool_name == "confirm_action" and current.type == "select_slot":
            return self._confirm_selected_slot(current)
        self.pending_store.transition(current.id, "executed")
        payload = current.payload or {}
        tool_name_to_run = str(payload.get("tool_name") or "")
        result = self.tool_router.execute(tool_name_to_run, dict(payload.get("tool_payload") or {}))
        if result.get("ok"):
            return {
                "status": "executed",
                "data": self._enrich_control_data(
                    tool_name=tool_name_to_run,
                    data=result.get("data"),
                ),
                "error": None,
            }
        return {"status": "failed", "data": None, "error": result.get("error")}

    @staticmethod
    def _enrich_control_data(*, tool_name: str, data: Any) -> dict[str, Any]:
        payload = dict(data or {}) if isinstance(data, dict) else {}
        if tool_name:
            payload["mutation_tool"] = tool_name
        if tool_name == "delete_task" and payload.get("deleted_id") is not None:
            payload.setdefault("entity_type", "task")
        if tool_name == "delete_event" and payload.get("deleted_id") is not None:
            payload.setdefault("entity_type", "event")
        return payload

    @staticmethod
    def _parse_entity_context_id(context_id: Any) -> tuple[str, int] | None:
        raw = str(context_id or "").strip()
        if not raw.startswith("e:"):
            return None
        parts = raw.split(":")
        if len(parts) != 3:
            return None
        entity_type = parts[1].strip()
        try:
            entity_id = int(parts[2])
        except (TypeError, ValueError):
            return None
        if entity_type not in {"task", "event"}:
            return None
        return entity_type, entity_id

    def _handle_direct_entity_update(self, changes: dict[str, Any]) -> dict[str, Any] | None:
        context = self._parse_entity_context_id(changes.get("context_id"))
        fields = changes.get("fields") if isinstance(changes.get("fields"), dict) else {}
        if not context or not fields:
            return None
        entity_type, entity_id = context
        if entity_type == "task":
            out = self.tool_router.execute("update_task", {"task_id": entity_id, "updates": fields})
            inner_tool = "update_task"
        else:
            out = self.tool_router.execute("update_event", {"event_id": entity_id, "updates": fields})
            inner_tool = "update_event"
        if out.get("ok"):
            merged = dict(out.get("data") or {}) if isinstance(out.get("data"), dict) else {}
            merged["mutation_tool"] = inner_tool
            return {"status": "executed", "data": merged, "error": None}
        return {"status": "failed", "data": None, "error": out.get("error")}

    def _confirm_selected_slot(self, current) -> dict[str, Any]:
        slot_candidates = [slot for slot in list(current.slot_candidates or []) if isinstance(slot, dict)]
        selected_idx_raw = current.meta.get("selected_slot_index")
        selected_idx = None
        if selected_idx_raw is not None:
            try:
                selected_idx = int(selected_idx_raw)
            except (TypeError, ValueError):
                selected_idx = None
        if selected_idx is None and len(slot_candidates) == 1:
            selected_idx = 0
        if selected_idx is None or selected_idx < 0 or selected_idx >= len(slot_candidates):
            return {"status": "pending", "data": {"pending_action_id": current.id}, "error": None}

        selected_slot = slot_candidates[selected_idx]
        start = selected_slot.get("start")
        end = selected_slot.get("end")
        if not start or not end:
            return {
                "status": "failed",
                "data": None,
                "error": {"code": "slot_invalid", "message": "Выбранный слот некорректен.", "recoverable": True},
            }

        payload = current.payload or {}
        tool_payload = dict(payload.get("tool_payload") or {})
        planning_context = (
            dict(tool_payload.get("planning_context") or {})
            if isinstance(tool_payload.get("planning_context"), dict)
            else {}
        )
        action = str(planning_context.get("action") or "create_event")

        if action == "move_event":
            event_id = planning_context.get("event_id") or tool_payload.get("event_id")
            if event_id is None:
                return {
                    "status": "failed",
                    "data": None,
                    "error": {"code": "event_id_missing", "message": "Не удалось определить событие для переноса.", "recoverable": True},
                }
            run_tool = "move_event"
            run_payload = {"event_id": event_id, "start": start, "end": end}
        else:
            title = str(
                planning_context.get("title")
                or tool_payload.get("title")
                or tool_payload.get("summary")
                or ""
            ).strip()
            if not title:
                title = "Событие"
            run_tool = "create_event"
            run_payload = {"title": title, "start": start, "end": end}
            if planning_context.get("task_id") is not None:
                run_payload["task_id"] = planning_context.get("task_id")
            elif tool_payload.get("task_id") is not None:
                run_payload["task_id"] = tool_payload.get("task_id")

        result = self.tool_router.execute(run_tool, run_payload)
        if not result.get("ok"):
            self.pending_store.transition(current.id, "failed")
            return {"status": "failed", "data": None, "error": result.get("error")}

        self.pending_store.transition(current.id, "executed")
        data = dict(result.get("data") or {}) if isinstance(result.get("data"), dict) else {}
        data["selected_slot"] = {"start": start, "end": end}
        data["applied_tool"] = run_tool
        return {
            "status": "executed",
            "data": self._enrich_control_data(tool_name=run_tool, data=data),
            "error": None,
        }

    def _resolve_selected_candidate(self, current, selected_context_id: Any) -> dict[str, Any] | None:
        context = self._parse_entity_context_id(selected_context_id)
        if context:
            entity_type, entity_id = context
            for candidate in list(current.disambiguation_candidates or []):
                if not isinstance(candidate, dict):
                    continue
                if str(candidate.get("entity_type") or "") == entity_type and candidate.get("id") == entity_id:
                    return candidate
        for candidate in list(current.disambiguation_candidates or []):
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("id")) == str(selected_context_id):
                return candidate
        return None

    def _fallback_reply(self, status: str, pending) -> str:
        if status == "needs_disambiguation":
            return "Выберите подходящий слот, и я продолжу."
        if status == "awaiting_confirmation" and pending:
            return f"Нужно подтверждение действия ({pending.type})."
        if status == "failed":
            return "Не удалось выполнить запрос. Уточните, пожалуйста, формулировку."
        return "Готово."

    def _local_time_view(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._local_time_view(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._local_time_view(item) for item in value]
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                return value
            if dt.tzinfo is None:
                return value
            return dt.strftime("%Y-%m-%d %H:%M")
        return value

    @staticmethod
    def _planner_handoff_message(messages: list[str]) -> str:
        cleaned = [str(item).strip() for item in list(messages or []) if str(item).strip()]
        if not cleaned:
            return ""
        # Keep only the latest signal to avoid noisy instruction accumulation.
        return cleaned[-1]

    def _build_orchestration_summary(
        self,
        *,
        status: str,
        results: list[dict[str, Any]],
        pending_action: dict[str, Any] | None,
        fsm_trace: list[str],
    ) -> dict[str, Any]:
        tool_sequence: list[str] = []
        counts = {
            "executed": 0,
            "pending": 0,
            "needs_disambiguation": 0,
            "failed": 0,
        }
        errors: list[dict[str, Any]] = []
        for item in list(results or []):
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or "")
            if tool_name:
                tool_sequence.append(tool_name)
            item_status = str(item.get("status") or "")
            if item_status in counts:
                counts[item_status] += 1
            error = item.get("error")
            if isinstance(error, dict):
                errors.append(
                    {
                        "tool_name": tool_name,
                        "code": error.get("code"),
                        "message": error.get("message"),
                        "recoverable": bool(error.get("recoverable")),
                    }
                )

        pending_brief = None
        if isinstance(pending_action, dict):
            pending_brief = {
                "id": pending_action.get("id"),
                "type": pending_action.get("type"),
                "status": pending_action.get("status"),
                "has_slot_candidates": bool(pending_action.get("slot_candidates")),
                "has_disambiguation_candidates": bool(pending_action.get("disambiguation_candidates")),
            }

        return {
            "status": status,
            "fsm_trace": list(fsm_trace),
            "tool_sequence": tool_sequence,
            "result_counts": counts,
            "errors": errors[:3],
            "pending_action_brief": pending_brief,
        }

    def handle_ui_action(self, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        control = self._handle_pending_control(action_type, payload or {})
        status = control.get("status") or "failed"
        if status == "pending":
            state = "awaiting_confirmation"
        elif status == "failed":
            state = "failed"
        else:
            state = "success"
        results = [{"action_id": "a_ui", "tool_name": action_type, **control}]
        pending_items = self.pending_store.active_items()
        pending = pending_items[-1] if pending_items else None
        return {
            "state": state,
            "status": state,
            "results": results,
            "pending_action": pending.to_dict() if pending else None,
            "user_message": self._fallback_reply(state, pending),
        }
