from __future__ import annotations

import logging
import time

from app.core.errors import AppError
from app.llm.base import ChatTurn, LLMProvider

logger = logging.getLogger("jistory.llm")


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        timeout_seconds: int = 60,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = None

    def _client_or_raise(self):
        if not self.api_key:
            raise AppError(
                "Gemini is not configured. Add GEMINI_API_KEY in Settings or your .env file.",
                code="missing_api_key",
                status_code=400,
            )
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise AppError(
                    "Gemini client library is not installed.",
                    code="missing_dependency",
                    status_code=500,
                ) from exc
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        history: list[ChatTurn],
    ) -> str:
        client = self._client_or_raise()
        contents = self._build_contents(history, prompt)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                try:
                    from google.genai import types

                    config = types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=0.2,
                        http_options=types.HttpOptions(timeout=self.timeout_seconds * 1000),
                    )
                    response = client.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=config,
                    )
                except Exception:
                    response = client.models.generate_content(
                        model=self.model_name,
                        contents=f"{system}\n\n{prompt}",
                    )
                text = getattr(response, "text", None)
                if not text:
                    raise AppError(
                        "Gemini returned an empty answer. Please try again.",
                        code="empty_completion",
                        status_code=502,
                    )
                return text.strip()
            except AppError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning("Gemini request failed (attempt %s)", attempt + 1)
                if attempt < self.max_retries:
                    time.sleep(0.6 * (attempt + 1))

        raise AppError(
            "Jistory could not reach Gemini. Check your API key and try again.",
            code="llm_unavailable",
            status_code=502,
        ) from last_error

    def _build_contents(self, history: list[ChatTurn], prompt: str) -> list[dict[str, str]]:
        contents: list[dict[str, str]] = []
        for turn in history:
            role = "user" if turn.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": turn.content}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return contents
