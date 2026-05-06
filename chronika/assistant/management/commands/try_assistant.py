# manage.py try_assistant --email daryaami10@gmail.com

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from assistant.services.dialog_session_store import (
    clear_user_assistant_session,
    get_session_history_payload,
    run_assistant_turn_with_persisted_state,
    run_assistant_ui_action,
)


class Command(BaseCommand):
    help = "Interactive CLI for assistant message/action flow."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="User email to run assistant as.")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear assistant session before starting interactive mode.",
        )

    def handle(self, *args, **options):
        user = self._get_user_or_fail(options["email"])
        if options["clear"]:
            summary = clear_user_assistant_session(user)
            self.stdout.write(self.style.WARNING(f"Session cleared: {summary}"))

        self.stdout.write(self.style.SUCCESS(f"Assistant CLI started for {user.email}"))
        self.stdout.write("Type text to send message.")
        self.stdout.write("Commands: /help, /history, /clear, /action <json>, /exit")

        while True:
            try:
                raw = input("assistant> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write("\nBye.")
                break

            if not raw:
                continue
            if raw in {"/exit", "/quit"}:
                self.stdout.write("Bye.")
                break
            if raw == "/help":
                self._print_help()
                continue
            if raw == "/history":
                payload = get_session_history_payload(user)
                self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
                continue
            if raw == "/clear":
                payload = clear_user_assistant_session(user)
                self.stdout.write(self.style.WARNING(json.dumps(payload, ensure_ascii=False)))
                continue
            if raw.startswith("/action "):
                self._handle_action(user, raw[len("/action ") :].strip())
                continue

            self._handle_message(user, raw)

    def _get_user_or_fail(self, email: str):
        user_model = get_user_model()
        user = user_model.objects.filter(email=email).first()
        if not user:
            raise CommandError(f"User not found: {email}")
        return user

    def _handle_message(self, user, text: str) -> None:
        try:
            result, message_id, blocks = run_assistant_turn_with_persisted_state(user, text)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Message failed: {exc}"))
            return

        self._print_result(
            state=result.state,
            message_id=message_id,
            user_message=result.user_message,
            blocks=blocks,
            extra={"results": result.results, "pending_action": result.pending_action},
        )

    def _handle_action(self, user, action_json: str) -> None:
        try:
            action = json.loads(action_json)
        except json.JSONDecodeError as exc:
            self.stdout.write(self.style.ERROR(f"Invalid JSON: {exc}"))
            return
        if not isinstance(action, dict):
            self.stdout.write(self.style.ERROR("Action must be a JSON object."))
            return

        try:
            result, message_id, blocks = run_assistant_ui_action(user, {"action": action})
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Action failed: {exc}"))
            return

        self._print_result(
            state=result.state,
            message_id=message_id,
            user_message=result.user_message,
            blocks=blocks,
            extra={"results": result.results, "pending_action": result.pending_action},
        )

    def _print_result(
        self,
        *,
        state: str,
        message_id: str,
        user_message: str,
        blocks: list[dict[str, Any]],
        extra: dict[str, Any],
    ) -> None:
        payload = {
            "message_id": message_id,
            "state": state,
            "assistant_text": user_message,
            "blocks": blocks,
            **extra,
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    def _print_help(self) -> None:
        self.stdout.write("Usage examples:")
        self.stdout.write("  Привет, что у меня сегодня по задачам?")
        self.stdout.write('  /action {"type":"confirm_action","payload":{}}')
        self.stdout.write('  /action {"type":"modify_action","payload":{"changes":{"slot_index":0}}}')
        self.stdout.write("  /history")
        self.stdout.write("  /clear")
        self.stdout.write("  /exit")
