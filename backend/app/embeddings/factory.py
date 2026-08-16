from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.gemini import GeminiEmbeddingProvider
from app.embeddings.hash import HashEmbeddingProvider
from app.embeddings.local import LocalEmbeddingProvider


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    name = (settings.embedding_provider or "local").strip().lower()
    if name in {"hash", "test"}:
        return HashEmbeddingProvider()
    if name == "gemini":
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.embedding_model or "gemini-embedding-001",
        )
    return LocalEmbeddingProvider(model_name=settings.embedding_model)
