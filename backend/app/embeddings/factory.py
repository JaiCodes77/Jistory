from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.errors import EmbeddingUnavailableError
from app.embeddings.gemini import GeminiEmbeddingProvider
from app.embeddings.hash import HashEmbeddingProvider
from app.embeddings.local import LocalEmbeddingProvider
from app.embeddings.runtime import set_embedding_status

_provider: EmbeddingProvider | None = None
_cache_key: tuple[str, str] | None = None


def reset_embedding_provider() -> None:
    global _provider, _cache_key
    _provider = None
    _cache_key = None


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    global _provider, _cache_key
    name = (settings.embedding_provider or "local").strip().lower()
    model = settings.embedding_model or "BAAI/bge-small-en-v1.5"
    key = (name, model)
    if _provider is not None and _cache_key == key:
        return _provider

    if name in {"hash", "test"}:
        provider: EmbeddingProvider = HashEmbeddingProvider()
        set_embedding_status("hash", "Using test hash embeddings.")
    elif name == "gemini":
        if not settings.gemini_api_key:
            raise EmbeddingUnavailableError(
                "Gemini embeddings need GEMINI_API_KEY. Use the local provider instead."
            )
        provider = GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model_name=model if model.startswith("gemini") else "gemini-embedding-001",
        )
        set_embedding_status("ready", "Gemini embedding provider is configured.")
    elif name == "local":
        provider = LocalEmbeddingProvider(model_name=model)
    else:
        raise EmbeddingUnavailableError(
            "Unknown embedding provider. Use local in Settings, or hash in tests."
        )

    _provider = provider
    _cache_key = key
    return provider
