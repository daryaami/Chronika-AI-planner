# python manage.py eval_assistant --email daryaami10@gmail.com --limit 10 --skip-setup

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from assistant.models import AssistantMessage, AssistantSession
from assistant.services.dialog_session_store import (
    clear_user_assistant_session,
    run_assistant_turn_with_persisted_state,
    run_assistant_ui_action,
)


TERMINAL_STATES = {"success", "failed", "idle"}
PENDING_STATES = {"waiting_confirmation", "needs_disambiguation", "awaiting_confirmation"}


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    title: str
    turns: int
    duration_seconds: float
    success: bool
    intent_correct: bool | None
    entity_correct: bool | None
    disambiguation_used: bool
    final_state: str
    tool_names: list[str]
    errors: list[str]


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * q))
    idx = max(0, min(idx, len(ordered) - 1))
    return ordered[idx]


def _normalize_state(state: str) -> str:
    if state == "awaiting_confirmation":
        return "waiting_confirmation"
    return state


class Command(BaseCommand):
    help = "Run assistant scenarios and generate metric report (JSON + Markdown)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="User email to run assistant as.")
        parser.add_argument(
            "--scenarios",
            default="assistant/evals/scenarios_40.json",
            help="Path to scenarios JSON file (relative to chronika/ or absolute).",
        )
        parser.add_argument(
            "--output-json",
            default="assistant/evals/reports/assistant_eval_report.json",
            help="Output path for raw report JSON.",
        )
        parser.add_argument(
            "--output-md",
            default="assistant/evals/reports/assistant_eval_report.md",
            help="Output path for human-readable markdown report.",
        )
        parser.add_argument(
            "--max-turns",
            type=int,
            default=4,
            help="Maximum assistant turns per scenario (with auto actions).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Run only first N scenarios (0 = all).",
        )
        parser.add_argument(
            "--no-clear-per-scenario",
            action="store_true",
            help="Do not clear assistant session before each scenario.",
        )
        parser.add_argument(
            "--skip-setup",
            action="store_true",
            help="Skip setup_messages from scenarios file.",
        )

    def handle(self, *args, **options):
        user = self._get_user_or_fail(options["email"])
        scenario_path = self._resolve_path(str(options["scenarios"]))
        output_json = self._resolve_path(str(options["output_json"]))
        output_md = self._resolve_path(str(options["output_md"]))
        max_turns = int(options["max_turns"])
        limit = int(options["limit"])
        clear_per_scenario = not bool(options["no_clear_per_scenario"])

        scenarios, setup_messages = self._load_scenarios(scenario_path)
        if limit > 0:
            scenarios = scenarios[:limit]
        if not scenarios:
            raise CommandError("No scenarios provided.")

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(scenarios)} scenarios from {scenario_path}"))
        self.stdout.write(self.style.WARNING(f"Running eval as: {user.email}"))

        setup_executed = 0
        setup_failed = 0
        if setup_messages and not bool(options["skip_setup"]):
            self.stdout.write(self.style.WARNING(f"Running setup messages: {len(setup_messages)}"))
            setup_executed, setup_failed = self._run_setup_messages(user=user, setup_messages=setup_messages)
            self.stdout.write(
                self.style.WARNING(f"Setup complete: executed={setup_executed}, failed={setup_failed}")
            )

        results: list[ScenarioResult] = []
        started_at = datetime.utcnow().isoformat() + "Z"
        run_started = time.perf_counter()

        for idx, scenario in enumerate(scenarios, start=1):
            sid = str(scenario.get("id") or f"s{idx}")
            title = str(scenario.get("title") or sid)
            self.stdout.write(f"[{idx}/{len(scenarios)}] {sid} - {title}")
            try:
                result = self._run_scenario(
                    user=user,
                    scenario=scenario,
                    max_turns=max_turns,
                    clear_before=clear_per_scenario,
                )
                results.append(result)
            except Exception as exc:
                results.append(
                    ScenarioResult(
                        scenario_id=sid,
                        category=str(scenario.get("category") or "unknown"),
                        title=title,
                        turns=0,
                        duration_seconds=0.0,
                        success=False,
                        intent_correct=False,
                        entity_correct=False,
                        disambiguation_used=False,
                        final_state="failed",
                        tool_names=[],
                        errors=[f"exception: {exc}"],
                    )
                )
                self.stdout.write(self.style.ERROR(f"  failed: {exc}"))

        elapsed = time.perf_counter() - run_started
        summary = self._build_summary(results)
        payload = {
            "meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "started_at": started_at,
                "duration_seconds": round(elapsed, 3),
                "user_email": user.email,
                "scenarios_file": str(scenario_path),
                "scenarios_total": len(scenarios),
                "setup_messages_total": len(setup_messages),
                "setup_messages_executed": setup_executed,
                "setup_messages_failed": setup_failed,
            },
            "summary": summary,
            "results": [r.__dict__ for r in results],
        }

        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        output_md.write_text(self._render_markdown(payload), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"JSON report: {output_json}"))
        self.stdout.write(self.style.SUCCESS(f"MD report: {output_md}"))
        self.stdout.write(self.style.SUCCESS(f"TSR: {summary['overall']['tsr_percent']:.1f}%"))

    def _run_setup_messages(self, *, user, setup_messages: list[str]) -> tuple[int, int]:
        # Reset chat history once before setup, but keep domain data (tasks/events) intact.
        clear_user_assistant_session(user)
        executed = 0
        failed = 0
        for message in setup_messages:
            text = str(message or "").strip()
            if not text:
                continue
            try:
                result, _message_id, _blocks = run_assistant_turn_with_persisted_state(user, text)
                executed += 1
                if _normalize_state(result.state) == "failed":
                    failed += 1
            except Exception:
                executed += 1
                failed += 1
        clear_user_assistant_session(user)
        return executed, failed

    def _run_scenario(
        self,
        *,
        user,
        scenario: dict[str, Any],
        max_turns: int,
        clear_before: bool,
    ) -> ScenarioResult:
        if clear_before:
            clear_user_assistant_session(user)

        message = str(scenario.get("message") or "").strip()
        if not message:
            raise ValueError("Scenario has empty message")

        expected_tool = scenario.get("expected_tool")
        expected_entity_type = scenario.get("expected_entity_type")
        expected_final_state = str(scenario.get("expected_final_state") or "success")
        auto_confirm = bool(scenario.get("auto_confirm", False))
        auto_cancel = bool(scenario.get("auto_cancel", False))
        auto_actions = list(scenario.get("auto_actions") or [])

        turns = 0
        total_duration = 0.0
        all_tool_names: list[str] = []
        errors: list[str] = []
        disambiguation_used = False
        final_state = "failed"
        last_metadata: dict[str, Any] = {}

        t0 = time.perf_counter()
        result, _message_id, _blocks = run_assistant_turn_with_persisted_state(user, message)
        turns += 1
        total_duration += time.perf_counter() - t0
        final_state = _normalize_state(result.state)

        last_msg = self._latest_assistant_message(user)
        if last_msg:
            last_metadata = dict(last_msg.metadata_json or {})
            all_tool_names.extend(self._extract_tool_names(last_metadata))
            if self._metadata_has_disambiguation(last_metadata) or final_state in PENDING_STATES:
                disambiguation_used = True

        scripted_actions = auto_actions[:]
        if auto_confirm:
            scripted_actions.append({"type": "confirm", "payload": {}})
        if auto_cancel:
            scripted_actions.append({"type": "cancel", "payload": {}})

        for action in scripted_actions:
            if turns >= max_turns or final_state in TERMINAL_STATES:
                break
            t1 = time.perf_counter()
            ui_result, _ui_message_id, _ui_blocks = run_assistant_ui_action(user, {"action": action})
            turns += 1
            total_duration += time.perf_counter() - t1
            final_state = _normalize_state(ui_result.state)

            last_msg = self._latest_assistant_message(user)
            if last_msg:
                last_metadata = dict(last_msg.metadata_json or {})
                all_tool_names.extend(self._extract_tool_names(last_metadata))
                if self._metadata_has_disambiguation(last_metadata) or final_state in PENDING_STATES:
                    disambiguation_used = True

        all_tool_names = sorted({name for name in all_tool_names if name})
        has_failed_tool = self._metadata_has_failed_tool(last_metadata)
        intent_correct = None
        if expected_tool:
            intent_correct = str(expected_tool) in all_tool_names

        entity_correct = None
        if expected_entity_type:
            entity_correct = self._metadata_has_entity_type(last_metadata, str(expected_entity_type))

        success = (final_state == expected_final_state) and not has_failed_tool
        if intent_correct is False:
            success = False
            errors.append(f"expected_tool_not_found:{expected_tool}")
        if entity_correct is False:
            success = False
            errors.append(f"expected_entity_not_found:{expected_entity_type}")
        if has_failed_tool:
            errors.append("tool_execution_failed")

        return ScenarioResult(
            scenario_id=str(scenario.get("id") or "unknown"),
            category=str(scenario.get("category") or "unknown"),
            title=str(scenario.get("title") or "untitled"),
            turns=turns,
            duration_seconds=round(total_duration, 3),
            success=success,
            intent_correct=intent_correct,
            entity_correct=entity_correct,
            disambiguation_used=disambiguation_used,
            final_state=final_state,
            tool_names=all_tool_names,
            errors=errors,
        )

    def _build_summary(self, results: list[ScenarioResult]) -> dict[str, Any]:
        total = len(results)
        successes = [r for r in results if r.success]
        latencies = [r.duration_seconds for r in results]
        turns_success = [r.turns for r in successes]
        intent_known = [r.intent_correct for r in results if r.intent_correct is not None]
        entity_known = [r.entity_correct for r in results if r.entity_correct is not None]
        disamb_count = sum(1 for r in results if r.disambiguation_used)

        by_category: dict[str, dict[str, Any]] = {}
        for r in results:
            bucket = by_category.setdefault(
                r.category,
                {"total": 0, "success": 0, "latencies": [], "turns": [], "intent": [], "entity": [], "disamb": 0},
            )
            bucket["total"] += 1
            bucket["success"] += int(r.success)
            bucket["latencies"].append(r.duration_seconds)
            if r.success:
                bucket["turns"].append(r.turns)
            if r.intent_correct is not None:
                bucket["intent"].append(bool(r.intent_correct))
            if r.entity_correct is not None:
                bucket["entity"].append(bool(r.entity_correct))
            if r.disambiguation_used:
                bucket["disamb"] += 1

        category_summary: dict[str, Any] = {}
        for cat, bucket in by_category.items():
            cat_total = bucket["total"] or 1
            category_summary[cat] = {
                "n": bucket["total"],
                "tsr_percent": round(bucket["success"] * 100.0 / cat_total, 2),
                "intent_accuracy_percent": round(
                    (sum(bucket["intent"]) * 100.0 / len(bucket["intent"])) if bucket["intent"] else 0.0,
                    2,
                ),
                "entity_accuracy_percent": round(
                    (sum(bucket["entity"]) * 100.0 / len(bucket["entity"])) if bucket["entity"] else 0.0,
                    2,
                ),
                "avg_turns_success": round(statistics.mean(bucket["turns"]), 2) if bucket["turns"] else 0.0,
                "median_latency_s": round(statistics.median(bucket["latencies"]), 3) if bucket["latencies"] else 0.0,
                "p95_latency_s": round(_quantile(bucket["latencies"], 0.95), 3) if bucket["latencies"] else 0.0,
                "disambiguation_rate_percent": round(bucket["disamb"] * 100.0 / cat_total, 2),
            }

        return {
            "overall": {
                "n": total,
                "tsr_percent": round((len(successes) * 100.0 / total) if total else 0.0, 2),
                "intent_accuracy_percent": round((sum(intent_known) * 100.0 / len(intent_known)) if intent_known else 0.0, 2),
                "entity_accuracy_percent": round((sum(entity_known) * 100.0 / len(entity_known)) if entity_known else 0.0, 2),
                "avg_turns_success": round(statistics.mean(turns_success), 2) if turns_success else 0.0,
                "median_latency_s": round(statistics.median(latencies), 3) if latencies else 0.0,
                "p95_latency_s": round(_quantile(latencies, 0.95), 3) if latencies else 0.0,
                "disambiguation_rate_percent": round((disamb_count * 100.0 / total) if total else 0.0, 2),
            },
            "by_category": category_summary,
        }

    def _render_markdown(self, payload: dict[str, Any]) -> str:
        meta = payload["meta"]
        summary = payload["summary"]["overall"]
        by_category = payload["summary"]["by_category"]
        results: list[dict[str, Any]] = payload["results"]

        lines = [
            "# Отчет по оценке ассистента Chronika AI",
            "",
            f"- Дата генерации: `{meta['generated_at']}`",
            f"- Пользователь: `{meta['user_email']}`",
            f"- Сценариев: `{meta['scenarios_total']}`",
            f"- Длительность прогона: `{meta['duration_seconds']}` с",
            "",
            "## Общие метрики",
            "",
            f"- TSR: **{summary['tsr_percent']}%**",
            f"- Intent Accuracy: **{summary['intent_accuracy_percent']}%**",
            f"- Entity Resolution Accuracy: **{summary['entity_accuracy_percent']}%**",
            f"- Avg Turns to Success: **{summary['avg_turns_success']}**",
            f"- Median Latency: **{summary['median_latency_s']} c**",
            f"- P95 Latency: **{summary['p95_latency_s']} c**",
            f"- Disambiguation Rate: **{summary['disambiguation_rate_percent']}%**",
            "",
            "## Разбивка по категориям",
            "",
            "| Категория | N | TSR % | Intent % | Entity % | Avg Turns | Median RT, c | P95 RT, c | Disambiguation % |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]

        for category, data in sorted(by_category.items()):
            lines.append(
                f"| {category} | {data['n']} | {data['tsr_percent']} | {data['intent_accuracy_percent']} | "
                f"{data['entity_accuracy_percent']} | {data['avg_turns_success']} | {data['median_latency_s']} | "
                f"{data['p95_latency_s']} | {data['disambiguation_rate_percent']} |"
            )

        lines.extend(["", "## Детализация по сценариям", "", "| ID | Категория | Успех | State | Turns | Time, c | Tools | Ошибки |", "|---|---|---:|---|---:|---:|---|---|"])
        for r in results:
            tools = ", ".join(r["tool_names"]) if r["tool_names"] else "-"
            errs = "; ".join(r["errors"]) if r["errors"] else "-"
            ok = "1" if r["success"] else "0"
            lines.append(
                f"| {r['scenario_id']} | {r['category']} | {ok} | {r['final_state']} | {r['turns']} | "
                f"{r['duration_seconds']} | {tools} | {errs} |"
            )

        return "\n".join(lines) + "\n"

    def _latest_assistant_message(self, user):
        session = AssistantSession.objects.filter(user=user).first()
        if not session:
            return None
        return session.messages.filter(role="assistant").order_by("-created_at").first()

    def _extract_tool_names(self, metadata: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for item in list((metadata or {}).get("results") or []):
            tool = str(item.get("tool_name") or "")
            if tool:
                out.append(tool)
        return out

    def _metadata_has_failed_tool(self, metadata: dict[str, Any]) -> bool:
        for item in list((metadata or {}).get("results") or []):
            if str(item.get("status") or "") == "failed":
                return True
        return False

    def _metadata_has_disambiguation(self, metadata: dict[str, Any]) -> bool:
        pending = (metadata or {}).get("pending_action") or {}
        status = str(pending.get("status") or "")
        return status in {"needs_disambiguation", "awaiting_confirmation"}

    def _metadata_has_entity_type(self, metadata: dict[str, Any], expected_entity_type: str) -> bool:
        expected = expected_entity_type.strip().lower()
        for item in list((metadata or {}).get("results") or []):
            data = item.get("data") or {}
            if isinstance(data, dict):
                if str(data.get("entity_type") or "").lower() == expected:
                    return True
                for key in ("task", "event"):
                    if key in data and key == expected:
                        return True
            resolved_payload = item.get("resolved_payload") or {}
            if str(resolved_payload.get("entity_type") or "").lower() == expected:
                return True
        return False

    def _load_scenarios(self, path: Path) -> tuple[list[dict[str, Any]], list[str]]:
        if not path.exists():
            raise CommandError(f"Scenario file not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        setup_messages: list[str] = []
        if isinstance(payload, dict):
            scenarios = payload.get("scenarios")
            setup_raw = payload.get("setup_messages") or []
            if isinstance(setup_raw, list):
                setup_messages = [str(x) for x in setup_raw if str(x).strip()]
        else:
            scenarios = payload
        if not isinstance(scenarios, list):
            raise CommandError("Scenarios JSON must be a list or {'scenarios': [...]}")
        normalized: list[dict[str, Any]] = []
        for i, item in enumerate(scenarios, start=1):
            if not isinstance(item, dict):
                raise CommandError(f"Scenario #{i} is not an object")
            normalized.append(item)
        return normalized, setup_messages

    def _resolve_path(self, value: str) -> Path:
        p = Path(value)
        if p.is_absolute():
            return p
        return Path.cwd() / p

    def _get_user_or_fail(self, email: str):
        user_model = get_user_model()
        user = user_model.objects.filter(email=email).first()
        if not user:
            raise CommandError(f"User not found: {email}")
        return user
