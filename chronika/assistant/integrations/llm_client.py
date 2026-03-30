import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Base exception for LLM client failures."""


class LLMConfigurationError(LLMClientError):
    """Raised when required client settings are missing."""


class MistralLLMClient:
    """
    Wrapper over Mistral Chat Completions API.

    Exposes only transport-level API calls.
    Business logic (intent parsing, prompt templates, JSON parsing policy)
    should live in service layer.
    """

    def __init__(self):
        self.api_key = getattr(settings, "MISTRAL_API_KEY", None)
        self.base_url = getattr(settings, "MISTRAL_API_BASE_URL", "https://api.mistral.ai")
        self.model = getattr(settings, "MISTRAL_MODEL", "mistral-small-latest")
        self.timeout = int(getattr(settings, "MISTRAL_TIMEOUT_SECONDS", 30))

        if not self.api_key:
            raise LLMConfigurationError(
                "MISTRAL_API_KEY is not configured. Set it in environment variables."
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMClientError(f"Mistral request failed: {exc}") from exc

        if not response.ok:
            body = response.text[:1000]
            raise LLMClientError(
                f"Mistral returned {response.status_code}: {body}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise LLMClientError("Mistral response is not valid JSON.") from exc

    @staticmethod
    def _extract_text_content(result: dict[str, Any]) -> str:
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError("Unexpected Mistral response shape.") from exc

        if isinstance(content, str):
            return content

        # Some providers may return rich content blocks; keep text parts.
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            return "".join(text_parts).strip()

        return str(content)

    def chat(
        self,
        user_text: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        result = self._chat_completions(payload)
        return self._extract_text_content(result)

    def chat_with_messages(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 512,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """
        Generic method for pre-built message lists.
        Caller is responsible for prompt construction and result parsing.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        result = self._chat_completions(payload)
        return self._extract_text_content(result)