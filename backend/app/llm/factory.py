from app.core.config import Settings
from app.core.errors import AppError
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    return GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def require_llm_provider(settings: Settings) -> LLMProvider:
    if not settings.gemini_api_key:
        raise AppError(
            "Gemini is not configured. Add GEMINI_API_KEY in Settings or your .env file.",
            code="missing_api_key",
            status_code=400,
        )
    return get_llm_provider(settings)
