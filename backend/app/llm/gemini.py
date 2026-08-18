from __future__ import annotations

import logging
import time

from app.core.errors import AppError
from app.llm.base import ChatTurn, LLMProvider

logger = logging.getLogger("jistory.llm")


def map_gemini_exception(exc: Exception) -> AppError:
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    combined = f"{name} {text}"
    if any(
        token in combined
        for token in (
            "api key not valid",
            "invalid api key",
            "api_key_invalid",
            "incorrect api key",
            "unauthenticated",
            "unauthorized",
            "permission_denied",
        )
    ):
        return AppError(
            "Gemini rejected the API key. Update it in Settings or your .env file.",
            code="invalid_api_key",
            status_code=400,
        )
    if any(token in combined for token in ("timeout", "timed out", "deadline exceeded")):
        return AppError(
            "Gemini timed out. Please try again.",
            code="llm_timeout",
            status_code=504,
        )
    if any(token in combined for token in ("resource_exhausted", "rate limit", "quota", "429")):
        return AppError(
            "Gemini is rate-limited right now. Please wait and try again.",
            code="llm_rate_limited",
            status_code=429,
        )
    return AppError(
        "Jistory could not reach Gemini. Check your API key and try again.",
        code="llm_unavailable",
        status_code=502,
    )


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
        last_error: AppError | None = None

        for attempt in range(self.max_retries + 1):
            try:
                text = self._generate_once(client, system, contents)
                if not text:
                    raise AppError(
                        "Gemini returned an empty answer. Please try again.",
                        code="empty_completion",
                        status_code=502,
                    )
                return text
            except AppError as exc:
                if exc.code in {"missing_api_key", "invalid_api_key", "missing_dependency"}:
                    raise
                last_error = exc
            except Exception as exc:
                last_error = map_gemini_exception(exc)
                if last_error.code in {"invalid_api_key", "missing_api_key"}:
                    raise last_error from exc
            logger.warning("Gemini request failed (attempt %s)", attempt + 1)
            if attempt < self.max_retries:
                time.sleep(0.6 * (attempt + 1))

        raise last_error or AppError(
            "Jistory could not reach Gemini. Check your API key and try again.",
            code="llm_unavailable",
            status_code=502,
        )

    def generate_stream(
        self,
        *,
        system: str,
        prompt: str,
        history: list[ChatTurn],
    ):
        client = self._client_or_raise()
        contents = self._build_contents(history, prompt)
        last_error: AppError | None = None
        yielded = False

        for attempt in range(self.max_retries + 1):
            try:
                for text in self._stream_once(client, system, contents):
                    if text:
                        yielded = True
                        yield text
                if not yielded:
                    raise AppError(
                        "Gemini returned an empty answer. Please try again.",
                        code="empty_completion",
                        status_code=502,
                    )
                return
            except AppError as exc:
                if yielded or exc.code in {"missing_api_key", "invalid_api_key", "missing_dependency"}:
                    raise
                last_error = exc
            except Exception as exc:
                last_error = map_gemini_exception(exc)
                if yielded or last_error.code in {"invalid_api_key", "missing_api_key"}:
                    raise last_error from exc
            logger.warning("Gemini stream failed (attempt %s)", attempt + 1)
            if attempt < self.max_retries:
                time.sleep(0.6 * (attempt + 1))

        raise last_error or AppError(
            "Jistory could not reach Gemini. Check your API key and try again.",
            code="llm_unavailable",
            status_code=502,
        )

    def _stream_once(self, client, system: str, contents: list[dict[str, str]]):
        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,
                http_options=types.HttpOptions(timeout=self.timeout_seconds * 1000),
            )
            stream = client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
        except AppError:
            raise
        except (ImportError, TypeError, AttributeError):
            stream = client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
            )
        for chunk in stream:
            text = getattr(chunk, "text", None)
            piece = (text or "").strip("\x00")
            if piece:
                yield piece

    def _generate_once(self, client, system: str, contents: list[dict[str, str]]) -> str:
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
        except AppError:
            raise
        except (ImportError, TypeError, AttributeError):
            response = client.models.generate_content(
                model=self.model_name,
                contents=contents,
            )
        text = getattr(response, "text", None)
        return (text or "").strip()

    def _build_contents(self, history: list[ChatTurn], prompt: str) -> list[dict[str, str]]:
        contents: list[dict[str, str]] = []
        for turn in history:
            role = "user" if turn.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": turn.content}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return contents
