import json
from dataclasses import asdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from assistant.services.intent_parser import IntentParserService


class Command(BaseCommand):
    help = (
        "Parse user text with IntentParserService (real Mistral API). "
        "Requires MISTRAL_API_KEY in the environment."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "text",
            nargs="*",
            help="User message (Russian or any language supported by the model).",
        )

    def handle(self, *args, **options):
        text = " ".join(options["text"]).strip()
        if not text:
            raise CommandError(
                'Pass a message, e.g.:\n  py manage.py try_assistant "Создай задачу купить молоко на завтра"'
            )

        if not getattr(settings, "MISTRAL_API_KEY", None):
            raise CommandError(
                "MISTRAL_API_KEY is not set. Add it to the environment or .env used by Django."
            )

        model = getattr(settings, "MISTRAL_MODEL", "mistral-small-latest")
        self.stdout.write(self.style.NOTICE(f"Model: {model}\n"))

        parser_svc = IntentParserService()
        result = parser_svc.parse(text)

        payload = asdict(result)
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        self.stdout.write("")
