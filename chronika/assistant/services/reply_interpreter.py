from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from assistant.domain.dialog import DialogIntent, NewIntentCandidate, ReplyInterpretation
from assistant.fsm.states import DialogState
from assistant.integrations.llm_client import LLMClientError, LLMConfigurationError, MistralLLMClient
from assistant.pipeline_log import interpretation_to_dict, log_exception, pretty_data, pretty_json_text, trace
from core.exceptions import AssistantLLMParseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplyInterpreterInput:
    state: str
    current_plan: dict[str, Any]
    entities_in_context: list[dict[str, Any]]
    disambiguation_options: list[dict[str, Any]]
    last_referenced_id: int | None
    user_message: str


class ReplyInterpreterService:
    """
    Интерпретация реплики во втором шаге диалога: подтверждение, отказ, выбор варианта,
    правка плана (step_patches / доп. actions), новый запрос.

    Автоподтверждение без LLM только для одного слова: «да», «ок», «хорошо»; с конца
    снимаются повторяющиеся . , ; : ! ? и аналоги (в т.ч. …). Всё остальное — Mistral JSON.
    """

    def __init__(self, llm_client: MistralLLMClient | None = None):
        if llm_client is not None:
            self._llm = llm_client
        else:
            try:
                self._llm = MistralLLMClient()
            except LLMConfigurationError:
                self._llm = None

    def interpret(self, payload: ReplyInterpreterInput) -> ReplyInterpretation:
        user_text = (payload.user_message or "").strip()
        input_len = len(user_text)
        n_opts = len(payload.disambiguation_options or [])
        n_actions = len((payload.current_plan or {}).get("actions") or [])
        trace(
            "FSM → ReplyInterpreter: вход (все поля, как в ReplyInterpreterInput)",
            вход_json=pretty_data(asdict(payload)),
        )
        print(
            f"[ReplyInterpreter] start interpret: state={payload.state}, input_len={input_len}, "
            f"disambig_options={n_opts}, plan_actions={n_actions}, llm_available={self._llm is not None}"
        )
        logger.debug(
            "ReplyInterpreter start: state=%s input_len=%s disambig_options=%s plan_actions=%s llm=%s",
            payload.state,
            input_len,
            n_opts,
            n_actions,
            self._llm is not None,
        )

        hit = self._heuristic_interpret(payload)
        if hit is not None:
            print(
                f"[ReplyInterpreter] heuristic path: intent={hit.dialog_intent.value}, "
                f"target_ids={hit.target_ids}, step_patches={len(hit.step_patches)}, "
                f"actions={len(hit.actions)}"
            )
            logger.debug(
                "ReplyInterpreter heuristic: intent=%s target_ids=%s",
                hit.dialog_intent.value,
                hit.target_ids,
            )
            trace(
                "ReplyInterpreter: ответ (эвристика, JSON от LLM не вызывался)",
                примечание="Ниже — нормализованный объект интерпретации (как после LLM).",
                интерпретация_json=pretty_data(interpretation_to_dict(hit)),
            )
            return hit

        if self._llm is not None:
            return self._llm_interpret(payload)

        print("[ReplyInterpreter] fallback: intent=unclear (no llm)")
        logger.debug("ReplyInterpreter unclear fallback")
        unclear = self._unclear()
        trace(
            "ReplyInterpreter: ответ (LLM недоступен)",
            интерпретация_json=pretty_data(interpretation_to_dict(unclear)),
        )
        return unclear

    @staticmethod
    def _unclear() -> ReplyInterpretation:
        return ReplyInterpretation(
            dialog_intent=DialogIntent.UNCLEAR,
            actions=[],
            target_ids=[],
            new_intent_candidate=None,
            step_patches=[],
        )

    def _heuristic_interpret(self, payload: ReplyInterpreterInput) -> ReplyInterpretation | None:
        msg = (payload.user_message or "").strip()
        if not msg:
            return self._unclear()

        state = payload.state

        if state == DialogState.DISAMBIGUATION.value:
            tids = self._heuristic_pick_disambiguation(msg, payload.disambiguation_options)
            if tids:
                return ReplyInterpretation(
                    dialog_intent=DialogIntent.SELECT,
                    target_ids=tids,
                    actions=[],
                    new_intent_candidate=None,
                    step_patches=[],
                )
            return None

        if state == DialogState.WAITING_CONFIRMATION.value:
            if self._looks_like_cancel(msg):
                return ReplyInterpretation(
                    dialog_intent=DialogIntent.CANCEL,
                    actions=[],
                    target_ids=[],
                    new_intent_candidate=None,
                    step_patches=[],
                )
            if self._looks_like_reject(msg):
                return ReplyInterpretation(
                    dialog_intent=DialogIntent.REJECT,
                    actions=[],
                    target_ids=[],
                    new_intent_candidate=None,
                    step_patches=[],
                )
            if self._is_strict_single_word_confirm(msg):
                return ReplyInterpretation(
                    dialog_intent=DialogIntent.CONFIRM,
                    actions=[],
                    target_ids=[],
                    new_intent_candidate=None,
                    step_patches=[],
                )
            return None

        if state == DialogState.WAITING_CLARIFICATION.value:
            if self._looks_like_cancel(msg) and len(msg) <= 32:
                return ReplyInterpretation(
                    dialog_intent=DialogIntent.CANCEL,
                    actions=[],
                    target_ids=[],
                    new_intent_candidate=None,
                    step_patches=[],
                )
            return None

        return None

    @staticmethod
    def _is_strict_single_word_confirm(text: str) -> bool:
        """Только одно слово: да / ок / хорошо; концевые знаки препинания снимаются циклом."""
        t = text.strip().lower()
        trail = ".,;:!?…。！？"
        while t and t[-1] in trail:
            t = t[:-1]
        if not t or any(c.isspace() for c in t):
            return False
        return t in {"да", "ок", "хорошо"}

    @staticmethod
    def _looks_like_reject(text: str) -> bool:
        t = text.strip().lower()
        return bool(
            re.match(
                r"^(нет|не\s+надо|не\s+нужно|не\s+хочу|отказываюсь|no)\b",
                t,
                re.I,
            )
        )

    @staticmethod
    def _looks_like_cancel(text: str) -> bool:
        t = text.strip().lower()
        return bool(
            re.match(
                r"^(отмена|забудь|стоп|cancel)\b",
                t,
                re.I,
            )
        )

    @staticmethod
    def _heuristic_pick_disambiguation(
        message: str,
        options: list[dict[str, Any]],
    ) -> list[int]:
        if not options:
            return []
        m = message.strip().lower()
        ord_map = {
            "первый": 1,
            "первую": 1,
            "первое": 1,
            "второй": 2,
            "вторую": 2,
            "второе": 2,
            "третий": 3,
            "третью": 3,
            "третье": 3,
        }
        for word, n in ord_map.items():
            if re.search(rf"\b{re.escape(word)}\b", m):
                return ReplyInterpreterService._object_ids_for_positions(options, n)

        match = re.search(r"\b(\d+)\b", m)
        if match:
            n = int(match.group(1))
            return ReplyInterpreterService._object_ids_for_positions(options, n)
        return []

    @staticmethod
    def _object_ids_for_positions(options: list[dict[str, Any]], one_based: int) -> list[int]:
        if one_based < 1:
            return []
        by_idx = {int(o.get("index", -1)): o for o in options if isinstance(o, dict)}
        opt = by_idx.get(one_based - 1)
        if opt and opt.get("object_id") is not None:
            return [int(opt["object_id"])]
        sorted_opts = sorted(
            [o for o in options if isinstance(o, dict)],
            key=lambda x: int(x.get("index", 0)),
        )
        if one_based <= len(sorted_opts) and sorted_opts[one_based - 1].get("object_id") is not None:
            return [int(sorted_opts[one_based - 1]["object_id"])]
        return []

    def _reply_interpreter_messages(self, payload: ReplyInterpreterInput) -> list[dict[str, str]]:
        plan_compact = json.dumps(payload.current_plan, ensure_ascii=False)
        options_compact = json.dumps(payload.disambiguation_options, ensure_ascii=False)
        system = (
            "Ты Reply Interpreter для диалога с ассистентом по задачам и календарю.\n"
            "Пользователь отвечает на уточняющий вопрос или подтверждение. Верни один JSON-объект без markdown.\n"
            f"Текущее состояние FSM: {payload.state}.\n"
            "Допустимые значения dialog_intent (строго): confirm, reject, cancel, select, modify, "
            "new_request, unclear.\n"
            "Смысл:\n"
            "- confirm — согласие выполнить текущий план.\n"
            "- reject — не выполнять (мягкий отказ).\n"
            "- cancel — прервать сценарий.\n"
            "- select — только при state=disambiguation: выбор одного варианта из списка.\n"
            "- modify — уточнение/правка плана (дата, текст, запрос): используй step_patches.\n"
            "- new_request — пользователь начал новую команду; положи полный текст в new_intent_raw.\n"
            "- unclear — нельзя понять.\n"
            "При select заполни target_ids: массив из одного целого object_id из disambiguation_options.\n"
            "При modify заполни step_patches: массив объектов "
            '{"index": <номер шага с 0>, "merge": {"fields": {}, "query": {}, "datetime": {}, '
            '"filters": {}, "meta": {}}} — указывай только ключи, которые меняются; пустые объекты не добавляй.\n'
            "При необходимости добавить отдельное действие в конец плана (редко) используй actions: массив "
            '{"context_id": "строка", "type": "create|schedule|update|delete|retrieve", '
            '"target_id": число или null, "data": {}}.\n'
            "Если dialog_intent не select, target_ids должен быть []. Если не new_request, new_intent_raw null.\n"
            f"Текущий план (JSON): {plan_compact}\n"
            f"Варианты для disambiguation (JSON): {options_compact}\n"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": payload.user_message},
        ]

    def _llm_chat_with_retry(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        assert self._llm is not None
        for attempt in range(2):
            try:
                return self._llm.chat_with_messages(
                    messages=messages,
                    temperature=0.0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            except LLMClientError as exc:
                print(f"[ReplyInterpreter] LLM error (attempt {attempt + 1}): {exc}")
                logger.warning("Reply interpreter LLM call failed (attempt %s): %s", attempt + 1, exc)
                if attempt == 1:
                    raise AssistantLLMParseError() from exc

    def _llm_interpret(self, payload: ReplyInterpreterInput) -> ReplyInterpretation:
        assert self._llm is not None
        messages = self._reply_interpreter_messages(payload)
        max_tokens = 500
        trace(
            "ReplyInterpreter → LLM: полные сообщения (system + user)",
            сообщения_json=pretty_data(messages),
            max_tokens=str(max_tokens),
        )
        print(
            f"[ReplyInterpreter] LLM inference start: max_tokens={max_tokens}, "
            f"messages=2 (system+user)"
        )
        started_at = time.perf_counter()
        raw = self._llm_chat_with_retry(messages, max_tokens)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        print(
            f"[ReplyInterpreter] LLM inference done: elapsed_ms={elapsed_ms}, "
            f"response_len={len(raw)}"
        )
        trace(
            "ReplyInterpreter: сырой JSON от LLM",
            ответ_llm_json=pretty_json_text(raw),
            elapsed_ms=str(elapsed_ms),
        )

        data = self._safe_parse_json(raw)
        if not data:
            print("[ReplyInterpreter] response JSON parse failed; one retry inference")
            logger.warning("Reply interpreter: failed to parse LLM JSON; retrying inference")
            started_at = time.perf_counter()
            raw = self._llm_chat_with_retry(messages, max_tokens)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            print(
                f"[ReplyInterpreter] LLM retry inference done: elapsed_ms={elapsed_ms}, "
                f"response_len={len(raw)}"
            )
            data = self._safe_parse_json(raw)
            if data:
                trace(
                    "ReplyInterpreter: сырой JSON от LLM (повторный запрос)",
                    ответ_llm_json=pretty_json_text(raw),
                )
        if not data:
            print("[ReplyInterpreter] JSON parse failed after retry; raising AssistantLLMParseError")
            logger.warning("Reply interpreter: failed to parse LLM JSON after retry")
            err = AssistantLLMParseError()
            log_exception("reply_interpret.llm", "ReplyInterpreterService._llm_interpret", err)
            raise err

        result = self._normalize_llm_payload(data, payload.state, payload.user_message)
        print(
            f"[ReplyInterpreter] LLM parse success: intent={result.dialog_intent.value}, "
            f"target_ids={result.target_ids}, step_patches={len(result.step_patches)}, "
            f"actions={len(result.actions)}"
        )
        logger.debug(
            "ReplyInterpreter LLM result: intent=%s target_ids=%s",
            result.dialog_intent.value,
            result.target_ids,
        )
        trace(
            "ReplyInterpreter: нормализованный объект после разбора JSON",
            интерпретация_json=pretty_data(interpretation_to_dict(result)),
        )
        return result

    @staticmethod
    def _safe_parse_json(raw_text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw_text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                parsed = json.loads(raw_text[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    def _normalize_llm_payload(
        self, data: dict[str, Any], fsm_state: str, user_message: str
    ) -> ReplyInterpretation:
        raw_intent = str(data.get("dialog_intent") or "unclear").strip().lower()
        try:
            intent = DialogIntent(raw_intent)
        except ValueError:
            intent = DialogIntent.UNCLEAR

        target_ids = self._coerce_int_list(data.get("target_ids"))
        actions = self._normalize_actions_list(data.get("actions"))
        step_patches = self._normalize_step_patches(data.get("step_patches"))
        new_raw = data.get("new_intent_raw")
        new_cand = None
        if isinstance(new_raw, str) and new_raw.strip():
            new_cand = NewIntentCandidate(raw=new_raw.strip())

        if intent == DialogIntent.SELECT and fsm_state != DialogState.DISAMBIGUATION.value:
            intent = DialogIntent.UNCLEAR
            target_ids = []

        if intent == DialogIntent.SELECT and not target_ids:
            intent = DialogIntent.UNCLEAR

        if intent == DialogIntent.NEW_REQUEST and new_cand is None:
            um = (user_message or "").strip()
            if len(um) > 3:
                new_cand = NewIntentCandidate(raw=um)
            else:
                intent = DialogIntent.UNCLEAR

        if intent == DialogIntent.MODIFY and not step_patches and not actions:
            intent = DialogIntent.UNCLEAR

        return ReplyInterpretation(
            dialog_intent=intent,
            actions=actions,
            target_ids=target_ids,
            new_intent_candidate=new_cand,
            step_patches=step_patches,
        )

    @staticmethod
    def _coerce_int_list(raw: Any) -> list[int]:
        if not isinstance(raw, list):
            return []
        out: list[int] = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    def _normalize_actions_list(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            cid = item.get("context_id")
            typ = item.get("type")
            tid = item.get("target_id")
            data = item.get("data")
            if data is not None and not isinstance(data, dict):
                data = {}
            tid_int: int | None
            if tid is None or tid == "":
                tid_int = None
            else:
                try:
                    tid_int = int(tid)
                except (TypeError, ValueError):
                    tid_int = None
            out.append(
                {
                    "context_id": str(cid or f"patch_{len(out)}"),
                    "type": str(typ or "retrieve"),
                    "target_id": tid_int,
                    "data": dict(data or {}),
                }
            )
        return out

    @staticmethod
    def _normalize_step_patches(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        merge_keys = ("fields", "query", "datetime", "filters", "meta")
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index", -1))
            except (TypeError, ValueError):
                continue
            if idx < 0:
                continue
            merge = item.get("merge")
            if not isinstance(merge, dict):
                continue
            clean_merge: dict[str, Any] = {}
            for k in merge_keys:
                if k not in merge or merge[k] is None:
                    continue
                sub = merge[k]
                if isinstance(sub, dict) and sub:
                    clean_merge[k] = sub
            if not clean_merge:
                continue
            out.append({"index": idx, "merge": clean_merge})
        return out
